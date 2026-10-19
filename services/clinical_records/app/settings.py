from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from telelink_common.settings import ServiceName, ServicePort, ServiceSettings


class Settings(ServiceSettings):
    name: ServiceName = "clinical_records"
    port: ServicePort = 8005
    scheduling_url: str | None = None
    fulfilment_url: str | None = None
    upstream_timeout_seconds: float = Field(default=3, ge=0.1, le=30)
    cursor_secret: SecretStr | None = None
    document_secret: SecretStr | None = None
    fulfilment_secret: SecretStr | None = None
    consultation_secret: SecretStr | None = None
    identity_document_secret: SecretStr | None = None
    tenant_document_secret: SecretStr | None = None
    tenant_url: str | None = None

    @model_validator(mode="after")
    def validate_records_configuration(self):
        for field in ("scheduling_url", "fulfilment_url", "tenant_url"):
            value = getattr(self, field)
            if value is None:
                continue
            url = urlsplit(value)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or (url.scheme != "https" and self.environment not in {"local", "test"})
            ):
                raise ValueError(
                    "Upstream URLs require HTTPS outside local/test and no credentials"
                )
            setattr(self, field, value.rstrip("/"))
        secrets = [
            secret.get_secret_value()
            for secret in (
                self.cursor_secret,
                self.document_secret,
                self.fulfilment_secret,
                self.consultation_secret,
                self.identity_document_secret,
                self.tenant_document_secret,
            )
            if secret is not None
        ]
        if any(len(secret.encode()) < 32 for secret in secrets):
            raise ValueError("Cursor and service secrets require at least 32 bytes")
        if len(secrets) != len(set(secrets)):
            raise ValueError("Cursor and service secrets must differ")
        return self
