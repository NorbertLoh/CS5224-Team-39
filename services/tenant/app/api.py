from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from telelink_common.access import (
    CurrentIdentity,
    has_tenant_role,
    require_identity,
    require_tenant_role,
)
from telelink_common.errors import DomainError, ErrorEnvelope

from app.auth import require_booking_service, require_identity_service
from app.database import get_session
from app.models import Clinic
from app.pagination import cursor_key, decode_cursor, encode_cursor
from app.provisioning import provision_creator
from app.schemas import (
    ClinicAdmin,
    ClinicCreate,
    ClinicMembershipProfile,
    ClinicPage,
    ClinicPublic,
    ClinicUpdate,
    profile,
)

router = APIRouter(
    tags=["clinics"],
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 422, 502, 503)},
)
DB = Annotated[Session, Depends(get_session)]
Identity = Annotated[CurrentIdentity, Depends(require_identity)]
Admin = Annotated[
    CurrentIdentity, Depends(require_tenant_role("clinic_admin", allow_platform_admin=True))
]


def clinic_or_404(session, tenant_id):
    clinic = session.get(Clinic, tenant_id)
    if clinic is None:
        raise DomainError(404, "not_found", "Resource not found.")
    return clinic


def editable_fields(body):
    fields = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.branding is not None:
        fields.update(body.branding.model_dump())
    if body.consultation_price is not None:
        fields.update(
            consultation_price_minor=body.consultation_price.amount_minor,
            currency=body.consultation_price.currency,
        )
    return fields


@router.post(
    "/clinics", response_model=ClinicAdmin, status_code=201, responses={200: {"model": ClinicAdmin}}
)
def create_clinic(
    body: ClinicCreate, request: Request, response: Response, identity: Identity, session: DB
):
    fields = editable_fields(body)
    clinic = session.scalar(select(Clinic).where(Clinic.slug == body.slug))
    if clinic is None:
        clinic = Clinic(slug=body.slug, creator_subject_id=identity.subject_id, **fields)
        session.add(clinic)
        try:
            # Durable reservation before the HTTP call; a lost response is safe to retry.
            session.commit()
        except IntegrityError as error:
            session.rollback()
            if getattr(error.orig.diag, "constraint_name", None) != "uq_clinics_slug":
                raise
            clinic = session.scalar(select(Clinic).where(Clinic.slug == body.slug))
            response.status_code = 200
    else:
        response.status_code = 200
    if clinic.creator_subject_id != identity.subject_id or any(
        getattr(clinic, key) != value for key, value in fields.items()
    ):
        raise DomainError(409, "slug_taken", "Clinic slug is already taken.")
    if not clinic.membership_provisioned:
        provision_creator(request, clinic)
        clinic.membership_provisioned = True
        session.commit()
    else:
        membership = next(
            (item for item in identity.memberships if item.tenant_id == clinic.tenant_id), None
        )
        if not has_tenant_role(
            membership,
            clinic.tenant_id,
            "clinic_admin",
            global_roles=identity.global_roles,
            allow_platform_admin=True,
        ):
            raise DomainError(404, "not_found", "Resource not found.")
    return profile(clinic, admin=True)


@router.get("/clinics", response_model=ClinicPage)
def clinics(
    request: Request,
    session: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
):
    settings = request.app.state.settings
    cursor_key(settings)
    query = select(Clinic).where(Clinic.status == "active", Clinic.membership_provisioned.is_(True))
    if cursor is not None:
        name, tenant_id = decode_cursor(settings, cursor)
        query = query.where(tuple_(Clinic.name, Clinic.tenant_id) > tuple_(name, tenant_id))
    rows = session.scalars(query.order_by(Clinic.name, Clinic.tenant_id).limit(limit + 1)).all()
    next_cursor = encode_cursor(settings, rows[limit - 1]) if len(rows) > limit else None
    return ClinicPage(items=[profile(row) for row in rows[:limit]], next_cursor=next_cursor)


@router.get("/clinics/by-slug/{slug}", response_model=ClinicPublic)
def public_clinic(slug: str, session: DB):
    clinic = session.scalar(
        select(Clinic).where(
            Clinic.slug == slug, Clinic.status == "active", Clinic.membership_provisioned.is_(True)
        )
    )
    if clinic is None:
        raise DomainError(404, "not_found", "Resource not found.")
    return profile(clinic)


@router.get("/clinics/{tenant_id}", response_model=ClinicAdmin)
def admin_clinic(tenant_id: UUID, identity: Admin, session: DB):
    return profile(clinic_or_404(session, tenant_id), admin=True)


@router.patch("/clinics/{tenant_id}", response_model=ClinicAdmin)
def update_clinic(tenant_id: UUID, body: ClinicUpdate, identity: Admin, session: DB):
    clinic = clinic_or_404(session, tenant_id)
    for key, value in editable_fields(body).items():
        setattr(clinic, key, value)
    session.flush()
    result = profile(clinic, admin=True)
    session.commit()
    return result


@router.get(
    "/internal/clinics/{tenant_id}/booking-profile",
    response_model=ClinicPublic,
    dependencies=[Depends(require_booking_service)],
    tags=["internal"],
)
def booking_profile(tenant_id: UUID, session: DB):
    clinic = clinic_or_404(session, tenant_id)
    if clinic.status != "active" or not clinic.membership_provisioned:
        raise DomainError(409, "clinic_not_active", "Clinic cannot accept new bookings.")
    return profile(clinic)


@router.get(
    "/internal/clinics/{tenant_id}/membership-profile",
    response_model=ClinicMembershipProfile,
    dependencies=[Depends(require_identity_service)],
    tags=["internal"],
)
def membership_profile(tenant_id: UUID, session: DB):
    clinic = clinic_or_404(session, tenant_id)
    return ClinicMembershipProfile(tenant_id=clinic.tenant_id)
