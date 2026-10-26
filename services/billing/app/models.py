"""C03 payment attempts and immutable trusted C03/C04 financial snapshots."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from telelink_common.outbox import outbox_table

SERVICE_SCHEMA = "billing"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SERVICE_SCHEMA)


event_outbox = outbox_table(Base.metadata)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "(purpose = 'consultation' AND appointment_id IS NOT NULL "
            "AND order_id IS NULL AND quote_id IS NULL) OR "
            "(purpose = 'medication_delivery' AND appointment_id IS NULL "
            "AND order_id IS NOT NULL AND quote_id IS NOT NULL)",
            name="ck_payments_resource_links",
        ),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', "
            "'refund_pending', 'refunded', 'refund_failed')",
            name="ck_payments_status",
        ),
        CheckConstraint(
            "resolution = 'none' OR (resolution = 'refund_required' "
            "AND status IN ('succeeded', 'refund_pending', 'refund_failed'))",
            name="ck_payments_resolution",
        ),
        CheckConstraint("currency = 'SGD'", name="ck_payments_currency"),
        CheckConstraint(
            "amount_minor = commissionable_minor + delivery_fee_minor",
            name="ck_payments_total",
        ),
        CheckConstraint(
            "purpose <> 'consultation' OR delivery_fee_minor = 0",
            name="ck_payments_consultation_fee",
        ),
        CheckConstraint("commission_bps BETWEEN 0 AND 10000", name="ck_payments_rate"),
        CheckConstraint(
            "commission_amount_minor = "
            "floor(commissionable_minor::numeric * commission_bps / 10000)",
            name="ck_payments_commission",
        ),
        CheckConstraint(
            "clinic_amount_minor = amount_minor - commission_amount_minor",
            name="ck_payments_clinic_amount",
        ),
        *(
            CheckConstraint(
                f"{column} BETWEEN 0 AND 9007199254740991", name=f"ck_payments_{column}"
            )
            for column in (
                "amount_minor",
                "commissionable_minor",
                "delivery_fee_minor",
                "commission_amount_minor",
                "clinic_amount_minor",
            )
        ),
        CheckConstraint("provider ~ '[^[:space:]]'", name="ck_payments_provider"),
        *(
            CheckConstraint(
                f"{column} IS NULL OR {column} ~ '[^[:space:]]'", name=f"ck_payments_{column}"
            )
            for column in (
                "provider_account_id",
                "provider_checkout_id",
                "provider_payment_id",
                "provider_idempotency_key",
            )
        ),
        *(
            Index(
                f"uq_payments_{column}",
                "provider",
                "provider_account_id",
                column,
                unique=True,
                postgresql_where=text(f"{column} IS NOT NULL"),
                postgresql_nulls_not_distinct=True,
            )
            for column in (
                "provider_checkout_id",
                "provider_payment_id",
                "provider_idempotency_key",
            )
        ),
        Index("ix_payments_patient_page", "patient_id", "created_at", "payment_id"),
        Index("ix_payments_tenant_page", "tenant_id", "created_at", "payment_id"),
        Index("ix_payments_appointment", "appointment_id"),
        Index("ix_payments_order", "order_id"),
    )
    __mapper_args__ = {"eager_defaults": True}

    payment_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    patient_id: Mapped[UUID] = mapped_column(Uuid)
    purpose: Mapped[str] = mapped_column(Text)
    appointment_id: Mapped[UUID | None] = mapped_column(Uuid)
    order_id: Mapped[UUID | None] = mapped_column(Uuid)
    quote_id: Mapped[UUID | None] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    resolution: Mapped[str] = mapped_column(Text, server_default=text("'none'"))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(Text)
    commissionable_minor: Mapped[int] = mapped_column(BigInteger)
    delivery_fee_minor: Mapped[int] = mapped_column(BigInteger)
    commission_bps: Mapped[int] = mapped_column(Integer)
    commission_amount_minor: Mapped[int] = mapped_column(BigInteger)
    clinic_amount_minor: Mapped[int] = mapped_column(BigInteger)
    provider: Mapped[str] = mapped_column(Text)
    provider_account_id: Mapped[str | None] = mapped_column(Text)
    provider_checkout_id: Mapped[str | None] = mapped_column(Text)
    provider_payment_id: Mapped[str | None] = mapped_column(Text)
    provider_idempotency_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue()
    )


class RefundAttempt(Base):
    __tablename__ = "refund_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'review')", name="ck_refund_status"
        ),
        CheckConstraint("length(trim(reason)) BETWEEN 1 AND 1000", name="ck_refund_reason"),
        Index("ix_refund_payment", "payment_id", "created_at"),
        Index("ix_refund_pending", "status", "next_attempt_at"),
        Index(
            "uq_refund_active_payment",
            "payment_id",
            unique=True,
            postgresql_where=text("status <> 'failed'"),
        ),
    )
    refund_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    payment_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("billing.payments.payment_id"))
    requested_by: Mapped[UUID] = mapped_column(Uuid)
    requested_by_name: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    provider_refund_id: Mapped[str | None] = mapped_column(Text, unique=True)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CheckoutAttempt(Base):
    """Durable operation before reservation/provider calls; may precede its payment snapshot."""

    __tablename__ = "checkout_attempts"
    payment_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    appointment_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    patient_id: Mapped[UUID] = mapped_column(Uuid)
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_fields: Mapped[dict | None] = mapped_column(JSONB)
    response: Mapped[dict | None] = mapped_column(JSONB)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CheckoutKey(Base):
    __tablename__ = "checkout_keys"
    patient_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    appointment_id: Mapped[UUID] = mapped_column(Uuid)
    payment_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("billing.checkout_attempts.payment_id", ondelete="CASCADE")
    )


class MedicationCheckoutAttempt(Base):
    __tablename__ = "medication_checkout_attempts"
    __table_args__ = (
        Index(
            "uq_medication_checkout_open_order",
            "order_id",
            unique=True,
            postgresql_where=text("closed_at IS NULL"),
        ),
    )
    payment_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    order_id: Mapped[UUID] = mapped_column(Uuid)
    quote_id: Mapped[UUID] = mapped_column(Uuid)
    patient_id: Mapped[UUID] = mapped_column(Uuid)
    quote_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reservation: Mapped[dict | None] = mapped_column(JSONB)
    provider_fields: Mapped[dict | None] = mapped_column(JSONB)
    response: Mapped[dict | None] = mapped_column(JSONB)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_reason: Mapped[str | None] = mapped_column(Text)
    resolution_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MedicationCheckoutKey(Base):
    __tablename__ = "medication_checkout_keys"
    patient_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    order_id: Mapped[UUID] = mapped_column(Uuid)
    quote_id: Mapped[UUID] = mapped_column(Uuid)
    payment_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("billing.medication_checkout_attempts.payment_id", ondelete="CASCADE")
    )


class StripeWebhookEvent(Base):
    """Durable verified receipt; B04 processes pending rows independently of delivery."""

    __tablename__ = "stripe_webhook_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'ignored', 'processed', 'rejected')", name="ck_webhook_status"
        ),
        Index("ix_stripe_webhook_pending", "status", "next_attempt_at", "received_at"),
    )
    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text)
    account_id: Mapped[str | None] = mapped_column(Text)
    api_version: Mapped[str | None] = mapped_column(Text)
    provider_created_at: Mapped[int] = mapped_column(BigInteger)
    object_data: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
