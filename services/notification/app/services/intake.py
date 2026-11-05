"""Commit a job and inbox row together; email sending occurs after acknowledgement."""

from app.models import NotificationJob

TEMPLATES = {
    "appointment_confirmed.v1": "booking_confirmed",
    "document_ready.v1": "document_ready",
    "delivery_status_changed.v1": "delivery_updated",
    "appointment_cancelled.v1": "booking_confirmed",
    "prescription_priced.v1": "document_ready",
    "payment_refunded.v1": "document_ready",
}


class QueueNotification:
    def __init__(self, directory):
        self.directory = directory

    def __call__(self, session, event):
        template = TEMPLATES.get(event.detail_type)
        if template is None:
            raise ValueError("Unsupported notification event")
        recipient = self.directory.resolve(event)
        if recipient is None:
            return
        session.add(
            NotificationJob(
                tenant_id=event.tenant_id,
                event_id=event.event_id,
                recipient_id=recipient.subject_id,
                recipient_email=recipient.email,
                template=template,
                source_event=event.model_dump(mode="json"),
            )
        )
