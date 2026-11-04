from datetime import timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services.lifecycle import can_join
from app.settings import Settings
from tests.test_lifecycle import END, START


@pytest.mark.parametrize("environment", ["local", "test"])
def test_extended_window_is_opt_in(environment):
    settings = Settings(_env_file=None, environment=environment)
    record = SimpleNamespace(starts_at=START, ends_at=END, status="scheduled")
    assert settings.test_join_early_minutes == 10
    assert not can_join(record, now=START - timedelta(hours=2))
    settings = Settings(_env_file=None, environment=environment, test_join_early_minutes=180)
    assert can_join(
        record, now=START - timedelta(hours=3), early_minutes=settings.test_join_early_minutes
    )
    assert not can_join(record, now=START - timedelta(hours=3, microseconds=1), early_minutes=180)
    assert not can_join(record, now=END, early_minutes=180)
    record.status = "completed"
    assert not can_join(record, now=START, early_minutes=180)


@pytest.mark.parametrize("environment", ["development", "demo", "production"])
def test_extended_window_rejected_outside_local_test(environment):
    with pytest.raises(ValidationError, match="local/test"):
        Settings(_env_file=None, environment=environment, test_join_early_minutes=180)


@pytest.mark.parametrize("minutes", [0, 9, 181])
def test_invalid_window_rejected(minutes):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, test_join_early_minutes=minutes)
