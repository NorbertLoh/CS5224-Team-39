import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import partial
from types import SimpleNamespace
from uuid import uuid4

import httpx
import jwt
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from telelink_common.events import new_event
from telelink_common.inbox import consume_batch, handle_event

from app.integrations.billing import BillingClient, PaymentFact
from app.models import Order, Quote, event_inbox
from app.services.payments import PaymentEventRejected, confirm_payment
from app.settings import Settings

SECRET = "d04-synthetic-service-secret-at-least-32-bytes"


@pytest.fixture
def payment_case(sessions):
    now = datetime.now(timezone.utc)
    order = Order(
        tenant_id=uuid4(),
        patient_id=uuid4(),
        appointment_id=uuid4(),
        prescription_id=uuid4(),
        payment_id=uuid4(),
        payment_status="pending",
        medication_subtotal_minor=2000,
        delivery_fee_minor=780,
        total_minor=2780,
    )
    with sessions.begin() as db:
        db.add(order)
        db.flush()
        quote = Quote(
            order_id=order.order_id,
            tenant_id=order.tenant_id,
            status="accepted",
            medication_subtotal_minor=2000,
            delivery_fee_minor=780,
            total_minor=2780,
            created_at=now - timedelta(minutes=15),
            expires_at=now - timedelta(minutes=5),
            items=[],
            destination={},
            provider_context={},
        )
        db.add(quote)
        db.flush()
        order.quote_id = quote.quote_id
    fact = PaymentFact(
        payment_id=order.payment_id,
        order_id=order.order_id,
        quote_id=order.quote_id,
        tenant_id=order.tenant_id,
        patient_id=order.patient_id,
        purpose="medication_delivery",
        status="succeeded",
        amount={"amount_minor": 2780, "currency": "SGD"},
        resolution="none",
    )
    case = SimpleNamespace(order=order, quote=quote, fact=fact, sessions=sessions, calls=0)

    def lookup(request):
        assert request.url.path == f"/internal/payments/{order.payment_id}"
        claims = jwt.decode(
            request.headers["Authorization"].split()[1],
            SECRET,
            algorithms=["HS256"],
            audience="telelink-billing-fulfilment",
            issuer="telelink-service:fulfilment",
        )
        assert claims["sub"] == "fulfilment" and claims["exp"] - claims["iat"] == 60
        case.calls += 1
        return httpx.Response(200, json=case.fact.model_dump(mode="json"))

    case.billing = BillingClient(
        Settings(environment="test", billing_url="http://billing.test", billing_secret=SECRET),
        transport=httpx.MockTransport(lookup),
    )
    yield case
    case.billing.close()


def event_for(case, **changes):
    return new_event(
        "medication_payment_succeeded.v1",
        tenant_id=changes.pop("tenant_id", case.order.tenant_id),
        correlation_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        data={
            "payment_id": case.order.payment_id,
            "order_id": case.order.order_id,
            "amount": {"amount_minor": 2780, "currency": "SGD"},
        }
        | changes,
    )


def apply(case, event=None):
    return handle_event(
        case.sessions,
        event_inbox,
        "fulfilment",
        event or event_for(case),
        partial(confirm_payment, billing=case.billing),
    )


def snapshot(case):
    with case.sessions() as db:
        order = db.get(Order, case.order.order_id)
        return (
            order.status,
            order.payment_status,
            order.medicine_status,
            order.payment_id,
            order.quote_id,
            order.delivery_id,
            order.updated_at,
        )


def inbox_count(case):
    with case.sessions() as db:
        return db.scalar(select(func.count()).select_from(event_inbox))


@pytest.mark.parametrize("ready", [False, True])
def test_paid_state_and_both_duplicate_forms_preserve_readiness(payment_case, ready):
    case = payment_case
    if ready:
        with case.sessions.begin() as db:
            db.get(Order, case.order.order_id).medicine_status = "ready"
    event = event_for(case)
    assert apply(case, event)
    paid = snapshot(case)
    assert paid[:6] == (
        "paid",
        "succeeded",
        "ready" if ready else "not_ready",
        case.order.payment_id,
        case.quote.quote_id,
        None,
    )
    assert not apply(case, event)
    assert case.calls == 1  # A committed inbox duplicate needs no upstream call.
    assert apply(case)  # Another event ID describing the same payment is also harmless.
    assert snapshot(case) == paid
    assert inbox_count(case) == 2


@pytest.mark.parametrize("status", ["submitting", "dispatched", "delivered", "exception"])
def test_distinct_replay_never_regresses_delivery(payment_case, status):
    case = payment_case
    apply(case)
    with case.sessions.begin() as db:
        order = db.get(Order, case.order.order_id)
        order.status = status
        order.delivery_id = uuid4()
    before = snapshot(case)
    assert apply(case)
    assert snapshot(case) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("payment_id", uuid4()),
        ("order_id", uuid4()),
        ("quote_id", uuid4()),
        ("tenant_id", uuid4()),
        ("patient_id", uuid4()),
        ("purpose", "consultation"),
        ("status", "pending"),
        ("status", "refunded"),
        ("resolution", "refund_required"),
        ("amount", {"amount_minor": 2781, "currency": "SGD"}),
        ("amount", {"amount_minor": 2780, "currency": "USD"}),
    ],
)
def test_mismatched_billing_facts_roll_back_inbox_and_order(payment_case, field, value):
    case = payment_case
    before = snapshot(case)
    case.fact = PaymentFact.model_validate(case.fact.model_dump() | {field: value})
    with pytest.raises(PaymentEventRejected):
        apply(case)
    assert snapshot(case) == before
    assert inbox_count(case) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"tenant_id": uuid4()},
        {"order_id": uuid4()},
        {"amount": {"amount_minor": 2781, "currency": "SGD"}},
        {"amount": {"amount_minor": 2780, "currency": "USD"}},
    ],
)
def test_event_context_is_verified(payment_case, changes):
    case = payment_case
    before = snapshot(case)
    with pytest.raises(PaymentEventRejected):
        apply(case, event_for(case, **changes))
    assert snapshot(case) == before
    assert inbox_count(case) == 0


@pytest.mark.parametrize(
    "target,field,value",
    [
        (Order, "payment_id", None),
        (Order, "payment_id", uuid4()),
        (Order, "quote_id", None),
        (Order, "payment_status", "unpaid"),
        (Order, "payment_status", "refund_required"),
        (Order, "payment_status", "refunded"),
        (Order, "status", "cancelled"),
        (Order, "status", "exception"),
        (Quote, "status", "active"),
        (Quote, "status", "superseded"),
        (Quote, "status", "expired"),
        (Quote, "tenant_id", uuid4()),
        (Quote, "order_id", None),
    ],
)
def test_missing_or_ineligible_reservation_is_not_paid(payment_case, target, field, value):
    case = payment_case
    with case.sessions.begin() as db:
        if target is Quote and field == "order_id":
            other = Order(
                tenant_id=uuid4(),
                patient_id=uuid4(),
                appointment_id=uuid4(),
                prescription_id=uuid4(),
                medication_subtotal_minor=0,
            )
            db.add(other)
            db.flush()
            value = other.order_id
        row = db.get(target, case.order.order_id if target is Order else case.quote.quote_id)
        setattr(row, field, value)
    before = snapshot(case)
    with pytest.raises(PaymentEventRejected):
        apply(case)
    assert snapshot(case) == before
    assert inbox_count(case) == 0


def test_quote_total_must_match_order(payment_case):
    case = payment_case
    with case.sessions.begin() as db:
        quote = db.get(Quote, case.quote.quote_id)
        quote.delivery_fee_minor += 1
        quote.total_minor += 1
    with pytest.raises(PaymentEventRejected):
        apply(case)
    assert inbox_count(case) == 0


def test_state_and_inbox_rollback_together_after_handler_flush(payment_case):
    case = payment_case
    event = event_for(case)
    before = snapshot(case)

    def crash(session, event):
        confirm_payment(session, event, case.billing)
        session.flush()
        raise RuntimeError("synthetic failure after state flush")

    with pytest.raises(RuntimeError):
        handle_event(case.sessions, event_inbox, "fulfilment", event, crash)
    assert snapshot(case) == before
    assert inbox_count(case) == 0
    assert apply(case, event)


@pytest.mark.parametrize("same_event", [True, False])
def test_concurrent_payments_produce_one_transition(payment_case, same_event):
    case = payment_case
    first = event_for(case)
    events = [first if same_event else event_for(case) for _ in range(6)]

    def attempt(event):
        try:
            return apply(case, event)
        except IntegrityError:
            # M03 leaves concurrent inbox conflicts unacknowledged; redelivery deduplicates.
            return apply(case, event)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(attempt, events))
    assert sum(results) == (1 if same_event else 6)
    assert snapshot(case)[:2] == ("paid", "succeeded")
    assert inbox_count(case) == (1 if same_event else 6)


class Queue:
    def __init__(self, case, event):
        self.case = case
        self.body = {
            "source": event.source,
            "detail-type": event.detail_type,
            "detail": event.detail(),
        }
        self.deleted = 0
        self.fail_delete = False

    def receive_message(self, **kwargs):
        assert kwargs["WaitTimeSeconds"] == 5
        return {"Messages": [{"Body": json.dumps(self.body), "ReceiptHandle": "synthetic"}]}

    def delete_message(self, **kwargs):
        assert inbox_count(self.case) == 1
        assert snapshot(self.case)[:2] == ("paid", "succeeded")
        if self.fail_delete:
            raise RuntimeError("synthetic acknowledgement failure")
        self.deleted += 1


def consume(case, queue):
    return consume_batch(
        case.sessions,
        event_inbox,
        queue,
        "synthetic-queue",
        "fulfilment",
        partial(confirm_payment, billing=case.billing),
        wait_seconds=5,
    )


def test_queue_acknowledges_only_committed_state_and_survives_delete_failure(payment_case):
    case = payment_case
    queue = Queue(case, event_for(case))
    queue.fail_delete = True
    assert consume(case, queue).processed == 1
    assert queue.deleted == 0
    queue.fail_delete = False
    assert consume(case, queue).duplicates == 1
    assert queue.deleted == 1
    assert case.calls == 1


@pytest.mark.parametrize("invalid", ["source", "type", "version", "fact"])
def test_invalid_messages_are_not_acknowledged(payment_case, invalid):
    case = payment_case
    queue = Queue(case, event_for(case))
    if invalid == "source":
        queue.body["source"] = "telelink.scheduling"
    elif invalid == "type":
        queue.body["detail-type"] = "consultation_payment_succeeded.v1"
    elif invalid == "version":
        queue.body["detail"]["schema_version"] = 2
    else:
        case.fact = case.fact.model_copy(update={"purpose": "consultation"})
    assert consume(case, queue).failed == 1
    assert queue.deleted == 0
    assert inbox_count(case) == 0
    assert snapshot(case)[:2] == ("awaiting_payment", "pending")


@pytest.mark.parametrize("status,body", [(401, {}), (404, {}), (503, {}), (302, {}), (200, {})])
def test_billing_lookup_errors_fail_closed(status, body):
    client = BillingClient(
        Settings(environment="test", billing_url="http://billing.test", billing_secret=SECRET),
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)),
    )
    try:
        with pytest.raises(PaymentEventRejected, match="verification unavailable"):
            client.payment(uuid4())
    finally:
        client.close()


@pytest.mark.parametrize(
    "values",
    [
        {"billing_secret": "short"},
        {"billing_secret": SECRET, "cursor_secret": SECRET},
        {"billing_url": "http://user:pass@billing.test"},
        {"billing_url": "http://billing.test?secret=hidden"},
        {"billing_url": "http://billing.test#fragment"},
        {"environment": "production", "billing_url": "http://billing.test"},
        {"payment_queue_name": "bad/queue"},
    ],
)
def test_payment_worker_configuration_fails_closed(values):
    with pytest.raises(ValidationError):
        Settings(**values)


def test_worker_requires_billing_credentials():
    with pytest.raises(ValueError, match="requires billing_url and billing_secret"):
        BillingClient(Settings(environment="test"))
