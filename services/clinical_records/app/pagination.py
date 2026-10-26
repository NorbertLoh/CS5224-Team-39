from datetime import datetime
from uuid import UUID

import jwt
from telelink_common.errors import DomainError
from telelink_common.pagination import cursor_key as key
from telelink_common.pagination import sign_cursor, verify_cursor


def scope_for(identity, appointment_id):
    return [
        str(identity.subject_id),
        sorted(identity.global_roles),
        sorted(
            [str(m.tenant_id), sorted(m.roles)]
            for m in identity.memberships
            if m.status == "active"
        ),
        str(appointment_id) if appointment_id else None,
        "created_at,prescription_id:desc",
    ]


def encode(settings, scope, row):
    return sign_cursor(
        {"scope": scope, "created": row.created_at.isoformat(), "id": str(row.prescription_id)},
        key(settings),
        issuer="telelink-clinical-records",
        audience="prescriptions",
    )


def decode(settings, scope, cursor):
    secret = key(settings)
    try:
        claims = verify_cursor(
            cursor,
            secret,
            issuer="telelink-clinical-records",
            audience="prescriptions",
            required=["scope", "created", "id"],
        )
        created = datetime.fromisoformat(claims["created"])
        if claims["scope"] != scope or created.tzinfo is None:
            raise ValueError()
        return created, UUID(claims["id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise DomainError(422, "validation_error", "Invalid prescription cursor.") from None
