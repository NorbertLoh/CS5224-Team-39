from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session
from telelink_common.access import CurrentIdentity, require_identity
from telelink_common.errors import ErrorEnvelope
from telelink_common.service_auth import require_service

from app import admissions
from app.database import get_session
from app.schemas import AdmissionPublic, AdmissionRequest, LeasePublic, LeaseRequest

router = APIRouter(
    responses={s: {"model": ErrorEnvelope} for s in (401, 403, 404, 409, 422, 502, 503)}
)
DB = Annotated[Session, Depends(get_session)]
Identity = Annotated[CurrentIdentity, Depends(require_identity)]
Signalling = Annotated[
    str,
    Depends(require_service("signalling", "telelink-consultation-admission", "signalling_secret")),
]


@router.post("/admissions", response_model=AdmissionPublic, status_code=201)
def issue(body: AdmissionRequest, request: Request, identity: Identity, session: DB):
    state = request.app.state
    result = admissions.issue(
        session,
        state.sources,
        state.settings,
        body.appointment_id,
        identity,
        request.state.request_id,
    )
    session.commit()
    return result


@router.post("/internal/admissions/consume", response_model=LeasePublic, tags=["internal"])
def consume(body: LeaseRequest, request: Request, caller: Signalling, session: DB):
    result = admissions.consume(
        session, request.app.state.sources, body.token, body.peer_id, request.state.request_id
    )
    session.commit()
    return result


@router.post("/internal/admissions/check", response_model=LeasePublic, tags=["internal"])
def check(body: LeaseRequest, request: Request, caller: Signalling, session: DB):
    return admissions.consume(
        session,
        request.app.state.sources,
        body.token,
        body.peer_id,
        request.state.request_id,
        check=True,
    )


@router.post("/internal/admissions/release", status_code=204, tags=["internal"])
def release(body: LeaseRequest, caller: Signalling, session: DB):
    admissions.release(session, body.token, body.peer_id)
    session.commit()
    return Response(status_code=204)
