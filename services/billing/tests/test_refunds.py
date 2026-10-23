"""Real DB authorization, audit, provider reconciliation and concurrency checks."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from telelink_common.errors import DomainError

from app.models import CheckoutAttempt, Payment, RefundAttempt
from app.provider import ProviderRejected, ProviderUncertain, StripeCheckout
from app.refunds import process_refunds
from app.settings import Settings
from app.upstream import CheckoutSources
from tests.test_queries import api as api


@pytest.fixture
def flow(api):
    client, headers, seed, state, tenant, foreign, patient, other, app = api
    state["roles"] = []
    state["memberships"] = [(tenant, ["clinic_admin"], "active")]
    payment_id = seed(status="succeeded", provider_payment_id="pi_RF08")
    with Session(app.state.database_engine) as session, session.begin():
        p = session.get(Payment, payment_id)
        session.add(
            CheckoutAttempt(
                payment_id=payment_id,
                appointment_id=p.appointment_id,
                patient_id=patient,
                provider_fields={"payment_intent_data[transfer_data][destination]": "acct_RF08"},
            )
        )
    operations = {
        "prepare": 0,
        "complete": 0,
        "post": [],
        "refunds": [],
        "outcome": "succeeded",
        "timeout": False,
        "reject": False,
        "sync_fail": False,
    }

    def prepare(payment, request_id):
        operations["prepare"] += 1
        if operations.get("active"):
            raise DomainError(409, "refund_appointment_active", "Cancel first")

    def complete(payment, request_id):
        operations["complete"] += 1
        if operations["sync_fail"]:
            raise DomainError(503, "unavailable", "Unavailable")
        # Scheduling reads only committed provider success.
        with Session(app.state.database_engine) as session:
            assert session.get(Payment, payment_id).status == "refunded"

    app.state.sources.close()
    app.state.sources = SimpleNamespace(
        prepare_refund=prepare, complete_refund=complete, close=lambda: None
    )

    def provider_request(method, path, *, fields=None, key=None):
        with Session(app.state.database_engine) as session:
            payment = session.get(Payment, payment_id)
            metadata = {
                name: str(getattr(payment, name))
                for name in ("payment_id", "tenant_id", "patient_id", "purpose", "appointment_id")
            }
        if path.startswith("payment_intents/"):
            return {
                "id": "pi_RF08",
                "object": "payment_intent",
                "status": "succeeded",
                "amount": 2500,
                "amount_received": 2500,
                "currency": "sgd",
                "metadata": metadata,
                "transfer_data": {"destination": "acct_RF08"},
                "application_fee_amount": 250,
            }
        if method == "GET" and path.startswith("refunds?"):
            return {"object": "list", "has_more": False, "data": operations["refunds"]}
        if method == "GET":
            result = operations["refunds"][-1].copy()
            result["status"] = operations["outcome"]
            return result
        operations["post"].append((fields, key))
        if operations["reject"]:
            raise ProviderRejected()
        refund = {
            "id": "re_" + fields["metadata[refund_id]"].replace("-", ""),
            "object": "refund",
            "payment_intent": "pi_RF08",
            "amount": 2500,
            "currency": "sgd",
            "status": operations["outcome"],
            "metadata": {"refund_id": fields["metadata[refund_id]"], "payment_id": str(payment_id)},
        }
        operations["refunds"].append(refund)
        if operations["timeout"]:
            raise ProviderUncertain()
        return refund

    provider = SimpleNamespace(request=provider_request)
    return api, payment_id, operations, provider


def request(flow, **kwargs):
    api, payment_id, _, _ = flow
    return api[0].post(
        f"/payments/{payment_id}/refunds",
        headers=api[1](),
        json={"reason": "Patient cancellation"} | kwargs,
    )


def run(flow, seconds=5):
    api, _, _, provider = flow
    return process_refunds(
        api[-1].state.database_engine,
        provider,
        api[-1].state.sources,
        now=datetime.now(timezone.utc) + timedelta(seconds=seconds),
    )


def test_full_refund_replay_audit_and_committed_sync(flow):
    first = request(flow)
    assert first.status_code == 202, first.text
    assert request(flow).json()["refund_id"] == first.json()["refund_id"]
    assert first.json()["requested_by_name"] == "Synthetic"
    assert flow[2]["prepare"] == 1
    run(flow)
    assert flow[2]["complete"] == 0  # Success must commit before scheduling can verify it.
    run(flow, 60)
    assert flow[2]["complete"] == 1
    assert len(flow[2]["post"]) == 1
    fields, key = flow[2]["post"][0]
    assert fields["amount"] == "2500"
    assert fields["reverse_transfer"] == fields["refund_application_fee"] == "true"
    assert key == "RF08-refund-" + first.json()["refund_id"]
    client, headers = flow[0][:2]
    assert client.get(f"/payments/{flow[1]}", headers=headers()).json()["status"] == "refunded"
    history = client.get(f"/payments/{flow[1]}/refunds", headers=headers()).json()
    assert history[0]["status"] == "succeeded"
    with Session(flow[0][-1].state.database_engine) as session:
        assert session.scalar(select(RefundAttempt)).synced_at is not None
        session.scalar(select(RefundAttempt)).reason = "Rewritten audit"
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    "role,status",
    [
        ("patient", "active"),
        ("platform_admin", "active"),
        ("doctor", "active"),
        ("clinic_admin", "revoked"),
        ("foreign", "active"),
    ],
)
def test_only_current_own_clinic_admin_can_refund(flow, role, status):
    api = flow[0]
    api[3]["roles"] = [role] if role in {"patient", "platform_admin"} else []
    api[3]["memberships"] = [
        (
            api[5] if role == "foreign" else api[4],
            ["doctor" if role == "doctor" else "clinic_admin"],
            status,
        )
    ]
    if role in {"patient", "platform_admin"}:
        api[3]["memberships"] = []
    assert request(flow).status_code == 404
    assert flow[2]["prepare"] == 0


def test_medication_seeded_unpaid_active_and_invalid_body_rejected(flow):
    api, payment_id, operations, _ = flow
    operations["active"] = True
    active_response = request(flow)
    assert active_response.status_code == 409
    assert active_response.json()["error"]["code"] == "refund_appointment_active"
    operations["active"] = False
    assert request(flow, reason="   ").status_code == 422
    assert request(flow, amount=1).status_code == 422
    with Session(api[-1].state.database_engine) as session, session.begin():
        session.get(Payment, payment_id).provider = "demo_seed"
    assert request(flow).status_code == 409
    med_id = api[2](
        purpose="medication_delivery",
        appointment_id=None,
        order_id=uuid4(),
        quote_id=uuid4(),
        status="succeeded",
        provider_payment_id="pi_medication",
    )
    assert (
        api[0]
        .post(f"/payments/{med_id}/refunds", headers=api[1](), json={"reason": "test"})
        .status_code
        == 409
    )
    assert not operations["post"]


def test_demo_payment_explains_unavailability_before_scheduling_or_provider(flow):
    api, payment_id, operations, _ = flow
    with Session(api[-1].state.database_engine) as session, session.begin():
        payment = session.get(Payment, payment_id)
        payment.provider = "demo_seed"
        payment.resolution = "refund_required"
    response = api[0].get(f"/payments/{payment_id}", headers=api[1]())
    assert response.status_code == 200
    assert response.json()["refund_availability"] == "demo_payment"
    assert response.json()["status"] == "succeeded"
    refused = request(flow)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "refund_demo_payment"
    assert "cancel" not in refused.json()["error"]["message"].lower()
    assert operations["prepare"] == 0 and not operations["post"]
    with Session(api[-1].state.database_engine) as session:
        assert session.scalar(select(RefundAttempt)) is None


def test_real_paid_payment_and_unpaid_payment_report_different_availability(flow):
    api, payment_id, _, _ = flow
    path = f"/payments/{payment_id}"
    assert api[0].get(path, headers=api[1]()).json()["refund_availability"] == "available"
    with Session(api[-1].state.database_engine) as session, session.begin():
        session.get(Payment, payment_id).status = "pending"
    assert api[0].get(path, headers=api[1]()).json()["refund_availability"] == "not_paid"
    refused = request(flow)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "refund_not_available"


def test_scheduling_active_error_code_survives_billing_adapter():
    settings = Settings(
        _env_file=None,
        environment="test",
        scheduling_url="http://scheduling.test",
        scheduling_secret="rf08-source-error-test-key-at-least-32-bytes",
    )
    sources = CheckoutSources(
        settings,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                409,
                json={"error": {"code": "refund_appointment_active", "message": "Cancel first"}},
            )
        ),
    )
    payment = SimpleNamespace(
        **{name: uuid4() for name in ("payment_id", "appointment_id", "patient_id", "tenant_id")}
    )
    try:
        with pytest.raises(DomainError) as error:
            sources.prepare_refund(payment, "rf08-error-check")
        assert error.value.code == "refund_appointment_active"
        assert "active appointment" in error.value.detail
    finally:
        sources.close()


def test_lost_response_recovers_without_second_post(flow):
    assert request(flow).status_code == 202
    flow[2]["timeout"] = True
    assert run(flow)["deferred"] == 1
    flow[2]["timeout"] = False
    run(flow, 120)
    assert len(flow[2]["post"]) == 1


def test_pending_poll_and_failed_retry_have_distinct_audits(flow):
    flow[2]["outcome"] = "pending"
    first = request(flow).json()
    run(flow)
    assert request(flow).json()["refund_id"] == first["refund_id"]
    flow[2]["outcome"] = "failed"
    run(flow, 120)
    # Listing truth agrees with failed GET before retry.
    flow[2]["refunds"][-1]["status"] = "failed"
    second = request(flow).json()
    assert second["refund_id"] != first["refund_id"]
    flow[2]["outcome"] = "succeeded"
    run(flow, 240)
    assert len(flow[2]["post"]) == 2
    assert flow[2]["post"][0][1] != flow[2]["post"][1][1]


def test_old_uncertain_operation_stops_reposting_and_requires_review(flow):
    result = request(flow).json()
    engine = flow[0][-1].state.database_engine
    # Advance worker time rather than altering immutable created_at.
    process_refunds(
        engine,
        flow[3],
        flow[0][-1].state.sources,
        now=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    assert not flow[2]["post"]
    assert request(flow).json()["refund_id"] == result["refund_id"]
    assert request(flow).json()["status"] == "review"


def test_external_refund_and_provider_rejection_never_automatic_retry(flow):
    flow[2]["refunds"] = [{"metadata": {}, "status": "pending"}]
    assert request(flow).status_code == 202
    run(flow)
    assert request(flow).json()["status"] == "review"
    assert not flow[2]["post"]


def test_provider_rejection_requires_review_and_cannot_create_new_operation(flow):
    flow[2]["reject"] = True
    first = request(flow).json()
    run(flow)
    assert request(flow).json()["status"] == "review"
    assert request(flow).json()["refund_id"] == first["refund_id"]
    run(flow, 120)
    assert len(flow[2]["post"]) == 1


@pytest.mark.parametrize(
    "field,value",
    [("amount", 1), ("currency", "usd"), ("payment_intent", "pi_other"), ("livemode", True)],
)
def test_mismatched_provider_refund_requires_review(flow, field, value):
    original = flow[3].request

    def changed(method, path, **kwargs):
        result = original(method, path, **kwargs)
        if method == "POST":
            result[field] = value
        return result

    flow[3].request = changed
    request(flow)
    run(flow)
    assert request(flow).json()["status"] == "review"


def test_concurrent_requests_and_workers_issue_once(flow):
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: request(flow), range(2)))
    assert all(r.status_code == 202 for r in responses)
    assert len({r.json()["refund_id"] for r in responses}) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: run(flow), range(2)))
    assert len(flow[2]["post"]) == 1


def test_sync_outage_does_not_undo_provider_success(flow):
    request(flow)
    run(flow)
    flow[2]["sync_fail"] = True
    assert run(flow, 120)["deferred"] == 1
    flow[2]["sync_fail"] = False
    run(flow, 240)
    assert len(flow[2]["post"]) == 1
    assert request(flow).json()["status"] == "succeeded"


def test_provider_refund_lists_allow_only_test_objects():
    settings = Settings(_env_file=None, environment="test", stripe_secret_key="sk_test_RF08")
    state = {"data": []}
    with httpx.Client():
        provider = StripeCheckout(
            settings,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"object": "list", "has_more": False, **state})
            ),
        )
        try:
            assert provider.request("GET", "refunds?payment_intent=pi_RF08")["data"] == []
            state["data"] = [{"livemode": True}]
            with pytest.raises(ProviderUncertain):
                provider.request("GET", "refunds?payment_intent=pi_RF08")
        finally:
            provider.close()


@pytest.mark.parametrize("method,path", [("POST", "refunds"), ("GET", "refunds/re_RF08")])
def test_real_stripe_refund_shape_omits_livemode(method, path):
    settings = Settings(_env_file=None, environment="test", stripe_secret_key="sk_test_RF08")
    provider = StripeCheckout(
        settings,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"object": "refund", "id": "re_RF08", "status": "succeeded"}
            )
        ),
    )
    try:
        assert provider.request(method, path)["status"] == "succeeded"
    finally:
        provider.close()
