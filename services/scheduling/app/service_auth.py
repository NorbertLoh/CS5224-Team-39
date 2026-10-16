from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False, scheme_name="SchedulingActionJWT")
Credential = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def require_service(caller, audience, secret_field):
    def dependency(request: Request, credentials: Credential):
        if credentials is None:
            raise HTTPException(
                401, "Service credential required", headers={"WWW-Authenticate": "Bearer"}
            )
        secret = getattr(request.app.state.settings, secret_field)
        if secret is None:
            raise HTTPException(503, "Service action authentication is not configured")
        try:
            claims = jwt.decode(
                credentials.credentials,
                secret.get_secret_value(),
                algorithms=["HS256"],
                issuer="telelink-service:" + caller,
                audience=audience,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
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

    return dependency


require_consultation = require_service(
    "consultation", "telelink-scheduling-consultation", "consultation_secret"
)
require_operator = require_service(
    "scheduling-operator", "telelink-scheduling-operator", "operator_secret"
)
