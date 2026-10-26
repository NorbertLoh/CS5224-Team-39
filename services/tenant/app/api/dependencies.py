from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session
from telelink_common.access import (
    CurrentIdentity,
    require_global_role,
    require_identity,
    require_tenant_role,
)
from telelink_common.service_auth import require_service

from app.database import get_session

PlatformAdmin = Annotated[CurrentIdentity, Depends(require_global_role("platform_admin"))]


DB = Annotated[Session, Depends(get_session)]


Identity = Annotated[CurrentIdentity, Depends(require_identity)]


ClinicAdmin = Annotated[
    CurrentIdentity, Depends(require_tenant_role("clinic_admin", allow_platform_admin=True))
]


Billing = Annotated[
    str, Depends(require_service("billing", "telelink-tenant-billing", "billing_secret"))
]


PickupAdmin = Annotated[CurrentIdentity, Depends(require_tenant_role("clinic_admin"))]
