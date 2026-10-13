"""Service-local C02 routes; ingress strips /api/v1/identity."""

from hashlib import blake2b
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select, text, tuple_
from sqlalchemy.orm import Session

from app.auth import Principal, require_principal, require_scheduling_service
from app.database import find_subject, get_session
from app.errors import DomainError
from app.models import Membership, Subject
from app.pagination import cursor_key, decode_cursor, encode_cursor
from app.schemas import (
    AccessDecision,
    AccessRequest,
    ErrorEnvelope,
    IdentityRead,
    MembershipPage,
    MembershipRead,
    MembershipStatus,
    MembershipWrite,
)

router = APIRouter(
    tags=["identity"],
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 422, 500, 503)},
)
DB = Annotated[Session, Depends(get_session)]
User = Annotated[Principal, Depends(require_principal)]
Service = Annotated[frozenset[str], Depends(require_scheduling_service)]


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
    if "platform_admin" not in subject.global_roles and (
        membership is None or "clinic_admin" not in membership.roles
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


@router.get("/me", response_model=IdentityRead)
def me(principal: User, session: DB):
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


@router.get("/clinics/{tenant_id}/memberships", response_model=MembershipPage)
def memberships(
    tenant_id: UUID,
    request: Request,
    principal: User,
    session: DB,
    status: MembershipStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
):
    subject = authorize_admin(session, principal, tenant_id)
    request.app.state.clinic_directory.require_clinic(tenant_id)
    settings = request.app.state.settings
    cursor_key(settings)
    query = select(Membership).where(Membership.tenant_id == tenant_id)
    if status is not None:
        query = query.where(Membership.status == status)
    if cursor is not None:
        created_at, membership_id = decode_cursor(
            settings, cursor, subject.subject_id, tenant_id, status
        )
        query = query.where(
            tuple_(Membership.created_at, Membership.membership_id)
            > tuple_(created_at, membership_id)
        )
    rows = session.scalars(
        query.order_by(Membership.created_at, Membership.membership_id).limit(limit + 1)
    ).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = encode_cursor(settings, subject.subject_id, tenant_id, status, rows[-1])
    return MembershipPage(
        items=[MembershipRead.model_validate(row) for row in rows], next_cursor=next_cursor
    )


@router.put(
    "/clinics/{tenant_id}/memberships/{subject_id}",
    response_model=MembershipRead,
    responses={201: {"model": MembershipRead}},
)
def put_membership(
    tenant_id: UUID,
    subject_id: UUID,
    body: MembershipWrite,
    request: Request,
    response: Response,
    principal: User,
    session: DB,
):
    # Pre-authorize before locking so unrelated callers cannot hold tenant locks.
    authorize_admin(session, principal, tenant_id)
    request.app.state.clinic_directory.require_clinic(tenant_id)
    lock_tenant(session, tenant_id)
    # Re-read current membership after serialization, including self-revocation races.
    session.expire_all()
    authorize_admin(session, principal, tenant_id)
    if session.get(Subject, subject_id) is None:
        raise DomainError(404, "not_found", "Resource not found.")
    membership = session.scalar(
        select(Membership).where(
            Membership.subject_id == subject_id,
            Membership.tenant_id == tenant_id,
        )
    )
    guard_last_admin(session, membership, body.roles, "active")
    if membership is None:
        membership = Membership(subject_id=subject_id, tenant_id=tenant_id, roles=body.roles)
        session.add(membership)
        response.status_code = 201
    else:
        membership.roles = body.roles
        membership.status = "active"
    session.flush()
    result = MembershipRead.model_validate(membership)
    session.commit()
    return result


@router.delete("/clinics/{tenant_id}/memberships/{subject_id}", status_code=204)
def revoke_membership(
    tenant_id: UUID, subject_id: UUID, request: Request, principal: User, session: DB
):
    authorize_admin(session, principal, tenant_id)
    request.app.state.clinic_directory.require_clinic(tenant_id)
    lock_tenant(session, tenant_id)
    session.expire_all()
    authorize_admin(session, principal, tenant_id)
    membership = session.scalar(
        select(Membership).where(
            Membership.subject_id == subject_id,
            Membership.tenant_id == tenant_id,
        )
    )
    guard_last_admin(session, membership, [], "revoked")
    if membership is not None and membership.status != "revoked":
        membership.status = "revoked"
    session.commit()
    return Response(status_code=204)


@router.post("/access-decisions", response_model=AccessDecision, tags=["internal"])
def access_decision(body: AccessRequest, actions: Service, session: DB):
    if body.action not in actions:
        raise DomainError(403, "forbidden", "Service is not allowed to request this action.")
    subject = session.get(Subject, body.subject_id)
    if subject is None:
        return AccessDecision(allowed=False, reason="not_authorized")
    membership = active_membership(session, subject.subject_id, body.tenant_id)
    roles = set(membership.roles) if membership is not None else set()
    own = subject.subject_id == body.resource.patient_id and "patient" in subject.global_roles
    assigned = subject.subject_id == body.resource.doctor_id and "doctor" in roles
    admin = "clinic_admin" in roles
    if own and body.action in {"appointment.read", "appointment.cancel", "clinical.read"}:
        return AccessDecision(allowed=True, reason="own_appointment")
    if assigned and body.action in {"appointment.read", "clinical.read", "clinical.write"}:
        return AccessDecision(allowed=True, reason="assigned_doctor")
    if admin and body.action in {"appointment.read", "appointment.cancel", "medicine.ready"}:
        return AccessDecision(allowed=True, reason="clinic_admin")
    if "platform_admin" in subject.global_roles and body.action == "appointment.read":
        return AccessDecision(allowed=True, reason="platform_admin")
    return AccessDecision(allowed=False, reason="not_authorized")
