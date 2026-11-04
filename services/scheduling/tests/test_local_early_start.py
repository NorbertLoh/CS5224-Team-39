from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services.transitions import consultation_action
from app.settings import Settings


@pytest.mark.parametrize("offset", [-86400, -1, 0, 1800, 86400])
def test_start_and_completion_ignore_slot_times(offset):
    start = datetime.now(timezone.utc)
    booking = SimpleNamespace(
        status="confirmed", starts_at=start, ends_at=start + timedelta(minutes=30)
    )
    now = start + timedelta(seconds=offset)
    consultation_action(booking, "start", now)
    assert booking.status == "in_progress"
    consultation_action(booking, "complete", now)
    assert booking.status == "completed"


@pytest.mark.parametrize("environment", ["development", "demo", "production"])
def test_early_start_configuration_is_local_only(environment):
    with pytest.raises(ValidationError, match="local/test"):
        Settings(_env_file=None, environment=environment, test_join_early_minutes=180)
