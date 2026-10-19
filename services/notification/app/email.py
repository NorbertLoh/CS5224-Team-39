"""SES acceptance is not a delivery receipt. No raw provider errors are exposed."""

from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from telelink_common.aws import client_options

from app.settings import Settings, validate_email
from app.templates import EmailMessage


class EmailSendError(RuntimeError):
    def __init__(
        self, message="SES did not confirm message acceptance", *, definitive=False, retryable=False
    ):
        super().__init__(message)
        self.definitive = definitive
        self.retryable = retryable


class EmailSender(Protocol):
    def send(self, recipient: str, message: EmailMessage) -> str: ...


class SESEmailSender:
    def __init__(self, settings: Settings, *, client=None):
        self.source = settings.email_sender
        # SES SendEmail has no idempotency token: disable hidden SDK retries.
        self.client = (
            client
            if client is not None
            else boto3.client(
                "ses",
                **client_options(settings),
                config=Config(
                    connect_timeout=3, read_timeout=10, retries={"total_max_attempts": 1}
                ),
            )
        )

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
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            retryable = code in {"Throttling", "ThrottlingException", "TooManyRequestsException"}
            definitive = retryable or code in {
                "MessageRejected",
                "AccessDenied",
                "AccessDeniedException",
                "MailFromDomainNotVerifiedException",
                "AccountSendingPausedException",
                "ConfigurationSetDoesNotExistException",
            }
            raise EmailSendError(definitive=definitive, retryable=retryable) from None
        except BotoCoreError:
            raise EmailSendError() from None
        message_id = result.get("MessageId")
        if not isinstance(message_id, str) or not message_id.strip():
            raise EmailSendError("SES did not confirm message acceptance")
        return message_id
