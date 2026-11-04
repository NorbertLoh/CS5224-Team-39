"""Names only, for clinical-records to assemble an issued prescription document."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.api.dependencies import DB
from app.models import Subject

router = APIRouter(tags=["internal"])
records_service = require_service(
    "clinical-records", "telelink-identity-document", "records_secret"
)


class DocumentParticipants(BaseModel):
    patient_id: UUID
    patient_name: str
    doctor_id: UUID
    doctor_name: str


@router.get(
    "/internal/document-participants",
    response_model=DocumentParticipants,
    dependencies=[Depends(records_service)],
)
def document_participants(patient_id: UUID, doctor_id: UUID, session: DB, response: Response):
    # Records supplies links from its persisted issued prescription, never a browser.
    patient, doctor = session.get(Subject, patient_id), session.get(Subject, doctor_id)
    if patient is None or doctor is None:
        raise DomainError(404, "not_found", "Resource not found.")
    response.headers["Cache-Control"] = "no-store"
    return DocumentParticipants(
        patient_id=patient_id,
        patient_name=patient.display_name,
        doctor_id=doctor_id,
        doctor_name=doctor.display_name,
    )
