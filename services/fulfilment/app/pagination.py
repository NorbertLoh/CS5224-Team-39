import time
from datetime import datetime
from uuid import UUID

import jwt
from telelink_common.errors import DomainError


def key(settings):
    if settings.cursor_secret is None:
        raise DomainError(503, "unavailable", "Pagination is not configured.")
    return settings.cursor_secret.get_secret_value()


def encode(settings, scope, value, resource_id):
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "telelink-fulfilment",
            "aud": "pagination",
            "scope": scope,
            "value": value.isoformat() if isinstance(value, datetime) else value,
            "id": str(resource_id),
            "iat": now,
            "exp": now + 900,
        },
        key(settings),
        algorithm="HS256",
    )


def decode(settings, scope, cursor, *, timestamp=False):
    secret = key(settings)
    try:
        claims = jwt.decode(
            cursor,
            secret,
            algorithms=["HS256"],
            issuer="telelink-fulfilment",
            audience="pagination",
            options={"require": ["iat", "exp", "scope", "value", "id"]},
        )
        if claims["scope"] != scope or not isinstance(claims["value"], str):
            raise ValueError("Wrong cursor scope")
        value = datetime.fromisoformat(claims["value"]) if timestamp else claims["value"]
        if timestamp and value.tzinfo is None:
            raise ValueError("Timezone required")
        return value, UUID(claims["id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise DomainError(422, "validation_error", "Invalid pagination cursor.") from None
