import hashlib
import json

from sqlalchemy import or_, true
from telelink_common.errors import DomainError

from app.models import Order


def require_clinic(identity, tenant_id, roles):
    if not any(
        membership.tenant_id == tenant_id
        and membership.status == "active"
        and set(roles).intersection(membership.roles)
        for membership in identity.memberships
    ):
        raise DomainError(404, "not_found", "Resource not found.")


def order_scope(identity):
    if "platform_admin" in identity.global_roles:
        return true()
    conditions = []
    if "patient" in identity.global_roles:
        conditions.append(Order.patient_id == identity.subject_id)
    conditions.extend(
        Order.tenant_id == membership.tenant_id
        for membership in identity.memberships
        if membership.status == "active" and "clinic_admin" in membership.roles
    )
    if not conditions:
        raise DomainError(403, "forbidden", "Order access is not permitted.")
    return or_(*conditions)


def permission_fingerprint(identity):
    permissions = [
        str(identity.subject_id),
        sorted(identity.global_roles),
        sorted(
            [str(item.tenant_id), sorted(item.roles)]
            for item in identity.memberships
            if item.status == "active"
        ),
    ]
    return hashlib.sha256(json.dumps(permissions, separators=(",", ":")).encode()).hexdigest()


def can_read_items(identity, order):
    return ("patient" in identity.global_roles and identity.subject_id == order.patient_id) or any(
        item.tenant_id == order.tenant_id
        and item.status == "active"
        and "clinic_admin" in item.roles
        for item in identity.memberships
    )
