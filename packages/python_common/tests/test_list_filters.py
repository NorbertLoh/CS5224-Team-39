from datetime import datetime, timezone

import pytest

from telelink_common.errors import DomainError
from telelink_common.list_filters import ListFilters


def test_filter_scopes_normalize_equivalent_search_and_timezones():
    assert ListFilters().scope == {}
    start = datetime.fromisoformat("2026-01-01T08:00:00+08:00")
    assert ListFilters("  JANE  ", start).scope == {
        "q": "jane",
        "from": "2026-01-01T00:00:00+00:00",
    }


def test_date_filters_require_timezones_and_a_nonempty_range():
    with pytest.raises(DomainError):
        ListFilters(from_at=datetime(2026, 1, 1))
    now = datetime.now(timezone.utc)
    with pytest.raises(DomainError):
        ListFilters(from_at=now, to_at=now)
