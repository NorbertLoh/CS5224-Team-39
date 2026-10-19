from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.database import get_session
from app.models import Appointment

router = APIRouter(tags=["internal"])
DB = Annotated[Session, Depends(get_session)]
notification_service = require_service(
    "notification", "telelink-scheduling-notification", "notification_secret"
)


@router.get(
    "/internal/appointments/{resource_id}/notification-context",
    dependencies=[Depends(notification_service)],
)
def notification_context(resource_id: UUID, tenant_id: UUID, session: DB, response: Response):
    row = session.get(Appointment, resource_id)
    if row is None or row.tenant_id != tenant_id:
        raise DomainError(404, "not_found", "Resource not found.")
    response.headers["Cache-Control"] = "no-store"
    return {
        "resource_id": row.appointment_id,
        "tenant_id": row.tenant_id,
        "patient_id": row.patient_id,
        "eligible": row.status in {"confirmed", "in_progress", "completed", "no_show"},
    }
