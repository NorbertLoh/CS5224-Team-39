from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from pydantic import SecretStr
from telelink_common.errors import DomainError

from app.pagination import decode_admin_cursor, encode_admin_cursor


def test_unfiltered_admin_cursor_round_trip_and_scope():
    settings = SimpleNamespace(cursor_secret=SecretStr("test-cursor-secret-at-least-32-bytes"))
    actor = uuid4()
    clinic = SimpleNamespace(tenant_id=uuid4(), created_at=datetime.now(timezone.utc))
    cursor = encode_admin_cursor(settings, actor, None, clinic)
    assert decode_admin_cursor(settings, cursor, actor, None) == (
        clinic.created_at,
        clinic.tenant_id,
    )
    for subject_id, status in [(uuid4(), None), (actor, "active")]:
        with pytest.raises(DomainError):
            decode_admin_cursor(settings, cursor, subject_id, status)
    claims = jwt.decode(cursor, options={"verify_signature": False})
    del claims["status"]
    missing_scope = jwt.encode(claims, settings.cursor_secret.get_secret_value(), algorithm="HS256")
    with pytest.raises(DomainError):
        decode_admin_cursor(settings, missing_scope, actor, None)
