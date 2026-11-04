from datetime import datetime
from uuid import UUID

import jwt
from telelink_common.errors import DomainError
from telelink_common.pagination import cursor_key as key
from telelink_common.pagination import sign_cursor, verify_cursor


def encode(settings, scope, value, resource_id):
    return sign_cursor(
        {
            "scope": scope,
            "value": value.isoformat() if isinstance(value, datetime) else value,
            "id": str(resource_id),
        },
        key(settings),
        issuer="telelink-fulfilment",
        audience="pagination",
    )


def decode(settings, scope, cursor, *, timestamp=False):
    secret = key(settings)
    try:
        claims = verify_cursor(
            cursor,
            secret,
            issuer="telelink-fulfilment",
            audience="pagination",
            required=["scope", "value", "id"],
        )
        if claims["scope"] != scope or not isinstance(claims["value"], str):
            raise ValueError("Wrong cursor scope")
        value = datetime.fromisoformat(claims["value"]) if timestamp else claims["value"]
        if timestamp and value.tzinfo is None:
            raise ValueError("Timezone required")
        return value, UUID(claims["id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise DomainError(422, "validation_error", "Invalid pagination cursor.") from None
