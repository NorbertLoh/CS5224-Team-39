from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

Nonblank = Annotated[str, Field(min_length=1, max_length=200)]
ClinicStatus = Literal["pending_review", "active", "rejected", "suspended"]


class Branding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    primary_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    logo_url: str | None = Field(max_length=2048)
    description: str = Field(max_length=2000)

    @field_validator("logo_url")
    @classmethod
    def https_url(cls, value):
        if value is not None:
            url = urlsplit(value)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or any(char.isspace() for char in value)
            ):
                raise ValueError("logo_url must be an HTTPS URL without credentials")
        return value

    @field_validator("description")
    @classmethod
    def plain_text(cls, value):
        if "<" in value or ">" in value:
            raise ValueError("description must be plain text")
        return value


class Money(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_minor: int = Field(strict=True, ge=0, le=9007199254740991)
    currency: Literal["SGD"]


class ClinicCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: Nonblank
    branding: Branding
    consultation_price: Money

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError("name must not be blank")
        return value


class ClinicUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Nonblank | None = None
    branding: Branding | None = None
    consultation_price: Money | None = None

    @model_validator(mode="after")
    def supplied_fields(self):
        if not self.model_fields_set:
            raise ValueError("Supply at least one editable field")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Editable fields cannot be null")
        if self.name is not None and not self.name.strip():
            raise ValueError("name must not be blank")
        return self


class ClinicPublic(BaseModel):
    tenant_id: UUID
    slug: str
    name: str
    status: ClinicStatus
    branding: Branding
    consultation_price: Money
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def timestamp(self, value):
        return (
            value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )


class ClinicAdmin(ClinicPublic):
    commission_bps: int
    review_reason: str | None


class ClinicPage(BaseModel):
    items: list[ClinicPublic]
    next_cursor: str | None


class ClinicAdminPage(BaseModel):
    items: list[ClinicAdmin]
    next_cursor: str | None


class ClinicReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject", "suspend"]
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def review_reason(self):
        if self.decision == "approve":
            if self.reason is not None:
                raise ValueError("Approval reason must be null")
        elif self.reason is None or not self.reason.strip():
            raise ValueError("Rejection/suspension requires a reason")
        if self.reason is not None and ("<" in self.reason or ">" in self.reason):
            raise ValueError("Review reason must be plain text")
        return self


class CommissionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commission_bps: int = Field(strict=True, ge=0, le=10000)


def profile(clinic, *, admin=False):
    fields = {
        field: getattr(clinic, field)
        for field in ("tenant_id", "slug", "name", "status", "created_at", "updated_at")
    }
    fields["branding"] = Branding(
        primary_color=clinic.primary_color, logo_url=clinic.logo_url, description=clinic.description
    )
    fields["consultation_price"] = Money(
        amount_minor=clinic.consultation_price_minor, currency=clinic.currency
    )
    if admin:
        return ClinicAdmin(
            **fields, commission_bps=clinic.commission_bps, review_reason=clinic.review_reason
        )
    return ClinicPublic(**fields)
