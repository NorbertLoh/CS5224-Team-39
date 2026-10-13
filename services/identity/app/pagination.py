"""Signed expiring C01 cursors bound to caller, tenant, filter and order."""

import time
from datetime import datetime, timezone
from uuid import UUID

import jwt
from telelink_common.errors import DomainError


def cursor_error():
    return DomainError(
        422,
        "validation_error",
        "Invalid membership cursor.",
        [
            {
                "field": "query.cursor",
                "code": "invalid_cursor",
                "message": "Reset pagination and try again.",
            }
        ],
    )


def cursor_key(settings):
    if settings.cursor_secret is None:
        raise DomainError(503, "unavailable", "Pagination is not configured.")
    return settings.cursor_secret.get_secret_value()


def encode_cursor(settings, subject_id, tenant_id, status, membership):
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "telelink-identity-cursor",
            "aud": "memberships",
            "sub": str(subject_id),
            "tenant": str(tenant_id),
            "status": status or "all",
            "order": "created_at,membership_id",
            "created_at": membership.created_at.isoformat(),
            "id": str(membership.membership_id),
            "iat": now,
            "exp": now + 900,
        },
        cursor_key(settings),
        algorithm="HS256",
    )


def decode_cursor(settings, cursor, subject_id, tenant_id, status):
    key = cursor_key(settings)
    try:
        claims = jwt.decode(
            cursor,
            key,
            algorithms=["HS256"],
            issuer="telelink-identity-cursor",
            audience="memberships",
            options={
                "require": ["exp", "iat", "sub", "tenant", "status", "order", "created_at", "id"]
            },
        )
        if (claims["sub"], claims["tenant"], claims["status"], claims["order"]) != (
            str(subject_id),
            str(tenant_id),
            status or "all",
            "created_at,membership_id",
        ):
            raise ValueError("mismatched cursor scope")
        created_at = datetime.fromisoformat(claims["created_at"])
        if created_at.tzinfo is None:
            raise ValueError("timezone missing")
        return created_at.astimezone(timezone.utc), UUID(claims["id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError, OverflowError):
        raise cursor_error() from None
