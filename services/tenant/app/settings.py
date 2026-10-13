from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from telelink_common.settings import ServiceName, ServicePort, ServiceSettings


class Settings(ServiceSettings):
    name: ServiceName = "tenant"
    port: ServicePort = 8002
    cursor_secret: SecretStr | None = None
    tenant_secret: SecretStr | None = None
    scheduling_secret: SecretStr | None = None
    cors_origins: list[str] = []

    @model_validator(mode="after")
    def validate_configuration(self):
        secrets = [
            value.get_secret_value()
            for value in (self.cursor_secret, self.tenant_secret, self.scheduling_secret)
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
