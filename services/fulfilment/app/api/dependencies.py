from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session
from telelink_common.access import CurrentIdentity, require_global_role, require_identity

from app.database import get_session

Identity = Annotated[CurrentIdentity, Depends(require_identity)]


DB = Annotated[Session, Depends(get_session)]


Patient = Annotated[CurrentIdentity, Depends(require_global_role("patient"))]


IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9._-]{1,64}$")]
