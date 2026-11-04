"""Real PostgreSQL ownership, HTTP service auth and concurrent participant placement."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from telelink_common.service_auth import service_token

from app.models import Admission, RoomAssignment, SignallingNode
from app.services import matchmaker
from tests.test_admission_api import api as admission_api
from tests.test_admission_api import database, internal, issue  # noqa: F401

api = admission_api


@pytest.fixture
def matched(api):
    api.settings.signalling_matchmaker = True
    with Session(api.database) as db, db.begin():
        db.execute(
            update(SignallingNode).values(
                lease_expires_at=matchmaker.clock(db) - timedelta(seconds=1)
            )
        )
    return api


def headers(api):
    return {
        "Authorization": "Bearer "
        + service_token(
            api.settings.signalling_secret, "signalling", "telelink-consultation-admission"
        )
    }


def heartbeat(api, node=None, **changes):
    node = node or {
        "node_id": str(uuid4()),
        "node_token": "n" * 43,
        "internal_url": "http://127.0.0.1:9000",
        "draining": False,
    }
    return node | changes, api.client.post(
        "/internal/signalling/heartbeat", headers=headers(api), json=node | changes
    )


def expire(api, node):
    with Session(api.database) as db, db.begin():
        db.execute(
            update(SignallingNode)
            .where(SignallingNode.node_id == UUID(node["node_id"]))
            .values(lease_expires_at=matchmaker.clock(db) - timedelta(seconds=1))
        )


def consume(api, grant, node, action="consume", **changes):
    return internal(
        api, action, grant, node_id=node["node_id"], node_token=node["node_token"], **changes
    )


def test_concurrent_participants_share_owner_and_wrong_node_cannot_consume(matched):
    first, response = heartbeat(matched)
    assert response.status_code == 200
    other, response = heartbeat(matched)
    assert response.status_code == 200
    with ThreadPoolExecutor(2) as pool:
        responses = list(
            pool.map(lambda subject: issue(matched, subject), [matched.patient, matched.doctor])
        )
    assert [r.status_code for r in responses] == [201, 201]
    patient, doctor = [r.json() for r in responses]
    assert patient["node_id"] == doctor["node_id"]
    assert patient["assignment_version"] == doctor["assignment_version"] == 1
    assert patient["signalling_path"] == f"/peerjs/nodes/{patient['node_id']}"
    owner, wrong = (first, other) if patient["node_id"] == first["node_id"] else (other, first)
    assert consume(matched, patient, wrong).status_code == 403
    assert internal(matched, "consume", patient).status_code == 403
    assert consume(matched, patient, owner).status_code == 200
    assert consume(matched, doctor, owner).status_code == 200
    assert consume(matched, patient, owner, "check").status_code == 200
    assert consume(matched, patient, owner, "release").status_code == 204


def test_owner_loss_reassigns_before_admission_expiry_and_fences_old_grants(matched):
    owner, _ = heartbeat(matched)
    patient = issue(matched).json()
    doctor = issue(matched, matched.doctor).json()
    assert consume(matched, patient, owner).status_code == 200
    expire(matched, owner)
    assert consume(matched, patient, owner, "check").status_code == 403
    assert heartbeat(matched, owner)[1].status_code == 403  # No resurrection of a boot identity.
    assert issue(matched).status_code == 503
    replacement, _ = heartbeat(matched)
    fresh = issue(matched).json()
    assert fresh["node_id"] == replacement["node_id"]
    assert fresh["assignment_version"] == 2
    assert fresh["peer_id"] != patient["peer_id"]
    assert consume(matched, doctor, owner).status_code == 403
    assert consume(matched, doctor, replacement).status_code == 403
    assert consume(matched, fresh, replacement).status_code == 200
    assert issue(matched, matched.doctor).json()["assignment_version"] == 2


def test_draining_keeps_existing_room_but_no_new_assignments(matched):
    owner, _ = heartbeat(matched)
    patient = issue(matched).json()
    assert heartbeat(matched, owner, draining=True)[1].status_code == 200
    doctor = issue(matched, matched.doctor).json()
    assert doctor["node_id"] == patient["node_id"]
    assert consume(matched, patient, owner).status_code == 200
    # Draining is irreversible for a process identity.
    assert heartbeat(matched, owner, draining=False)[1].status_code == 200
    matched.appointment_id = uuid4()
    matched.state["appointment"]["appointment_id"] = str(matched.appointment_id)
    matched.state["payment"]["appointment_id"] = str(matched.appointment_id)
    assert issue(matched).status_code == 503
    replacement, _ = heartbeat(matched)
    assert issue(matched).json()["node_id"] == replacement["node_id"]


def test_heartbeat_auth_address_and_boot_identity_guards(matched):
    owner, _ = heartbeat(matched)
    assert matched.client.post("/internal/signalling/heartbeat", json=owner).status_code == 401
    assert matched.client.get(f"/internal/signalling/nodes/{owner['node_id']}").status_code == 401
    assert heartbeat(matched, owner, node_token="x" * 43)[1].status_code == 403
    for address in [
        "http://169.254.169.254:9000",
        "http://example.com:9000",
        "http://127.0.0.1:8004",
        "http://user:secret@127.0.0.1:9000",
        "http://127.0.0.1:9000/path",
        "http://127.0.0.1:9000?x=1",
    ]:
        assert heartbeat(matched, internal_url=address)[1].status_code == 403
    route = f"/internal/signalling/nodes/{owner['node_id']}"
    assert matched.client.get(route, headers=headers(matched)).json() == {
        "internal_url": owner["internal_url"]
    }
    expire(matched, owner)
    assert matched.client.get(route, headers=headers(matched)).status_code == 503


def test_reassignment_still_checks_membership_payment_and_completion(matched):
    owner, _ = heartbeat(matched)
    grant = issue(matched).json()
    assert consume(matched, grant, owner).status_code == 200
    expire(matched, owner)
    heartbeat(matched)
    matched.state["decision_allowed"] = False
    assert issue(matched).status_code == 404
    matched.state["decision_allowed"] = True
    matched.state["payment"]["status"] = "refunded"
    assert issue(matched).status_code == 409
    matched.state["payment"]["status"] = "succeeded"
    matched.state["appointment"]["status"] = "completed"
    assert issue(matched).status_code == 409


def test_legacy_grant_is_revoked_when_matchmaker_enabled(api):
    grant = issue(api).json()
    api.settings.signalling_matchmaker = True
    assert internal(api, "consume", grant).status_code == 403
    with Session(api.database) as db:
        lease = db.scalar(select(Admission).where(Admission.peer_id == UUID(grant["peer_id"])))
        assert lease.consumed_at is None
        assert db.get(RoomAssignment, lease.session_id) is None
