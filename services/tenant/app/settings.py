from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from telelink_common.settings import ServiceName, ServicePort, ServiceSettings


class Settings(ServiceSettings):
    name: ServiceName = "tenant"
    port: ServicePort = 8002
    cursor_secret: SecretStr | None = None
    tenant_secret: SecretStr | None = None
    scheduling_secret: SecretStr | None = None
    identity_secret: SecretStr | None = None
    records_secret: SecretStr | None = None
    billing_secret: SecretStr | None = None
    fulfilment_secret: SecretStr | None = None
    cors_origins: list[str] = []
    logo_bucket: str | None = None
    logo_public_base_url: str | None = None
    logo_s3_endpoint: str | None = None
    logo_region: str = "ap-southeast-1"

    @model_validator(mode="after")
    def validate_configuration(self):
        if bool(self.logo_bucket) != bool(self.logo_public_base_url):
            raise ValueError("logo_bucket and logo_public_base_url are required together")
        if self.logo_public_base_url is not None:
            url = urlsplit(self.logo_public_base_url)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or len(self.logo_public_base_url) > 1500
                or any(char.isspace() for char in self.logo_public_base_url)
            ):
                raise ValueError("logo_public_base_url requires a plain HTTPS asset URL")
            self.logo_public_base_url = self.logo_public_base_url.rstrip("/")
        if self.logo_s3_endpoint is not None:
            url = urlsplit(self.logo_s3_endpoint)
            if (
                self.environment not in {"local", "test"}
                or url.scheme not in {"http", "https"}
                or url.hostname not in {"localhost", "127.0.0.1", "floci"}
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path not in {"", "/"}
            ):
                raise ValueError("logo_s3_endpoint is only for the local emulator")
        secrets = [
            value.get_secret_value()
            for value in (
                self.cursor_secret,
                self.tenant_secret,
                self.scheduling_secret,
                self.identity_secret,
                self.records_secret,
                self.billing_secret,
                self.fulfilment_secret,
            )
            if value is not None
        ]
        if any(len(value.encode()) < 32 for value in secrets):
            raise ValueError("Cursor and service secrets require at least 32 bytes")
        if len(secrets) != len(set(secrets)):
            raise ValueError("Cursor and service secrets must be different")
        for origin in self.cors_origins:
            url = urlsplit(origin)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.path
                or url.query
                or url.fragment
                or (url.scheme != "https" and self.environment not in {"local", "test"})
            ):
                raise ValueError("CORS requires explicit origins, HTTPS outside local/test")
        return self
