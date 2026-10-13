"""Template authentication probe using the shared Cognito verifier."""

from typing import Annotated

from fastapi import APIRouter, Depends
from telelink_common.auth import Principal, require_principal

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/session")
def session(principal: Annotated[Principal, Depends(require_principal)]):
    return {"subject": principal.subject, "scopes": sorted(principal.scopes)}
