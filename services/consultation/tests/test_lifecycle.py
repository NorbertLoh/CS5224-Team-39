from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.lifecycle import can_join, utc

START = datetime(2030, 1, 1, 10, tzinfo=timezone.utc)
END = START + timedelta(minutes=30)


@pytest.mark.parametrize("offset", [-172800, -601, -600, -1, 0, 1799, 1800, 86400])
@pytest.mark.parametrize("status", ["scheduled", "in_progress", "completed"])
def test_schedule_does_not_limit_unfinished_sessions(offset, status):
    record = SimpleNamespace(starts_at=START, ends_at=END, status=status)
    assert can_join(record, now=START + timedelta(seconds=offset)) == (status != "completed")


def test_timezone_normalization():
    assert utc(START.astimezone(timezone(timedelta(hours=8)))) == START
    with pytest.raises(ValueError, match="timezone"):
        utc(START.replace(tzinfo=None))
