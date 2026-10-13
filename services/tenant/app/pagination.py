import time
from uuid import UUID

import jwt
from telelink_common.errors import DomainError


def cursor_key(settings):
    if settings.cursor_secret is None:
        raise DomainError(503, "unavailable", "Pagination is not configured.")
    return settings.cursor_secret.get_secret_value()


def encode_cursor(settings, clinic):
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "telelink-tenant-cursor",
            "aud": "public-active-clinics",
            "order": "name,tenant_id",
            "name": clinic.name,
            "id": str(clinic.tenant_id),
            "iat": now,
            "exp": now + 900,
        },
        cursor_key(settings),
        algorithm="HS256",
    )


def decode_cursor(settings, cursor):
    key = cursor_key(settings)
    try:
        claims = jwt.decode(
            cursor,
            key,
            algorithms=["HS256"],
            issuer="telelink-tenant-cursor",
            audience="public-active-clinics",
            options={"require": ["exp", "iat", "order", "name", "id"]},
        )
        if claims["order"] != "name,tenant_id" or not isinstance(claims["name"], str):
            raise ValueError("Invalid cursor")
        return claims["name"], UUID(claims["id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise DomainError(
            422,
            "validation_error",
            "Invalid clinic cursor.",
            [{"field": "query.cursor", "code": "invalid_cursor", "message": "Reset pagination."}],
        ) from None
