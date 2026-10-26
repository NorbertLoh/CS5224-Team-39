"""Context-bound issued MC projection, with current trusted names and a durable audit."""

from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from telelink_common.errors import DomainError

from app.api.dependencies import DB
from app.api.documents import ClinicName, ParticipantNames, document_service, profile
from app.api.medical_certificates import MCPublic
from app.models import MedicalCertificate, ServiceReadAudit
from app.upstream import not_found

router = APIRouter(prefix="/api/v1/clinical-records/internal", tags=["internal"])


class DocumentMC(MCPublic):
    patient_name: str
    doctor_name: str
    clinic_name: str


@router.get("/medical-certificates/{medical_certificate_id}/document", response_model=DocumentMC)
def mc_projection(
    medical_certificate_id: UUID,
    tenant_id: UUID,
    appointment_id: UUID,
    request: Request,
    session: DB,
    caller: Annotated[str, Depends(document_service)],
    purpose: Literal["medical_certificate_pdf"] = Query(...),
):
    row = session.scalar(
        select(MedicalCertificate).where(
            MedicalCertificate.medical_certificate_id == medical_certificate_id,
            MedicalCertificate.tenant_id == tenant_id,
            MedicalCertificate.appointment_id == appointment_id,
        )
    )
    if row is None:
        not_found()
    if row.issued_at is None:
        raise DomainError(409, "mc_not_issued", "Medical certificate is not issued.")
    config = request.app.state.settings
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
    result = DocumentMC(
        **MCPublic.model_validate(row).model_dump(),
        patient_name=names.patient_name,
        doctor_name=names.doctor_name,
        clinic_name=clinic.clinic_name,
    )
    session.add(
        ServiceReadAudit(
            caller=caller,
            purpose=purpose,
            medical_certificate_id=row.medical_certificate_id,
            tenant_id=row.tenant_id,
            appointment_id=row.appointment_id,
            request_id=request.state.request_id,
        )
    )
    session.commit()
    return result
