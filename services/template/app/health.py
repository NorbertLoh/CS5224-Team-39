from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["alive", "ready", "not_ready"]
    service: str


@router.get("/live", response_model=HealthResponse)
async def live(request: Request) -> HealthResponse:
    """Process responds; does not depend on external services."""
    return HealthResponse(status="alive", service=request.app.state.settings.name)


@router.get("/ready", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
async def ready(request: Request) -> JSONResponse:
    """Template readiness reflects completed application startup only."""
    is_ready = request.app.state.ready
    payload = HealthResponse(
        status="ready" if is_ready else "not_ready", service=request.app.state.settings.name
    )
    return JSONResponse(payload.model_dump(), status_code=200 if is_ready else 503)
