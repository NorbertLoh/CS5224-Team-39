import time
from datetime import datetime
from uuid import UUID

import jwt
from telelink_common.errors import DomainError


def cursor_key(settings):
    if settings.cursor_secret is None:
        raise DomainError(503, "unavailable", "Pagination is not configured.")
    return settings.cursor_secret.get_secret_value()


def encode_cursor(settings, scope, slot):
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "telelink-scheduling-cursor",
            "aud": "public-slots",
            "scope": scope,
            "start": slot.starts_at.isoformat(),
            "id": str(slot.slot_id),
            "iat": now,
            "exp": now + 900,
        },
        cursor_key(settings),
        algorithm="HS256",
    )


def decode_cursor(settings, scope, cursor):
    key = cursor_key(settings)
    try:
        claims = jwt.decode(
            cursor,
            key,
            algorithms=["HS256"],
            issuer="telelink-scheduling-cursor",
            audience="public-slots",
            options={"require": ["exp", "iat", "scope", "start", "id"]},
        )
        start = datetime.fromisoformat(claims["start"])
        if claims["scope"] != scope or start.tzinfo is None:
            raise ValueError("Invalid cursor scope")
        return start, UUID(claims["id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise DomainError(
            422,
            "validation_error",
            "Invalid slot cursor.",
            [{"field": "query.cursor", "code": "invalid_cursor", "message": "Reset pagination."}],
        ) from None


def encode_appointment_cursor(settings, scope, appointment):
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "telelink-scheduling-cursor",
            "aud": "appointments",
            "scope": scope,
            "start": appointment.starts_at.isoformat(),
            "id": str(appointment.appointment_id),
            "iat": now,
            "exp": now + 900,
        },
        cursor_key(settings),
        algorithm="HS256",
    )


def decode_appointment_cursor(settings, scope, cursor):
    key = cursor_key(settings)
    try:
        claims = jwt.decode(
            cursor,
            key,
            algorithms=["HS256"],
            issuer="telelink-scheduling-cursor",
            audience="appointments",
            options={"require": ["exp", "iat", "scope", "start", "id"]},
        )
        start = datetime.fromisoformat(claims["start"])
        if claims["scope"] != scope or start.tzinfo is None:
            raise ValueError("Wrong cursor scope")
        return start, UUID(claims["id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise DomainError(
            422,
            "validation_error",
            "Invalid appointment cursor.",
            [{"field": "query.cursor", "code": "invalid_cursor", "message": "Reset pagination."}],
        ) from None
