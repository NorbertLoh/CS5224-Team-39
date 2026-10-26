from uuid import UUID

from sqlalchemy import false, or_
from telelink_common.access import has_tenant_role
from telelink_common.errors import DomainError

from app.models import Payment


def access_scope(identity, *, admin_only=False, conceal=False):
    platform = "platform_admin" in identity.global_roles
    patient = not admin_only and "patient" in identity.global_roles
    tenants = sorted(
        str(m.tenant_id)
        for m in identity.memberships
        if has_tenant_role(m, m.tenant_id, "clinic_admin")
    )
    if not (platform or patient or tenants):
        if conceal:
            raise DomainError(404, "not_found", "Resource not found.")
        raise DomainError(403, "forbidden", "This role is not permitted.")
    conditions = []
    if patient:
        conditions.append(Payment.patient_id == identity.subject_id)
    if tenants:
        conditions.append(Payment.tenant_id.in_([UUID(t) for t in tenants]))
    predicate = True if platform else or_(false(), *conditions)
    scope = {
        "subject": str(identity.subject_id),
        "platform": platform,
        "patient": patient,
        "tenants": tenants,
        "order": "created_at,payment_id:desc",
    }
    return predicate, scope
