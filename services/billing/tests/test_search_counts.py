from datetime import datetime, timezone

import pytest

from tests.test_queries import api as api


def test_payment_counts_search_dates_scope_and_cursor(api):
    client, headers, seed, state, tenant, foreign, patient, other, _ = api
    state["roles"] = []
    state["memberships"] = [(tenant, ["clinic_admin"], "active")]
    day = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for _ in range(28):
        seed(created_at=day, status="succeeded")
    seed(tenant_id=foreign, patient_id=other, created_at=day, status="succeeded")
    seed(created_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    params = {
        "tenant_id": str(tenant),
        "q": str(patient),
        "from": "2026-01-01T00:00:00Z",
        "to": "2026-01-02T00:00:00Z",
    }
    counts = client.get("/payment-counts", params=params, headers=headers())
    assert counts.status_code == 200
    assert counts.json()["total"] == counts.json()["filtered_total"] == 28
    assert counts.json()["purpose"]["consultation"] == 28
    assert counts.json()["status"]["succeeded"] == 28
    first = client.get("/payments", params=params | {"limit": 25}, headers=headers()).json()
    assert len(first["items"]) == 25 and first["next_cursor"]
    assert (
        client.get(
            "/payments",
            params=params | {"cursor": first["next_cursor"], "q": str(other)},
            headers=headers(),
        ).status_code
        == 422
    )
    summary = client.get("/commission-totals", params=params, headers=headers()).json()
    assert summary["payment_count"] == 28
    assert (
        client.get("/payment-counts", params=params | {"q": "%"}, headers=headers()).json()["total"]
        == 0
    )
    assert (
        client.get(
            "/payment-counts", params=params | {"tenant_id": str(foreign)}, headers=headers()
        ).json()["total"]
        == 0
    )
    state["memberships"][0] = (tenant, ["clinic_admin"], "revoked")
    assert client.get("/payment-counts", params=params, headers=headers()).status_code == 403


def test_payment_tab_facets_honor_the_other_selected_filter(api):
    client, headers, seed, state, tenant, _, _, _, _ = api
    state["roles"] = ["platform_admin"]
    seed(status="pending")
    seed(status="succeeded")
    from uuid import uuid4

    seed(
        purpose="medication_delivery",
        appointment_id=None,
        order_id=uuid4(),
        quote_id=uuid4(),
        status="succeeded",
    )
    result = client.get(
        "/payment-counts",
        params={"tenant_id": str(tenant), "purpose": "consultation", "status": "succeeded"},
        headers=headers(),
    ).json()
    assert result["purpose"] == {"consultation": 1, "medication_delivery": 1, "all": 2}
    assert result["status"]["pending"] == result["status"]["succeeded"] == 1
    assert result["filtered_total"] == 1 and result["total"] == 3


@pytest.mark.parametrize("role", ["patient", "doctor"])
def test_payment_counts_deny_non_admin_roles(api, role):
    client, headers, _, state, tenant, _, _, _, _ = api
    state["roles"] = ["patient"] if role == "patient" else []
    state["memberships"] = [(tenant, [role], "active")] if role == "doctor" else []
    assert (
        client.get(
            "/payment-counts", params={"tenant_id": str(tenant)}, headers=headers()
        ).status_code
        == 403
    )
