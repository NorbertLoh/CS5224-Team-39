"""Renewal keeps a consumed peer alive, with fresh participant and owner checks."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.models import Admission
from tests.test_admission_api import api as admission_api
from tests.test_admission_api import database, internal, issue  # noqa: F401
from tests.test_matchmaker import expire, heartbeat

api = admission_api


def renew(api, grant, subject=None, **changes):
    return api.client.post(
        "/admissions/renew",
        headers=api.headers(subject or api.patient),
        json={"peer_id": grant["peer_id"], "token": grant["token"]} | changes,
    )


def test_renewal_passes_original_join_deadline_without_rotating_peer(api):
    grant = issue(api).json()
    assert renew(api, grant).status_code == 403
    assert internal(api, "consume", grant).status_code == 200
    for _ in range(5):
        api.state["clock"] += timedelta(seconds=30)
        response = renew(api, grant)
        assert response.status_code == 200, response.text
        assert response.json()["peer_id"] == grant["peer_id"]
        assert internal(api, "check", grant).json() == response.json()
        assert internal(api, "consume", grant).status_code == 403
        assert issue(api).status_code == 409
    with Session(api.database) as db:
        lease = db.get(Admission, (UUID(grant["session_id"]), api.patient))
        assert lease.expires_at == lease.issued_at + timedelta(seconds=60)
        assert lease.active_expires_at > lease.expires_at
    api.state["clock"] += timedelta(seconds=60)
    assert renew(api, grant).status_code == 403
    assert internal(api, "check", grant).status_code == 403
    assert issue(api).status_code == 201


def test_renewal_requires_current_user_and_consumed_unreleased_grant(api):
    grant = issue(api).json()
    assert (
        api.client.post(
            "/admissions/renew", json={"peer_id": grant["peer_id"], "token": grant["token"]}
        ).status_code
        == 401
    )
    assert internal(api, "consume", grant).status_code == 200
    assert renew(api, grant, api.doctor).status_code == 403
    assert renew(api, grant, uuid4()).status_code in {403, 404}
    assert renew(api, grant, token="x" * 43).status_code == 403
    assert renew(api, grant, peer_id=str(uuid4())).status_code == 403
    assert renew(api, grant, expires_at="2099-01-01T00:00:00Z").status_code == 422
    assert internal(api, "release", grant).status_code == 204
    assert renew(api, grant).status_code == 403


@pytest.mark.parametrize("failure", ["membership", "payment", "completed", "unavailable"])
def test_renewal_rechecks_access_and_never_extends_on_denial(api, failure):
    grant = issue(api).json()
    assert internal(api, "consume", grant).status_code == 200
    api.state["clock"] += timedelta(seconds=30)
    if failure == "membership":
        api.state["decision_allowed"] = False
    elif failure == "payment":
        api.state["payment"]["status"] = "refunded"
    elif failure == "completed":
        api.state["appointment"]["status"] = "completed"
    else:
        api.state["sources_status"] = 503
    assert renew(api, grant).status_code in {403, 404, 409, 503}
    with Session(api.database) as db:
        lease = db.get(Admission, (UUID(grant["session_id"]), api.patient))
        assert lease.active_expires_at == lease.expires_at


def test_concurrent_renewals_and_release_do_not_revive_connection(api):
    grant = issue(api).json()
    assert internal(api, "consume", grant).status_code == 200
    api.state["clock"] += timedelta(seconds=30)
    with ThreadPoolExecutor(3) as pool:
        responses = list(pool.map(lambda _: renew(api, grant), range(3)))
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()["expires_at"] for r in responses}) == 1
    with ThreadPoolExecutor(2) as pool:
        renewal = pool.submit(renew, api, grant)
        released = pool.submit(internal, api, "release", grant)
        assert renewal.result().status_code in {200, 403}
        assert released.result().status_code == 204
    assert renew(api, grant).status_code == 403


def test_renewal_respects_call_limit_and_scheduled_end(api):
    api.settings.call_max_seconds = 300
    grant = issue(api).json()
    assert internal(api, "consume", grant).status_code == 200
    for _ in range(9):
        api.state["clock"] += timedelta(seconds=30)
        assert renew(api, grant).status_code == 200
    deadline = datetime.fromisoformat(grant["call_expires_at"])
    observed = datetime.fromisoformat(
        internal(api, "check", grant).json()["expires_at"].replace("Z", "+00:00")
    )
    assert abs(observed - deadline) < timedelta(milliseconds=1)
    api.state["clock"] += timedelta(seconds=30)
    assert renew(api, grant).status_code == 403
    grant = issue(api).json()
    assert internal(api, "consume", grant).status_code == 200
    with Session(api.database) as db:
        lease = db.get(Admission, (UUID(grant["session_id"]), api.patient))
        # Confirm join expiry remains bounded independently of the active limit.
        assert lease.expires_at <= lease.issued_at + timedelta(seconds=300)


def test_renewal_cannot_cross_scheduled_end(api):
    api.state["clock"] = datetime.fromisoformat(api.state["appointment"]["ends_at"]) - timedelta(
        seconds=20
    )
    grant = issue(api).json()
    assert internal(api, "consume", grant).status_code == 200
    api.state["clock"] += timedelta(seconds=10)
    assert renew(api, grant).json()["expires_at"] == grant["expires_at"]
    api.state["clock"] += timedelta(seconds=10)
    assert renew(api, grant).status_code == 403


def test_expired_owner_cannot_renew_even_before_active_deadline(api):
    api.settings.signalling_matchmaker = True
    owner, response = heartbeat(api)
    assert response.status_code == 200
    grant = issue(api).json()
    assert (
        internal(
            api, "consume", grant, node_id=owner["node_id"], node_token=owner["node_token"]
        ).status_code
        == 200
    )
    expire(api, owner)
    assert renew(api, grant).status_code == 403
    heartbeat(api)
    fresh = issue(api).json()
    assert fresh["assignment_version"] > grant["assignment_version"]
    assert renew(api, grant).status_code == 403
