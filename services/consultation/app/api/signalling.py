from uuid import UUID

from fastapi import APIRouter, Request

from app.api.dependencies import DB, Signalling
from app.schemas import NodeHeartbeat
from app.services import matchmaker

router = APIRouter(prefix="/internal/signalling", tags=["internal"])


@router.post("/heartbeat")
def heartbeat(body: NodeHeartbeat, request: Request, caller: Signalling, session: DB):
    result = matchmaker.heartbeat(session, request.app.state.settings, body)
    session.commit()
    return result


@router.get("/nodes/{node_id}")
def resolve(node_id: UUID, request: Request, caller: Signalling, session: DB):
    return matchmaker.resolve(session, request.app.state.settings, node_id)
