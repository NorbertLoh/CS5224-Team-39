from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session
from telelink_common.auth import Principal, require_principal

from app.auth import require_access_service
from app.database import get_session

DB = Annotated[Session, Depends(get_session)]


User = Annotated[Principal, Depends(require_principal)]


Service = Annotated[frozenset[str], Depends(require_access_service)]
