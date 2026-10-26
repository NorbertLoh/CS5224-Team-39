from datetime import datetime
from uuid import UUID

import jwt
from telelink_common.errors import DomainError
from telelink_common.pagination import cursor_key, sign_cursor, verify_cursor


def encode_cursor(settings, clinic):
    return sign_cursor(
        {"order": "name,tenant_id", "name": clinic.name, "id": str(clinic.tenant_id)},
        cursor_key(settings),
        issuer="telelink-tenant-cursor",
        audience="public-active-clinics",
    )


def decode_cursor(settings, cursor):
    key = cursor_key(settings)
    try:
        claims = verify_cursor(
            cursor,
            key,
            issuer="telelink-tenant-cursor",
            audience="public-active-clinics",
            required=["order", "name", "id"],
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


def encode_admin_cursor(settings, subject_id, status, clinic):
    return sign_cursor(
        {
            "sub": str(subject_id),
            "status": status,
            "order": "created_at,tenant_id",
            "created_at": clinic.created_at.isoformat(),
            "id": str(clinic.tenant_id),
        },
        cursor_key(settings),
        issuer="telelink-tenant-cursor",
        audience="admin-clinics",
    )


def decode_admin_cursor(settings, cursor, subject_id, status):
    key = cursor_key(settings)
    try:
        claims = verify_cursor(
            cursor,
            key,
            issuer="telelink-tenant-cursor",
            audience="admin-clinics",
            required=["sub", "order", "created_at", "id"],
        )
        # JWT's required-claim check rejects null; null means the unfiltered list.
        if "status" not in claims:
            raise ValueError("Missing cursor scope")
        if (claims["sub"], claims["status"], claims["order"]) != (
            str(subject_id),
            status,
            "created_at,tenant_id",
        ):
            raise ValueError("Mismatched cursor scope")
        created_at = datetime.fromisoformat(claims["created_at"])
        if created_at.tzinfo is None:
            raise ValueError("Missing cursor timezone")
        return created_at, UUID(claims["id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise DomainError(
            422,
            "validation_error",
            "Invalid admin clinic cursor.",
            [{"field": "query.cursor", "code": "invalid_cursor", "message": "Reset pagination."}],
        ) from None
