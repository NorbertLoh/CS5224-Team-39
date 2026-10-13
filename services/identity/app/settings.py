"""Identity-specific configuration on the shared service settings."""

from pathlib import Path
from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from telelink_common.settings import ServiceName, ServicePort, ServiceSettings


class Settings(ServiceSettings):
    name: ServiceName = "identity"
    port: ServicePort = 8001
    cursor_secret: SecretStr | None = None
    scheduling_secret: SecretStr | None = None
    tenant_secret: SecretStr | None = None
    scheduling_actions: str = ""
    clinic_fixture_path: Path | None = None
    cors_origins: list[str] = []

    @model_validator(mode="after")
    def validate_service_configuration(self):
        secrets = (self.cursor_secret, self.scheduling_secret, self.tenant_secret)
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
