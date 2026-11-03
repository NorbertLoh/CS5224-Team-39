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
    decision_body,
    headers,
    path,
    signing_key,
    tenant_token,
)

from app.models import Membership, Subject

# Reuse the real PostgreSQL/JWT fixtures from the identity API suite.
__all__ = ["api", "api_database", "signing_key"]


def evidence(api, actor="target", content=b"%PDF-1.4 synthetic licence"):
    return api.client.post(
        "/me/doctor-documents",
        content=content,
        headers=headers(api, actor) | {"Content-Type": "application/pdf"},
    )


def application_body(document_id, revision=0):
    return {
        "legal_name": "Synthetic applicant",
        "licence_number": "TEST-123",
        "licensing_authority": "Test licensing board",
        "specialty": "General practice",
        "document_id": document_id,
        "expected_revision": revision,
    }


def apply(api, actor="target"):
    document = evidence(api, actor)
    assert document.status_code == 201
    body = application_body(document.json()["document_id"])
    result = api.client.post("/me/doctor-application", json=body, headers=headers(api, actor))
    assert result.status_code == 200, result.text
    return result.json(), body


def review(api, subject="target", decision="approved", revision=1, actor="platform"):
    return api.client.post(
        f"/platform/doctor-applications/{api.ids[subject]}/review",
        json={
            "decision": decision,
            "reason": "Synthetic manual review",
            "expected_revision": revision,
        },
        headers=headers(api, actor),
    )


def assign(api, roles=None, actor="target", tenant=TENANT_A):
    result = api.client.put(
        path(tenant, api.ids[actor]),
        json={"roles": roles or ["doctor"]},
        headers=headers(api, "platform"),
    )
    assert result.status_code in {200, 201}
    return result.json()


def can_write(api, actor="target", tenant=TENANT_A):
    response = api.client.post(
        "/access-decisions",
        json=decision_body(api, actor, "clinical.write", tenant, actor),
        headers={"Authorization": "Bearer " + api.service_token()},
    )
    assert response.status_code == 200
    return response.json()["allowed"]


def test_assignment_is_pending_until_approved_and_active(api):
    assigned = assign(api)
    assert assigned["status"] == "active"
    assert assigned["subject"]["doctor_verification"] == "not_applied"
    assert api.client.get("/me", headers=headers(api, "target")).json()["memberships"] == []
    assert not can_write(api)
    application, _ = apply(api)
    assert application["status"] == "pending"
    assert not can_write(api)
    assert review(api).status_code == 200
    assert can_write(api)
    assert api.client.get("/me", headers=headers(api, "target")).json()["memberships"][0][
        "roles"
    ] == ["doctor"]
    assert (
        api.client.delete(
            path(subject=api.ids["target"]), headers=headers(api, "platform")
        ).status_code
        == 204
    )
    assert not can_write(api)


def test_approval_without_clinic_grants_no_clinical_rights(api):
    apply(api)
    assert review(api).status_code == 200
    assert not can_write(api)
    assign(api, tenant=TENANT_B)
    assert not can_write(api, tenant=TENANT_A)
    assert can_write(api, tenant=TENANT_B)


def test_approval_never_reactivates_revoked_membership(api):
    assign(api)
    apply(api)
    api.client.delete(path(subject=api.ids["target"]), headers=headers(api, "platform"))
    assert review(api).status_code == 200
    assert not can_write(api)
    with Session(api.engine) as session:
        membership = session.scalar(
            select(Membership).where(Membership.subject_id == api.ids["target"])
        )
        assert membership.status == "revoked"


def test_combined_admin_and_patient_rights_survive_pending_doctor_verification(api):
    with Session(api.engine) as session, session.begin():
        session.get(Subject, api.ids["target"]).global_roles = ["patient"]
    assign(api, ["doctor", "clinic_admin"])
    result = api.client.get("/me", headers=headers(api, "target")).json()
    assert result["global_roles"] == ["patient"]
    assert result["memberships"][0]["roles"] == ["clinic_admin"]
    assert api.client.get(path(), headers=headers(api, "target")).status_code == 200
    assert not can_write(api)


def test_rejection_resubmission_preserves_snapshot_and_rejects_stale_review(api):
    first, body = apply(api)
    assert review(api, decision="rejected").status_code == 200
    rejected = api.client.get("/me/doctor-application", headers=headers(api, "target")).json()
    assert rejected["rejection_reason"] == "Synthetic manual review"
    next_document = evidence(api, content=b"%PDF-1.4 corrected evidence").json()["document_id"]
    body.update(expected_revision=1, licence_number="TEST-456", document_id=next_document)
    resubmitted = api.client.post(
        "/me/doctor-application", json=body, headers=headers(api, "target")
    )
    assert resubmitted.json()["revision"] == 2
    assert resubmitted.json()["rejection_reason"] is None
    assert review(api, revision=1).status_code == 409
    assert review(api, revision=2).status_code == 200
    history = api.client.get(
        f"/platform/doctor-applications/{api.ids['target']}/history",
        headers=headers(api, "platform"),
    ).json()
    assert [event["action"] for event in history] == [
        "submitted",
        "rejected",
        "submitted",
        "approved",
    ]
    assert history[0]["snapshot"]["licence_number"] == "TEST-123"
    assert history[0]["snapshot"]["document_id"] == first["document_id"]
    assert history[-1]["snapshot"]["licence_number"] == "TEST-456"


@pytest.mark.parametrize("actor", ["patient", "doctor", "admin_a", "admin_b", "target"])
def test_review_and_history_are_platform_only(api, actor):
    apply(api)
    assert review(api, actor=actor).status_code == 403
    assert (
        api.client.get("/platform/doctor-applications", headers=headers(api, actor)).status_code
        == 403
    )
    assert (
        api.client.get(
            f"/platform/doctor-applications/{api.ids['target']}/history",
            headers=headers(api, actor),
        ).status_code
        == 403
    )


def test_platform_cannot_review_own_application(api):
    apply(api, "platform")
    assert review(api, subject="platform").status_code == 403


def test_private_documents_ownership_and_download_headers(api):
    document = evidence(api).json()["document_id"]
    endpoint = f"/doctor-documents/{document}"
    assert api.client.get(endpoint).status_code == 401
    for actor in ("patient", "doctor", "admin_a", "admin_b"):
        assert api.client.get(endpoint, headers=headers(api, actor)).status_code == 404
    for actor in ("target", "platform"):
        result = api.client.get(endpoint, headers=headers(api, actor))
        assert result.status_code == 200
        assert result.content.startswith(b"%PDF-")
        assert result.headers["Cache-Control"] == "no-store"
        assert result.headers["Content-Disposition"].startswith("attachment;")
        assert result.headers["X-Content-Type-Options"] == "nosniff"
    body = application_body(document)
    assert (
        api.client.post(
            "/me/doctor-application", json=body, headers=headers(api, "patient")
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "content,media_type,status",
    [
        (b"", "application/pdf", 422),
        (b"<html>not a PDF", "application/pdf", 422),
        (b"%PDF-" + b"x" * (5 * 1024 * 1024), "application/pdf", 413),
        (b"<svg/>", "image/svg+xml", 422),
        (b"\x89PNG\r\n\x1a\nimage", "image/png", 201),
    ],
    ids=["empty", "wrong-signature", "oversized", "unsupported", "png"],
)
def test_upload_size_and_format(api, content, media_type, status):
    result = api.client.post(
        "/me/doctor-documents",
        content=content,
        headers=headers(api, "target") | {"Content-Type": media_type},
    )
    assert result.status_code == status


def test_pending_application_cannot_be_edited_or_claim_approval(api):
    _, body = apply(api)
    assert (
        api.client.post(
            "/me/doctor-application", json=body, headers=headers(api, "target")
        ).status_code
        == 409
    )
    assert (
        api.client.post(
            "/me/doctor-application",
            json=body | {"status": "approved"},
            headers=headers(api, "target"),
        ).status_code
        == 422
    )
    assert (
        api.client.post(
            f"/platform/doctor-applications/{api.ids['target']}/review",
            json={"decision": "rejected", "reason": " ", "expected_revision": 1},
            headers=headers(api, "platform"),
        ).status_code
        == 422
    )


def test_concurrent_review_has_one_winner(api):
    apply(api)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda decision: review(api, decision=decision).status_code,
                ["approved", "rejected"],
            )
        )
    assert sorted(results) == [200, 409]


def test_concurrent_first_submission_has_one_winner(api):
    document = evidence(api).json()["document_id"]
    body = application_body(document)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: (
                    api.client.post(
                        "/me/doctor-application", json=body, headers=headers(api, "target")
                    ).status_code
                ),
                range(2),
            )
        )
    assert sorted(results) == [200, 409]


def test_directory_omits_unverified_doctors_and_lists_after_approval(api):
    api.app.state.settings.tenant_secret = SecretStr(TENANT_KEY)
    credential = {"Authorization": "Bearer " + tenant_token(aud="telelink-identity-doctors")}
    endpoint = f"/internal/clinics/{TENANT_A}/doctors"
    assign(api)
    apply(api)
    assert str(api.ids["target"]) not in {
        row["doctor_id"] for row in api.client.get(endpoint, headers=credential).json()["items"]
    }
    assert review(api).status_code == 200
    assert str(api.ids["target"]) in {
        row["doctor_id"] for row in api.client.get(endpoint, headers=credential).json()["items"]
    }


def test_application_endpoints_require_authentication(api):
    assert api.client.get("/me/doctor-application").status_code == 401
    assert api.client.get("/platform/doctor-applications").status_code == 401
    assert api.client.post("/me/doctor-documents", content=b"%PDF-").status_code == 401


def test_migration_refuses_to_discard_evidence_and_history(api):
    apply(api)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with pytest.raises(DBAPIError, match="Doctor verification evidence prevents downgrade"):
        command.downgrade(config, "0003")
    assert (
        api.client.get("/me/doctor-application", headers=headers(api, "target")).status_code == 200
    )


def test_review_queue_filters_status_and_paginates(api):
    apply(api, "target")
    apply(api, "patient")
    credential = headers(api, "platform")
    endpoint = "/platform/doctor-applications"
    first = api.client.get(endpoint, params={"limit": 1}, headers=credential).json()
    assert len(first) == 1
    second = api.client.get(
        endpoint, params={"limit": 1, "after": first[0]["subject_id"]}, headers=credential
    ).json()
    assert len(second) == 1 and second[0]["subject_id"] != first[0]["subject_id"]
    assert review(api).status_code == 200
    assert len(api.client.get(endpoint, headers=credential).json()) == 1
    assert str(api.ids["target"]) in {
        row["subject_id"]
        for row in api.client.get(
            endpoint, params={"status": "approved"}, headers=credential
        ).json()
    }
