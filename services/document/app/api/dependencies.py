from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session
from telelink_common.access import CurrentIdentity, require_identity

from app.database import get_session

DB = Annotated[Session, Depends(get_session)]


Identity = Annotated[CurrentIdentity, Depends(require_identity)]
