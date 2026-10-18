from urllib.parse import urlsplit
from uuid import UUID

from pydantic import SecretStr, model_validator
from telelink_common.settings import ServiceName, ServicePort, ServiceSettings


class Settings(ServiceSettings):
    name: ServiceName = "billing"
    port: ServicePort = 8009
    cursor_secret: SecretStr | None = None
    scheduling_url: str | None = None
    scheduling_secret: SecretStr | None = None
    tenant_url: str | None = None
    tenant_secret: SecretStr | None = None
    stripe_secret_key: SecretStr | None = None
    stripe_webhook_secret: SecretStr | None = None
    stripe_destinations: dict[UUID, str] = {}
    checkout_success_url: str = "http://localhost:5173/payments/return"
    checkout_cancel_url: str = "http://localhost:5173/appointments"
    cors_origins: list[str] = []

    @model_validator(mode="after")
    def validate_checkout(self):
        import re

        if self.cursor_secret and len(self.cursor_secret.get_secret_value().encode()) < 32:
            raise ValueError("cursor_secret requires at least 32 bytes")

        for field in (
            "scheduling_url",
            "tenant_url",
            "checkout_success_url",
            "checkout_cancel_url",
        ):
            value = getattr(self, field)
            if value is None:
                continue
            url = urlsplit(value)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.fragment
                or url.query
                or (url.scheme != "https" and self.environment not in {"local", "test"})
            ):
                raise ValueError(f"{field} requires a plain URL, HTTPS outside local/test")
            setattr(self, field, value.rstrip("/"))
        for origin in self.cors_origins:
            url = urlsplit(origin)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.path
                or url.query
                or url.fragment
                or url.username
                or url.password
                or (url.scheme != "https" and self.environment not in {"local", "test"})
            ):
                raise ValueError("CORS requires explicit origins, HTTPS outside local/test")
        secrets = [s.get_secret_value() for s in (self.scheduling_secret, self.tenant_secret) if s]
        if any(len(s.encode()) < 32 for s in secrets) or len(secrets) != len(set(secrets)):
            raise ValueError("Service secrets must differ and contain at least 32 bytes")
        if self.stripe_secret_key and not re.fullmatch(
            r"sk_test_[A-Za-z0-9]+", self.stripe_secret_key.get_secret_value()
        ):
            raise ValueError("Only Stripe test secret keys are supported")
        if self.stripe_webhook_secret and not re.fullmatch(
            r"whsec_[A-Za-z0-9_]+", self.stripe_webhook_secret.get_secret_value()
        ):
            raise ValueError("Stripe webhook signing secret must start with whsec_")
        if any(
            not re.fullmatch(r"acct_[A-Za-z0-9]+", a) for a in self.stripe_destinations.values()
        ):
            raise ValueError("Stripe destinations require connected account IDs")
        return self
