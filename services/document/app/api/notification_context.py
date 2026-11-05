from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Request, Response
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service, service_token

from app.api.dependencies import DB
from app.models import Document

router = APIRouter(tags=["internal"])
notification_service = require_service(
    "notification", "telelink-document-notification", "notification_secret"
)


@router.get(
    "/internal/documents/{resource_id}/notification-context",
    dependencies=[Depends(notification_service)],
)
def notification_context(
    resource_id: UUID, tenant_id: UUID, session: DB, response: Response, request: Request
):
    row = session.get(Document, resource_id)
    if row is None or row.tenant_id != tenant_id:
        raise DomainError(404, "not_found", "Resource not found.")
    response.headers["Cache-Control"] = "no-store"
    result = {
        "resource_id": row.document_id,
        "tenant_id": row.tenant_id,
        "patient_id": row.patient_id,
        "appointment_id": row.appointment_id,
        "prescription_id": row.prescription_id,
        "medical_certificate_id": row.medical_certificate_id,
        "payment_id": row.payment_id,
        "kind": row.kind,
        "eligible": row.status == "ready",
    }
    if row.kind == "receipt_pdf" and row.status == "ready":
        from app.services.receipt_generation import PaidSnapshot

        settings = request.app.state.settings
        if not settings.billing_url or not settings.billing_secret:
            raise DomainError(503, "unavailable", "Receipt details unavailable.")
        try:
            with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
                source = client.get(
                    f"{settings.billing_url}/internal/payments/{row.payment_id}/receipt",
                    headers={
                        "Authorization": "Bearer "
                        + service_token(
                            settings.billing_secret, "document", "telelink-billing-receipt"
                        )
                    },
                )
                source.raise_for_status()
                paid = PaidSnapshot.model_validate(source.json())
            if (paid.payment_id, paid.tenant_id, paid.patient_id, paid.appointment_id) != (
                row.payment_id,
                row.tenant_id,
                row.patient_id,
                row.appointment_id,
            ):
                raise ValueError("Receipt context mismatch")
        except (httpx.HTTPError, ValueError):
            raise DomainError(503, "unavailable", "Receipt details unavailable.") from None
        result.update(
            clinic_name=paid.clinic_name,
            purpose=paid.purpose,
            amount_minor=paid.amount.amount_minor,
            currency=paid.amount.currency,
            paid_at=paid.paid_at,
            order_id=paid.order_id,
        )
    return result


@router.get(
    "/internal/documents/{resource_id}/notification-receipt",
    dependencies=[Depends(notification_service)],
)
def notification_receipt(
    resource_id: UUID, tenant_id: UUID, patient_id: UUID, request: Request, session: DB
):
    row = session.get(Document, resource_id)
    if row is None or (row.tenant_id, row.patient_id, row.kind) != (
        tenant_id,
        patient_id,
        "receipt_pdf",
    ):
        raise DomainError(404, "not_found", "Resource not found.")
    downloads = request.app.state.downloads
    downloads.prepare(row)
    return Response(
        downloads.content(row),
        media_type="application/pdf",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
