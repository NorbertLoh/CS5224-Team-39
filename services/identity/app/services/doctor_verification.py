"""Verification is independent of clinic assignment and never reactivates it."""

from types import SimpleNamespace

from sqlalchemy import select
from telelink_common.errors import DomainError

from app.models import DoctorApplication


def approved_doctor(subject_column):
    return (
        select(DoctorApplication.subject_id)
        .where(
            DoctorApplication.subject_id == subject_column,
            DoctorApplication.status == "approved",
        )
        .exists()
    )


def effective_membership(session, membership):
    if membership is None:
        return None
    roles = list(membership.roles)
    if "doctor" in roles and not session.scalar(select(approved_doctor(membership.subject_id))):
        roles.remove("doctor")
    return SimpleNamespace(
        **{
            key: getattr(membership, key)
            for key in (
                "membership_id",
                "subject_id",
                "tenant_id",
                "status",
                "created_at",
                "updated_at",
            )
        },
        roles=roles,
    )


def platform_reviewer(session, principal):
    from app.services.identity import current_subject

    subject = current_subject(session, principal)
    if "platform_admin" not in subject.global_roles:
        raise DomainError(403, "forbidden", "Platform administrator access is required.")
    return subject
