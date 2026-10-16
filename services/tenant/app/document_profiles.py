"""Clinic name for records' issued-document projection, including inactive clinics."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.api import DB
from app.models import Clinic

router = APIRouter(tags=["internal"])
records_service = require_service("clinical-records", "telelink-tenant-document", "records_secret")


class DocumentClinic(BaseModel):
    tenant_id: UUID
    clinic_name: str


@router.get(
    "/internal/clinics/{tenant_id}/document-profile",
    response_model=DocumentClinic,
    dependencies=[Depends(records_service)],
)
def document_clinic(tenant_id: UUID, session: DB, response: Response):
    clinic = session.get(Clinic, tenant_id)
    if clinic is None:
        raise DomainError(404, "not_found", "Resource not found.")
    response.headers["Cache-Control"] = "no-store"
    return DocumentClinic(tenant_id=tenant_id, clinic_name=clinic.name)
