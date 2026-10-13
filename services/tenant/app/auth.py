from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False, scheme_name="SchedulingServiceJWT")


def require_booking_service(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    if credentials is None:
        raise HTTPException(
            401, "Service credential required", headers={"WWW-Authenticate": "Bearer"}
        )
    secret = request.app.state.settings.scheduling_secret
    if secret is None:
        raise HTTPException(503, "Booking service authentication is not configured")
    try:
        claims = jwt.decode(
            credentials.credentials,
            secret.get_secret_value(),
            algorithms=["HS256"],
            issuer="telelink-service:scheduling",
            audience="telelink-tenant-booking",
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
        if (
            claims["sub"] != "scheduling"
            or type(claims["exp"]) is not int
            or type(claims["iat"]) is not int
            or not 0 < claims["exp"] - claims["iat"] <= 300
        ):
            raise jwt.InvalidTokenError("Invalid service token")
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(
            401, "Invalid service credential", headers={"WWW-Authenticate": "Bearer"}
        ) from None
