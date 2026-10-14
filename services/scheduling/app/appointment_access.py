"""C02 metadata access expressed at query source and rechecked on each request."""

import hashlib
import json

from sqlalchemy import or_, true
from telelink_common.access import has_tenant_role
from telelink_common.errors import DomainError

from app.models import Appointment


def appointment_scope(identity):
    if "platform_admin" in identity.global_roles:
        return true()
    conditions = []
    if "patient" in identity.global_roles:
        conditions.append(Appointment.patient_id == identity.subject_id)
    for membership in identity.memberships:
        if membership.status != "active":
            continue
        if "clinic_admin" in membership.roles:
            conditions.append(Appointment.tenant_id == membership.tenant_id)
        elif "doctor" in membership.roles:
            conditions.append(
                (Appointment.tenant_id == membership.tenant_id)
                & (Appointment.doctor_id == identity.subject_id)
            )
    if not conditions:
        raise DomainError(403, "forbidden", "Appointment access is not permitted.")
    return or_(*conditions)


def can_access(identity, appointment, *, cancel=False):
    own = "patient" in identity.global_roles and appointment.patient_id == identity.subject_id
    membership = next(
        (item for item in identity.memberships if item.tenant_id == appointment.tenant_id), None
    )
    admin = has_tenant_role(membership, appointment.tenant_id, "clinic_admin")
    if cancel:
        return own or admin
    assigned = appointment.doctor_id == identity.subject_id and has_tenant_role(
        membership, appointment.tenant_id, "doctor"
    )
    return own or admin or assigned or "platform_admin" in identity.global_roles


def authorization_scope(identity):
    # Bind cursors to current roles, not just a once-authorized subject ID.
    permissions = [
        str(identity.subject_id),
        sorted(identity.global_roles),
        sorted(
            [str(item.tenant_id), sorted(item.roles)]
            for item in identity.memberships
            if item.status == "active"
        ),
    ]
    fingerprint = hashlib.sha256(
        json.dumps(permissions, separators=(",", ":")).encode()
    ).hexdigest()
    return [str(identity.subject_id), fingerprint]


def require_collection_tenant(identity, tenant_id):
    if tenant_id is None or {"patient", "platform_admin"}.intersection(identity.global_roles):
        return
    if not any(
        item.tenant_id == tenant_id
        and item.status == "active"
        and {"doctor", "clinic_admin"}.intersection(item.roles)
        for item in identity.memberships
    ):
        raise DomainError(404, "not_found", "Resource not found.")
