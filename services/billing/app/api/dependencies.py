from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from telelink_common.access import (
    CurrentIdentity,
    require_global_role,
    require_identity,
)
from telelink_common.service_auth import bearer, require_service

from app.database import get_session


def payment_reader(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    for caller in ("scheduling", "fulfilment", "consultation"):
        if getattr(request.app.state.settings, caller + "_secret") is None:
            continue
        try:
            return require_service(caller, "telelink-billing-" + caller, caller + "_secret")(
                request, credentials
            )
        except HTTPException as error:
            if error.status_code != 401:
                raise
    raise HTTPException(401, "Service credential required", headers={"WWW-Authenticate": "Bearer"})


def resolution_caller(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
):
    for caller in ("scheduling", "fulfilment"):
        if getattr(request.app.state.settings, caller + "_secret") is None:
            continue
        try:
            return require_service(caller, "telelink-billing-" + caller, caller + "_secret")(
                request, credentials
            )
        except HTTPException as error:
            if error.status_code != 401:
                raise
    raise HTTPException(401, "Service credential required")


Patient = Annotated[CurrentIdentity, Depends(require_global_role("patient"))]


PaymentReader = Annotated[str, Depends(payment_reader)]


Fulfilment = Annotated[
    str, Depends(require_service("fulfilment", "telelink-billing-fulfilment", "fulfilment_secret"))
]


ResolutionCaller = Annotated[str, Depends(resolution_caller)]


Identity = Annotated[CurrentIdentity, Depends(require_identity)]


Database = Annotated[Session, Depends(get_session)]
