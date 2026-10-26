import logging
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger("telelink.database")


class HealthResponse(BaseModel):
    status: Literal["alive", "ready", "not_ready"]
    service: str


@router.get("/live", response_model=HealthResponse)
async def live(request: Request) -> HealthResponse:
    """Process responds; does not depend on external services."""
    return HealthResponse(status="alive", service=request.app.state.settings.name)


@router.get("/ready", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
def ready(request: Request) -> JSONResponse:
    """Startup plus database/table availability when database mode is enabled."""
    is_ready = request.app.state.ready and request.app.state.database is not None
    if is_ready and request.app.state.database is not None:
        try:
            request.app.state.database.check_ready()
        except SQLAlchemyError:
            is_ready = False
            logger.warning("database_not_ready", extra={"service": request.app.state.settings.name})
    payload = HealthResponse(
        status="ready" if is_ready else "not_ready", service=request.app.state.settings.name
    )
    return JSONResponse(payload.model_dump(), status_code=200 if is_ready else 503)
