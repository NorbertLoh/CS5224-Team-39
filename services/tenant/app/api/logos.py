"""One managed S3 logo per clinic; no client-supplied object keys."""

from io import BytesIO
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Request, Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from telelink_common.errors import DomainError, ErrorEnvelope

from app.api.dependencies import DB
from app.api.dependencies import ClinicAdmin as Admin
from app.models import Clinic
from app.schemas import ClinicAdmin, profile

MAX_LOGO_BYTES = 2 * 1024 * 1024
router = APIRouter(
    tags=["clinic logos"],
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 413, 422, 503)},
)


def logo_png(data):
    try:
        with Image.open(BytesIO(data)) as image:
            if (
                image.format not in {"PNG", "JPEG", "WEBP"}
                or image.width * image.height > 4_000_000
            ):
                raise ValueError("Unsupported image")
            image.load()
            image.thumbnail((512, 512))
            output = BytesIO()
            image.convert("RGBA").save(output, format="PNG")
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise DomainError(
            422, "invalid_logo", "Use a valid PNG, JPEG or WebP image up to 4 megapixels."
        ) from None


class LogoStorage:
    def __init__(self, settings):
        self.settings = settings
        self.client = None
        if settings.logo_bucket:
            options = {}
            if settings.logo_s3_endpoint:
                options = {"aws_access_key_id": "test", "aws_secret_access_key": "test"}
            self.client = boto3.client(
                "s3",
                region_name=settings.logo_region,
                endpoint_url=settings.logo_s3_endpoint,
                config=Config(
                    connect_timeout=3,
                    read_timeout=3,
                    retries={"max_attempts": 1},
                    s3={"addressing_style": "path"},
                ),
                **options,
            )

    def close(self):
        if self.client is not None:
            self.client.close()

    def key(self, tenant_id):
        return f"clinic-logos/{tenant_id}/logo.png"

    def url(self, tenant_id):
        if self.client is None:
            raise DomainError(503, "unavailable", "Logo storage is not configured.")
        return f"{self.settings.logo_public_base_url}/{self.key(tenant_id)}"

    def change(self, tenant_id, data=None):
        self.url(tenant_id)
        try:
            # Versioned buckets retain old files even after replacement/deletion.
            if self.client.get_bucket_versioning(Bucket=self.settings.logo_bucket).get("Status"):
                raise DomainError(503, "unavailable", "Use an unversioned bucket for clinic logos.")
            if data is None:
                self.client.delete_object(Bucket=self.settings.logo_bucket, Key=self.key(tenant_id))
            else:
                self.client.put_object(
                    Bucket=self.settings.logo_bucket,
                    Key=self.key(tenant_id),
                    Body=data,
                    ContentType="image/png",
                    CacheControl="no-cache",
                )
        except (BotoCoreError, ClientError):
            raise DomainError(
                503, "unavailable", "Logo storage is unavailable; retry the change."
            ) from None

    def read(self, tenant_id):
        self.url(tenant_id)
        try:
            response = self.client.get_object(
                Bucket=self.settings.logo_bucket, Key=self.key(tenant_id)
            )
            with response["Body"] as body:
                return body.read()
        except (BotoCoreError, ClientError):
            raise DomainError(503, "unavailable", "Logo storage is unavailable.") from None


def locked_clinic(session, tenant_id):
    clinic = session.scalar(select(Clinic).where(Clinic.tenant_id == tenant_id).with_for_update())
    if clinic is None:
        raise DomainError(404, "not_found", "Resource not found.")
    return clinic


def replace_logo(session, storage, tenant_id, data):
    clinic = locked_clinic(session, tenant_id)
    storage.change(tenant_id, logo_png(data))
    clinic.logo_url = storage.url(tenant_id)
    session.commit()
    return profile(clinic, admin=True)


@router.put("/clinics/{tenant_id}/logo", response_model=ClinicAdmin)
async def upload_logo(tenant_id: UUID, request: Request, identity: Admin, session: DB):
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_LOGO_BYTES:
            raise DomainError(413, "logo_too_large", "Choose an image up to 2 MB.")
        data.extend(chunk)
    return await run_in_threadpool(
        replace_logo, session, request.app.state.logo_storage, tenant_id, bytes(data)
    )


@router.delete("/clinics/{tenant_id}/logo", response_model=ClinicAdmin)
def remove_logo(tenant_id: UUID, request: Request, identity: Admin, session: DB):
    clinic = locked_clinic(session, tenant_id)
    request.app.state.logo_storage.change(tenant_id)
    clinic.logo_url = None
    session.commit()
    return profile(clinic, admin=True)


@router.get("/clinics/{tenant_id}/logo")
def preview_logo(tenant_id: UUID, request: Request, identity: Admin, session: DB):
    clinic = session.get(Clinic, tenant_id)
    if clinic is None or clinic.logo_url is None:
        raise DomainError(404, "not_found", "Resource not found.")
    data = request.app.state.logo_storage.read(tenant_id)
    return Response(data, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/clinics/{tenant_id}/public-logo")
def public_logo(tenant_id: UUID, request: Request, session: DB):
    clinic = session.get(Clinic, tenant_id)
    if (
        clinic is None
        or clinic.status != "active"
        or not clinic.membership_provisioned
        or clinic.logo_url is None
    ):
        raise DomainError(404, "not_found", "Resource not found.")
    data = request.app.state.logo_storage.read(tenant_id)
    return Response(data, media_type="image/png", headers={"Cache-Control": "no-cache"})
