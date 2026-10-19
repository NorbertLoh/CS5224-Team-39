from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.database import get_session
from app.models import Subject

router = APIRouter(tags=["internal"])
DB = Annotated[Session, Depends(get_session)]
notification_service = require_service(
    "notification", "telelink-identity-notification", "notification_secret"
)


@router.get(
    "/internal/notification-recipients/{subject_id}", dependencies=[Depends(notification_service)]
)
def recipient(subject_id: UUID, session: DB, response: Response):
    row = session.get(Subject, subject_id)
    if row is None or "patient" not in row.global_roles or not row.email:
        raise DomainError(404, "not_found", "Resource not found.")
    response.headers["Cache-Control"] = "no-store"
    return {"recipient_id": row.subject_id, "email": row.email}
