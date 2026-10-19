"""Notification-owned jobs; no clinical content or rendered message bodies."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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

SERVICE_SCHEMA = "notification"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SERVICE_SCHEMA)


class NotificationJob(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "recipient_id", "template", name="uq_jobs_event_recipient_template"
        ),
        CheckConstraint(
            "template IN ('booking_confirmed', 'document_ready', 'delivery_updated')",
            name="ck_jobs_template",
        ),
        CheckConstraint("status IN ('pending', 'sent', 'failed')", name="ck_jobs_status"),
        CheckConstraint("attempts >= 0", name="ck_jobs_attempts"),
        CheckConstraint(
            "error_code IS NULL OR error_code = 'ses_unconfirmed'", name="ck_jobs_error_code"
        ),
        CheckConstraint(
            "length(btrim(recipient_email)) BETWEEN 3 AND 254 "
            "AND position(chr(10) in recipient_email) = 0 "
            "AND position(chr(13) in recipient_email) = 0",
            name="ck_jobs_email",
        ),
        CheckConstraint(
            "(status = 'sent' AND provider_message_id IS NOT NULL "
            "AND btrim(provider_message_id) <> '' AND sent_at IS NOT NULL "
            "AND attempts > 0 AND error_code IS NULL) "
            "OR (status IN ('pending', 'failed') AND provider_message_id IS NULL "
            "AND sent_at IS NULL)",
            name="ck_jobs_sent",
        ),
        Index("ix_jobs_status_created", "status", "created_at"),
    )
    job_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    event_id: Mapped[UUID] = mapped_column(Uuid)
    recipient_id: Mapped[UUID] = mapped_column(Uuid)
    recipient_email: Mapped[str] = mapped_column(Text)
    template: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
