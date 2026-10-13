"""Identity-specific authentication of trusted scheduling resource context."""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

scheduling_bearer = HTTPBearer(auto_error=False, scheme_name="SchedulingServiceJWT")


def require_scheduling_service(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(scheduling_bearer)],
) -> frozenset[str]:
    """Only scheduling may supply the appointment resource context in C02."""
    if credentials is None:
        raise HTTPException(
            401, "Service bearer credential required", headers={"WWW-Authenticate": "Bearer"}
        )
    settings = request.app.state.settings
    if settings.scheduling_secret is None:
        raise HTTPException(503, "Service authentication is not configured")
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.scheduling_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer="telelink-service:scheduling",
            audience="telelink-identity-access",
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
        if claims["sub"] != "scheduling":
            raise jwt.InvalidTokenError("invalid service")
        if (
            type(claims["exp"]) is not int
            or type(claims["iat"]) is not int
            or not 0 < claims["exp"] - claims["iat"] <= 300
        ):
            raise jwt.InvalidTokenError("invalid service lifetime")
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(
            401, "Invalid or expired service credential", headers={"WWW-Authenticate": "Bearer"}
        ) from None
    return frozenset(settings.scheduling_actions.split())
