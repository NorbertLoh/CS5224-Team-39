"""One managed S3 logo per clinic; no client-supplied object keys."""

from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from telelink_common.errors import DomainError, ErrorEnvelope

from app.api.dependencies import DB
from app.api.dependencies import ClinicAdmin as Admin
from app.integrations.logos import MAX_LOGO_BYTES, logo_png
from app.models import Clinic
from app.schemas import ClinicAdmin, profile

router = APIRouter(
    tags=["clinic logos"],
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 413, 422, 503)},
)


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
