from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from types import SimpleNamespace
from uuid import uuid4

import pytest
from telelink_common.events import new_event
from test_worker import Sender, config, database, queue, rows, work  # noqa: F401, F811

from app.integrations.email import SESEmailSender
from app.integrations.recipients import NotificationDeferred, Recipient, ResourceContext
from app.services.dispatch import dispatch_one
from app.services.lifecycle_email import prepare_email


def receipt_event():
    return new_event(
        "document_ready.v1",
        tenant_id=uuid4(),
        correlation_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        data={"document_id": uuid4(), "appointment_id": uuid4(), "payment_id": uuid4()},
    )


class Directory:
    def __init__(self, event, purpose="consultation"):
        self.current = Recipient(
            uuid4(),
            "current@example.test",
            ResourceContext(
                resource_id=event.data.document_id,
                tenant_id=event.tenant_id,
                patient_id=uuid4(),
                eligible=True,
                kind="receipt_pdf",
                payment_id=event.data.payment_id,
                clinic_name="Clinic <West>",
                amount_minor=3500,
                currency="SGD",
                purpose=purpose,
                paid_at="2026-11-05T01:00:00Z",
            ),
        )

    def resolve(self, event):
        return self.current

    def receipt(self, event, patient_id):
        assert patient_id == self.current.subject_id
        return b"%PDF-synthetic receipt"


@pytest.mark.parametrize(
    "purpose,label",
    [("consultation", "Consultation"), ("medication_delivery", "Medicines and delivery")],
)
def test_verified_receipt_mime_attachment_and_copy(purpose, label):
    event = receipt_event()
    directory = Directory(event, purpose)
    message = prepare_email(event, directory.current, directory, "https://app.example.test")
    assert label in message.subject and "paid to Clinic <West>" in message.text
    assert "SGD 35.00" in message.text and "09:00 AM SGT" in message.text
    assert "Clinic &lt;West&gt;" in message.html

    class SES:
        def send_raw_email(self, **request):
            assert request["Destinations"] == ["current@example.test"]
            mime = BytesParser(policy=policy.default).parsebytes(request["RawMessage"]["Data"])
            assert mime["To"] == "current@example.test" and mime["Bcc"] is None
            (attachment,) = mime.iter_attachments()
            assert attachment.get_content_type() == "application/pdf"
            assert attachment.get_payload(decode=True) == b"%PDF-synthetic receipt"
            assert attachment.get_filename() == f"receipt-{event.data.payment_id}.pdf"
            return {"MessageId": "accepted-synthetic"}

    assert SESEmailSender(config(), client=SES()).send("current@example.test", message)


@pytest.mark.parametrize("source", ["prescription_id", "medical_certificate_id"])
def test_clinical_notice_has_no_attachment_or_bearer_url(source):
    event = new_event(
        "document_ready.v1",
        tenant_id=uuid4(),
        correlation_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        data={"document_id": uuid4(), "appointment_id": uuid4(), source: uuid4()},
    )
    message = prepare_email(
        event,
        Recipient(uuid4(), "patient@example.test", object()),
        object(),
        "https://app.example.test",
    )
    assert message.attachment is None
    assert "https://app.example.test/patient/documents" in message.text
    assert "X-Amz" not in message.text


def test_price_link_routes_to_authenticated_order_review():
    event = new_event(
        "prescription_priced.v1",
        tenant_id=uuid4(),
        correlation_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        data={"prescription_id": uuid4(), "patient_id": uuid4()},
    )
    message = prepare_email(
        event,
        Recipient(event.data.patient_id, "patient@example.test"),
        object(),
        "https://app.example.test",
    )
    assert (
        f"/patient/medication-orders?prescription_id={event.data.prescription_id}" in message.text
    )
    assert "final total" in message.text and message.attachment is None


def test_receipt_event_is_one_durable_job_and_send(work):  # noqa: F811
    event = receipt_event()
    directory = Directory(event)
    queue(work, event, directory)
    queue(work, event, directory)
    sender = Sender()
    assert dispatch_one(work, sender, config(), directory)
    assert not dispatch_one(work, sender, config(), directory)
    assert sender.calls == 1 and rows(work)[0].status == "sent"


def test_stale_notice_is_skipped_without_ses(work):  # noqa: F811
    event = receipt_event()
    directory = Directory(event)
    queue(work, event, directory)
    directory.current = None
    sender = Sender()
    assert dispatch_one(work, sender, config(), directory)
    assert rows(work)[0].status == "skipped" and sender.calls == 0


def test_preparation_failure_is_retryable_and_never_claimed_as_sent(work):  # noqa: F811
    event = receipt_event()
    directory = Directory(event)
    queue(work, event, directory)
    directory.receipt = lambda *args: (_ for _ in ()).throw(RuntimeError("unavailable"))
    sender = Sender()
    assert dispatch_one(work, sender, config(), directory)
    job = rows(work)[0]
    assert (job.status, job.attempts, job.prepare_attempts) == ("pending", 0, 1)
    assert job.ready_at is not None and job.error_code == "source_unavailable"
    assert sender.calls == 0


def test_mc_waits_for_completed_consult_without_spending_send_attempt(work):  # noqa: F811
    event = new_event(
        "document_ready.v1",
        tenant_id=uuid4(),
        correlation_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        data={"document_id": uuid4(), "appointment_id": uuid4(), "medical_certificate_id": uuid4()},
    )
    directory = SimpleNamespace(resolve=lambda _: Recipient(uuid4(), "patient@example.test"))
    queue(work, event, directory)
    recipient = rows(work)[0].recipient_id
    directory.resolve = lambda _: Recipient(recipient, "patient@example.test")
    directory.clinical_ready = lambda *args: (_ for _ in ()).throw(NotificationDeferred())
    sender = Sender()
    assert dispatch_one(work, sender, config(), directory)
    job = rows(work)[0]
    assert job.status == "pending" and job.attempts == 0 and job.prepare_attempts == 0
    assert sender.calls == 0


def test_lifecycle_history_blocks_destructive_downgrade(work):  # noqa: F811
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    event = receipt_event()
    directory = Directory(event)
    queue(work, event, directory)
    assert dispatch_one(work, Sender(), config(), directory)
    with pytest.raises(RuntimeError, match="Retain lifecycle migration"):
        command.downgrade(
            Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")),
            "0002_notification_worker",
        )
