from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session
from test_api import api as api
from test_api import api_database as api_database
from test_api import headers
from test_api import signing_key as signing_key
from test_doctor_applications import apply

from app.models import DoctorApplication


def test_search_dates_and_counts_share_the_same_full_query(api):
    apply(api)
    with Session(api.engine) as session, session.begin():
        row = session.get(DoctorApplication, api.ids["target"])
        row.legal_name = "Jane 50% Tan"
        row.submitted_at = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    auth = headers(api, "platform")
    endpoint = "/platform/doctor-applications"
    params = {"q": "  JANE 50% ", "from": "2026-01-01T00:00:00Z", "to": "2026-01-02T00:00:00Z"}
    rows = api.client.get(endpoint, params=params, headers=auth)
    assert rows.status_code == 200 and len(rows.json()) == 1
    counts = api.client.get(endpoint + "/counts", params=params, headers=auth).json()
    assert counts == {"pending": 1, "approved": 0, "rejected": 0, "revoked": 0, "total": 1}
    for changed in (
        {"q": "missing"},
        {"from": "2026-01-02T00:00:00Z", "to": "2026-01-03T00:00:00Z"},
    ):
        query = params | changed
        assert api.client.get(endpoint, params=query, headers=auth).json() == []
        assert api.client.get(endpoint + "/counts", params=query, headers=auth).json()["total"] == 0
    assert (
        api.client.get(endpoint + "/counts", params={"q": "%"}, headers=auth).json()["total"] == 1
    )
    assert (
        api.client.get(endpoint + "/counts", params={"q": "TEST-123"}, headers=auth).json()["total"]
        == 1
    )


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-01-01T00:00:00"},
        {"from": "2026-02-01T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
        {"q": "x" * 201},
    ],
)
def test_invalid_application_filters_are_rejected(api, params):
    assert (
        api.client.get(
            "/platform/doctor-applications/counts", params=params, headers=headers(api, "platform")
        ).status_code
        == 422
    )
