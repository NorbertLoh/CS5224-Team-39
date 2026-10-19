import re

from pydantic import field_validator
from telelink_common.settings import ServiceName, ServiceSettings

from app.templates import validate_app_url


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
