"""Short-lived payment cursors, bound to the current caller, access and filters."""

from datetime import datetime
from uuid import UUID

import jwt
from telelink_common.errors import DomainError
from telelink_common.pagination import cursor_key, sign_cursor, verify_cursor


def encode_cursor(settings, scope, payment):
    return sign_cursor(
        {
            "scope": scope,
            "created_at": payment.created_at.isoformat(),
            "id": str(payment.payment_id),
        },
        cursor_key(settings),
        issuer="telelink-billing-cursor",
        audience="payments",
    )


def decode_cursor(settings, scope, cursor):
    key = cursor_key(settings)
    try:
        claims = verify_cursor(
            cursor,
            key,
            issuer="telelink-billing-cursor",
            audience="payments",
            required=["scope", "created_at", "id"],
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
