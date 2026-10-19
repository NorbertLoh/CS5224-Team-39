"""C04 clinical data; IDs belonging to other services have no foreign keys."""

from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    FetchedValue,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from telelink_common.outbox import outbox_table

SERVICE_SCHEMA = "clinical_records"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SERVICE_SCHEMA)


event_outbox = outbox_table(Base.metadata)


class AppointmentContext:
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    appointment_id: Mapped[UUID] = mapped_column(Uuid)
    patient_id: Mapped[UUID] = mapped_column(Uuid)
    doctor_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue()
    )


class Note(AppointmentContext, Base):
    __tablename__ = "notes"
    __table_args__ = (
        UniqueConstraint("appointment_id", name="uq_notes_appointment"),
        CheckConstraint("btrim(text) <> ''", name="ck_notes_text"),
        Index("ix_notes_patient_page", "patient_id", "created_at", "note_id"),
        Index("ix_notes_tenant_doctor", "tenant_id", "doctor_id", "appointment_id"),
    )
    __mapper_args__ = {"eager_defaults": True}

    note_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    text: Mapped[str] = mapped_column(Text)


class MedicalCertificate(AppointmentContext, Base):
    __tablename__ = "medical_certificates"
    __table_args__ = (
        UniqueConstraint("appointment_id", name="uq_mc_appointment"),
        CheckConstraint("duration_days IS NULL OR duration_days > 0", name="ck_mc_duration"),
        CheckConstraint(
            "NOT selected OR (start_date IS NOT NULL AND duration_days IS NOT NULL)",
            name="ck_mc_selected_period",
        ),
        CheckConstraint(
            "(finalized_at IS NULL AND issued_at IS NULL AND consultation_date IS NULL) OR "
            "(finalized_at IS NOT NULL AND consultation_date IS NOT NULL AND "
            "((selected AND issued_at IS NOT NULL) OR (NOT selected AND issued_at IS NULL)))",
            name="ck_mc_finalization",
        ),
    )
    __mapper_args__ = {"eager_defaults": True}

    medical_certificate_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    selected: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    start_date: Mapped[date | None] = mapped_column(Date)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    additional_notes: Mapped[str] = mapped_column(Text, server_default=text("''"))
    consultation_date: Mapped[date | None] = mapped_column(Date)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def end_date(self):
        if self.start_date is not None and self.duration_days is not None:
            return self.start_date + timedelta(days=self.duration_days - 1)
        return None


class Prescription(AppointmentContext, Base):
    __tablename__ = "prescriptions"
    __table_args__ = (
        UniqueConstraint("prescription_id", "tenant_id", name="uq_prescriptions_tenant_context"),
        CheckConstraint("status IN ('draft', 'issued', 'voided')", name="ck_prescriptions_status"),
        CheckConstraint(
            "(status = 'draft' AND issued_at IS NULL) OR "
            "(status = 'issued' AND issued_at IS NOT NULL) OR status = 'voided'",
            name="ck_prescriptions_issued_at",
        ),
        CheckConstraint(
            "issued_at IS NULL OR (isfinite(issued_at) AND issued_at >= created_at)",
            name="ck_prescriptions_issued_time",
        ),
        Index(
            "uq_prescriptions_live_appointment",
            "appointment_id",
            unique=True,
            postgresql_where=text("status <> 'voided'"),
        ),
        Index("ix_prescriptions_patient_page", "patient_id", "created_at", "prescription_id"),
        Index(
            "ix_prescriptions_tenant_doctor_page",
            "tenant_id",
            "doctor_id",
            "created_at",
            "prescription_id",
        ),
        Index(
            "ix_prescriptions_appointment_page", "appointment_id", "created_at", "prescription_id"
        ),
    )
    __mapper_args__ = {"eager_defaults": True}

    prescription_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(Text, default="draft", server_default=text("'draft'"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["prescription_id", "tenant_id"],
            [
                "clinical_records.prescriptions.prescription_id",
                "clinical_records.prescriptions.tenant_id",
            ],
            name="fk_prescription_items_tenant_parent",
            ondelete="RESTRICT",
        ),
        CheckConstraint("quantity > 0", name="ck_prescription_items_quantity"),
        CheckConstraint("btrim(instructions) <> ''", name="ck_prescription_items_instructions"),
        CheckConstraint("btrim(display_name) <> ''", name="ck_prescription_items_display_name"),
        Index("ix_prescription_items_parent", "prescription_id", "prescription_item_id"),
    )

    prescription_item_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    prescription_id: Mapped[UUID] = mapped_column(Uuid)
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    medication_id: Mapped[UUID] = mapped_column(Uuid)
    quantity: Mapped[int] = mapped_column(Integer)
    instructions: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)


class ReadAudit(Base):
    """Minimal durable access trail; never stores clinical text or credentials."""

    __tablename__ = "read_audits"
    __table_args__ = (
        CheckConstraint(
            "resource_type IN ('note', 'prescription', 'prescription_list', 'medical_certificate')",
            name="ck_read_audit_type",
        ),
        Index("ix_read_audits_actor_time", "actor_id", "created_at"),
    )
    audit_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    actor_id: Mapped[UUID] = mapped_column(Uuid)
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid)
    appointment_id: Mapped[UUID | None] = mapped_column(Uuid)
    resource_id: Mapped[UUID | None] = mapped_column(Uuid)
    resource_type: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServiceReadAudit(Base):
    __tablename__ = "service_read_audits"
    __table_args__ = (
        CheckConstraint(
            "(prescription_id IS NOT NULL AND medical_certificate_id IS NULL) OR "
            "(prescription_id IS NULL AND medical_certificate_id IS NOT NULL)",
            name="ck_service_read_source",
        ),
    )
    audit_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    caller: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    prescription_id: Mapped[UUID | None] = mapped_column(Uuid)
    medical_certificate_id: Mapped[UUID | None] = mapped_column(Uuid)
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    appointment_id: Mapped[UUID] = mapped_column(Uuid)
    request_id: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
