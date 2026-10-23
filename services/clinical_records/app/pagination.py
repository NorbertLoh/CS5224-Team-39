import time
from datetime import datetime
from uuid import UUID

import jwt
from telelink_common.errors import DomainError


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


def key(settings):
    if settings.cursor_secret is None:
        raise DomainError(503, "unavailable", "Pagination is not configured.")
    return settings.cursor_secret.get_secret_value()


def encode(settings, scope, row):
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "telelink-clinical-records",
            "aud": "prescriptions",
            "iat": now,
            "exp": now + 900,
            "scope": scope,
            "created": row.created_at.isoformat(),
            "id": str(row.prescription_id),
        },
        key(settings),
        algorithm="HS256",
    )


def decode(settings, scope, cursor):
    secret = key(settings)
    try:
        claims = jwt.decode(
            cursor,
            secret,
            algorithms=["HS256"],
            issuer="telelink-clinical-records",
            audience="prescriptions",
            options={"require": ["iat", "exp", "scope", "created", "id"]},
        )
        created = datetime.fromisoformat(claims["created"])
        if claims["scope"] != scope or created.tzinfo is None:
            raise ValueError()
        return created, UUID(claims["id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise DomainError(422, "validation_error", "Invalid prescription cursor.") from None
