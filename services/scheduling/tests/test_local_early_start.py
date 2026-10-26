from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from telelink_common.errors import DomainError

from app.settings import Settings
from app.transitions import consultation_action


def test_early_start_requires_opt_in_and_supports_completion():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(
        status="confirmed",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=2, minutes=30),
    )
    with pytest.raises(DomainError):
        consultation_action(booking, "start", now)
    with pytest.raises(DomainError):
        consultation_action(booking, "start", now - timedelta(hours=2), early_minutes=180)
    consultation_action(booking, "start", now, early_minutes=180)
    assert booking.status == "in_progress"
    consultation_action(booking, "complete", now, early_minutes=180)
    assert booking.status == "completed"


@pytest.mark.parametrize("environment", ["development", "demo", "production"])
def test_early_start_configuration_is_local_only(environment):
    with pytest.raises(ValidationError, match="local/test"):
        Settings(_env_file=None, environment=environment, test_join_early_minutes=180)
