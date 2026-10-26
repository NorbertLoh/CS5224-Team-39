"""Cursor JWT mechanics only; resource scope, ordering and errors stay service-local."""

import time

import jwt

from telelink_common.errors import DomainError

CURSOR_LIFETIME_SECONDS = 900


def cursor_key(settings):
    if settings.cursor_secret is None:
        raise DomainError(503, "unavailable", "Pagination is not configured.")
    return settings.cursor_secret.get_secret_value()


def sign_cursor(claims: dict, key: str, *, issuer: str, audience: str) -> str:
    now = int(time.time())
    return jwt.encode(
        claims | {"iss": issuer, "aud": audience, "iat": now, "exp": now + CURSOR_LIFETIME_SECONDS},
        key,
        algorithm="HS256",
    )


def verify_cursor(
    cursor: str, key: str, *, issuer: str, audience: str, required: list[str]
) -> dict:
    # Do not translate JWT errors here: each resource retains its public error contract.
    return jwt.decode(
        cursor,
        key,
        algorithms=["HS256"],
        issuer=issuer,
        audience=audience,
        options={"require": ["exp", "iat", *required]},
    )
