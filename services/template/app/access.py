"""A06 permission probe; contains no clinic records or cross-service table reads."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from telelink_common.access import CurrentIdentity, require_tenant_role
from telelink_common.errors import ErrorEnvelope

router = APIRouter(
    tags=["tenant access"],
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 422, 502, 503)},
)


@router.get("/clinics/{tenant_id}/access")
def clinic_access(
    tenant_id: UUID,
    identity: Annotated[
        CurrentIdentity, Depends(require_tenant_role("clinic_admin", allow_platform_admin=True))
    ],
):
    return {
        "tenant_id": str(tenant_id),
        "subject_id": str(identity.subject_id),
        "allowed": True,
    }
