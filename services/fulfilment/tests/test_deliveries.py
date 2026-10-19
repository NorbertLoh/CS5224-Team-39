import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from telelink_common.events import new_event
from telelink_common.inbox import handle_event
from telelink_common.outbox import publish_pending

from app.deliveries import (
    claim_deliveries,
    deliver_resolutions,
    prepare_submission,
    reconcile,
    submit_delivery,
)
from app.delivery_orders import DeliveryUnavailable, SubmissionRejected, SubmissionUncertain
from app.delivery_provider import DeliveryPrice
from app.delivery_worker import submit_pending
from app.models import Delivery, Order, Quote, event_inbox, event_outbox
from app.payments import confirm_payment
from tests.test_api import OTHER_PATIENT, OTHER_TENANT, create, identity
from tests.test_api import api as api
from tests.test_payments import payment_case as payment_case

STOPS = [
    {
        "coordinates": {"lat": "1.2844", "lng": "103.8511"},
        "address": "1 Raffles Place, Singapore 048616",
    },
    {
        "coordinates": {"lat": "1.2935", "lng": "103.8572"},
        "address": "3 Temasek Boulevard, Singapore 038983",
    },
]


class Provider:
    def __init__(self, case):
        self.case = case
        self.calls = 0
        self.prepares = 0
        self.fee = 780
        self.error = None
        self.preparation_error = None
        self.status = "ASSIGNING_DRIVER"
        self.provider_id = "3608133045767029417"

    def prepare(self, order, quote, delivery):
        self.prepares += 1
        if self.preparation_error:
            raise self.preparation_error
        return DeliveryPrice(
            amount_minor=self.fee,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            context={},
        ), {
            "quotationId": "3608770529626608275",
            "metadata": {
                "delivery_id": str(delivery.delivery_id),
                "operation_id": str(delivery.operation_id),
            },
            "sender": {"name": "Synthetic sender", "phone": "+6580000000"},
        }

    def submit(self, delivery, quote, fee):
        self.calls += 1
        with self.case.sessions() as db:
            stored = db.get(Delivery, delivery.delivery_id)
            assert stored.status == "unknown" and stored.send_started_at is not None
            assert stored.request_payload == delivery.request_payload
        if self.error:
            raise self.error
        return SimpleNamespace(orderId=self.provider_id, status=self.status)

    def inspect(self, provider_id, delivery, quote, fee):
        assert provider_id == self.provider_id
        return SimpleNamespace(orderId=provider_id, status=self.status)


@pytest.fixture
def eligible(payment_case):
    case = payment_case
    with case.sessions.begin() as db:
        order = db.get(Order, case.order.order_id)
        order.status, order.payment_status, order.medicine_status = "paid", "succeeded", "ready"
        db.get(Quote, case.quote.quote_id).provider_context = {
            "stops": STOPS,
            "mode": "lalamove-sandbox",
            "service_type": "MOTORCYCLE",
        }
    case.fact = case.fact.model_copy(
        update={"updated_at": case.quote.created_at + timedelta(minutes=1)}
    )
    # Retain the signed adapter's real response parsing, while permitting a controllable fact.
    case.billing.payment = lambda payment_id: case.fact
    case.provider = Provider(case)
    return case


def rows(case):
    with case.sessions() as db:
        order = db.get(Order, case.order.order_id)
        delivery = db.scalar(select(Delivery).where(Delivery.order_id == order.order_id))
        events = (
            db.execute(select(event_outbox).order_by(event_outbox.c.created_at)).mappings().all()
        )
        return order, delivery, [json.loads(row["detail"])["data"]["status"] for row in events]


@pytest.mark.parametrize(
    "changes",
    [
        {"medicine_status": "not_ready"},
        {"payment_status": "pending"},
        {"status": "awaiting_payment"},
        {"status": "cancelled"},
        {"payment_status": "refund_required"},
    ],
)
def test_gate_never_claims_ineligible_order(eligible, changes):
    case = eligible
    with case.sessions.begin() as db:
        for key, value in changes.items():
            setattr(db.get(Order, case.order.order_id), key, value)
    assert submit_pending(case.sessions, case.provider, case.billing)["claimed"] == 0
    assert case.provider.calls == case.provider.prepares == 0
    assert rows(case)[1] is None


def test_success_emits_durable_states_and_repeated_poll_is_safe(eligible):
    case = eligible
    submit_pending(case.sessions, case.provider, case.billing)
    order, delivery, statuses = rows(case)
    assert (order.status, order.payment_status, order.medicine_status) == (
        "dispatched",
        "succeeded",
        "ready",
    )
    assert order.delivery_id == delivery.delivery_id
    assert delivery.status == "submitted"
    assert delivery.provider_order_id == case.provider.provider_id
    assert statuses == ["pending", "unknown", "submitted"]
    for _ in range(3):
        submit_pending(case.sessions, case.provider, case.billing)
    assert case.provider.calls == 1
    assert rows(case)[1].updated_at == delivery.updated_at
    assert rows(case)[2] == statuses


def test_concurrent_workers_send_one_order(eligible):
    case = eligible
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(lambda _: submit_pending(case.sessions, case.provider, case.billing), range(6))
        )
    assert sum(result["claimed"] for result in results) == 1
    assert case.provider.calls == 1
    assert rows(case)[1].status == "submitted"


@pytest.mark.parametrize("error", [SubmissionUncertain(), SystemExit("synthetic process exit")])
def test_uncertain_or_crashed_send_is_never_automatically_retried(eligible, error):
    case = eligible
    case.provider.error = error
    if isinstance(error, SystemExit):
        with pytest.raises(SystemExit):
            submit_pending(case.sessions, case.provider, case.billing)
    else:
        submit_pending(case.sessions, case.provider, case.billing)
    order, delivery, statuses = rows(case)
    assert order.status == "submitting" and delivery.status == "unknown"
    assert statuses == ["pending", "unknown"]
    case.provider.error = None
    for _ in range(3):
        submit_pending(case.sessions, case.provider, case.billing)
    assert case.provider.calls == 1
    assert reconcile(
        case.sessions,
        delivery.delivery_id,
        case.provider.provider_id,
        case.provider,
        "synthetic-operator",
    )
    order, resolved, statuses = rows(case)
    assert resolved.status == "submitted" and order.status == "dispatched"
    assert resolved.reconciled_by == "synthetic-operator" and resolved.reconciled_at
    assert not reconcile(
        case.sessions,
        delivery.delivery_id,
        case.provider.provider_id,
        case.provider,
        "synthetic-operator",
    )
    assert statuses == ["pending", "unknown", "submitted"]
    assert case.provider.calls == 1


def test_crash_after_intent_commit_before_post_stays_unknown(eligible):
    case = eligible
    delivery_id = claim_deliveries(case.sessions)[0]
    assert prepare_submission(case.sessions, delivery_id, case.provider, case.billing)
    assert not submit_delivery(case.sessions, delivery_id, case.provider, case.billing)
    assert case.provider.calls == 0
    assert rows(case)[1].status == "unknown"


def test_crash_after_provider_acceptance_before_local_result_commit(eligible, monkeypatch):
    case = eligible

    def crash(*args, **kwargs):
        raise RuntimeError("Synthetic failure while persisting acceptance")

    with monkeypatch.context() as patch:
        patch.setattr("app.deliveries.finish_submission", crash)
        assert submit_pending(case.sessions, case.provider, case.billing)["errors"] == 1
    assert rows(case)[1].status == "unknown"
    submit_pending(case.sessions, case.provider, case.billing)
    assert case.provider.calls == 1
    delivery = rows(case)[1]
    assert reconcile(
        case.sessions,
        delivery.delivery_id,
        case.provider.provider_id,
        case.provider,
        "synthetic-operator",
    )


def test_claim_and_outbox_roll_back_together(eligible, monkeypatch):
    case = eligible

    def crash(*args):
        raise RuntimeError("Synthetic outbox failure")

    with monkeypatch.context() as patch:
        patch.setattr("app.deliveries.emit", crash)
        with pytest.raises(RuntimeError):
            claim_deliveries(case.sessions)
    order, delivery, statuses = rows(case)
    assert order.status == "paid" and order.delivery_id is None
    assert delivery is None and statuses == []
    assert len(claim_deliveries(case.sessions)) == 1


def test_preparation_failure_retries_with_backoff_without_sending(eligible):
    case = eligible
    case.provider.preparation_error = DeliveryUnavailable("Synthetic outage")
    assert submit_pending(case.sessions, case.provider, case.billing)["errors"] == 1
    _, delivery, statuses = rows(case)
    assert delivery.status == "pending" and delivery.send_started_at is None
    assert delivery.attempts == 1 and delivery.next_attempt_at > datetime.now(timezone.utc)
    assert statuses == ["pending"]
    assert submit_pending(case.sessions, case.provider, case.billing)["checked"] == 0
    with case.sessions.begin() as db:
        db.get(Delivery, delivery.delivery_id).next_attempt_at = datetime.now(timezone.utc)
    case.provider.preparation_error = None
    submit_pending(case.sessions, case.provider, case.billing)
    assert case.provider.calls == 1 and rows(case)[1].status == "submitted"


@pytest.mark.parametrize("late", [True, False])
def test_late_payment_or_changed_fee_persists_refund_resolution_without_post(eligible, late):
    case = eligible
    if late:
        case.fact = case.fact.model_copy(update={"updated_at": case.quote.expires_at})
    else:
        case.provider.fee = 781
    submit_pending(case.sessions, case.provider, case.billing)
    order, delivery, statuses = rows(case)
    assert (order.status, order.payment_status, delivery.status) == (
        "exception",
        "refund_required",
        "failed",
    )
    assert delivery.resolution_reason == ("quote_expired" if late else "delivery_price_changed")
    assert delivery.send_started_at is None and case.provider.calls == 0
    assert statuses == ["pending", "failed"]
    acknowledgements = []

    def resolution(payment_id, order_id, reason):
        acknowledgements.append(reason)
        return case.fact.model_copy(update={"resolution": "refund_required"})

    case.billing.refund_required = resolution
    assert deliver_resolutions(case.sessions, case.billing) == 1
    assert deliver_resolutions(case.sessions, case.billing) == 0
    assert acknowledgements == [delivery.resolution_reason]


def test_failed_resolution_ack_is_durable_for_retry(eligible):
    case = eligible
    case.provider.fee += 1
    submit_pending(case.sessions, case.provider, case.billing)
    case.billing.refund_required = lambda *args: case.fact  # Not acknowledged by billing.
    with pytest.raises(Exception, match="acknowledgement invalid"):
        deliver_resolutions(case.sessions, case.billing)
    assert rows(case)[1].resolution_delivered_at is None


@pytest.mark.parametrize(
    "changes",
    [
        {"updated_at": None},
        {"patient_id": uuid4()},
        {"resolution": "refund_required"},
        {"purpose": "consultation"},
        {"status": "pending"},
        {"quote_id": uuid4()},
    ],
)
def test_current_billing_context_is_required_before_sending(eligible, changes):
    case = eligible
    case.fact = case.fact.model_copy(update=changes)
    submit_pending(case.sessions, case.provider, case.billing)
    assert rows(case)[1].failure_code == "invalid_payment"
    assert case.provider.calls == case.provider.prepares == 0


@pytest.mark.parametrize("terminal", [None, "CANCELED", "REJECTED", "EXPIRED"])
def test_definite_provider_rejection_is_exception_and_does_not_retry(eligible, terminal):
    case = eligible
    if terminal:
        case.provider.status = terminal
    else:
        case.provider.error = SubmissionRejected("Synthetic rejection")
    submit_pending(case.sessions, case.provider, case.billing)
    order, delivery, statuses = rows(case)
    assert order.status == "exception" and delivery.status == "failed"
    assert statuses == ["pending", "unknown", "failed"]
    submit_pending(case.sessions, case.provider, case.billing)
    assert case.provider.calls == 1


def test_unique_order_and_provider_reference_constraints(eligible):
    case = eligible
    delivery_id = claim_deliveries(case.sessions)[0]
    with pytest.raises(IntegrityError), case.sessions.begin() as db:
        db.add(Delivery(order_id=case.order.order_id, tenant_id=case.order.tenant_id))
    assert rows(case)[1].delivery_id == delivery_id


def test_payment_replay_after_dispatch_does_not_regress_delivery(eligible):
    case = eligible
    submit_pending(case.sessions, case.provider, case.billing)
    before = rows(case)[0].updated_at
    event = new_event(
        "medication_payment_succeeded.v1",
        tenant_id=case.order.tenant_id,
        correlation_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        data={
            "payment_id": case.order.payment_id,
            "order_id": case.order.order_id,
            "amount": {"amount_minor": 2780, "currency": "SGD"},
        },
    )
    assert handle_event(
        case.sessions,
        event_inbox,
        "fulfilment",
        event,
        lambda db, ev: confirm_payment(db, ev, case.billing),
    )
    assert rows(case)[0].status == "dispatched" and rows(case)[0].updated_at == before
    assert case.provider.calls == 1


def test_delivery_outbox_retries_without_resubmitting(eligible):
    case = eligible
    submit_pending(case.sessions, case.provider, case.billing)

    class Events:
        def put_events(self, **kwargs):
            assert len(kwargs["Entries"]) == 3
            return {"FailedEntryCount": 0, "Entries": [{"EventId": str(uuid4())} for _ in range(3)]}

    publish_pending(case.sessions, event_outbox, Events(), "synthetic-bus")
    with case.sessions() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(event_outbox)
                .where(event_outbox.c.published_at.is_not(None))
            )
            == 3
        )
    assert case.provider.calls == 1


@pytest.mark.parametrize(
    "who,allowed",
    [
        (identity(), True),
        (identity(subject=OTHER_PATIENT), False),
        (identity(roles=(), clinic_role="clinic_admin"), True),
        (identity(roles=(), clinic_role="clinic_admin", active=False), False),
        (identity(roles=(), clinic_role="clinic_admin", tenant=OTHER_TENANT), False),
        (identity(roles=(), clinic_role="doctor"), False),
        (identity(roles=("platform_admin",)), True),
    ],
)
def test_delivery_read_access_omits_private_provider_data(api, who, allowed):
    client, state, _ = api
    order_id = create(client).json()["order_id"]
    with state.sessions.begin() as db:
        order = db.get(Order, UUID(order_id))
        order.status, order.payment_status, order.medicine_status = "paid", "succeeded", "ready"
    delivery_id = claim_deliveries(state.sessions)[0]
    state.identity = who
    response = client.get(f"/deliveries/{delivery_id}")
    assert (response.status_code == 200) == allowed
    if allowed:
        assert set(response.json()) == {
            "delivery_id",
            "order_id",
            "tenant_id",
            "status",
            "created_at",
            "updated_at",
        }
