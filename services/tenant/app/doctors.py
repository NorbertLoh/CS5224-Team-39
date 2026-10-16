"""Resolve current doctor summaries from identity without sharing its database."""

import time
from typing import Annotated
from uuid import UUID

import httpx
import jwt
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from telelink_common.errors import DomainError

from app.api import DB, clinic_or_404

router = APIRouter(tags=["clinics"])


class DoctorSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doctor_id: UUID
    display_name: str = Field(min_length=1)


class DoctorPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[DoctorSummary]
    next_cursor: str | None = Field(max_length=4096)


@router.get("/clinics/{tenant_id}/doctors", response_model=DoctorPage)
def doctors(
    tenant_id: UUID,
    request: Request,
    session: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
):
    clinic = clinic_or_404(session, tenant_id)
    if clinic.status != "active" or not clinic.membership_provisioned:
        raise DomainError(404, "not_found", "Resource not found.")
    settings = request.app.state.settings
    client = request.app.state.identity_client.client
    if client is None or settings.tenant_secret is None:
        raise DomainError(503, "unavailable", "Doctor directory is not configured.")
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": "telelink-service:tenant",
            "aud": "telelink-identity-doctors",
            "sub": "tenant",
            "iat": now,
            "exp": now + 60,
        },
        settings.tenant_secret.get_secret_value(),
        algorithm="HS256",
    )
    params = {"limit": limit}
    if cursor is not None:
        params["cursor"] = cursor
    try:
        response = client.get(
            f"internal/clinics/{tenant_id}/doctors",
            params=params,
            headers={"Authorization": "Bearer " + token, "X-Request-ID": request.state.request_id},
        )
        if response.status_code == 422:
            raise DomainError(422, "validation_error", "Invalid doctor directory cursor.")
        if response.status_code != 200:
            raise ValueError("Doctor directory unavailable")
        result = DoctorPage.model_validate(response.json())
        if len(result.items) > limit:
            raise ValueError("Invalid doctor page")
        return result
    except (httpx.RequestError, ValueError, TypeError):
        raise DomainError(503, "unavailable", "Doctor directory is unavailable.") from None
