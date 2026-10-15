"""Metadata only: source records remain owned by records/billing services."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    FetchedValue,
    Index,
    MetaData,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SERVICE_SCHEMA = "document"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SERVICE_SCHEMA)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'prescription_pdf' AND prescription_id IS NOT NULL "
            "AND payment_id IS NULL AND medical_certificate_id IS NULL AND doctor_id IS NOT NULL) "
            "OR (kind = 'receipt_pdf' AND payment_id IS NOT NULL "
            "AND prescription_id IS NULL AND medical_certificate_id IS NULL) "
            "OR (kind = 'medical_certificate_pdf' AND medical_certificate_id IS NOT NULL "
            "AND prescription_id IS NULL AND payment_id IS NULL AND doctor_id IS NOT NULL)",
            name="ck_documents_source",
        ),
        CheckConstraint("status IN ('pending', 'ready', 'failed')", name="ck_documents_status"),
        CheckConstraint("content_type = 'application/pdf'", name="ck_documents_content_type"),
        CheckConstraint(
            "(status = 'ready' AND storage_bucket IS NOT NULL AND btrim(storage_bucket) <> '' "
            "AND storage_key IS NOT NULL AND btrim(storage_key) <> '' "
            "AND size_bytes IS NOT NULL AND size_bytes > 0 "
            "AND sha256 IS NOT NULL AND sha256 ~ '^[0-9a-f]{64}$') "
            "OR (status IN ('pending', 'failed') AND storage_bucket IS NULL "
            "AND storage_key IS NULL AND size_bytes IS NULL AND sha256 IS NULL)",
            name="ck_documents_storage",
        ),
        UniqueConstraint("tenant_id", "kind", "prescription_id", name="uq_documents_prescription"),
        UniqueConstraint("tenant_id", "kind", "payment_id", name="uq_documents_payment"),
        UniqueConstraint(
            "tenant_id", "kind", "medical_certificate_id", name="uq_documents_medical_certificate"
        ),
        UniqueConstraint("storage_bucket", "storage_key", name="uq_documents_object"),
        Index("ix_documents_patient_page", "tenant_id", "patient_id", "created_at", "document_id"),
        Index(
            "ix_documents_appointment_page",
            "tenant_id",
            "appointment_id",
            "created_at",
            "document_id",
        ),
    )
    __mapper_args__ = {"eager_defaults": True}

    document_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    appointment_id: Mapped[UUID] = mapped_column(Uuid)
    patient_id: Mapped[UUID] = mapped_column(Uuid)
    doctor_id: Mapped[UUID | None] = mapped_column(Uuid)
    prescription_id: Mapped[UUID | None] = mapped_column(Uuid)
    payment_id: Mapped[UUID | None] = mapped_column(Uuid)
    medical_certificate_id: Mapped[UUID | None] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    content_type: Mapped[str] = mapped_column(Text, server_default=text("'application/pdf'"))
    storage_bucket: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue()
    )
