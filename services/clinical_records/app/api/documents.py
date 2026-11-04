"""Service-only, audited issued prescription projection. No consultation notes."""

from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service, service_token

from app.api.dependencies import DB
from app.models import Prescription, ServiceReadAudit
from app.schemas import PrescriptionPublic
from app.services.records import prescription_public

router = APIRouter(prefix="/api/v1/clinical-records/internal", tags=["internal"])
document_service = require_service("document", "telelink-records-document", "document_secret")


class ParticipantNames(BaseModel):
    patient_id: UUID
    patient_name: str = Field(min_length=1, max_length=200)
    doctor_id: UUID
    doctor_name: str = Field(min_length=1, max_length=200)


class ClinicName(BaseModel):
    tenant_id: UUID
    clinic_name: str = Field(min_length=1, max_length=200)


class DocumentPrescription(PrescriptionPublic):
    status: Literal["issued"]
    patient_name: str
    doctor_name: str
    clinic_name: str


def profile(client, base, path, secret, audience, request_id, model, params=None):
    if base is None or secret is None:
        raise DomainError(503, "unavailable", "Document profiles are not configured.")
    try:
        response = client.get(
            base + path,
            params=params,
            headers={
                "Authorization": "Bearer " + service_token(secret, "clinical-records", audience),
                "X-Request-ID": request_id,
            },
        )
        if response.status_code != 200:
            raise ValueError()
        return model.model_validate(response.json())
    except (httpx.RequestError, ValueError, TypeError):
        raise DomainError(503, "unavailable", "Document profiles are unavailable.") from None


@router.get("/prescriptions/{prescription_id}/document", response_model=DocumentPrescription)
def document_projection(
    prescription_id: UUID,
    tenant_id: UUID,
    appointment_id: UUID,
    request: Request,
    session: DB,
    caller: Annotated[str, Depends(document_service)],
    purpose: Literal["prescription_pdf"] = Query(...),
):
    row = session.get(Prescription, prescription_id)
    if row is None or row.tenant_id != tenant_id or row.appointment_id != appointment_id:
        raise DomainError(404, "not_found", "Resource not found.")
    if row.status != "issued":
        raise DomainError(409, "prescription_not_issued", "Prescription is not issued.")
    config = request.app.state.settings
    # Use owning-service APIs; no direct access to identity/tenant databases.
    with httpx.Client(
        timeout=config.upstream_timeout_seconds, follow_redirects=False, trust_env=False
    ) as client:
        names = profile(
            client,
            config.identity_url,
            "/internal/document-participants",
            config.identity_document_secret,
            "telelink-identity-document",
            request.state.request_id,
            ParticipantNames,
            {"patient_id": str(row.patient_id), "doctor_id": str(row.doctor_id)},
        )
        clinic = profile(
            client,
            config.tenant_url,
            f"/internal/clinics/{row.tenant_id}/document-profile",
            config.tenant_document_secret,
            "telelink-tenant-document",
            request.state.request_id,
            ClinicName,
        )
    if (
        names.patient_id != row.patient_id
        or names.doctor_id != row.doctor_id
        or clinic.tenant_id != row.tenant_id
    ):
        raise DomainError(502, "upstream_error", "Invalid document profile context.")
    result = DocumentPrescription(
        **prescription_public(session, row).model_dump(),
        patient_name=names.patient_name,
        doctor_name=names.doctor_name,
        clinic_name=clinic.clinic_name,
    )
    session.add(
        ServiceReadAudit(
            caller=caller,
            purpose=purpose,
            prescription_id=row.prescription_id,
            tenant_id=row.tenant_id,
            appointment_id=row.appointment_id,
            request_id=request.state.request_id,
        )
    )
    session.commit()  # No clinical response unless the service read audit persisted.
    return result
