"""Signature-verified Cognito access tokens; identity is not tenant authorisation."""

from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from app.settings import Settings

bearer = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/auth", tags=["authentication"])


@dataclass(frozen=True)
class Principal:
    subject: str
    scopes: frozenset[str]


class TokenVerifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jwks = (
            PyJWKClient(settings.auth_jwks_url, lifespan=300, timeout=5)
            if settings.auth_jwks_url
            else None
        )

    def verify(self, token: str) -> Principal:
        if self.jwks is None:
            raise HTTPException(503, "Authentication is not configured")
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise jwt.InvalidTokenError("invalid signing header")
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                issuer=self.settings.auth_issuer,
                options={
                    "require": ["exp", "iat", "iss", "sub", "token_use", "client_id"],
                    "verify_aud": False,
                },
            )
            if (
                claims["token_use"] != "access"
                or claims["client_id"] != self.settings.auth_client_id
            ):
                raise jwt.InvalidTokenError("invalid token purpose or client")
            if not isinstance(claims["sub"], str) or not claims["sub"]:
                raise jwt.InvalidTokenError("invalid subject")
            scope = claims.get("scope", "")
            if not isinstance(scope, str):
                raise jwt.InvalidTokenError("invalid scope")
            scopes = frozenset(scope.split())
            if not set(self.settings.auth_required_scopes.split()).issubset(scopes):
                raise HTTPException(403, "Insufficient access token scope")
            return Principal(subject=claims["sub"], scopes=scopes)
        except PyJWKClientConnectionError:
            raise HTTPException(503, "Authentication keys unavailable") from None
        except (jwt.InvalidTokenError, PyJWKClientError, ValueError, TypeError, KeyError):
            raise HTTPException(
                401, "Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"}
            ) from None


def require_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    if credentials is None:
        raise HTTPException(
            401, "Bearer access token required", headers={"WWW-Authenticate": "Bearer"}
        )
    return request.app.state.token_verifier.verify(credentials.credentials)


@router.get("/session")
def session(principal: Annotated[Principal, Depends(require_principal)]):
    """Minimal integration probe; does not expose roles or grant tenant access."""
    return {"subject": principal.subject, "scopes": sorted(principal.scopes)}
