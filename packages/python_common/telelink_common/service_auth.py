"""Short-lived, purpose-specific service credentials; separate from Cognito users."""

from datetime import datetime, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False, scheme_name="ServiceJWT")


def service_token(secret, caller: str, audience: str) -> str:
    if secret is None:
        raise RuntimeError("Service authentication is not configured")
    now = int(datetime.now(timezone.utc).timestamp())
    return jwt.encode(
        {
            "iss": "telelink-service:" + caller,
            "sub": caller,
            "aud": audience,
            "iat": now,
            "exp": now + 60,
        },
        secret.get_secret_value(),
        algorithm="HS256",
    )


def require_service(caller: str, audience: str, secret_field: str):
    def dependency(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        if credentials is None:
            raise HTTPException(
                401, "Service credential required", headers={"WWW-Authenticate": "Bearer"}
            )
        secret = getattr(request.app.state.settings, secret_field)
        if secret is None:
            raise HTTPException(503, "Service authentication is not configured")
        try:
            claims = jwt.decode(
                credentials.credentials,
                secret.get_secret_value(),
                algorithms=["HS256"],
                issuer="telelink-service:" + caller,
                audience=audience,
                options={"require": ["exp", "iat", "sub", "iss", "aud"], "strict_aud": True},
            )
            if (
                claims["sub"] != caller
                or type(claims["exp"]) is not int
                or type(claims["iat"]) is not int
                or not 0 < claims["exp"] - claims["iat"] <= 300
            ):
                raise jwt.InvalidTokenError("Invalid service credential")
        except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
            raise HTTPException(
                401, "Invalid service credential", headers={"WWW-Authenticate": "Bearer"}
            ) from None
        return caller

    return dependency
