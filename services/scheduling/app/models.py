"""Fixed slots and immutable appointment context; external IDs have no foreign keys."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKeyConstraint,
    Index,
    MetaData,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from telelink_common.inbox import inbox_table
from telelink_common.outbox import outbox_table

SERVICE_SCHEMA = "scheduling"
ACTIVE_RESERVATION_STATES = ("held", "pending_payment", "confirmed", "in_progress")


class Base(DeclarativeBase):
    metadata = MetaData(schema=SERVICE_SCHEMA)


event_inbox = inbox_table(Base.metadata)
event_outbox = outbox_table(Base.metadata)


class PaymentRecovery(Base):
    """One decision per verified charge; refund rows double as a durable delivery queue."""

    __tablename__ = "payment_recoveries"
    __table_args__ = (
        CheckConstraint("outcome IN ('recovered', 'refund_required')", name="ck_recovery_outcome"),
        CheckConstraint(
            "reason IN ('late_payment', 'slot_reallocated', 'appointment_cancelled', "
            "'appointment_unavailable', 'duplicate_charge')",
            name="ck_recovery_reason",
        ),
        Index("ix_recovery_pending", "delivered_at", "created_at"),
    )

    payment_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    appointment_id: Mapped[UUID] = mapped_column(Uuid)
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    event_id: Mapped[UUID | None] = mapped_column(Uuid)
    outcome: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    previous_status: Mapped[str] = mapped_column(Text)
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"
    __table_args__ = (
        CheckConstraint("isfinite(starts_at) AND isfinite(ends_at)", name="ck_slots_finite"),
        CheckConstraint("ends_at = starts_at + interval '30 minutes'", name="ck_slots_duration"),
        UniqueConstraint(
            "slot_id", "tenant_id", "doctor_id", "starts_at", "ends_at", name="uq_slots_context"
        ),
        ExcludeConstraint(
            ("doctor_id", "="),
            (func.tstzrange(text("starts_at"), text("ends_at"), text("'[)'")), "&&"),
            name="ex_slots_doctor_overlap",
            using="gist",
            where=text("withdrawn_at IS NULL"),
        ),
        Index("ix_slots_tenant_time", "tenant_id", "starts_at", "slot_id"),
        Index("ix_slots_tenant_doctor_time", "tenant_id", "doctor_id", "starts_at", "slot_id"),
    )

    slot_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    doctor_id: Mapped[UUID] = mapped_column(Uuid)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["slot_id", "tenant_id", "doctor_id", "starts_at", "ends_at"],
            [
                f"scheduling.availability_slots.{field}"
                for field in ("slot_id", "tenant_id", "doctor_id", "starts_at", "ends_at")
            ],
            name="fk_appointments_slot_context",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('held', 'pending_payment', 'confirmed', 'in_progress', "
            "'completed', 'expired', 'cancelled', 'no_show')",
            name="ck_appointments_status",
        ),
        CheckConstraint(
            "payment_resolution IN ('none', 'awaiting_payment', 'confirmed', "
            "'refund_required', 'refunded')",
            name="ck_appointments_payment_resolution",
        ),
        CheckConstraint(
            "consultation_price_minor BETWEEN 0 AND 9007199254740991",
            name="ck_appointments_price",
        ),
        CheckConstraint("currency = 'SGD'", name="ck_appointments_currency"),
        CheckConstraint(
            "(cancelled_at IS NULL AND cancellation_reason IS NULL "
            "AND cancelled_by_subject_id IS NULL) OR "
            "(status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND cancelled_by_subject_id IS NOT NULL AND cancellation_reason IS NOT NULL "
            "AND btrim(cancellation_reason) <> '' AND length(cancellation_reason) <= 2000)",
            name="ck_appointments_cancellation_record",
        ),
        CheckConstraint(
            "hold_expires_at IS NULL OR "
            "(hold_expires_at > created_at AND hold_expires_at <= starts_at "
            "AND hold_expires_at <= created_at + interval '10 minutes')",
            name="ck_appointments_hold_deadline",
        ),
        CheckConstraint(
            "status NOT IN ('held', 'pending_payment', 'expired') OR hold_expires_at IS NOT NULL",
            name="ck_appointments_hold_required",
        ),
        CheckConstraint(
            "status NOT IN ('confirmed', 'in_progress', 'completed', 'no_show') "
            "OR hold_expires_at IS NULL",
            name="ck_appointments_confirmed_hold",
        ),
        Index("ix_appointments_tenant_time", "tenant_id", "starts_at", "appointment_id"),
        Index("ix_appointments_patient_time", "patient_id", "starts_at", "appointment_id"),
        Index("ix_appointments_doctor_time", "doctor_id", "starts_at", "appointment_id"),
        Index("ix_appointments_slot", "slot_id"),
        Index(
            "uq_appointments_active_slot",
            "slot_id",
            unique=True,
            postgresql_where=text(
                "status IN ('held', 'pending_payment', 'confirmed', 'in_progress')"
            ),
        ),
        Index(
            "ix_appointments_expiry",
            "hold_expires_at",
            "appointment_id",
            postgresql_where=text("status IN ('held', 'pending_payment')"),
        ),
    )
    __mapper_args__ = {"eager_defaults": True}

    appointment_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    patient_id: Mapped[UUID] = mapped_column(Uuid)
    doctor_id: Mapped[UUID] = mapped_column(Uuid)
    slot_id: Mapped[UUID] = mapped_column(Uuid)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="held", server_default=text("'held'"))
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consultation_price_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(Text, default="SGD", server_default=text("'SGD'"))
    payment_id: Mapped[UUID | None] = mapped_column(Uuid)
    patient_name: Mapped[str | None] = mapped_column(Text)
    doctor_name: Mapped[str | None] = mapped_column(Text)
    clinic_name: Mapped[str | None] = mapped_column(Text)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_by_subject_id: Mapped[UUID | None] = mapped_column(Uuid)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_resolution: Mapped[str] = mapped_column(
        Text, default="none", server_default=text("'none'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue()
    )
