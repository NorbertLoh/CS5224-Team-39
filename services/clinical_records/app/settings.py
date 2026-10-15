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

    @model_validator(mode="after")
    def validate_records_configuration(self):
        for field in ("scheduling_url", "fulfilment_url"):
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
        if self.cursor_secret and len(self.cursor_secret.get_secret_value().encode()) < 32:
            raise ValueError("Cursor secret requires at least 32 bytes")
        return self
