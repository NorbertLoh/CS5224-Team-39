"""Identity-specific configuration on the shared service settings."""

from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from telelink_common.settings import ServiceName, ServicePort, ServiceSettings


class Settings(ServiceSettings):
    notification_secret: SecretStr | None = None
    name: ServiceName = "identity"
    port: ServicePort = 8001
    cursor_secret: SecretStr | None = None
    scheduling_secret: SecretStr | None = None
    tenant_secret: SecretStr | None = None
    identity_secret: SecretStr | None = None
    records_secret: SecretStr | None = None
    consultation_secret: SecretStr | None = None
    tenant_url: str | None = None
    tenant_timeout_seconds: int = Field(default=3, ge=1, le=30)
    scheduling_actions: str = ""
    clinic_fixture_path: Path | None = None
    cors_origins: list[str] = []

    @field_validator("tenant_url")
    @classmethod
    def validate_tenant_url(cls, value, info):
        if value is None:
            return value
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or (url.scheme != "https" and info.data.get("environment") not in {"local", "test"})
        ):
            raise ValueError(
                "tenant_url requires HTTP(S), HTTPS outside local/test, no credentials"
            )
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_service_configuration(self):
        secrets = (
            self.cursor_secret,
            self.scheduling_secret,
            self.tenant_secret,
            self.identity_secret,
            self.records_secret,
            self.notification_secret,
            self.consultation_secret,
        )
        for secret in secrets:
            if secret is not None and len(secret.get_secret_value().encode()) < 32:
                raise ValueError("cursor and service secrets require at least 32 bytes")
        configured = [secret.get_secret_value() for secret in secrets if secret is not None]
        if len(configured) != len(set(configured)):
            raise ValueError("cursor and service secrets must be different")
        actions = {
            "appointment.read",
            "appointment.cancel",
            "clinical.read",
            "clinical.write",
            "medicine.ready",
        }
        if not set(self.scheduling_actions.split()).issubset(actions):
            raise ValueError("scheduling_actions contains an unsupported action")
        if self.scheduling_actions and self.scheduling_secret is None:
            raise ValueError("scheduling_secret is required for enabled service actions")
        if self.clinic_fixture_path is not None and self.environment not in {"local", "test"}:
            raise ValueError("clinic fixtures are only allowed in local/test environments")
        if self.tenant_url is not None:
            if self.identity_secret is None:
                raise ValueError("identity_secret is required for live clinic validation")
            if self.clinic_fixture_path is not None:
                raise ValueError("choose live clinic validation or fixtures, not both")
        for origin in self.cors_origins:
            url = urlsplit(origin)
            if (
                url.scheme not in {"http", "https"}
                or not url.netloc
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path
                or (url.scheme != "https" and self.environment not in {"local", "test"})
            ):
                raise ValueError("CORS origins must be explicit origins, HTTPS outside local/test")
        return self
