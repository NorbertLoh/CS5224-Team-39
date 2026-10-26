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

DB = Annotated[Session, Depends(get_session)]


Identity = Annotated[CurrentIdentity, Depends(require_identity)]


Doctor = Annotated[CurrentIdentity, Depends(require_tenant_role("doctor"))]


Patient = Annotated[CurrentIdentity, Depends(require_global_role("patient"))]


Billing = Annotated[
    str, Depends(require_service("billing", "telelink-scheduling-billing", "billing_secret"))
]
