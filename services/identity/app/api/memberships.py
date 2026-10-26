"""Service-local C02 routes; ingress strips /api/v1/identity."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select, tuple_
from telelink_common.errors import DomainError, ErrorEnvelope

from app.api.dependencies import DB, User
from app.models import Membership, Subject
from app.pagination import cursor_key, decode_cursor, encode_cursor
from app.schemas import (
    MembershipByEmailWrite,
    MembershipPage,
    MembershipStatus,
    MembershipWrite,
    StaffMembershipRead,
)
from app.services.identity import (
    authorize_admin,
    guard_last_admin,
    lock_tenant,
)

router = APIRouter(
    tags=["identity"],
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 422, 500, 503)},
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
    request.app.state.clinic_directory.require_clinic(tenant_id, request.state.request_id)
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
        items=[StaffMembershipRead.model_validate(row) for row in rows], next_cursor=next_cursor
    )


@router.put(
    "/clinics/{tenant_id}/memberships/{subject_id}",
    response_model=StaffMembershipRead,
    responses={201: {"model": StaffMembershipRead}},
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
    request.app.state.clinic_directory.require_clinic(tenant_id, request.state.request_id)
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
    result = StaffMembershipRead.model_validate(membership)
    session.commit()
    return result


@router.post(
    "/clinics/{tenant_id}/memberships",
    response_model=StaffMembershipRead,
    responses={201: {"model": StaffMembershipRead}},
)
def assign_by_email(
    tenant_id: UUID,
    body: MembershipByEmailWrite,
    request: Request,
    response: Response,
    principal: User,
    session: DB,
):
    # Resolve accounts only after clinic authorization, without a public directory.
    authorize_admin(session, principal, tenant_id)
    request.app.state.clinic_directory.require_clinic(tenant_id, request.state.request_id)
    subject = session.scalar(select(Subject).where(Subject.email == body.email))
    if subject is None:
        raise DomainError(404, "not_found", "Resource not found.")
    return put_membership(
        tenant_id,
        subject.subject_id,
        MembershipWrite(roles=body.roles),
        request,
        response,
        principal,
        session,
    )


@router.delete("/clinics/{tenant_id}/memberships/{subject_id}", status_code=204)
def revoke_membership(
    tenant_id: UUID, subject_id: UUID, request: Request, principal: User, session: DB
):
    authorize_admin(session, principal, tenant_id)
    request.app.state.clinic_directory.require_clinic(tenant_id, request.state.request_id)
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
