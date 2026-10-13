"""C02 subjects and memberships, confined to the identity service schema."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    MetaData,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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
        CheckConstraint("btrim(cognito_sub) <> ''", name="ck_subjects_cognito_sub"),
        CheckConstraint("btrim(display_name) <> ''", name="ck_subjects_display_name"),
        CheckConstraint(GLOBAL_ROLES_CHECK, name="ck_subjects_global_roles"),
    )

    subject_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # Opaque verified runtime value, never inferred from a fixture UUID or group.
    cognito_sub: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    global_roles: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)), default=list, server_default=text("'{}'::text[]")
    )


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
    # Tenant owns clinics; clinic existence must be checked through its API in A10.
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    roles: Mapped[list[str]] = mapped_column(MutableList.as_mutable(ARRAY(Text)))
    status: Mapped[str] = mapped_column(Text, default="active", server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue()
    )
