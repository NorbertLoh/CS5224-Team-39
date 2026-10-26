"""Send one synthetic local email and verify its Floci capture. No event worker."""

import json
from urllib.request import urlopen

from app.integrations.email import SESEmailSender
from app.services.templates import render_email
from app.settings import Settings


def main():
    settings = Settings()
    if settings.environment not in {"local", "test"} or settings.aws_endpoint_url not in {
        "http://localhost:4566",
        "http://127.0.0.1:4566",
    }:
        raise ValueError("This check only supports host-local Floci on port 4566")
    if settings.email_sender != "notifications@telelink.test":
        raise ValueError("This check requires the synthetic notifications@telelink.test sender")
    recipient = "n01-patient@telelink.test"
    sender = SESEmailSender(settings)
    # Explicit local-only identity setup; production verification is an operator action.
    sender.client.verify_email_identity(EmailAddress=settings.email_sender)
    sender.client.verify_email_identity(EmailAddress=recipient)
    message = render_email("booking_confirmed", settings.app_url)
    message_id = sender.send(recipient, message)
    with urlopen(settings.aws_endpoint_url + "/_aws/ses", timeout=10) as response:
        messages = json.load(response)["messages"]
    captured = next((item for item in messages if item.get("Id") == message_id), None)
    if (
        captured is None
        or captured.get("Subject") != message.subject
        or captured.get("Source") != settings.email_sender
        or captured.get("Destination", {}).get("ToAddresses") != [recipient]
        or captured.get("Body", {}).get("text_part") != message.text
        or captured.get("Body", {}).get("html_part") != message.html
    ):
        raise RuntimeError("Expected SES message was not captured")
    print("N01: SES acceptance, recipient and both bodies verified in Floci capture.")


if __name__ == "__main__":
    main()
