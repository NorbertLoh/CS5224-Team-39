"""Public doctor summaries, available only through the tenant service."""

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import select, tuple_
from telelink_common.pagination import sign_cursor, verify_cursor

from app.api.dependencies import DB
from app.api.provisioning import bearer, verify_tenant_service
from app.models import Membership, Subject
from app.pagination import cursor_error, cursor_key

router = APIRouter(tags=["internal"])


class DoctorSummary(BaseModel):
    doctor_id: UUID
    display_name: str


class DoctorPage(BaseModel):
    items: list[DoctorSummary]
    next_cursor: str | None


def require_doctor_directory(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    verify_tenant_service(request, credentials, "telelink-identity-doctors")


def encode_doctor_cursor(settings, tenant_id, subject):
    return sign_cursor(
        {"tenant": str(tenant_id), "name": subject.display_name, "id": str(subject.subject_id)},
        cursor_key(settings),
        issuer="telelink-identity-cursor",
        audience="public-doctors",
    )


def decode_doctor_cursor(settings, tenant_id, cursor):
    try:
        claims = verify_cursor(
            cursor,
            cursor_key(settings),
            issuer="telelink-identity-cursor",
            audience="public-doctors",
            required=["tenant", "name", "id"],
        )
        if claims["tenant"] != str(tenant_id) or not isinstance(claims["name"], str):
            raise ValueError("Wrong cursor scope")
        return claims["name"], UUID(claims["id"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise cursor_error() from None


@router.get(
    "/internal/clinics/{tenant_id}/doctors",
    response_model=DoctorPage,
    dependencies=[Depends(require_doctor_directory)],
)
def doctors(
    tenant_id: UUID,
    request: Request,
    session: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
):
    settings = request.app.state.settings
    cursor_key(settings)
    query = (
        select(Membership, Subject)
        .join(Subject)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.status == "active",
            Membership.roles.any("doctor"),
        )
    )
    if cursor is not None:
        name, doctor_id = decode_doctor_cursor(settings, tenant_id, cursor)
        query = query.where(
            tuple_(Subject.display_name, Subject.subject_id) > tuple_(name, doctor_id)
        )
    rows = session.execute(
        query.order_by(Subject.display_name, Subject.subject_id).limit(limit + 1)
    ).all()
    next_cursor = (
        encode_doctor_cursor(settings, tenant_id, rows[limit - 1][1]) if len(rows) > limit else None
    )
    return DoctorPage(
        items=[
            DoctorSummary(doctor_id=subject.subject_id, display_name=subject.display_name)
            for membership, subject in rows[:limit]
        ],
        next_cursor=next_cursor,
    )
