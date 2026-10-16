"""C02 clinic fields stored as ordinary columns in the tenant schema."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SERVICE_SCHEMA = "tenant"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SERVICE_SCHEMA)


class Clinic(Base):
    __tablename__ = "clinics"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_clinics_slug"),
        CheckConstraint("btrim(slug) <> ''", name="ck_clinics_slug"),
        CheckConstraint("btrim(name) <> ''", name="ck_clinics_name"),
        CheckConstraint(
            "status IN ('pending_review', 'active', 'rejected', 'suspended')",
            name="ck_clinics_status",
        ),
        CheckConstraint("primary_color ~ '^#[0-9A-Fa-f]{6}$'", name="ck_clinics_color"),
        CheckConstraint(
            "logo_url IS NULL OR logo_url ~ '^https://[^[:space:]/?#]+[^[:space:]]*$'",
            name="ck_clinics_logo_url",
        ),
        CheckConstraint(
            "consultation_price_minor BETWEEN 0 AND 9007199254740991",
            name="ck_clinics_price",
        ),
        CheckConstraint("currency = 'SGD'", name="ck_clinics_currency"),
        CheckConstraint("commission_bps BETWEEN 0 AND 10000", name="ck_clinics_commission"),
        CheckConstraint(
            "review_reason IS NULL OR btrim(review_reason) <> ''",
            name="ck_clinics_review_reason",
        ),
        Index("ix_clinics_public_page", "status", "name", "tenant_id"),
        Index("ix_clinics_admin_page", "status", "created_at", "tenant_id"),
    )
    __mapper_args__ = {"eager_defaults": True}

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # External identity ID; only tenant creates clinics, never identity tables.
    creator_subject_id: Mapped[UUID | None] = mapped_column(Uuid)
    membership_provisioned: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    slug: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, default="pending_review", server_default=text("'pending_review'")
    )
    # A08 maps these columns to C02's branding and consultation_price objects.
    primary_color: Mapped[str] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    consultation_price_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(Text, default="SGD", server_default=text("'SGD'"))
    commission_bps: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    review_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue()
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('clinic.approved', 'clinic.rejected', 'clinic.suspended', "
            "'clinic.commission_changed')",
            name="ck_audit_events_action",
        ),
        CheckConstraint(
            "reason IS NULL OR btrim(reason) <> ''",
            name="ck_audit_events_reason",
        ),
        Index("ix_audit_events_tenant_time", "tenant_id", "occurred_at", "event_id"),
    )

    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tenant.clinics.tenant_id", name="fk_audit_events_clinic", ondelete="RESTRICT"),
    )
    actor_subject_id: Mapped[UUID] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(Text)
    previous_values: Mapped[dict] = mapped_column(JSONB)
    new_values: Mapped[dict] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
