"""Minimal billing-only commission profile. Connected accounts remain operator configuration."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.api import DB, clinic_or_404

router = APIRouter(tags=["internal"])
Billing = Annotated[
    str, Depends(require_service("billing", "telelink-tenant-billing", "billing_secret"))
]


class BillingProfile(BaseModel):
    tenant_id: UUID
    status: Literal["active"]
    commission_bps: int


@router.get("/internal/clinics/{tenant_id}/billing-profile", response_model=BillingProfile)
def billing_profile(tenant_id: UUID, caller: Billing, session: DB, response: Response):
    clinic = clinic_or_404(session, tenant_id)
    if clinic.status != "active" or not clinic.membership_provisioned:
        raise DomainError(409, "clinic_not_active", "Clinic cannot accept checkout.")
    response.headers["Cache-Control"] = "no-store"
    return BillingProfile(
        tenant_id=clinic.tenant_id, status="active", commission_bps=clinic.commission_bps
    )
