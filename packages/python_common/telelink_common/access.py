"""Current identity API lookup and reusable tenant/global role dependencies."""

from collections.abc import Collection
from datetime import datetime
from typing import Annotated, Literal, Protocol
from uuid import UUID

import httpx
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from telelink_common.auth import Principal, bearer, require_principal
from telelink_common.errors import DomainError
from telelink_common.settings import ServiceSettings

ClinicRole = Literal["doctor", "clinic_admin"]
GlobalRole = Literal["patient", "platform_admin"]


class MembershipLike(Protocol):
    tenant_id: UUID
    roles: Collection[str]
    status: str


def has_global_role(global_roles: Collection[str], role: GlobalRole) -> bool:
    return role in global_roles


def has_tenant_role(
    membership: MembershipLike | None,
    tenant_id: UUID,
    role: ClinicRole,
    *,
    global_roles: Collection[str] = (),
    allow_platform_admin: bool = False,
) -> bool:
    if allow_platform_admin and has_global_role(global_roles, "platform_admin"):
        return True
    return (
        membership is not None
        and membership.tenant_id == tenant_id
        and membership.status == "active"
        and role in membership.roles
    )


class ClinicMembership(BaseModel):
    model_config = ConfigDict(frozen=True)
    membership_id: UUID
    subject_id: UUID
    tenant_id: UUID
    roles: list[ClinicRole]
    status: Literal["active", "revoked"]
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_membership(self):
        if not self.roles or len(self.roles) != len(set(self.roles)):
            raise ValueError("invalid role set")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("membership instants require timezones")
        return self


class CurrentIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)
    subject_id: UUID
    cognito_sub: str
    display_name: str
    global_roles: list[GlobalRole]
    memberships: list[ClinicMembership]

    @model_validator(mode="after")
    def validate_identity(self):
        if len(self.global_roles) != len(set(self.global_roles)):
            raise ValueError("duplicate global roles")
        tenants = [membership.tenant_id for membership in self.memberships]
        if len(tenants) != len(set(tenants)) or any(
            membership.subject_id != self.subject_id for membership in self.memberships
        ):
            raise ValueError("invalid membership ownership")
        return self


class IdentityClient:
    def __init__(self, settings: ServiceSettings, *, transport=None):
        self.client = None
        if settings.identity_url is not None:
            self.client = httpx.Client(
                base_url=settings.identity_url + "/",
                timeout=settings.identity_timeout_seconds,
                follow_redirects=False,
                trust_env=False,
                transport=transport,
            )

    def close(self):
        if self.client is not None:
            self.client.close()

    def current_identity(
        self, access_token: str, expected_sub: str, request_id: str
    ) -> CurrentIdentity:
        if self.client is None:
            raise DomainError(503, "unavailable", "Identity lookup is not configured.")
        try:
            response = self.client.get(
                "me",
                headers={
                    "Authorization": "Bearer " + access_token,
                    "X-Request-ID": request_id,
                },
            )
        except httpx.RequestError:
            raise DomainError(503, "unavailable", "Identity service is unavailable.") from None
        if response.status_code == 401:
            # Preserve authentication failure without reflecting upstream payloads.
            error = DomainError(401, "unauthenticated", "Invalid or expired access token.")
            error.headers = {"WWW-Authenticate": "Bearer"}
            raise error
        if response.status_code == 403:
            raise DomainError(403, "forbidden", "Identity access is not permitted.")
        if response.status_code >= 500:
            raise DomainError(503, "unavailable", "Identity service is unavailable.")
        if response.status_code != 200:
            raise DomainError(
                502, "upstream_error", "Identity service returned an invalid response."
            )
        try:
            identity = CurrentIdentity.model_validate(response.json())
            if identity.cognito_sub != expected_sub:
                raise ValueError("identity does not match the verified subject")
            return identity
        except (ValueError, ValidationError, TypeError):
            raise DomainError(
                502, "upstream_error", "Identity service returned an invalid response."
            ) from None


def require_identity(
    request: Request,
    principal: Annotated[Principal, Depends(require_principal)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
) -> CurrentIdentity:
    # No cross-request permission cache. Identity independently verifies this token.
    return request.app.state.identity_client.current_identity(
        credentials.credentials,
        principal.subject,
        request.state.request_id,
    )


def require_tenant_role(role: ClinicRole, *, allow_platform_admin: bool = False):
    def dependency(
        tenant_id: UUID,
        identity: Annotated[CurrentIdentity, Depends(require_identity)],
    ) -> CurrentIdentity:
        membership = next(
            (item for item in identity.memberships if item.tenant_id == tenant_id), None
        )
        if not has_tenant_role(
            membership,
            tenant_id,
            role,
            global_roles=identity.global_roles,
            allow_platform_admin=allow_platform_admin,
        ):
            raise DomainError(404, "not_found", "Resource not found.")
        return identity

    return dependency


def require_global_role(role: GlobalRole):
    def dependency(
        identity: Annotated[CurrentIdentity, Depends(require_identity)],
    ) -> CurrentIdentity:
        if not has_global_role(identity.global_roles, role):
            raise DomainError(403, "forbidden", "This role is not permitted.")
        return identity

    return dependency
