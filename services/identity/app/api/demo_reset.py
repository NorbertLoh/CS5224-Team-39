"""The browser may request a fixed demo operation, never supply AWS targets."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from telelink_common.errors import DomainError

from app.api.dependencies import DB, User
from app.services.demo_reset import ResetControl
from app.services.doctor_verification import platform_reviewer
from app.services.local_demo_reset import LocalResetControl

router = APIRouter(tags=["demo operations"])


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    confirmation: Literal["RESET DEMO"]


def control(request, session, principal):
    actor = platform_reviewer(session, principal)
    config = request.app.state.settings.demo_reset_config
    local = request.app.state.settings.local_reset_state_dir
    if not local and (not config or config.get("deployment") != "demo"):
        raise DomainError(404, "not_found", "Demo reset is not enabled.")
    # The five-account seed must retain the operator who started the reset.
    if actor.email != "platform@example.test":
        raise DomainError(403, "forbidden", "Use the seeded platform administrator.")
    return (LocalResetControl(local) if local else ResetControl(config)), actor


@router.get("/demo-reset")
def status(request: Request, principal: User, session: DB):
    service, _ = control(request, session, principal)
    return service.status()


@router.post("/demo-reset", status_code=202)
def start(body: ResetRequest, request: Request, principal: User, session: DB):
    service, actor = control(request, session, principal)
    # Release the authorization transaction before the reset worker quiesces DB users.
    actor_id = str(actor.subject_id)
    session.commit()
    return service.start(str(body.request_id), actor_id)
