"""C02 subjects and memberships, confined to the identity service schema."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SERVICE_SCHEMA = "identity"

# Enumerating the small C02 sets also rejects duplicates, NULL elements,
# multidimensional arrays and unusual array bounds, in either role order.
GLOBAL_ROLES_CHECK = """global_roles = ARRAY[]::text[]
    OR global_roles = ARRAY['patient']::text[]
    OR global_roles = ARRAY['platform_admin']::text[]
    OR global_roles = ARRAY['patient', 'platform_admin']::text[]
    OR global_roles = ARRAY['platform_admin', 'patient']::text[]"""
MEMBERSHIP_ROLES_CHECK = """roles = ARRAY['doctor']::text[]
    OR roles = ARRAY['clinic_admin']::text[]
    OR roles = ARRAY['doctor', 'clinic_admin']::text[]
    OR roles = ARRAY['clinic_admin', 'doctor']::text[]"""


class Base(DeclarativeBase):
    metadata = MetaData(schema=SERVICE_SCHEMA)


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("cognito_sub", name="uq_subjects_cognito_sub"),
        UniqueConstraint("email", name="uq_subjects_email"),
        CheckConstraint(
            "email IS NULL OR (email = lower(btrim(email)) AND email <> '')",
            name="ck_subjects_email",
        ),
        CheckConstraint("btrim(cognito_sub) <> ''", name="ck_subjects_cognito_sub"),
        CheckConstraint("btrim(display_name) <> ''", name="ck_subjects_display_name"),
        CheckConstraint(GLOBAL_ROLES_CHECK, name="ck_subjects_global_roles"),
    )

    subject_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # Opaque verified runtime value, never inferred from a fixture UUID or group.
    cognito_sub: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    global_roles: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)), default=list, server_default=text("'{}'::text[]")
    )


class PatientProfile(Base):
    __tablename__ = "patient_profiles"
    __table_args__ = (
        CheckConstraint("phone_number ~ '^\\+65[689][0-9]{7}$'", name="ck_patient_profile_phone"),
        CheckConstraint("btrim(address_line) <> ''", name="ck_patient_profile_address"),
        CheckConstraint("postal_code ~ '^[0-9]{6}$'", name="ck_patient_profile_postal"),
        CheckConstraint("country_code = 'SG'", name="ck_patient_profile_country"),
    )
    subject_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("identity.subjects.subject_id", ondelete="CASCADE"), primary_key=True
    )
    phone_number: Mapped[str] = mapped_column(Text)
    address_line: Mapped[str] = mapped_column(Text)
    postal_code: Mapped[str] = mapped_column(Text)
    country_code: Mapped[str] = mapped_column(Text, default="SG", server_default=text("'SG'"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("subject_id", "tenant_id", name="uq_memberships_subject_tenant"),
        CheckConstraint(MEMBERSHIP_ROLES_CHECK, name="ck_memberships_roles"),
        CheckConstraint("status IN ('active', 'revoked')", name="ck_memberships_status"),
        Index("ix_memberships_tenant_page", "tenant_id", "created_at", "membership_id"),
    )
    __mapper_args__ = {"eager_defaults": True}

    membership_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "identity.subjects.subject_id", name="fk_memberships_subject", ondelete="RESTRICT"
        ),
    )
    subject: Mapped[Subject] = relationship(lazy="joined")
    # Tenant owns clinics; clinic existence must be checked through its API in A10.
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    roles: Mapped[list[str]] = mapped_column(MutableList.as_mutable(ARRAY(Text)))
    status: Mapped[str] = mapped_column(Text, default="active", server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue()
    )


class DoctorPhoto(Base):
    """One sanitized public portrait per doctor, separate from licence evidence."""

    __tablename__ = "doctor_photos"
    __table_args__ = (
        CheckConstraint("octet_length(content) BETWEEN 1 AND 2097152", name="ck_doctor_photo_size"),
    )
    subject_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("identity.subjects.subject_id", ondelete="CASCADE"), primary_key=True
    )
    photo_id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class DoctorDocument(Base):
    """Private evidence, served through authenticated endpoints only."""

    __tablename__ = "doctor_documents"
    __table_args__ = (
        CheckConstraint("octet_length(content) BETWEEN 1 AND 5242880", name="ck_doctor_doc_size"),
    )
    document_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("identity.subjects.subject_id", ondelete="CASCADE"), index=True
    )
    content_type: Mapped[str] = mapped_column(Text)
    filename: Mapped[str | None] = mapped_column(Text)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DoctorApplication(Base):
    __tablename__ = "doctor_applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','revoked')", name="ck_doctor_status"
        ),
        CheckConstraint("revision > 0", name="ck_doctor_revision"),
    )
    subject_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("identity.subjects.subject_id", ondelete="CASCADE"), primary_key=True
    )
    legal_name: Mapped[str] = mapped_column(Text)
    licence_number: Mapped[str] = mapped_column(Text)
    licensing_authority: Mapped[str] = mapped_column(Text)
    specialty: Mapped[str] = mapped_column(Text)
    document_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("identity.doctor_documents.document_id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(Text, default="pending")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_id: Mapped[UUID | None] = mapped_column(Uuid)


class DoctorApplicationEvent(Base):
    """Immutable submission/review snapshots, including the evidence identifier."""

    __tablename__ = "doctor_application_events"
    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("identity.subjects.subject_id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[UUID] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
