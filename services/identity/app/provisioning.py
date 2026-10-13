"""A08 boundary: tenant may provision only a clinic creator's admin membership."""

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from telelink_common.errors import DomainError, ErrorEnvelope

from app.api import DB, lock_tenant
from app.models import Membership, Subject
from app.schemas import MembershipRead

bearer = HTTPBearer(auto_error=False, scheme_name="TenantServiceJWT")
router = APIRouter(
    tags=["internal"],
    responses={status: {"model": ErrorEnvelope} for status in (401, 404, 409, 422, 503)},
)


def require_tenant_service(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    if credentials is None:
        raise HTTPException(
            401, "Service credential required", headers={"WWW-Authenticate": "Bearer"}
        )
    secret = request.app.state.settings.tenant_secret
    if secret is None:
        raise HTTPException(503, "Tenant service authentication is not configured")
    try:
        claims = jwt.decode(
            credentials.credentials,
            secret.get_secret_value(),
            algorithms=["HS256"],
            issuer="telelink-service:tenant",
            audience="telelink-identity-provisioning",
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
        if (
            claims["sub"] != "tenant"
            or type(claims["exp"]) is not int
            or type(claims["iat"]) is not int
            or not 0 < claims["exp"] - claims["iat"] <= 300
        ):
            raise jwt.InvalidTokenError("Invalid service token")
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(
            401, "Invalid service credential", headers={"WWW-Authenticate": "Bearer"}
        ) from None


class CreatorMembership(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    subject_id: UUID


@router.put(
    "/internal/clinic-creators",
    response_model=MembershipRead,
    dependencies=[Depends(require_tenant_service)],
)
def provision_creator(body: CreatorMembership, session: DB):
    lock_tenant(session, body.tenant_id)
    if session.get(Subject, body.subject_id) is None:
        raise DomainError(404, "not_found", "Resource not found.")
    membership = session.scalar(
        select(Membership).where(
            Membership.tenant_id == body.tenant_id,
            Membership.subject_id == body.subject_id,
        )
    )
    if membership is None:
        # The authenticated tenant service owns clinic existence and creator identity.
        membership = Membership(
            tenant_id=body.tenant_id, subject_id=body.subject_id, roles=["clinic_admin"]
        )
        session.add(membership)
    elif membership.status != "active" or "clinic_admin" not in membership.roles:
        # A retry cannot restore a subsequently revoked/demoted administrator.
        raise DomainError(409, "conflict", "Creator membership no longer permits provisioning.")
    session.flush()
    result = MembershipRead.model_validate(membership)
    session.commit()
    return result
