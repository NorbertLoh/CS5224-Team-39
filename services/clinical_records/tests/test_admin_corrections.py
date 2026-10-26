from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session
from test_api import PREFIX, body, create
from test_api import api as api
from test_api import database as database
from test_issuance import outbox_row

from app.models import Prescription, PrescriptionCorrection


def setup_draft(api):
    client, state, _, appointment, _, _, _ = api
    draft = create(api)
    assert (
        client.post(PREFIX + f"/prescriptions/{draft['prescription_id']}/issue").status_code == 200
    )
    state["user"] = "admin"
    state["appointment"] = appointment.model_copy(update={"status": "completed"})
    return (
        draft,
        PREFIX + f"/clinics/{appointment.tenant_id}/prescriptions/{draft['prescription_id']}",
    )


def test_admin_add_edit_remove_and_retry_preserves_original(api):
    client, state, users, appointment, medication, engine, _ = api
    original, path = setup_draft(api)
    extra = uuid4()
    state["extra_medications"] = [
        dict(
            medication_id=str(extra),
            tenant_id=str(appointment.tenant_id),
            display_name="Added medicine",
            active=True,
        )
    ]
    changed = {
        "reason": "Correct quantity and add missing medicine",
        "items": [
            dict(medication_id=str(medication), quantity=4, instructions="Corrected instructions"),
            dict(medication_id=str(extra), quantity=1, instructions="Added instructions"),
        ],
    }
    assert client.get(path + "/correction").status_code == 200
    first = client.post(path + "/corrections", json=changed)
    assert first.status_code == 200, first.text
    replacement = first.json()["prescription"]
    assert replacement["status"] == "issued"
    assert replacement["doctor_id"] == str(appointment.doctor_id)
    assert len(replacement["items"]) == 2
    assert client.post(path + "/corrections", json=changed).json() == first.json()
    with Session(engine) as db:
        old = db.get(Prescription, UUID(original["prescription_id"]))
        assert old.status == "voided"
        history = db.get(PrescriptionCorrection, old.prescription_id)
        assert history.corrected_by == users["admin"].subject_id
    assert outbox_row(engine, replacement["prescription_id"]) is not None
    assert (
        client.post(path + "/corrections", json=changed | {"reason": "Different"}).status_code
        == 409
    )
    path = (
        PREFIX + f"/clinics/{appointment.tenant_id}/prescriptions/{replacement['prescription_id']}"
    )
    withdrawn = client.post(
        path + "/corrections", json={"reason": "Remove medications entered in error", "items": []}
    )
    assert withdrawn.status_code == 200 and withdrawn.json()["prescription"] is None


@pytest.mark.parametrize(
    "user",
    [
        "doctor",
        "patient",
        "other_patient",
        "other_doctor",
        "cross_tenant",
        "platform",
        "revoked_admin",
        "other_clinic_admin",
    ],
)
def test_only_active_owning_admin_can_correct(api, user):
    client, state, users, _, medication, _, _ = api
    _, path = setup_draft(api)
    if user == "revoked_admin":
        users["admin"].memberships[0].__dict__["status"] = "revoked"
    elif user == "other_clinic_admin":
        users["admin"].memberships[0].__dict__["tenant_id"] = uuid4()
    else:
        state["user"] = user
    assert client.get(path + "/correction").status_code == 404
    assert (
        client.post(path + "/corrections", json=body(medication) | {"reason": "Fix"}).status_code
        == 404
    )


@pytest.mark.parametrize("failure", [409, 503])
def test_financial_hold_failure_keeps_original_issued(api, failure):
    client, state, _, _, medication, engine, _ = api
    original, path = setup_draft(api)
    state["correction_failure"] = failure
    result = client.post(path + "/corrections", json=body(medication) | {"reason": "Fix quantity"})
    assert result.status_code == failure
    with Session(engine) as db:
        assert db.get(Prescription, UUID(original["prescription_id"])).status == "issued"
        assert db.get(PrescriptionCorrection, UUID(original["prescription_id"])) is None


def test_concurrent_identical_corrections_share_one_replacement(api):
    client, _, _, _, medication, _, _ = api
    _, path = setup_draft(api)
    payload = body(medication) | {"reason": "Corrected medication instructions"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda _: client.post(path + "/corrections", json=payload), range(2))
        )
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
