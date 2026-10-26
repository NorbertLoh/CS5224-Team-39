from datetime import datetime
from uuid import UUID

import jwt
from telelink_common.errors import DomainError
from telelink_common.pagination import cursor_key, sign_cursor, verify_cursor


def encode_cursor(settings, scope, slot):
    return sign_cursor(
        {"scope": scope, "start": slot.starts_at.isoformat(), "id": str(slot.slot_id)},
        cursor_key(settings),
        issuer="telelink-scheduling-cursor",
        audience="public-slots",
    )


def decode_cursor(settings, scope, cursor):
    key = cursor_key(settings)
    try:
        claims = verify_cursor(
            cursor,
            key,
            issuer="telelink-scheduling-cursor",
            audience="public-slots",
            required=["scope", "start", "id"],
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
    return sign_cursor(
        {
            "scope": scope,
            "start": appointment.starts_at.isoformat(),
            "id": str(appointment.appointment_id),
        },
        cursor_key(settings),
        issuer="telelink-scheduling-cursor",
        audience="appointments",
    )


def decode_appointment_cursor(settings, scope, cursor):
    key = cursor_key(settings)
    try:
        claims = verify_cursor(
            cursor,
            key,
            issuer="telelink-scheduling-cursor",
            audience="appointments",
            required=["scope", "start", "id"],
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
