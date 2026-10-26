from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session
from telelink_common.access import CurrentIdentity, require_identity

from app.access import authorize
from app.database import get_session

DB = Annotated[Session, Depends(get_session)]


Identity = Annotated[CurrentIdentity, Depends(require_identity)]


def token(request):
    return request.headers["authorization"].split(" ", 1)[1]


def context(request, identity, appointment_id, *, write=False, record=None):
    appointment = request.app.state.upstream.appointment(
        appointment_id, token(request), request.state.request_id
    )
    authorize(identity, appointment, write=write, record=record)
    return appointment
