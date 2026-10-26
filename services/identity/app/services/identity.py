from hashlib import blake2b

from sqlalchemy import func, select, text
from telelink_common.access import has_tenant_role
from telelink_common.errors import DomainError

from app.database import find_subject
from app.models import Membership
from app.schemas import (
    IdentityRead,
    MembershipRead,
)


def current_subject(session, principal):
    subject = find_subject(session, principal.subject)
    if subject is None:
        raise DomainError(403, "identity_not_provisioned", "Identity is not provisioned.")
    return subject


def active_membership(session, subject_id, tenant_id):
    return session.scalar(
        select(Membership).where(
            Membership.subject_id == subject_id,
            Membership.tenant_id == tenant_id,
            Membership.status == "active",
        )
    )


def authorize_admin(session, principal, tenant_id):
    subject = current_subject(session, principal)
    membership = active_membership(session, subject.subject_id, tenant_id)
    if not has_tenant_role(
        membership,
        tenant_id,
        "clinic_admin",
        global_roles=subject.global_roles,
        allow_platform_admin=True,
    ):
        raise DomainError(404, "not_found", "Resource not found.")
    return subject


def lock_tenant(session, tenant_id):
    # Transaction-scoped, shared by all API replicas and all membership writes.
    digest = blake2b(b"identity-memberships:" + tenant_id.bytes, digest_size=8).digest()
    lock_id = int.from_bytes(digest, "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})


def guard_last_admin(session, membership, roles, status):
    if (
        membership is None
        or membership.status != "active"
        or "clinic_admin" not in membership.roles
    ):
        return
    if status == "active" and "clinic_admin" in roles:
        return
    count = session.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.tenant_id == membership.tenant_id,
            Membership.status == "active",
            Membership.roles.any("clinic_admin"),
        )
    )
    if count == 1:
        raise DomainError(
            409, "last_clinic_admin", "The last active clinic administrator must remain."
        )


def read_identity(principal, session):
    subject = current_subject(session, principal)
    memberships = session.scalars(
        select(Membership)
        .where(
            Membership.subject_id == subject.subject_id,
            Membership.status == "active",
        )
        .order_by(Membership.created_at, Membership.membership_id)
    ).all()
    return IdentityRead(
        subject_id=subject.subject_id,
        cognito_sub=subject.cognito_sub,
        display_name=subject.display_name,
        global_roles=subject.global_roles,
        memberships=[MembershipRead.model_validate(item) for item in memberships],
    )
