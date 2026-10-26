from io import BytesIO

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image, UnidentifiedImageError
from telelink_common.errors import DomainError

MAX_LOGO_BYTES = 2 * 1024 * 1024


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
