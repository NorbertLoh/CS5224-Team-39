from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session
from test_api import api as api
from test_api import api_database as api_database

from app.models import Clinic


def test_admin_search_counts_dates_and_cursor_filters(api):
    marker = f"filter-{uuid4()}"
    ids = [uuid4() for _ in range(28)]
    try:
        with Session(api.engine) as session, session.begin():
            for i, tenant_id in enumerate(ids):
                session.add(
                    Clinic(
                        tenant_id=tenant_id,
                        slug=f"{marker}-{i}",
                        name=f"{marker} 50% clinic",
                        status="active" if i == 27 else "pending_review",
                        primary_color="#156B63",
                        description="Synthetic",
                        consultation_price_minor=2500,
                        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    )
                )
        auth = api.user("platform")
        query = {"q": marker.upper(), "from": "2026-01-01T00:00:00Z", "to": "2026-01-02T00:00:00Z"}
        counts = api.client.get("/admin/clinic-counts", params=query, headers=auth)
        assert counts.status_code == 200
        assert counts.json() == {
            "pending_review": 27,
            "active": 1,
            "rejected": 0,
            "suspended": 0,
            "total": 28,
        }
        first = api.client.get("/admin/clinics", params=query | {"limit": 25}, headers=auth).json()
        assert len(first["items"]) == 25 and first["next_cursor"]
        second = api.client.get(
            "/admin/clinics", params=query | {"cursor": first["next_cursor"]}, headers=auth
        ).json()
        assert len(second["items"]) == 3
        for change in ({"q": "another"}, {"to": "2026-01-03T00:00:00Z"}):
            response = api.client.get(
                "/admin/clinics",
                params=query | change | {"cursor": first["next_cursor"]},
                headers=auth,
            )
            assert response.status_code == 422
        assert (
            api.client.get(
                "/admin/clinic-counts",
                params=query | {"to": "2026-01-01T00:00:00Z", "from": "2025-12-31T00:00:00Z"},
                headers=auth,
            ).json()["total"]
            == 0
        )
        assert (
            api.client.get(
                "/admin/clinic-counts", params={"q": marker + " 50%"}, headers=auth
            ).json()["total"]
            == 28
        )
    finally:
        with Session(api.engine) as session, session.begin():
            session.execute(delete(Clinic).where(Clinic.tenant_id.in_(ids)))


@pytest.mark.parametrize("actor", ["creator", "doctor", "other"])
def test_clinic_counts_are_platform_only(api, actor):
    assert api.client.get("/admin/clinic-counts", headers=api.user(actor)).status_code == 403
