import re
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from telelink_common.settings import ServiceName, ServiceSettings

from app.services.templates import validate_app_url


def validate_email(value: str) -> str:
    # One bare ASCII mailbox. Display names, lists and header controls are rejected.
    if len(value) > 254 or not re.fullmatch(
        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}",
        value,
    ):
        raise ValueError("Expected one bare email address")
    return value


class Settings(ServiceSettings):
    name: ServiceName = "notification"
    queue_name: str = Field(default="telelink-local-notification", pattern=r"^[\w-]{1,80}$")
    scheduling_url: str | None = None
    document_url: str | None = None
    fulfilment_url: str | None = None
    identity_secret: SecretStr | None = None
    scheduling_secret: SecretStr | None = None
    document_secret: SecretStr | None = None
    fulfilment_secret: SecretStr | None = None
    lookup_timeout_seconds: int = Field(default=3, ge=1, le=10)
    send_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_seconds: int = Field(default=60, ge=1, le=3600)
    stale_seconds: int = Field(default=300, ge=60, le=3600)
    email_sender: str
    app_url: str

    @field_validator("email_sender")
    @classmethod
    def sender_valid(cls, value):
        return validate_email(value)

    @field_validator("app_url")
    @classmethod
    def app_url_valid(cls, value):
        return validate_app_url(value)

    @field_validator("app_url")
    @classmethod
    def deployed_url(cls, value, info):
        if info.data.get("environment") not in {"local", "test"} and not value.startswith(
            "https://"
        ):
            raise ValueError("Deployed app URL requires HTTPS")
        return value

    @model_validator(mode="after")
    def worker_configuration(self):
        keys = [
            getattr(self, name + "_secret")
            for name in ("identity", "scheduling", "document", "fulfilment")
        ]
        values = [key.get_secret_value() for key in keys if key is not None]
        if any(len(value.encode()) < 32 for value in values) or len(values) != len(set(values)):
            raise ValueError("Upstream service keys require distinct 32+ byte values")
        for name in ("scheduling_url", "document_url", "fulfilment_url"):
            value = getattr(self, name)
            if value is None:
                continue
            url = urlsplit(value)
            if (
                not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.scheme not in {"http", "https"}
                or (self.environment not in {"local", "test"} and url.scheme != "https")
            ):
                raise ValueError(
                    "Upstream URL requires HTTPS outside local/test and no credentials"
                )
            setattr(self, name, value.rstrip("/"))
        return self
