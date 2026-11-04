from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session
from test_api import (
    TENANT_B,
    api,
    api_database,
    approve_fixture_doctor,
    headers,
    signing_key,
)
from test_doctor_applications import apply, assign, review

from app.models import DoctorApplication, DoctorDocument, Subject

__all__ = ["api", "api_database", "signing_key"]
ENDPOINT = "/platform/doctor-applications/counts"


def test_totals_follow_application_lifecycle_and_do_not_count_clinic_memberships(api):
    _, body = apply(api)
    apply(api, "patient")
    apply(api, "other_patient")
    assign(api)
    assign(api, tenant=TENANT_B)
    credential = headers(api, "platform")
    assert api.client.get(ENDPOINT, headers=credential).json() == {
        "pending": 3,
        "approved": 1,
        "rejected": 0,
        "revoked": 0,
        "total": 4,
    }
    assert review(api, decision="rejected").status_code == 200
    assert review(api, subject="patient").status_code == 200
    assert review(api, subject="patient", decision="revoked").status_code == 200
    assert api.client.get(ENDPOINT, headers=credential).json() == {
        "pending": 1,
        "approved": 1,
        "rejected": 1,
        "revoked": 1,
        "total": 4,
    }
    body["expected_revision"] = 1
    assert (
        api.client.post(
            "/me/doctor-application", json=body, headers=headers(api, "target")
        ).status_code
        == 200
    )
    assert api.client.get(ENDPOINT, headers=credential).json() == {
        "pending": 2,
        "approved": 1,
        "rejected": 0,
        "revoked": 1,
        "total": 4,
    }


@pytest.mark.parametrize("actor", ["patient", "doctor", "admin_a", "target"])
def test_application_counts_are_platform_only(api, actor):
    assert api.client.get(ENDPOINT, headers=headers(api, actor)).status_code == 403


def test_application_counts_require_sign_in(api):
    assert api.client.get(ENDPOINT).status_code == 401


def test_counts_include_applications_beyond_the_first_page(api):
    ids = [uuid4() for _ in range(30)]
    try:
        with Session(api.engine) as session, session.begin():
            for subject_id in ids:
                session.add(
                    Subject(
                        subject_id=subject_id,
                        cognito_sub=f"count-test-{subject_id}",
                        display_name="Synthetic count test",
                        global_roles=[],
                    )
                )
            session.flush()
            for subject_id in ids:
                approve_fixture_doctor(session, subject_id)
        credential = headers(api, "platform")
        page = api.client.get(
            "/platform/doctor-applications",
            params={"status": "approved", "limit": 25},
            headers=credential,
        ).json()
        assert len(page) == 25
        counts = api.client.get(ENDPOINT, headers=credential)
        assert counts.status_code == 200
        assert counts.json() == {
            "pending": 0,
            "approved": 31,
            "rejected": 0,
            "revoked": 0,
            "total": 31,
        }
    finally:
        with Session(api.engine) as session, session.begin():
            session.execute(delete(DoctorApplication).where(DoctorApplication.subject_id.in_(ids)))
            session.execute(delete(DoctorDocument).where(DoctorDocument.subject_id.in_(ids)))
            session.execute(delete(Subject).where(Subject.subject_id.in_(ids)))
