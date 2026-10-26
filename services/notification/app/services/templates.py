"""Version-one privacy-conscious email copy. Details require signing into the app."""

from dataclasses import dataclass
from html import escape
from typing import Literal
from urllib.parse import urlsplit

TemplateName = Literal["booking_confirmed", "document_ready", "delivery_updated"]
COPY = {
    "booking_confirmed": ("Your booking is confirmed", "Your appointment booking is confirmed."),
    "document_ready": ("Your document is ready", "A document is ready in your account."),
    "delivery_updated": (
        "Your delivery has an update",
        "Your medicine delivery status has changed.",
    ),
}


@dataclass(frozen=True)
class EmailMessage:
    subject: str
    text: str
    html: str


def validate_app_url(value: str) -> str:
    url = urlsplit(value)
    if (
        not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or (
            url.scheme != "https"
            and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"})
        )
        or any(ord(c) < 33 for c in value)
    ):
        raise ValueError(
            "App URL requires HTTPS (HTTP localhost permitted), without credentials/query/fragment"
        )
    return value.rstrip("/")


def render_email(template: TemplateName, app_url: str) -> EmailMessage:
    if template not in COPY:
        raise ValueError("Unknown notification template")
    link = validate_app_url(app_url) + "/patient"
    subject, body = COPY[template]
    return EmailMessage(
        subject,
        f"{body}\n\nSign in to TeleLink Health: {link}\n",
        f'<p>{escape(body)}</p><p><a href="{escape(link, quote=True)}">'
        "Sign in to TeleLink Health</a></p>",
    )
