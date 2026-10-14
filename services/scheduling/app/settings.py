from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from telelink_common.settings import ServiceName, ServicePort, ServiceSettings


class Settings(ServiceSettings):
    name: ServiceName = "scheduling"
    port: ServicePort = 8003
    tenant_url: str | None = None
    scheduling_secret: SecretStr | None = None
    cursor_secret: SecretStr | None = None
    cors_origins: list[str] = []

    @model_validator(mode="after")
    def validate_configuration(self):
        if self.tenant_url is not None:
            url = urlsplit(self.tenant_url)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or (url.scheme != "https" and self.environment not in {"local", "test"})
            ):
                raise ValueError("tenant_url requires HTTPS outside local/test and no credentials")
            self.tenant_url = self.tenant_url.rstrip("/")
        secrets = [
            secret.get_secret_value()
            for secret in (self.scheduling_secret, self.cursor_secret)
            if secret is not None
        ]
        if any(len(secret.encode()) < 32 for secret in secrets):
            raise ValueError("Service and cursor secrets require at least 32 bytes")
        if len(secrets) != len(set(secrets)):
            raise ValueError("Service and cursor secrets must differ")
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
