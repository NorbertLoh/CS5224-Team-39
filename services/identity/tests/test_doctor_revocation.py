from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_api import (
    TENANT_A,
    TENANT_B,
    TENANT_KEY,
    api,
    api_database,
    headers,
    path,
    signing_key,
    tenant_token,
)
from test_doctor_applications import apply, assign, can_write, review

from app.models import Membership, Subject

__all__ = ["api", "api_database", "signing_key"]


def test_revoke_blocks_access_and_allows_resubmission_then_reapproval(api):
    assigned = assign(api)
    _, body = apply(api)
    assert review(api).status_code == 200
    credential = headers(api, "target")
    assert api.client.get("/me", headers=credential).json()["memberships"][0]["roles"] == ["doctor"]
    assert can_write(api)
    revoked = review(api, decision="revoked")
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert revoked.json()["rejection_reason"] == "Synthetic manual review"
    assert not can_write(api)
    assert api.client.get("/me", headers=credential).json()["memberships"] == []
    staff = api.client.get(path(), headers=headers(api, "platform")).json()["items"]
    membership = next(item for item in staff if item["membership_id"] == assigned["membership_id"])
    assert membership["status"] == "active"
    assert membership["subject"]["doctor_verification"] == "revoked"
    queue = api.client.get(
        "/platform/doctor-applications",
        params={"status": "revoked"},
        headers=headers(api, "platform"),
    ).json()
    assert queue[0]["subject_id"] == str(api.ids["target"])
    assert review(api, decision="revoked").status_code == 409
    assert review(api).status_code == 409
    body.update(expected_revision=1, specialty="Updated specialty")
    result = api.client.post("/me/doctor-application", json=body, headers=credential)
    assert result.status_code == 200
    assert result.json()["status"] == "pending" and result.json()["revision"] == 2
    assert result.json()["rejection_reason"] is None
    assert not can_write(api)
    assert review(api, decision="revoked", revision=1).status_code == 409
    assert review(api, revision=2).status_code == 200
    assert can_write(api)
    events = api.client.get(
        f"/platform/doctor-applications/{api.ids['target']}/history",
        headers=headers(api, "platform"),
    ).json()
    assert [event["action"] for event in events] == [
        "submitted",
        "approved",
        "revoked",
        "submitted",
        "approved",
    ]
    assert events[2]["actor_id"] == str(api.ids["platform"])
    assert events[2]["snapshot"]["review_reason"] == "Synthetic manual review"


@pytest.mark.parametrize("actor", ["patient", "doctor", "admin_a", "target"])
def test_only_platform_can_revoke_approved_applications(api, actor):
    apply(api)
    assert review(api).status_code == 200
    assert review(api, decision="revoked", actor=actor).status_code == 403
    assert (
        api.client.get("/me/doctor-application", headers=headers(api, "target")).json()["status"]
        == "approved"
    )


def test_revocation_preserves_independent_roles_and_revoked_clinic_membership(api):
    with Session(api.engine) as session, session.begin():
        session.get(Subject, api.ids["target"]).global_roles = ["patient"]
    assign(api, ["doctor", "clinic_admin"])
    assign(api, tenant=TENANT_B)
    apply(api)
    assert review(api).status_code == 200
    api.client.delete(path(TENANT_B, api.ids["target"]), headers=headers(api, "platform"))
    assert review(api, decision="revoked").status_code == 200
    identity = api.client.get("/me", headers=headers(api, "target")).json()
    assert identity["global_roles"] == ["patient"]
    assert identity["memberships"][0]["roles"] == ["clinic_admin"]
    assert not can_write(api)
    assert not can_write(api, tenant=TENANT_B)
    with Session(api.engine) as session:
        membership = session.scalar(
            select(Membership).where(
                Membership.subject_id == api.ids["target"], Membership.tenant_id == TENANT_B
            )
        )
        assert membership.status == "revoked"


def test_revoke_requires_approved_application_reason_and_current_revision(api):
    apply(api)
    assert review(api, decision="revoked").status_code == 409
    assert review(api).status_code == 200
    assert review(api, decision="revoked", revision=2).status_code == 409
    result = api.client.post(
        f"/platform/doctor-applications/{api.ids['target']}/review",
        json={"decision": "revoked", "reason": " ", "expected_revision": 1},
        headers=headers(api, "platform"),
    )
    assert result.status_code == 422
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: review(api, decision="revoked").status_code, range(2)))
    assert sorted(results) == [200, 409]


def test_revoked_verification_is_hidden_from_directory_and_prevents_downgrade(api):
    assign(api)
    apply(api)
    assert review(api).status_code == 200
    assert review(api, decision="revoked").status_code == 200
    api.app.state.settings.tenant_secret = SecretStr(TENANT_KEY)
    credential = {"Authorization": "Bearer " + tenant_token(aud="telelink-identity-doctors")}
    rows = api.client.get(f"/internal/clinics/{TENANT_A}/doctors", headers=credential).json()[
        "items"
    ]
    assert str(api.ids["target"]) not in {row["doctor_id"] for row in rows}
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with pytest.raises(DBAPIError, match="Revoked doctor applications prevent downgrade"):
        command.downgrade(config, "0005")
