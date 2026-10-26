"""Sign using the browser endpoint itself: rewriting a signed host breaks SigV4."""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from telelink_common.aws import client_options
from telelink_common.errors import DomainError

from app.integrations.storage import PrivatePDFStore
from app.schemas import DownloadPublic


def create_signer(settings):
    options = client_options(settings)
    if settings.s3_browser_endpoint_url:
        options["endpoint_url"] = settings.s3_browser_endpoint_url
    if options.get("endpoint_url") and urlsplit(options["endpoint_url"]).hostname == "floci":
        raise ValueError("Set SERVICE_S3_BROWSER_ENDPOINT_URL for container-based Floci")
    return boto3.client(
        "s3",
        **options,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=3,
            read_timeout=10,
            retries={"mode": "standard", "max_attempts": 3},
        ),
    )


class Downloads:
    def __init__(self, settings, storage, signer):
        self.settings, self.storage, self.signer = settings, storage, signer

    def prepare(self, row):
        if row.status != "ready":
            raise DomainError(409, "document_not_ready", "Document is not ready.")
        if row.storage_bucket != self.settings.document_bucket:
            raise DomainError(503, "unavailable", "Document storage is unavailable.")
        try:
            PrivatePDFStore(self.storage, self.settings.document_bucket).verify_private()
            head = self.storage.head_object(Bucket=row.storage_bucket, Key=row.storage_key)
            metadata = head.get("Metadata", {})
            expected = {
                "document-id": str(row.document_id),
                "tenant-id": str(row.tenant_id),
                "appointment-id": str(row.appointment_id),
                "patient-id": str(row.patient_id),
                "sha256": row.sha256,
            }
            if row.doctor_id is not None:
                expected["doctor-id"] = str(row.doctor_id)
            if (
                head.get("ContentLength") != row.size_bytes
                or head.get("ContentType") != "application/pdf"
                or any(metadata.get(k) != v for k, v in expected.items())
            ):
                raise RuntimeError("Document integrity check failed")
        except (BotoCoreError, ClientError, RuntimeError):
            raise DomainError(503, "unavailable", "Document storage is unavailable.") from None

    def sign(self, row):
        ttl = self.settings.download_ttl_seconds
        # Calculated before signing so the advertised lifetime never exceeds the URL lifetime.
        expires_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=ttl)
        try:
            url = self.signer.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": row.storage_bucket,
                    "Key": row.storage_key,
                    "ResponseContentType": "application/pdf",
                    "ResponseContentDisposition": f'attachment; filename="{row.document_id}.pdf"',
                    "ResponseCacheControl": "no-store",
                },
                ExpiresIn=ttl,
                HttpMethod="GET",
            )
        except (BotoCoreError, ClientError):
            raise DomainError(503, "unavailable", "Document storage is unavailable.") from None
        return DownloadPublic(download_url=url, expires_at=expires_at)
