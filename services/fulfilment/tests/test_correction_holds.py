from uuid import UUID, uuid4

import pytest

from app.models import Order, PrescriptionCorrectionHold
from tests.test_api import OTHER_TENANT, PATIENT, RX, TENANT, create, identity
from tests.test_api import api as api


def path():
    return f"/clinics/{TENANT}/prescriptions/{RX}/prepare-correction"


@pytest.mark.parametrize("existing", [False, True])
def test_correction_holds_stop_old_orders_and_replay(api, existing):
    client, state, _ = api
    order = create(client).json() if existing else None
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    response = client.post(path(), json={"patient_id": str(PATIENT)})
    assert response.status_code == 200, response.text
    assert client.post(path(), json={"patient_id": str(PATIENT)}).json() == response.json()
    with state.sessions() as db:
        assert db.get(PrescriptionCorrectionHold, RX) is not None
        if order:
            assert db.get(Order, UUID(order["order_id"])).status == "cancelled"
    state.identity = identity()
    assert create(client, key="fresh").json()["error"]["code"] == "prescription_corrected"
    if existing:
        assert create(client).json()["error"]["code"] == "prescription_corrected"


@pytest.mark.parametrize(
    "changes",
    [
        {"payment_status": "pending"},
        {"payment_status": "succeeded", "status": "paid"},
        {"quote_id": uuid4()},
        {"medicine_status": "ready"},
        {"delivery_id": uuid4()},
    ],
)
def test_cannot_silently_correct_checkout_paid_or_prepared_orders(api, changes):
    client, state, _ = api
    order = create(client).json()
    with state.sessions.begin() as db:
        row = db.get(Order, UUID(order["order_id"]))
        for name, value in changes.items():
            setattr(row, name, value)
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    response = client.post(path(), json={"patient_id": str(PATIENT)})
    assert response.status_code == 409
    with state.sessions() as db:
        assert db.get(PrescriptionCorrectionHold, RX) is None


@pytest.mark.parametrize(
    "who",
    [
        identity(),
        identity(roles=(), clinic_role="doctor"),
        identity(roles=(), clinic_role="clinic_admin", tenant=OTHER_TENANT),
        identity(roles=(), clinic_role="clinic_admin", active=False),
    ],
)
def test_hold_is_clinic_admin_only(api, who):
    client, state, _ = api
    state.identity = who
    assert client.post(path(), json={"patient_id": str(PATIENT)}).status_code == 404
