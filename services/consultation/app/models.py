"""Consultation owns sessions; scheduling/identity IDs have no cross-service FKs."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    MetaData,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SERVICE_SCHEMA = "consultation"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SERVICE_SCHEMA)


class ConsultationSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("appointment_id", name="uq_sessions_appointment"),
        UniqueConstraint("session_id", "tenant_id", name="uq_sessions_tenant"),
        CheckConstraint("patient_id <> doctor_id", name="ck_sessions_distinct_participants"),
        CheckConstraint(
            "isfinite(starts_at) AND isfinite(ends_at) AND starts_at < ends_at",
            name="ck_sessions_schedule",
        ),
        CheckConstraint(
            "status IN ('scheduled', 'in_progress', 'completed')", name="ck_sessions_status"
        ),
        CheckConstraint(
            "(status = 'scheduled' AND started_at IS NULL AND ended_at IS NULL) OR "
            "(status = 'in_progress' AND started_at IS NOT NULL AND ended_at IS NULL) OR "
            "(status = 'completed' AND started_at IS NOT NULL AND ended_at IS NOT NULL)",
            name="ck_sessions_lifecycle",
        ),
        CheckConstraint(
            "started_at IS NULL OR (isfinite(started_at) "
            "AND started_at >= starts_at AND started_at < ends_at)",
            name="ck_sessions_start_window",
        ),
        CheckConstraint(
            "ended_at IS NULL OR (isfinite(ended_at) AND ended_at >= started_at)",
            name="ck_sessions_end_time",
        ),
        Index("ix_sessions_tenant_doctor", "tenant_id", "doctor_id", "starts_at"),
        Index("ix_sessions_patient", "patient_id", "starts_at"),
    )

    session_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    appointment_id: Mapped[UUID] = mapped_column(Uuid)
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    patient_id: Mapped[UUID] = mapped_column(Uuid)
    doctor_id: Mapped[UUID] = mapped_column(Uuid)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        Text, default="scheduled", server_default=text("'scheduled'")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Admission(Base):
    """One bounded pending/active lease per appointment participant; no bearer in storage."""

    __tablename__ = "admissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "tenant_id"],
            ["consultation.sessions.session_id", "consultation.sessions.tenant_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("token_digest", name="uq_admissions_digest"),
        UniqueConstraint("peer_id", name="uq_admissions_peer"),
        CheckConstraint("token_digest ~ '^[0-9a-f]{64}$'", name="ck_admissions_digest"),
        CheckConstraint(
            "isfinite(expires_at) AND expires_at > issued_at "
            "AND expires_at <= issued_at + interval '300 seconds'",
            name="ck_admissions_expiry",
        ),
        CheckConstraint(
            "consumed_at IS NULL OR (consumed_at >= issued_at AND consumed_at < expires_at)",
            name="ck_admissions_consumed",
        ),
        CheckConstraint(
            "released_at IS NULL OR (consumed_at IS NOT NULL AND released_at >= consumed_at)",
            name="ck_admissions_released",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    subject_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    token_digest: Mapped[str] = mapped_column(Text)
    peer_id: Mapped[UUID] = mapped_column(Uuid)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
