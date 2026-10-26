"""Platform clinic changes with an audit event in the same transaction."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import select, tuple_
from telelink_common.errors import DomainError, ErrorEnvelope

from app.api.dependencies import DB, PlatformAdmin
from app.models import AuditEvent, Clinic
from app.pagination import cursor_key, decode_admin_cursor, encode_admin_cursor
from app.schemas import (
    ClinicAdmin,
    ClinicAdminPage,
    ClinicReview,
    ClinicStatus,
    CommissionWrite,
    profile,
)

router = APIRouter(
    tags=["platform administration"],
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 422, 502, 503)},
)


def lock_clinic(session, tenant_id):
    # Serialize review/commission changes so retries see the last committed state.
    clinic = session.scalar(select(Clinic).where(Clinic.tenant_id == tenant_id).with_for_update())
    if clinic is None:
        raise DomainError(404, "not_found", "Resource not found.")
    return clinic


def record_audit(session, clinic, actor, action, previous, new, reason=None):
    session.add(
        AuditEvent(
            tenant_id=clinic.tenant_id,
            actor_subject_id=actor.subject_id,
            action=action,
            previous_values=previous,
            new_values=new,
            reason=reason,
        )
    )


@router.get("/admin/clinics", response_model=ClinicAdminPage)
def clinics(
    request: Request,
    identity: PlatformAdmin,
    session: DB,
    status: ClinicStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
):
    settings = request.app.state.settings
    cursor_key(settings)
    query = select(Clinic)
    if status is not None:
        query = query.where(Clinic.status == status)
    if cursor is not None:
        created_at, tenant_id = decode_admin_cursor(settings, cursor, identity.subject_id, status)
        query = query.where(
            tuple_(Clinic.created_at, Clinic.tenant_id) > tuple_(created_at, tenant_id)
        )
    rows = session.scalars(
        query.order_by(Clinic.created_at, Clinic.tenant_id).limit(limit + 1)
    ).all()
    next_cursor = (
        encode_admin_cursor(settings, identity.subject_id, status, rows[limit - 1])
        if len(rows) > limit
        else None
    )
    return ClinicAdminPage(
        items=[profile(row, admin=True) for row in rows[:limit]], next_cursor=next_cursor
    )


@router.post("/clinics/{tenant_id}/review", response_model=ClinicAdmin)
def review(tenant_id: UUID, body: ClinicReview, identity: PlatformAdmin, session: DB):
    clinic = lock_clinic(session, tenant_id)
    target = {"approve": "active", "reject": "rejected", "suspend": "suspended"}[body.decision]
    if clinic.status == target:
        return profile(clinic, admin=True)
    allowed = {
        "approve": {"pending_review", "rejected", "suspended"},
        "reject": {"pending_review"},
        "suspend": {"active"},
    }
    if clinic.status not in allowed[body.decision]:
        raise DomainError(
            409, "invalid_clinic_transition", "Clinic review transition is not allowed."
        )
    previous = {"status": clinic.status, "review_reason": clinic.review_reason}
    clinic.status = target
    clinic.review_reason = body.reason
    record_audit(
        session,
        clinic,
        identity,
        {"approve": "clinic.approved", "reject": "clinic.rejected", "suspend": "clinic.suspended"}[
            body.decision
        ],
        previous,
        {"status": target, "review_reason": body.reason},
        body.reason,
    )
    session.flush()
    result = profile(clinic, admin=True)
    session.commit()
    return result


@router.put("/clinics/{tenant_id}/commission", response_model=ClinicAdmin)
def commission(tenant_id: UUID, body: CommissionWrite, identity: PlatformAdmin, session: DB):
    clinic = lock_clinic(session, tenant_id)
    if clinic.commission_bps == body.commission_bps:
        return profile(clinic, admin=True)
    previous = {"commission_bps": clinic.commission_bps}
    clinic.commission_bps = body.commission_bps
    record_audit(
        session,
        clinic,
        identity,
        "clinic.commission_changed",
        previous,
        {"commission_bps": body.commission_bps},
    )
    session.flush()
    result = profile(clinic, admin=True)
    session.commit()
    return result
