import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import partial
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import httpx
import jwt
import pytest
import test_api
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from telelink_common.inbox import consume_batch, handle_event
from test_appointments import record
from test_payments import SECRET, Queue, adapter, event_for, rows

from app import payments
from app.billing import BillingClient
from app.models import Appointment, AvailabilitySlot, PaymentRecovery, event_inbox
from app.payment_recovery import deliver_resolutions
from app.payments import PaymentEventRejected, confirm_payment
from app.transitions import cancel_appointment, lock_appointment

api = test_api.api
api_database = test_api.api_database


def process(api, appointment, *, billing=None, event=None):
    billing = billing or adapter(appointment)
    try:
        return handle_event(
            sessionmaker(api[-1]),
            event_inbox,
            "scheduling",
            event or event_for(appointment),
            partial(confirm_payment, billing=billing, tenant=api[0].app.state.tenant_client),
        )
    finally:
        billing.close()


def audit(api, payment_id):
    with Session(api[-1]) as session:
        return session.get(PaymentRecovery, payment_id)


@pytest.mark.parametrize("already_expired", [False, True])
def test_late_recovery_and_duplicates_retain_original_deadline(api, already_expired):
    appointment = record(api, status="pending_payment", expired=True)
    if already_expired:
        with Session(api[-1]) as session, session.begin():
            session.get(Appointment, appointment.appointment_id).status = "expired"
    event = event_for(appointment)
    assert process(api, appointment, event=event)
    assert not process(api, appointment, event=event)
    assert process(api, appointment)
    assert rows(api[-1], appointment)[:3] == ("confirmed", "confirmed", None)
    recovery = audit(api, appointment.payment_id)
    assert recovery.outcome == "recovered"
    assert recovery.hold_expires_at == appointment.hold_expires_at
    assert recovery.event_id == event.event_id
    assert len(rows(api[-1], appointment)[3]) == 1


@pytest.mark.parametrize("condition", ["inactive", "doctor_removed", "withdrawn", "started"])
def test_unavailable_late_success_becomes_explicit_exception(api, condition, monkeypatch):
    appointment = record(api, status="pending_payment", expired=True)
    if condition == "inactive":
        api[5]["active"] = False
    elif condition == "doctor_removed":
        api[5]["directory"] = []
    elif condition == "withdrawn":
        with Session(api[-1]) as session, session.begin():
            session.get(AvailabilitySlot, appointment.slot_id).withdrawn_at = datetime.now(
                timezone.utc
            )
    else:
        monkeypatch.setattr(payments, "server_now", lambda _: appointment.starts_at)
    process(api, appointment)
    assert rows(api[-1], appointment)[:2] == ("expired", "refund_required")
    assert audit(api, appointment.payment_id).reason == "appointment_unavailable"
    assert not rows(api[-1], appointment)[3]
    response = api[0].get(f"/appointments/{appointment.appointment_id}", headers=api[1]("patient"))
    assert response.status_code == 200
    assert response.json()["payment_resolution"] == "refund_required"


@pytest.mark.parametrize("error_field", ["tenant_error", "doctor_error"])
def test_eligibility_outage_rolls_back_and_retry_recovers(api, error_field):
    appointment = record(api, status="pending_payment", expired=True)
    api[5][error_field] = 503
    with pytest.raises(PaymentEventRejected):
        process(api, appointment)
    assert rows(api[-1], appointment)[0] == "pending_payment"
    assert audit(api, appointment.payment_id) is None
    api[5][error_field] = None
    process(api, appointment)
    assert rows(api[-1], appointment)[0] == "confirmed"


def test_cancelled_late_success_never_reopens_and_is_deduplicated(api):
    appointment = record(api, status="pending_payment")
    with Session(api[-1]) as session, session.begin():
        cancel_appointment(
            lock_appointment(session, appointment.appointment_id),
            datetime.now(timezone.utc),
            "Requested",
            api[4]["patient"],
            session=session,
        )
    process(api, appointment)
    process(api, appointment)
    assert rows(api[-1], appointment)[:2] == ("cancelled", "refund_required")
    assert audit(api, appointment.payment_id).reason == "appointment_cancelled"
    assert not rows(api[-1], appointment)[3]


def test_earlier_success_can_replace_unconfirmed_attempt_but_extra_charge_cannot(api):
    appointment = record(api, status="pending_payment", expired=True)
    earlier_id = uuid4()
    process(
        api,
        appointment,
        billing=adapter(appointment, lookup_id=earlier_id, payment_id=str(earlier_id)),
        event=event_for(appointment, payment_id=earlier_id),
    )
    with Session(api[-1]) as session:
        assert session.get(Appointment, appointment.appointment_id).payment_id == earlier_id
    process(api, appointment)
    with Session(api[-1]) as session:
        current = session.get(Appointment, appointment.appointment_id)
        assert current.payment_id == earlier_id
        assert current.payment_resolution == "confirmed"
    assert audit(api, appointment.payment_id).reason == "duplicate_charge"
    assert len(rows(api[-1], appointment)[3]) == 1


def test_late_success_competing_with_new_hold_never_double_books(api):
    old = record(api, status="pending_payment", expired=True)
    barrier = Barrier(2)

    def pay():
        barrier.wait(timeout=5)
        process(api, old)

    def book():
        barrier.wait(timeout=5)
        return api[0].post(
            "/appointments",
            headers=api[1]("other_patient"),
            json={"tenant_id": str(old.tenant_id), "slot_id": str(old.slot_id)},
        )

    with ThreadPoolExecutor(2) as pool:
        paid, booked = pool.submit(pay), pool.submit(book)
        paid.result(timeout=15)
        response = booked.result(timeout=15)
    if response.status_code == 201:
        assert rows(api[-1], old)[:2] == ("expired", "refund_required")
        assert audit(api, old.payment_id).reason == "slot_reallocated"
    else:
        assert response.status_code == 409
        assert rows(api[-1], old)[:2] == ("confirmed", "confirmed")
    with Session(api[-1]) as session:
        active = session.scalars(
            select(Appointment).where(
                Appointment.slot_id == old.slot_id,
                Appointment.status.in_(["held", "pending_payment", "confirmed", "in_progress"]),
            )
        ).all()
        assert len(active) == 1


def test_reallocated_hold_that_also_expired_can_be_released_for_recovery(api):
    old = record(api, status="pending_payment", expired=True)
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
            hold_expires_at=now - timedelta(minutes=1),
            created_at=now - timedelta(minutes=5),
        )
        session.add(replacement)
        session.flush()
    process(api, old)
    assert rows(api[-1], old)[0] == "confirmed"
    assert rows(api[-1], replacement)[0] == "expired"


def test_refund_delivery_failure_retry_and_idempotent_acknowledgement(api):
    appointment = record(api, status="pending_payment", expired=True)
    api[5]["active"] = False
    process(api, appointment)
    calls, fail = [], [True]

    def respond(request):
        assert request.method == "POST"
        assert request.url.path == f"/internal/payments/{appointment.payment_id}/resolution"
        assert json.loads(request.content) == {
            "resolution": "refund_required",
            "resource_id": str(appointment.appointment_id),
            "reason": "appointment_unavailable",
        }
        claims = jwt.decode(
            request.headers["Authorization"].split()[1],
            SECRET,
            algorithms=["HS256"],
            audience="telelink-billing-scheduling",
            issuer="telelink-service:scheduling",
        )
        assert claims["sub"] == "scheduling"
        calls.append(request.content)
        if fail[0]:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "payment_id": str(appointment.payment_id),
                "appointment_id": str(appointment.appointment_id),
                "tenant_id": str(appointment.tenant_id),
                "patient_id": str(appointment.patient_id),
                "purpose": "consultation",
                "status": "succeeded",
                "amount": {"amount_minor": 3210, "currency": "SGD"},
                "resolution": "refund_required",
            },
        )

    settings = test_api.configuration(billing_url="http://billing.test", billing_secret=SECRET)
    billing = BillingClient(settings, transport=httpx.MockTransport(respond))
    sessions = sessionmaker(api[-1])
    with Session(api[-1]) as session, session.begin():
        for row in session.scalars(
            select(PaymentRecovery).where(PaymentRecovery.payment_id != appointment.payment_id)
        ):
            row.delivered_at = datetime.now(timezone.utc)
    assert deliver_resolutions(sessions, billing) == {"delivered": 0, "failed": 1}
    assert audit(api, appointment.payment_id).delivered_at is None
    fail[0] = False
    assert deliver_resolutions(sessions, billing) == {"delivered": 1, "failed": 0}
    assert audit(api, appointment.payment_id).delivered_at is not None
    assert deliver_resolutions(sessions, billing) == {"delivered": 0, "failed": 0}
    assert len(calls) == 2 and calls[0] == calls[1]
    billing.close()


def test_late_outbox_failure_rolls_back_recovery_audit(api, monkeypatch):
    appointment = record(api, status="pending_payment", expired=True)

    def fail(*_):
        raise RuntimeError("outbox failure")

    monkeypatch.setattr(payments, "add_event", fail)
    with pytest.raises(RuntimeError):
        process(api, appointment)
    assert rows(api[-1], appointment)[:2] == ("pending_payment", "awaiting_payment")
    assert audit(api, appointment.payment_id) is None


def test_refund_exception_commits_before_queue_acknowledgement(api):
    appointment = record(api, status="pending_payment", expired=True)
    api[5]["active"] = False
    queue = Queue(event_for(appointment))
    billing = adapter(appointment)
    result = consume_batch(
        sessionmaker(api[-1]),
        event_inbox,
        queue,
        "test",
        "scheduling",
        partial(confirm_payment, billing=billing, tenant=api[0].app.state.tenant_client),
    )
    assert result.processed == 1 and queue.deleted == ["receipt"]
    assert audit(api, appointment.payment_id).delivered_at is None
    assert rows(api[-1], appointment)[:2] == ("expired", "refund_required")
    billing.close()


def test_cancel_after_late_recovery_preserves_audit_and_queues_refund(api):
    appointment = record(api, status="pending_payment", expired=True)
    process(api, appointment)
    recovered = audit(api, appointment.payment_id)
    assert recovered.recovered_at is not None
    with Session(api[-1]) as session, session.begin():
        cancel_appointment(
            lock_appointment(session, appointment.appointment_id),
            datetime.now(timezone.utc),
            "Requested",
            api[4]["patient"],
            session=session,
        )
    current = audit(api, appointment.payment_id)
    assert current.recovered_at == recovered.recovered_at
    assert current.hold_expires_at == appointment.hold_expires_at
    assert current.reason == "appointment_cancelled" and current.delivered_at is None
    process(api, appointment)
    assert rows(api[-1], appointment)[:2] == ("cancelled", "refund_required")
    assert len(rows(api[-1], appointment)[3]) == 1


def test_remote_success_local_commit_failure_replays_idempotently(api):
    appointment = record(api, status="pending_payment", expired=True)
    api[5]["active"] = False
    process(api, appointment)
    sessions = sessionmaker(api[-1])
    with sessions.begin() as session:
        for row in session.scalars(
            select(PaymentRecovery).where(PaymentRecovery.payment_id != appointment.payment_id)
        ):
            row.delivered_at = datetime.now(timezone.utc)
    fact_client = adapter(appointment)
    fact = fact_client.payment(appointment.payment_id)
    fact_client.close()
    calls = []

    def acknowledge(recovery):
        calls.append((recovery.payment_id, recovery.reason))
        return fact

    billing = SimpleNamespace(refund_required=acknowledge)

    def fail_commit(session):
        raise RuntimeError("commit failure after remote acknowledgement")

    sqlalchemy_event.listen(sessions, "before_commit", fail_commit)
    try:
        with pytest.raises(RuntimeError, match="commit failure"):
            deliver_resolutions(sessions, billing)
    finally:
        sqlalchemy_event.remove(sessions, "before_commit", fail_commit)
    assert audit(api, appointment.payment_id).delivered_at is None
    assert deliver_resolutions(sessions, billing) == {"delivered": 1, "failed": 0}
    assert len(calls) == 2 and calls[0] == calls[1]
