"""Durable MC generation status, private-object recovery and idempotent publication."""

from datetime import date, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from telelink_common.events import new_event
from telelink_common.outbox import add_event

from app.models import Document, event_outbox
from app.rendering.template_data import MedicalCertificate
from app.rendering.templates import render_medical_certificate


class IssuedMC(BaseModel):
    medical_certificate_id: UUID
    tenant_id: UUID
    appointment_id: UUID
    patient_id: UUID
    doctor_id: UUID
    selected: bool
    issued_at: AwareDatetime
    finalized_at: AwareDatetime
    consultation_date: date
    start_date: date
    end_date: date
    duration_days: int = Field(strict=True, gt=0)
    additional_notes: str = Field(max_length=20000)
    clinic_name: str = Field(min_length=1, max_length=200)
    patient_name: str = Field(min_length=1, max_length=200)
    doctor_name: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def issued_period(self):
        if (
            not self.selected
            or self.start_date + timedelta(days=self.duration_days - 1) != self.end_date
        ):
            raise ValueError("Invalid issued MC period")
        return self

    def render_data(self):
        return MedicalCertificate(
            reference=str(self.medical_certificate_id),
            issued_at=self.issued_at,
            clinic_name=self.clinic_name,
            patient_name=self.patient_name,
            doctor_name=self.doctor_name,
            consultation_date=self.consultation_date,
            unfit_from=self.start_date,
            unfit_through=self.end_date,
            additional_notes=self.additional_notes,
        )


def document_id_for(medical_certificate_id):
    return uuid5(NAMESPACE_URL, "telelink:medical_certificate_pdf:" + str(medical_certificate_id))


def lock(session, mc_id):
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": "document:mc:" + str(mc_id)},
    )


def validate_context(row, event):
    if any(
        getattr(row, key) != value
        for key, value in {
            "tenant_id": event.tenant_id,
            "appointment_id": event.data.appointment_id,
            "patient_id": event.data.patient_id,
            "doctor_id": event.data.doctor_id,
            "medical_certificate_id": event.data.medical_certificate_id,
        }.items()
    ):
        raise ValueError("MC document context mismatch")


class GenerateMedicalCertificate:
    def __init__(self, records, store):
        self.records, self.store = records, store

    def __call__(self, session, event):
        engine = session.get_bind()
        document_id = document_id_for(event.data.medical_certificate_id)
        try:
            # Status commits separately from the inbox: rollback/retry must not
            # make a failed MC disappear from the patient's document list.
            with Session(engine) as status, status.begin():
                lock(status, event.data.medical_certificate_id)
                row = status.get(Document, document_id)
                if row is None:
                    status.add(
                        Document(
                            document_id=document_id,
                            tenant_id=event.tenant_id,
                            appointment_id=event.data.appointment_id,
                            patient_id=event.data.patient_id,
                            doctor_id=event.data.doctor_id,
                            medical_certificate_id=event.data.medical_certificate_id,
                            kind="medical_certificate_pdf",
                        )
                    )
                else:
                    validate_context(row, event)
            self.handle(session, event, document_id)
        except Exception:
            session.rollback()  # Release the generation lock before persisting failure.
            with Session(engine) as status, status.begin():
                lock(status, event.data.medical_certificate_id)
                row = status.get(Document, document_id)
                if row is not None:
                    validate_context(row, event)
                    if row.status != "ready":
                        row.status = "failed"
            raise RuntimeError("Medical certificate PDF processing failed") from None

    def handle(self, session, event, document_id):
        lock(session, event.data.medical_certificate_id)
        row = session.get(Document, document_id)
        validate_context(row, event)
        if row.status == "ready":
            return
        self.store.verify_private()
        key = f"medical-certificates/{event.tenant_id}/{event.data.medical_certificate_id}.pdf"
        expected = {
            "document-id": str(document_id),
            "medical-certificate-id": str(event.data.medical_certificate_id),
            "tenant-id": str(event.tenant_id),
            "appointment-id": str(event.data.appointment_id),
        }
        stored = self.store.load(key, expected)
        if stored is None:
            source = self.records.medical_certificate(event)
            validate_context(source, event)
            stored = self.store.put(
                key,
                render_medical_certificate(source.render_data()),
                expected,
                source.patient_id,
                source.doctor_id,
            )
        if stored.patient_id != row.patient_id or stored.doctor_id != row.doctor_id:
            raise ValueError("Stored MC ownership mismatch")
        row.status, row.storage_bucket, row.storage_key = "ready", self.store.bucket, key
        row.size_bytes, row.sha256 = stored.size_bytes, stored.sha256
        session.flush()
        add_event(
            session,
            event_outbox,
            new_event(
                "document_ready.v1",
                occurred_at=session.scalar(select(func.clock_timestamp())),
                event_id=uuid5(NAMESPACE_URL, "telelink:document_ready.v1:" + str(document_id)),
                tenant_id=row.tenant_id,
                correlation_id=event.correlation_id,
                data={
                    "document_id": document_id,
                    "medical_certificate_id": row.medical_certificate_id,
                    "appointment_id": row.appointment_id,
                },
            ),
        )
