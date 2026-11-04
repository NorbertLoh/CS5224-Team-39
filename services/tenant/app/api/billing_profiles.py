"""Minimal billing-only commission profile. Connected accounts remain operator configuration."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel
from telelink_common.errors import DomainError

from app.api.dependencies import DB, Billing
from app.services.clinics import clinic_or_404

router = APIRouter(tags=["internal"])


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
