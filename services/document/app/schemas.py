from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    document_id: UUID
    tenant_id: UUID
    appointment_id: UUID
    prescription_id: UUID | None
    payment_id: UUID | None
    medical_certificate_id: UUID | None
    kind: Literal["prescription_pdf", "receipt_pdf", "medical_certificate_pdf"]
    status: Literal["pending", "ready", "failed"]
    created_at: datetime
    updated_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentPublic]
    next_cursor: str | None


class DownloadPublic(BaseModel):
    download_url: str
    expires_at: datetime
