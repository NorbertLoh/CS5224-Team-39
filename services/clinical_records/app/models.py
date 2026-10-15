"""C04 clinical data; IDs belonging to other services have no foreign keys."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKey,
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

SERVICE_SCHEMA = "clinical_records"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SERVICE_SCHEMA)


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


class Prescription(AppointmentContext, Base):
    __tablename__ = "prescriptions"
    __table_args__ = (
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
        CheckConstraint("quantity > 0", name="ck_prescription_items_quantity"),
        CheckConstraint("btrim(instructions) <> ''", name="ck_prescription_items_instructions"),
        CheckConstraint("btrim(display_name) <> ''", name="ck_prescription_items_display_name"),
        Index("ix_prescription_items_parent", "prescription_id", "prescription_item_id"),
    )

    prescription_item_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    prescription_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("clinical_records.prescriptions.prescription_id", ondelete="RESTRICT"),
    )
    medication_id: Mapped[UUID] = mapped_column(Uuid)
    quantity: Mapped[int] = mapped_column(Integer)
    instructions: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
