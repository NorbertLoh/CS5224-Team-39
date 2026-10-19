from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from telelink_common.settings import ServiceName, ServicePort, ServiceSettings


class Settings(ServiceSettings):
    notification_secret: SecretStr | None = None
    name: ServiceName = "scheduling"
    port: ServicePort = 8003
    tenant_url: str | None = None
    scheduling_secret: SecretStr | None = None
    consultation_secret: SecretStr | None = None
    operator_secret: SecretStr | None = None
    billing_secret: SecretStr | None = None
    billing_url: str | None = None
    payment_queue_name: str = Field(default="telelink-local-scheduling", pattern=r"^[\w-]{1,80}$")
    cursor_secret: SecretStr | None = None
    cors_origins: list[str] = []
    redis_url: SecretStr | None = None
    redis_timeout_seconds: float = Field(default=0.3, ge=0.05, le=5)

    @model_validator(mode="after")
    def validate_configuration(self):
        if self.billing_url is not None:
            url = urlsplit(self.billing_url)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or (url.scheme != "https" and self.environment not in {"local", "test"})
            ):
                raise ValueError("billing_url requires HTTPS outside local/test and no credentials")
            self.billing_url = self.billing_url.rstrip("/")
        if self.redis_url is not None:
            url = urlsplit(self.redis_url.get_secret_value())
            if (
                url.scheme not in {"redis", "rediss"}
                or not url.hostname
                or url.query
                or url.fragment
                or (url.path and (not url.path.startswith("/") or not url.path[1:].isdigit()))
                or (url.scheme != "rediss" and self.environment not in {"local", "test"})
            ):
                raise ValueError(
                    "redis_url requires rediss outside local/test and a database number"
                )
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
            for secret in (
                self.scheduling_secret,
                self.cursor_secret,
                self.consultation_secret,
                self.operator_secret,
                self.billing_secret,
                self.notification_secret,
            )
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
