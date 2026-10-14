import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import partial
from threading import Barrier
from uuid import uuid4

import httpx
import jwt
import pytest
import test_api
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from telelink_common.events import new_event
from telelink_common.inbox import consume_batch, handle_event
from test_appointments import record

from app import payments
from app.billing import BillingClient
from app.models import Appointment, event_inbox, event_outbox
from app.payments import PaymentEventRejected, confirm_payment
from app.transitions import cancel_appointment, lock_appointment

api = test_api.api
api_database = test_api.api_database
SECRET = "s05-billing-test-secret-at-least-32-bytes"


def event_for(appointment, **changes):
    return new_event(
        "consultation_payment_succeeded.v1",
        tenant_id=appointment.tenant_id,
        correlation_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        data={
            "appointment_id": appointment.appointment_id,
            "payment_id": appointment.payment_id,
            "amount": {"amount_minor": 3210, "currency": "SGD"},
        }
        | changes,
    )


def adapter(appointment, **changes):
    fact = {
        "payment_id": str(appointment.payment_id),
        "appointment_id": str(appointment.appointment_id),
        "tenant_id": str(appointment.tenant_id),
        "patient_id": str(appointment.patient_id),
        "purpose": "consultation",
        "status": "succeeded",
        "amount": {"amount_minor": 3210, "currency": "SGD"},
    } | changes

    def respond(request):
        assert request.url.path == f"/internal/payments/{appointment.payment_id}"
        claims = jwt.decode(
            request.headers["Authorization"].split()[1],
            SECRET,
            algorithms=["HS256"],
            audience="telelink-billing-scheduling",
            issuer="telelink-service:scheduling",
        )
        assert claims["sub"] == "scheduling" and claims["exp"] - claims["iat"] == 60
        return httpx.Response(200, json=fact)

    settings = test_api.configuration(billing_url="http://billing.test", billing_secret=SECRET)
    return BillingClient(settings, transport=httpx.MockTransport(respond))


def rows(engine, appointment):
    with Session(engine) as session:
        stored = session.get(Appointment, appointment.appointment_id)
        outgoing = (
            session.execute(
                select(event_outbox).where(
                    event_outbox.c.detail.contains(str(appointment.appointment_id))
                )
            )
            .mappings()
            .all()
        )
        return stored.status, stored.payment_resolution, stored.hold_expires_at, outgoing


def test_success_and_both_kinds_of_duplicate(api):
    appointment = record(api, status="pending_payment")
    billing = adapter(appointment)
    event = event_for(appointment)
    sessions = sessionmaker(api[-1])
    handler = partial(confirm_payment, billing=billing)
    assert handle_event(sessions, event_inbox, "scheduling", event, handler)
    assert not handle_event(sessions, event_inbox, "scheduling", event, handler)
    assert handle_event(sessions, event_inbox, "scheduling", event_for(appointment), handler)
    status, resolution, deadline, outgoing = rows(api[-1], appointment)
    assert (status, resolution, deadline) == ("confirmed", "confirmed", None)
    assert len(outgoing) == 1
    detail = json.loads(outgoing[0]["detail"])
    assert detail["correlation_id"] == str(event.correlation_id)
    assert detail["tenant_id"] == str(appointment.tenant_id)
    billing.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"tenant_id": str(uuid4())},
        {"patient_id": str(uuid4())},
        {"appointment_id": str(uuid4())},
        {"payment_id": str(uuid4())},
        {"purpose": "medication_delivery"},
        {"status": "pending"},
        {"amount": {"amount_minor": 3209, "currency": "SGD"}},
        {"amount": {"amount_minor": 3210, "currency": "USD"}},
    ],
)
def test_billing_context_mismatch_rolls_back_inbox_and_appointment(api, changes):
    appointment = record(api, status="pending_payment")
    billing = adapter(appointment, **changes)
    event = event_for(appointment)
    with pytest.raises(PaymentEventRejected):
        handle_event(
            sessionmaker(api[-1]),
            event_inbox,
            "scheduling",
            event,
            partial(confirm_payment, billing=billing),
        )
    assert rows(api[-1], appointment)[0] == "pending_payment"
    with Session(api[-1]) as session:
        assert (
            session.scalar(
                select(event_inbox.c.event_id).where(event_inbox.c.event_id == event.event_id)
            )
            is None
        )
    billing.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("payment_id", uuid4()),
        ("amount", {"amount_minor": 1, "currency": "SGD"}),
    ],
)
def test_event_context_mismatch(api, field, value):
    appointment = record(api, status="pending_payment")
    billing = adapter(appointment)
    # Adapter accepts the lookup ID here; mismatch is rejected by the domain handler.
    fact = billing.payment(appointment.payment_id)
    billing.payment = lambda _: fact
    with pytest.raises(PaymentEventRejected):
        handle_event(
            sessionmaker(api[-1]),
            event_inbox,
            "scheduling",
            event_for(appointment, **{field: value}),
            partial(confirm_payment, billing=billing),
        )
    billing.close()


@pytest.mark.parametrize("status", ["cancelled", "expired", "held"])
def test_no_reopening_or_unbound_confirmation(api, status):
    appointment = record(api, status="pending_payment")
    billing = adapter(appointment)
    with Session(api[-1]) as session, session.begin():
        session.get(Appointment, appointment.appointment_id).status = status
    with pytest.raises(PaymentEventRejected):
        handle_event(
            sessionmaker(api[-1]),
            event_inbox,
            "scheduling",
            event_for(appointment),
            partial(confirm_payment, billing=billing),
        )
    assert rows(api[-1], appointment)[0] == status
    billing.close()


def test_exact_deadline_uses_processing_time(api, monkeypatch):
    appointment = record(api, status="pending_payment")
    billing = adapter(appointment)
    monkeypatch.setattr(payments, "server_now", lambda _: appointment.hold_expires_at)
    with pytest.raises(PaymentEventRejected, match="S06"):
        handle_event(
            sessionmaker(api[-1]),
            event_inbox,
            "scheduling",
            event_for(appointment),
            partial(confirm_payment, billing=billing),
        )
    assert rows(api[-1], appointment)[0] == "pending_payment"
    billing.close()


def test_outbox_failure_rolls_back_confirmation(api, monkeypatch):
    appointment = record(api, status="pending_payment")
    billing = adapter(appointment)

    def fail(*_):
        raise RuntimeError("test outbox failure")

    monkeypatch.setattr(payments, "add_event", fail)
    with pytest.raises(RuntimeError):
        handle_event(
            sessionmaker(api[-1]),
            event_inbox,
            "scheduling",
            event_for(appointment),
            partial(confirm_payment, billing=billing),
        )
    assert rows(api[-1], appointment)[0] == "pending_payment"
    billing.close()


def test_concurrent_distinct_events_emit_one_confirmation(api):
    appointment = record(api, status="pending_payment")
    billing = adapter(appointment)
    barrier = Barrier(2)

    def run(_):
        barrier.wait(timeout=5)
        return handle_event(
            sessionmaker(api[-1]),
            event_inbox,
            "scheduling",
            event_for(appointment),
            partial(confirm_payment, billing=billing),
        )

    with ThreadPoolExecutor(2) as executor:
        assert list(executor.map(run, range(2))) == [True, True]
    assert len(rows(api[-1], appointment)[3]) == 1
    billing.close()


class Queue:
    def __init__(self, event):
        self.deleted = []
        self.messages = [
            {
                "ReceiptHandle": "receipt",
                "Body": json.dumps(
                    {
                        "source": event.source,
                        "detail-type": event.detail_type,
                        "detail": event.detail(),
                    }
                ),
            }
        ]

    def receive_message(self, **_):
        return {"Messages": self.messages}

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs["ReceiptHandle"])


def test_queue_acknowledgement_after_commit_and_retry_on_failure(api):
    appointment = record(api, status="pending_payment")
    billing = adapter(appointment, status="pending")
    queue = Queue(event_for(appointment))
    sessions = sessionmaker(api[-1])
    assert (
        consume_batch(
            sessions,
            event_inbox,
            queue,
            "test",
            "scheduling",
            partial(confirm_payment, billing=billing),
        ).failed
        == 1
    )
    assert not queue.deleted
    billing.close()
    billing = adapter(appointment)
    assert (
        consume_batch(
            sessions,
            event_inbox,
            queue,
            "test",
            "scheduling",
            partial(confirm_payment, billing=billing),
        ).processed
        == 1
    )
    assert queue.deleted == ["receipt"]
    assert (
        consume_batch(
            sessions,
            event_inbox,
            queue,
            "test",
            "scheduling",
            partial(confirm_payment, billing=billing),
        ).duplicates
        == 1
    )
    billing.close()


@pytest.mark.parametrize("response", [httpx.Response(503), httpx.Response(200, json={})])
def test_billing_unavailable_safe_error(response):
    settings = test_api.configuration(billing_url="http://billing.test", billing_secret=SECRET)
    client = BillingClient(settings, transport=httpx.MockTransport(lambda _: response))
    with pytest.raises(PaymentEventRejected, match="verification unavailable"):
        client.payment(uuid4())
    client.close()


def test_payment_and_cancellation_race_never_reopens(api):
    appointment = record(api, status="pending_payment")
    billing = adapter(appointment)
    barrier = Barrier(2)

    def pay():
        barrier.wait(timeout=5)
        try:
            handle_event(
                sessionmaker(api[-1]),
                event_inbox,
                "scheduling",
                event_for(appointment),
                partial(confirm_payment, billing=billing),
            )
            return "confirmed"
        except PaymentEventRejected:
            return "recovery"

    def cancel():
        barrier.wait(timeout=5)
        with Session(api[-1]) as session, session.begin():
            locked = lock_appointment(session, appointment.appointment_id)
            cancel_appointment(locked, payments.server_now(session), "Requested", api[4]["patient"])

    with ThreadPoolExecutor(2) as executor:
        paid, cancelled = executor.submit(pay), executor.submit(cancel)
        outcome = paid.result(timeout=10)
        cancelled.result(timeout=10)
    status, resolution, _, outgoing = rows(api[-1], appointment)
    assert status == "cancelled"
    assert resolution == ("refund_required" if outcome == "confirmed" else "awaiting_payment")
    assert len(outgoing) == (1 if outcome == "confirmed" else 0)
    billing.close()


def test_foreign_event_tenant_is_rejected(api):
    appointment = record(api, status="pending_payment")
    billing = adapter(appointment)
    event = event_for(appointment).model_copy(update={"tenant_id": uuid4()})
    with pytest.raises(PaymentEventRejected):
        handle_event(
            sessionmaker(api[-1]),
            event_inbox,
            "scheduling",
            event,
            partial(confirm_payment, billing=billing),
        )
    assert rows(api[-1], appointment)[0] == "pending_payment"
    billing.close()


def test_late_success_cannot_take_reallocated_slot(api):
    old = record(api, status="pending_payment", expired=True)
    billing = adapter(old)
    now = datetime.now(timezone.utc)
    with Session(api[-1], expire_on_commit=False) as session, session.begin():
        session.get(Appointment, old.appointment_id).status = "expired"
        session.flush()
        replacement = Appointment(
            slot_id=old.slot_id,
            tenant_id=old.tenant_id,
            patient_id=uuid4(),
            doctor_id=old.doctor_id,
            starts_at=old.starts_at,
            ends_at=old.ends_at,
            consultation_price_minor=3210,
            hold_expires_at=now + timedelta(minutes=5),
            created_at=now,
        )
        session.add(replacement)
        session.flush()
    with pytest.raises(PaymentEventRejected):
        handle_event(
            sessionmaker(api[-1]),
            event_inbox,
            "scheduling",
            event_for(old),
            partial(confirm_payment, billing=billing),
        )
    assert rows(api[-1], replacement)[0] == "held"
    assert rows(api[-1], old)[0] == "expired"
    billing.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"billing_url": "http://user:password@billing.test"},
        {"billing_secret": "short"},
        {"billing_secret": test_api.SERVICE},
    ],
)
def test_billing_configuration_guards(changes):
    with pytest.raises(ValueError):
        test_api.configuration(
            **({"billing_url": "http://billing.test", "billing_secret": SECRET} | changes)
        )


def test_live_floci_consumer_and_confirmation_publication(api):
    # Opt-in: real transport, synthetic authoritative billing read and checkout fixture.
    import os

    from telelink_common.aws import create_client
    from telelink_common.events import parse_sqs_body, to_put_events_entry
    from telelink_common.outbox import publish_pending

    endpoint = os.environ.get("TEST_AWS_ENDPOINT_URL")
    if not endpoint:
        pytest.skip("Set TEST_AWS_ENDPOINT_URL for the live Floci transport check")
    settings = test_api.configuration(aws_endpoint_url=endpoint)
    events, sqs = create_client("events", settings), create_client("sqs", settings)
    name = "s05-check-" + uuid4().hex
    queue_url = None
    rules = []
    events.create_event_bus(Name=name)
    billing = None
    try:
        queue_url = sqs.create_queue(QueueName=name)["QueueUrl"]
        arn = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])[
            "Attributes"
        ]["QueueArn"]
        rule_arns = []
        for index, (source, kind) in enumerate(
            [
                ("telelink.billing", "consultation_payment_succeeded.v1"),
                ("telelink.scheduling", "appointment_confirmed.v1"),
            ]
        ):
            rule = f"{name}-{index}"
            rule_arns.append(
                events.put_rule(
                    Name=rule,
                    EventBusName=name,
                    EventPattern=json.dumps({"source": [source], "detail-type": [kind]}),
                )["RuleArn"]
            )
            rules.append(rule)
            events.put_targets(Rule=rule, EventBusName=name, Targets=[{"Id": "queue", "Arn": arn}])
        sqs.set_queue_attributes(
            QueueUrl=queue_url,
            Attributes={
                "Policy": json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "events.amazonaws.com"},
                                "Action": "sqs:SendMessage",
                                "Resource": arn,
                                "Condition": {"ArnEquals": {"aws:SourceArn": rule_arns}},
                            }
                        ],
                    }
                )
            },
        )
        appointment = record(api, status="pending_payment")
        billing = adapter(appointment)
        event = event_for(appointment)
        assert (
            events.put_events(Entries=[to_put_events_entry(event, name)])["FailedEntryCount"] == 0
        )
        sessions = sessionmaker(api[-1])
        processed = 0
        for _ in range(10):
            result = consume_batch(
                sessions,
                event_inbox,
                sqs,
                queue_url,
                "scheduling",
                partial(confirm_payment, billing=billing),
                wait_seconds=1,
            )
            assert result.failed == 0
            processed += result.processed
            if processed:
                break
        assert processed == 1
        assert rows(api[-1], appointment)[0] == "confirmed"
        assert publish_pending(sessions, event_outbox, events, name).published >= 1
        found = False
        for _ in range(10):
            messages = sqs.receive_message(
                QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=1
            ).get("Messages", [])
            for message in messages:
                outgoing = parse_sqs_body(message["Body"], consumer="notification")
                if outgoing.data.appointment_id == appointment.appointment_id:
                    assert outgoing.correlation_id == event.correlation_id
                    found = True
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
            if found:
                break
        assert found
    finally:
        if billing:
            billing.close()
        for rule in rules:
            events.remove_targets(Rule=rule, EventBusName=name, Ids=["queue"])
            events.delete_rule(Name=rule, EventBusName=name)
        if queue_url:
            sqs.delete_queue(QueueUrl=queue_url)
        events.delete_event_bus(Name=name)
        events.close()
        sqs.close()
