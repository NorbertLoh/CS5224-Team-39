from fastapi import APIRouter
from telelink_common.access import has_global_role, has_tenant_role
from telelink_common.errors import DomainError, ErrorEnvelope

from app.api.dependencies import DB, Service, User
from app.models import Subject
from app.schemas import (
    AccessDecision,
    AccessRequest,
    IdentityRead,
)
from app.services.identity import (
    active_membership,
    read_identity,
)

router = APIRouter(
    tags=["identity"],
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 422, 500, 503)},
)


@router.get("/me", response_model=IdentityRead)
def me(principal: User, session: DB):
    return read_identity(principal, session)


@router.post("/access-decisions", response_model=AccessDecision, tags=["internal"])
def access_decision(body: AccessRequest, actions: Service, session: DB):
    if body.action not in actions:
        raise DomainError(403, "forbidden", "Service is not allowed to request this action.")
    subject = session.get(Subject, body.subject_id)
    if subject is None:
        return AccessDecision(allowed=False, reason="not_authorized")
    membership = active_membership(session, subject.subject_id, body.tenant_id)
    own = subject.subject_id == body.resource.patient_id and has_global_role(
        subject.global_roles, "patient"
    )
    assigned = subject.subject_id == body.resource.doctor_id and has_tenant_role(
        membership, body.tenant_id, "doctor"
    )
    admin = has_tenant_role(membership, body.tenant_id, "clinic_admin")
    if own and body.action in {
        "appointment.read",
        "appointment.cancel",
        "clinical.read",
        "consultation.join",
    }:
        return AccessDecision(allowed=True, reason="own_appointment")
    if assigned and body.action in {
        "appointment.read",
        "clinical.read",
        "clinical.write",
        "consultation.join",
    }:
        return AccessDecision(allowed=True, reason="assigned_doctor")
    if admin and body.action in {"appointment.read", "appointment.cancel", "medicine.ready"}:
        return AccessDecision(allowed=True, reason="clinic_admin")
    if (
        has_global_role(subject.global_roles, "platform_admin")
        and body.action == "appointment.read"
    ):
        return AccessDecision(allowed=True, reason="platform_admin")
    return AccessDecision(allowed=False, reason="not_authorized")
