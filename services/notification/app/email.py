"""SES acceptance is not a delivery receipt. No raw provider errors are exposed."""

from typing import Protocol

from botocore.exceptions import BotoCoreError, ClientError
from telelink_common.aws import create_client

from app.settings import Settings, validate_email
from app.templates import EmailMessage


class EmailSendError(RuntimeError):
    pass


class EmailSender(Protocol):
    def send(self, recipient: str, message: EmailMessage) -> str: ...


class SESEmailSender:
    def __init__(self, settings: Settings, *, client=None):
        self.source = settings.email_sender
        self.client = client if client is not None else create_client("ses", settings)

    def send(self, recipient: str, message: EmailMessage) -> str:
        validate_email(recipient)
        if not message.subject.strip() or any(c in message.subject for c in "\r\n"):
            raise ValueError("Invalid email subject")
        try:
            result = self.client.send_email(
                Source=self.source,
                Destination={"ToAddresses": [recipient]},
                Message={
                    "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": message.text, "Charset": "UTF-8"},
                        "Html": {"Data": message.html, "Charset": "UTF-8"},
                    },
                },
            )
        except (BotoCoreError, ClientError):
            raise EmailSendError("SES did not confirm message acceptance") from None
        message_id = result.get("MessageId")
        if not isinstance(message_id, str) or not message_id.strip():
            raise EmailSendError("SES did not confirm message acceptance")
        return message_id
