from uuid import UUID

from fastapi import APIRouter, Request, Response
from telelink_common.errors import ErrorEnvelope

from app import admissions, ice
from app.api.dependencies import DB, Identity, Signalling
from app.schemas import AdmissionPublic, AdmissionRequest, LeasePublic, LeaseRequest
from app.session_actions import act

router = APIRouter(
    responses={s: {"model": ErrorEnvelope} for s in (401, 403, 404, 409, 422, 502, 503)}
)


@router.post("/appointments/{appointment_id}/start")
def start(appointment_id: UUID, request: Request, identity: Identity, session: DB):
    return act(
        session,
        request.app.state.sources,
        appointment_id,
        identity,
        request.state.request_id,
        "start",
    )


@router.post("/appointments/{appointment_id}/complete")
def complete(appointment_id: UUID, request: Request, identity: Identity, session: DB):
    return act(
        session,
        request.app.state.sources,
        appointment_id,
        identity,
        request.state.request_id,
        "complete",
        user_token=request.headers["authorization"].split(" ", 1)[1],
    )


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
    return {**result, **ice.configuration(state.settings, result)}


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
