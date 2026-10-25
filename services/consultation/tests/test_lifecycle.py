from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.lifecycle import can_join, utc

START = datetime(2030, 1, 1, 10, tzinfo=timezone.utc)
END = START + timedelta(minutes=30)


@pytest.mark.parametrize(
    "offset,allowed",
    [
        (-601, False),
        (-600, True),
        (-1, True),
        (0, True),
        (1799, True),
        (1800, False),
        (86400, False),
    ],
)
@pytest.mark.parametrize("status", ["scheduled", "in_progress", "completed"])
def test_exact_join_boundaries(offset, allowed, status):
    record = SimpleNamespace(starts_at=START, ends_at=END, status=status)
    assert can_join(record, now=START + timedelta(seconds=offset)) == (
        status != "completed" and (allowed or (status == "in_progress" and offset >= 0))
    )


def test_timezone_normalization():
    assert utc(START.astimezone(timezone(timedelta(hours=8)))) == START
    with pytest.raises(ValueError, match="timezone"):
        utc(START.replace(tzinfo=None))
