from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import Order, PrescriptionPrice
from tests.test_api import ITEM, OTHER_TENANT, PATIENT, RX, TENANT, create, identity
from tests.test_api import api as api


def named_context(state):
    state.source.context = state.source.context.model_copy(
        update={
            "pricing_mode": "prescription",
            "items": [
                state.source.context.items[0].model_copy(
                    update={"display_name": "Typed test medicine"}
                )
            ],
        }
    )


def body(amount=250):
    return {
        "patient_id": str(PATIENT),
        "items": [
            {
                "prescription_item_id": str(ITEM),
                "unit_price": {"amount_minor": amount, "currency": "SGD"},
            }
        ],
    }


def test_individual_prices_gate_orders_and_do_not_reuse_rates(api):
    client, state, _ = api
    named_context(state)
    path = f"/clinics/{TENANT}/prescriptions/{RX}/prices"
    assert create(client).json()["error"]["code"] == "medication_unpriced"
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    response = client.put(path, json=body())
    assert response.status_code == 200 and response.json()["locked"] is False
    with state.sessions() as db:
        row = db.scalar(select(PrescriptionPrice))
        assert row.priced_by == state.identity.subject_id and row.quantity == 2
    state.identity = identity()
    other = create(client, key="other-rx", rx=uuid4())
    assert other.status_code == 409 and other.json()["error"]["code"] == "medication_unpriced"
    opened = create(client)
    assert opened.status_code == 201 and opened.json()["medication_subtotal"]["amount_minor"] == 500
    with state.sessions() as db:
        assert db.scalar(select(Order)).pricing_mode == "prescription"
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    assert client.get(path).json()["locked"] is True
    assert client.put(path, json=body()).status_code == 200
    changed = client.put(path, json=body(300))
    assert (
        changed.status_code == 409
        and changed.json()["error"]["code"] == "prescription_price_locked"
    )


@pytest.mark.parametrize(
    "who",
    [
        identity(),
        identity(roles=(), clinic_role="doctor"),
        identity(roles=(), clinic_role="clinic_admin", tenant=OTHER_TENANT),
        identity(roles=(), clinic_role="clinic_admin", active=False),
    ],
)
def test_only_owning_active_admin_prices(api, who):
    client, state, _ = api
    named_context(state)
    state.identity = who
    path = f"/clinics/{TENANT}/prescriptions/{RX}/prices"
    assert client.put(path, json=body()).status_code == 404
    assert client.get(path).status_code == 404


def test_pricing_rejects_wrong_patient_lines_and_unsafe_totals(api):
    client, state, _ = api
    named_context(state)
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    path = f"/clinics/{TENANT}/prescriptions/{RX}/prices"
    assert client.put(path, json=body() | {"patient_id": str(uuid4())}).status_code == 404
    assert client.put(path, json=body() | {"items": []}).status_code == 422
    wrong = body()
    wrong["items"][0]["prescription_item_id"] = str(uuid4())
    assert client.put(path, json=wrong).status_code == 422
    duplicate = body()
    duplicate["items"] *= 2
    assert client.put(path, json=duplicate).status_code == 422
    assert client.put(path, json=body(-1)).status_code == 422
    assert client.put(path, json=body(9007199254740991)).status_code == 422
    assert client.put(path, json=body() | {"instructions": "not accepted"}).status_code == 422
