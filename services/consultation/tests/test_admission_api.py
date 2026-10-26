"""Actual JWT authentication, HTTP adapters and PostgreSQL; upstream transport fixtures explicit."""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from telelink_common.access import IdentityClient
from telelink_common.service_auth import service_token

from app.database import create_database_engine
from app.integrations.upstream import AdmissionSources
from app.main import create_app
from app.models import Admission, ConsultationSession
from app.services import admissions
from app.services.lifecycle import transition
from app.settings import Settings


@pytest.fixture(scope="module")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to disposable PostgreSQL")
    if os.environ.get("CONSULTATION_TEST_ALLOW_RESET") != "1":
        pytest.fail("Set CONSULTATION_TEST_ALLOW_RESET=1 for disposable data only")
    old_url = os.environ.get("SERVICE_DATABASE_URL")
    os.environ["SERVICE_DATABASE_URL"] = url
    try:
        command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
        engine = create_database_engine(url)
        yield engine
        engine.dispose()
    finally:
        if old_url is None:
            os.environ.pop("SERVICE_DATABASE_URL", None)
        else:
            os.environ["SERVICE_DATABASE_URL"] = old_url


@pytest.fixture
def api(database, monkeypatch):
    tenant, doctor, patient, appointment_id, payment_id = [uuid4() for _ in range(5)]
    clock = datetime.now(timezone.utc)
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=os.environ["TEST_DATABASE_URL"],
        auth_issuer="http://auth.test/pool",
        auth_jwks_url="http://auth.test/jwks",
        auth_client_id="v02-web",
        identity_url="http://identity.test",
        scheduling_url="http://scheduling.test",
        billing_url="http://billing.test",
        identity_secret="v02-identity-secret-at-least-32-bytes",
        scheduling_secret="v02-scheduling-secret-at-least-32-bytes",
        billing_secret="v02-billing-secret-at-least-32-bytes",
        signalling_secret="v02-signalling-secret-at-least-32-bytes",
        records_url="http://records.test/api/v1/clinical-records",
        records_secret="u17-records-secret-at-least-32-bytes",
    )
    appointment = dict(
        appointment_id=str(appointment_id),
        tenant_id=str(tenant),
        patient_id=str(patient),
        doctor_id=str(doctor),
        status="confirmed",
        starts_at=(clock - timedelta(minutes=1)).isoformat(),
        ends_at=(clock + timedelta(minutes=29)).isoformat(),
        payment_id=str(payment_id),
        payment_resolution="confirmed",
        consultation_price={"amount_minor": 5000, "currency": "SGD"},
    )
    payment = dict(
        payment_id=str(payment_id),
        tenant_id=str(tenant),
        patient_id=str(patient),
        appointment_id=str(appointment_id),
        purpose="consultation",
        status="succeeded",
        resolution="none",
        amount=appointment["consultation_price"].copy(),
    )
    state = dict(
        appointment=appointment,
        payment=payment,
        clock=clock,
        roles={str(patient): ["patient"], str(doctor): []},
        doctor_active=True,
        sources_status=200,
        identity_status=200,
        decision_allowed=True,
    )
    monkeypatch.setattr(admissions, "now", lambda: state["clock"])
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="v02", use="sig", alg="RS256")
    app = create_app(settings)
    app.state.token_verifier.jwks.fetch_data = lambda: {"keys": [jwk]}

    def user_headers(subject=patient, **changes):
        timestamp = int(time.time())
        claims = {
            "iss": settings.auth_issuer,
            "sub": str(subject),
            "iat": timestamp,
            "exp": timestamp + 300,
            "token_use": "access",
            "client_id": "v02-web",
        } | changes
        return {
            "Authorization": "Bearer "
            + jwt.encode(claims, key, algorithm="RS256", headers={"kid": "v02"})
        }

    def transport(request):
        if request.url.path == "/me":
            if state["identity_status"] != 200:
                return httpx.Response(state["identity_status"])
            token = request.headers["authorization"].split()[1]
            subject = jwt.decode(token, key.public_key(), algorithms=["RS256"])["sub"]
            member = dict(
                membership_id=str(uuid4()),
                subject_id=subject,
                tenant_id=str(tenant),
                roles=["doctor"],
                status="active" if state["doctor_active"] else "revoked",
                created_at=clock.isoformat(),
                updated_at=clock.isoformat(),
            )
            return httpx.Response(
                200,
                json=dict(
                    subject_id=subject,
                    cognito_sub=subject,
                    display_name="Synthetic",
                    global_roles=state["roles"].get(subject, []),
                    memberships=[member] if subject == str(doctor) else [],
                ),
            )
        service = request.url.host.split(".")[0]
        if service == "records" and request.url.path.endswith("/finalize-prescription"):
            # This owning-service endpoint authenticates the assigned doctor's
            # actual JWT, rather than accepting a browser-supplied identity.
            claims = jwt.decode(
                request.headers["authorization"].split()[1],
                key.public_key(),
                algorithms=["RS256"],
            )
            assert claims["sub"] == str(doctor)
            assert state["appointment"]["status"] in {"in_progress", "completed"}
            state["prescription_calls"] = state.get("prescription_calls", 0) + 1
            if state.get("prescription_failure"):
                return httpx.Response(state["prescription_failure"])
            if state.pop("lost_prescription_response", False):
                state["issued_prescription"] = str(uuid4())
                return httpx.Response(503)
            links = {
                name: state["appointment"][name]
                for name in ("appointment_id", "tenant_id", "patient_id", "doctor_id")
            }
            if state.get("wrong_prescription_context"):
                links["tenant_id"] = str(uuid4())
            return httpx.Response(
                200,
                json={
                    **links,
                    "prescription_id": state.get("issued_prescription"),
                    "status": "issued" if state.get("issued_prescription") else "none",
                },
            )
        claims = jwt.decode(
            request.headers["authorization"].split()[1],
            getattr(settings, service + "_secret").get_secret_value(),
            algorithms=["HS256"],
            issuer="telelink-service:consultation",
            audience="telelink-" + service + "-consultation",
        )
        assert claims["sub"] == "consultation" and request.headers["x-request-id"]
        if state["sources_status"] != 200:
            return httpx.Response(state["sources_status"], json={"private": "do not reflect"})
        if service == "scheduling":
            if request.method == "POST":
                action = request.url.path.rsplit("/", 1)[-1]
                assert action in {"start", "complete"}
                if action == "complete":
                    assert state.get("prescription_calls", 0) > 0
                state["appointment"]["status"] = "in_progress" if action == "start" else "completed"
                if state.pop("lost_scheduling_response", False):
                    return httpx.Response(503)
            return httpx.Response(200, json=state["appointment"])
        if service == "billing":
            return httpx.Response(200, json=state["payment"])
        if service == "records":
            body = json.loads(request.content)
            assert state["appointment"]["status"] == "completed"
            state["mc_calls"] = state.get("mc_calls", 0) + 1
            if state.pop("lost_mc_response", False):
                return httpx.Response(503)
            return httpx.Response(200, json={**body, "finalized_at": body["completed_at"]})
        body = json.loads(request.content)
        assert body["action"] == "consultation.join"
        subject = body["subject_id"]
        own = subject == str(patient) and "patient" in state["roles"].get(subject, [])
        assigned = subject == str(doctor) and state["doctor_active"]
        return httpx.Response(
            200,
            json={
                "allowed": state["decision_allowed"] and (own or assigned),
                "reason": "own_appointment"
                if own
                else "assigned_doctor"
                if assigned
                else "not_authorized",
            },
        )

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.identity_client.close()
        app.state.sources.close()
        app.state.identity_client = IdentityClient(
            settings, transport=httpx.MockTransport(transport)
        )
        app.state.sources = AdmissionSources(settings, transport=httpx.MockTransport(transport))
        yield SimpleNamespace(
            client=client,
            state=state,
            headers=user_headers,
            app=app,
            appointment_id=appointment_id,
            patient=patient,
            doctor=doctor,
            settings=settings,
            database=database,
        )


def issue(api, subject=None, **body):
    return api.client.post(
        "/admissions",
        headers=api.headers(subject or api.patient),
        json={"appointment_id": str(api.appointment_id)} | body,
    )


def internal(api, action, grant, *, secret=None, caller="signalling", **overrides):
    token = service_token(
        secret or api.settings.signalling_secret, caller, "telelink-consultation-admission"
    )
    return api.client.post(
        "/internal/admissions/" + action,
        headers={"Authorization": "Bearer " + token},
        json={"token": grant["token"], "peer_id": grant["peer_id"]} | overrides,
    )


def test_grant_consumption_release_and_fresh_rejoin(api):
    assert api.client.get("/health/ready").status_code == 200
    response = issue(api)
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    grant = response.json()
    assert grant["subject_id"] == str(api.patient)
    assert UUID(grant["peer_id"]) and len(grant["token"]) == 43
    assert internal(api, "check", grant).status_code == 403
    assert internal(api, "consume", grant).status_code == 200
    assert internal(api, "consume", grant).status_code == 403
    assert internal(api, "check", grant).status_code == 200
    assert issue(api).status_code == 409
    for _ in range(2):
        assert internal(api, "release", grant).status_code == 204
    assert internal(api, "check", grant).status_code == 403
    assert internal(api, "consume", grant).status_code == 403
    rejoin = issue(api).json()
    assert rejoin["token"] != grant["token"] and rejoin["peer_id"] != grant["peer_id"]
    assert internal(api, "consume", grant).status_code == 403
    assert internal(api, "consume", rejoin).status_code == 200


def test_local_extended_window_covers_issue_consume_and_check(api):
    start = api.state["clock"] + timedelta(hours=2)
    api.state["appointment"].update(
        starts_at=start.isoformat(), ends_at=(start + timedelta(minutes=30)).isoformat()
    )
    assert issue(api).status_code == 403
    api.settings.test_join_early_minutes = 180
    response = issue(api)
    assert response.status_code == 201, response.text
    grant = response.json()
    assert internal(api, "consume", grant).status_code == 200
    assert internal(api, "check", grant).status_code == 200
    api.settings.test_join_early_minutes = 10
    assert internal(api, "check", grant).status_code == 403


def test_local_early_clinical_start_and_completion(api):
    start = api.state["clock"] + timedelta(hours=2)
    api.state["appointment"].update(
        starts_at=start.isoformat(), ends_at=(start + timedelta(minutes=30)).isoformat()
    )
    route = f"/appointments/{api.appointment_id}"
    headers = api.headers(api.doctor)
    assert api.client.post(route + "/start", headers=headers).status_code == 409
    api.settings.test_join_early_minutes = 180
    assert api.client.post(route + "/start", headers=api.headers()).status_code == 404
    response = api.client.post(route + "/start", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "in_progress"
    assert api.client.post(route + "/start", headers=headers).status_code == 200
    assert api.client.post(route + "/complete", headers=headers).status_code == 200
    with Session(api.database) as db:
        row = db.scalar(
            select(ConsultationSession).where(
                ConsultationSession.appointment_id == api.appointment_id
            )
        )
        assert row.test_start_early_minutes == 180
        assert row.started_at < row.starts_at
        assert row.ended_at >= row.started_at
        # Remove only this isolated test record so downgrade/isolation tests can run.
        db.delete(row)
        db.commit()


def test_pending_rotation_and_durable_hash_only_storage(api):
    first, second = issue(api).json(), issue(api).json()
    assert internal(api, "consume", first).status_code == 403
    with Session(api.database) as db:
        rows = db.scalars(
            select(Admission).where(Admission.session_id == UUID(second["session_id"]))
        ).all()
        assert len(rows) == 1
        assert rows[0].token_digest == admissions.digest(second["token"])
        assert second["token"] not in repr(rows[0].__dict__)
    assert internal(api, "consume", second).status_code == 200


def test_patient_and_assigned_doctor_only(api):
    assert issue(api, api.doctor).status_code == 201
    assert issue(api, uuid4()).status_code == 404
    api.state["doctor_active"] = False
    assert issue(api, api.doctor).status_code == 404
    api.state["roles"][str(api.patient)] = ["platform_admin"]
    assert issue(api).status_code == 404


@pytest.mark.parametrize(
    "field,value",
    [
        ("subject_id", str(uuid4())),
        ("peer_id", str(uuid4())),
        ("tenant_id", str(uuid4())),
        ("payment_status", "paid"),
        ("now", "2030-01-01T00:00:00Z"),
    ],
)
def test_client_cannot_supply_trusted_context(api, field, value):
    assert issue(api, **{field: value}).status_code == 422


@pytest.mark.parametrize(
    "changes",
    [{"exp": 1}, {"token_use": "id"}, {"client_id": "other"}, {"iss": "http://other.test"}],
)
def test_invalid_user_tokens(api, changes):
    assert (
        api.client.post(
            "/admissions",
            headers=api.headers(**changes),
            json={"appointment_id": str(api.appointment_id)},
        ).status_code
        == 401
    )


def test_missing_auth_and_service_credentials_cannot_issue(api):
    assert (
        api.client.post("/admissions", json={"appointment_id": str(api.appointment_id)}).status_code
        == 401
    )
    grant = issue(api).json()
    assert (
        api.client.post(
            "/internal/admissions/consume",
            headers=api.headers(),
            json={"token": grant["token"], "peer_id": grant["peer_id"]},
        ).status_code
        == 401
    )
    assert internal(api, "consume", grant, caller="billing").status_code == 401
    assert (
        internal(
            api, "consume", grant, secret=SecretStr("wrong-secret-at-least-32-bytes-long")
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "status", ["held", "pending_payment", "expired", "cancelled", "no_show", "completed"]
)
def test_ineligible_appointment_states(api, status):
    api.state["appointment"]["status"] = status
    assert issue(api).status_code == 409


@pytest.mark.parametrize(
    "field,value", [("payment_id", None), ("payment_resolution", "refund_required")]
)
def test_scheduling_payment_gate(api, field, value):
    api.state["appointment"][field] = value
    assert issue(api).status_code == 409


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "pending"),
        ("status", "refunded"),
        ("resolution", "refund_required"),
        ("purpose", "medication_delivery"),
        ("payment_id", str(uuid4())),
        ("tenant_id", str(uuid4())),
        ("patient_id", str(uuid4())),
        ("appointment_id", str(uuid4())),
        ("amount", {"amount_minor": 4999, "currency": "SGD"}),
    ],
)
def test_billing_must_match_trusted_appointment(api, field, value):
    api.state["payment"][field] = value
    assert issue(api).status_code == 409


@pytest.mark.parametrize(
    "status,expected", [(401, 503), (403, 404), (404, 404), (500, 503), (302, 502)]
)
def test_upstream_failures_are_closed_and_redacted(api, status, expected):
    api.state["sources_status"] = status
    response = issue(api)
    assert response.status_code == expected
    assert "private" not in response.text


def test_unavailable_identity_and_storage(api):
    api.state["identity_status"] = 503
    assert issue(api).status_code == 503
    api.state["identity_status"] = 200
    original_engine = api.app.state.database_engine
    api.app.state.database_engine = None
    assert issue(api).status_code == 503
    assert api.client.get("/health/ready").status_code == 503
    # Restore the engine so lifespan disposes it.
    api.app.state.database_engine = original_engine


def test_peer_binding_and_concurrent_single_use(api):
    grant = issue(api).json()
    assert internal(api, "consume", grant, peer_id=str(uuid4())).status_code == 403
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: internal(api, "consume", grant).status_code, range(2)))
    assert sorted(statuses) == [200, 403]


def test_duplicate_issue_is_bounded_under_concurrency(api):
    with ThreadPoolExecutor(max_workers=2) as pool:
        grants = list(pool.map(lambda _: issue(api).json(), range(2)))
    statuses = [internal(api, "consume", grant).status_code for grant in grants]
    assert sorted(statuses) == [200, 403]
    with Session(api.database) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Admission)
                .where(Admission.session_id == UUID(grants[0]["session_id"]))
            )
            == 1
        )


@pytest.mark.parametrize("started", [False, True])
def test_expiry_and_appointment_boundary(api, started):
    if started:
        response = api.client.post(
            f"/appointments/{api.appointment_id}/start", headers=api.headers(api.doctor)
        )
        assert response.status_code == 200
    grant = issue(api).json()
    api.state["clock"] += timedelta(seconds=60)
    assert internal(api, "consume", grant).status_code == 403
    new = issue(api).json()
    assert internal(api, "consume", new).status_code == 200
    api.state["clock"] += timedelta(seconds=60)
    assert internal(api, "check", new).status_code == 403
    api.state["clock"] = datetime.fromisoformat(api.state["appointment"]["ends_at"]) - timedelta(
        seconds=1
    )
    final = issue(api).json()
    if not started:
        assert final["expires_at"] == api.state["appointment"]["ends_at"][:23] + "Z"
    api.state["clock"] += timedelta(seconds=1)
    assert internal(api, "consume", final).status_code == (200 if started else 403)
    assert issue(api, api.doctor).status_code == (201 if started else 403)
    if started:
        api.state["clock"] += timedelta(days=1)
        for subject in (api.patient, api.doctor):
            grant = issue(api, subject)
            assert grant.status_code == 201
            expiry = datetime.fromisoformat(grant.json()["expires_at"].replace("Z", "+00:00"))
            assert 0 < (expiry - api.state["clock"]).total_seconds() <= 300
            assert internal(api, "consume", grant.json()).status_code == 200
            api.state["clock"] += timedelta(seconds=api.settings.admission_ttl_seconds)
            assert internal(api, "check", grant.json()).status_code == 403
        api.state["appointment"]["status"] = "completed"
        assert issue(api).status_code == 409


@pytest.mark.parametrize("target", ["membership", "payment", "appointment", "context"])
@pytest.mark.parametrize("started", [False, True])
def test_current_context_rechecked_before_connection_and_on_check(api, target, started):
    if started:
        response = api.client.post(
            f"/appointments/{api.appointment_id}/start", headers=api.headers(api.doctor)
        )
        assert response.status_code == 200
        api.state["clock"] += timedelta(days=1)
    grant = issue(api, api.doctor).json()
    assert internal(api, "consume", grant).status_code == 200
    if target == "membership":
        api.state["doctor_active"] = False
    elif target == "payment":
        api.state["payment"]["status"] = "refunded"
    elif target == "appointment":
        api.state["appointment"]["status"] = "cancelled"
    else:
        api.state["appointment"]["tenant_id"] = str(uuid4())
    assert internal(api, "check", grant).status_code in {403, 404, 409}


def test_revocation_between_issue_and_consume(api):
    grant = issue(api, api.doctor).json()
    api.state["doctor_active"] = False
    assert internal(api, "consume", grant).status_code == 404
    api.state["doctor_active"] = True
    assert internal(api, "consume", grant).status_code == 200


def test_completed_session_rejects_pending_grant(api):
    grant = issue(api).json()
    with Session(api.database) as db, db.begin():
        args = dict(
            session_id=UUID(grant["session_id"]),
            tenant_id=UUID(grant["tenant_id"]),
            doctor_id=api.doctor,
            now=api.state["clock"],
        )
        transition(db, action="start", **args)
        transition(db, action="end", **args)
    assert internal(api, "consume", grant).status_code == 403
    assert issue(api).status_code == 403


def test_malformed_source_and_schedule_are_rejected(api):
    api.state["appointment"]["starts_at"] = "2030-01-01T00:00:00"
    assert issue(api).status_code == 502


def test_no_raw_grant_in_request_logs(api, caplog):
    grant = issue(api).json()
    internal(api, "consume", grant)
    assert grant["token"] not in caplog.text


def test_doctor_lifecycle_syncs_scheduling_and_closes_admission(api):
    path = f"/appointments/{api.appointment_id}"
    assert api.client.post(path + "/start", headers=api.headers()).status_code == 404
    grant = issue(api).json()
    for _ in range(2):
        result = api.client.post(path + "/start", headers=api.headers(api.doctor))
        assert result.status_code == 200
        assert result.json()["status"] == "in_progress"
    assert api.state["appointment"]["status"] == "in_progress"
    for _ in range(2):
        result = api.client.post(path + "/complete", headers=api.headers(api.doctor))
        assert result.status_code == 200
    assert api.state["appointment"]["status"] == "completed"
    assert internal(api, "consume", grant).status_code in {403, 409}
    assert issue(api).status_code == 409


@pytest.mark.parametrize("target", ["doctor_active", "payment", "sources_status"])
def test_lifecycle_denies_revocation_refund_and_upstream_outage(api, target):
    if target == "payment":
        api.state["payment"]["status"] = "refunded"
    elif target == "sources_status":
        api.state[target] = 503
    else:
        api.state[target] = False
    response = api.client.post(
        f"/appointments/{api.appointment_id}/start", headers=api.headers(api.doctor)
    )
    assert response.status_code in {404, 409, 503}
    assert api.state["appointment"]["status"] == "confirmed"


def test_lifecycle_recovers_lost_scheduling_response_without_repeating_transition(api):
    path = f"/appointments/{api.appointment_id}"
    for action, target in [("start", "in_progress"), ("complete", "completed")]:
        api.state["lost_scheduling_response"] = True
        assert (
            api.client.post(path + "/" + action, headers=api.headers(api.doctor)).status_code == 503
        )
        assert api.state["appointment"]["status"] == target
        assert (
            api.client.post(path + "/" + action, headers=api.headers(api.doctor)).status_code == 200
        )


def test_completion_handoff_can_retry_after_scheduling_finished(api):
    path = f"/appointments/{api.appointment_id}"
    assert api.client.post(path + "/start", headers=api.headers(api.doctor)).status_code == 200
    api.state["lost_mc_response"] = True
    assert api.client.post(path + "/complete", headers=api.headers(api.doctor)).status_code == 503
    assert api.state["appointment"]["status"] == "completed"
    assert api.client.post(path + "/complete", headers=api.headers(api.doctor)).status_code == 200
    assert api.state["mc_calls"] == 2


@pytest.mark.parametrize("failure", [409, 503, "context", "lost_response"])
def test_prescription_must_finalize_before_completion_and_can_retry(api, failure):
    path = f"/appointments/{api.appointment_id}"
    assert api.client.post(path + "/start", headers=api.headers(api.doctor)).status_code == 200
    if failure == "context":
        api.state["wrong_prescription_context"] = True
    elif failure == "lost_response":
        api.state["lost_prescription_response"] = True
    else:
        api.state["prescription_failure"] = failure
    response = api.client.post(path + "/complete", headers=api.headers(api.doctor))
    assert response.status_code == (
        502 if failure == "context" else 503 if failure == "lost_response" else failure
    )
    assert api.state["appointment"]["status"] == "in_progress"
    with Session(api.database) as db:
        record = db.scalar(
            select(ConsultationSession).where(
                ConsultationSession.appointment_id == api.appointment_id
            )
        )
        assert record.status == "in_progress" and record.ended_at is None
    api.state.pop("wrong_prescription_context", None)
    api.state.pop("prescription_failure", None)
    assert api.client.post(path + "/complete", headers=api.headers(api.doctor)).status_code == 200
    assert api.state["appointment"]["status"] == "completed"
    assert api.state["prescription_calls"] == 2
