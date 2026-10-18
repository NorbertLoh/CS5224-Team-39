"""Short-lived payment cursors, bound to the current caller, access and filters."""

import time
from datetime import datetime
from uuid import UUID

import jwt
from telelink_common.errors import DomainError


def cursor_key(settings):
    if settings.cursor_secret is None:
        raise DomainError(503, "unavailable", "Pagination is not configured.")
    return settings.cursor_secret.get_secret_value()


def encode_cursor(settings, scope, payment):
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "telelink-billing-cursor",
            "aud": "payments",
            "scope": scope,
            "created_at": payment.created_at.isoformat(),
            "id": str(payment.payment_id),
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
            issuer="telelink-billing-cursor",
            audience="payments",
            options={"require": ["exp", "iat", "scope", "created_at", "id"]},
        )
        created_at = datetime.fromisoformat(claims["created_at"])
        if claims["scope"] != scope or created_at.tzinfo is None:
            raise ValueError("Invalid cursor scope")
        return created_at, UUID(claims["id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise DomainError(
            422,
            "validation_error",
            "Invalid payment cursor.",
            [{"field": "query.cursor", "code": "invalid_cursor", "message": "Reset pagination."}],
        ) from None
