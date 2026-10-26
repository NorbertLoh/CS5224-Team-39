from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from telelink_common.settings import ServiceName, ServicePort, ServiceSettings


class Settings(ServiceSettings):
    name: ServiceName = "consultation"
    port: ServicePort = 8004
    scheduling_url: str | None = None
    billing_url: str | None = None
    records_url: str | None = None
    records_secret: SecretStr | None = None
    scheduling_secret: SecretStr | None = None
    billing_secret: SecretStr | None = None
    identity_secret: SecretStr | None = None
    signalling_secret: SecretStr | None = None
    upstream_timeout_seconds: float = Field(default=3, ge=0.1, le=30)
    admission_ttl_seconds: int = Field(default=60, ge=1, le=300)
    turn_urls: list[str] = Field(default_factory=list)
    turn_secret: SecretStr | None = None
    relay_only: bool = False
    test_join_early_minutes: int = Field(default=10, ge=10, le=180)

    @model_validator(mode="after")
    def validate_admission(self):
        if self.test_join_early_minutes != 10 and self.environment not in {"local", "test"}:
            raise ValueError("Extended test join window requires local/test environment")
        if any(
            not url.startswith(("turn:", "turns:")) or any(c.isspace() for c in url)
            for url in self.turn_urls
        ):
            raise ValueError("TURN URLs must use turn: or turns:")
        if bool(self.turn_urls) != bool(self.turn_secret) or (
            self.relay_only and not self.turn_urls
        ):
            raise ValueError(
                "TURN URLs and secret must be configured together; relay requires TURN"
            )
        if self.turn_secret and len(self.turn_secret.get_secret_value().encode()) < 32:
            raise ValueError("TURN secret must contain at least 32 bytes")
        for field in ("scheduling_url", "billing_url", "records_url"):
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
            s.get_secret_value()
            for s in (
                self.scheduling_secret,
                self.billing_secret,
                self.identity_secret,
                self.signalling_secret,
                self.turn_secret,
                self.records_secret,
            )
            if s is not None
        ]
        if any(len(s.encode()) < 32 for s in secrets) or len(secrets) != len(set(secrets)):
            raise ValueError("Service secrets must differ and contain at least 32 bytes")
        return self
