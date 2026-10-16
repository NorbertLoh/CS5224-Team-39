"""One logical PDF and ready event, despite repeated queue delivery."""

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select, text
from telelink_common.events import new_event
from telelink_common.outbox import add_event

from app.models import Document, event_outbox
from app.templates import render_prescription


def document_id_for(prescription_id):
    return uuid5(NAMESPACE_URL, "telelink:prescription_pdf:" + str(prescription_id))


class GeneratePrescription:
    def __init__(self, records, store):
        self.records, self.store = records, store

    def __call__(self, session, event):
        try:
            self.handle(session, event)
        except Exception:
            # Shared M03 logs exception traces. Never expose clinical validation/provider details.
            raise RuntimeError("Prescription PDF processing failed") from None

    def handle(self, session, event):
        if event.detail_type != "prescription_issued.v1":
            raise ValueError("Unsupported document event")
        prescription_id = event.data.prescription_id
        # Lock absent rows too, including distinct event IDs for the same prescription.
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "document:prescription:" + str(prescription_id)},
        )
        row = session.scalar(
            select(Document).where(
                Document.prescription_id == prescription_id, Document.kind == "prescription_pdf"
            )
        )
        if row is not None:
            if row.tenant_id != event.tenant_id or row.appointment_id != event.data.appointment_id:
                raise ValueError("Document context mismatch")
            if row.status == "ready":
                return
        self.store.verify_private()
        document_id = row.document_id if row is not None else document_id_for(prescription_id)
        key = f"prescriptions/{event.tenant_id}/{prescription_id}.pdf"
        expected = {
            "document-id": str(document_id),
            "prescription-id": str(prescription_id),
            "tenant-id": str(event.tenant_id),
            "appointment-id": str(event.data.appointment_id),
        }
        # Uploaded objects survive a failed DB commit. Recover before fetching or rendering again.
        stored = self.store.load(key, expected)
        if stored is None:
            source = self.records.prescription(event)
            stored = self.store.put(
                key,
                render_prescription(source.render_data()),
                expected,
                source.patient_id,
                source.doctor_id,
            )
        if row is None:
            row = Document(
                document_id=document_id,
                tenant_id=event.tenant_id,
                appointment_id=event.data.appointment_id,
                prescription_id=prescription_id,
                patient_id=stored.patient_id,
                doctor_id=stored.doctor_id,
                kind="prescription_pdf",
            )
            session.add(row)
        elif row.patient_id != stored.patient_id or row.doctor_id != stored.doctor_id:
            raise ValueError("Stored document ownership mismatch")
        row.status, row.storage_bucket, row.storage_key = "ready", self.store.bucket, key
        row.size_bytes, row.sha256 = stored.size_bytes, stored.sha256
        session.flush()
        ready = new_event(
            "document_ready.v1",
            occurred_at=session.scalar(select(func.clock_timestamp())),
            event_id=uuid5(NAMESPACE_URL, "telelink:document_ready.v1:" + str(document_id)),
            tenant_id=row.tenant_id,
            correlation_id=event.correlation_id,
            data={
                "document_id": document_id,
                "prescription_id": prescription_id,
                "appointment_id": row.appointment_id,
            },
        )
        add_event(session, event_outbox, ready)
