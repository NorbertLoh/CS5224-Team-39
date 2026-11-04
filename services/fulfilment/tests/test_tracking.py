import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.integrations.delivery_orders import DeliveryUnavailable, SandboxDeliveries
from app.models import Delivery, event_outbox
from app.services.tracking import poll_delivery, poll_next
from app.settings import Settings
from app.workers.deliveries import submit_pending
from tests.test_deliveries import STOPS, rows
from tests.test_deliveries import eligible as eligible
from tests.test_payments import payment_case as payment_case


class Provider:
    def __init__(self, case):
        self.case = case
        self.status = "ASSIGNING_DRIVER"
        self.calls = 0
        self.error = False

    def inspect(self, provider_id, delivery, quote, fee):
        assert provider_id == self.case.provider.provider_id
        self.calls += 1
        if self.error:
            raise DeliveryUnavailable("Synthetic provider outage")
        return SimpleNamespace(orderId=provider_id, status=self.status)

    def submit(self, *args):
        raise AssertionError("Tracking must never create an order")


@pytest.fixture
def tracking(eligible):
    case = eligible
    submit_pending(case.sessions, case.provider, case.billing)
    case.delivery_id = rows(case)[1].delivery_id
    case.tracker = Provider(case)
    return case


def due(case, **changes):
    with case.sessions.begin() as db:
        delivery = db.get(Delivery, case.delivery_id)
        delivery.next_poll_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        for key, value in changes.items():
            setattr(delivery, key, value)


@pytest.mark.parametrize(
    "initial,provider,expected,order_status",
    [
        ("submitted", "ASSIGNING_DRIVER", "submitted", "dispatched"),
        ("submitted", "ON_GOING", "submitted", "dispatched"),
        ("submitted", "PICKED_UP", "picked_up", "dispatched"),
        ("submitted", "COMPLETED", "delivered", "delivered"),
        ("submitted", "CANCELED", "cancelled", "exception"),
        ("submitted", "REJECTED", "failed", "exception"),
        ("submitted", "EXPIRED", "failed", "exception"),
        ("unknown", "ASSIGNING_DRIVER", "submitted", "dispatched"),
        ("unknown", "PICKED_UP", "picked_up", "dispatched"),
        ("unknown", "COMPLETED", "delivered", "delivered"),
        ("unknown", "CANCELED", "failed", "exception"),
        ("picked_up", "ASSIGNING_DRIVER", "picked_up", "dispatched"),
        ("picked_up", "ON_GOING", "picked_up", "dispatched"),
        ("picked_up", "CANCELED", "failed", "exception"),
        ("picked_up", "COMPLETED", "delivered", "delivered"),
    ],
)
def test_verified_mapping_preserves_financial_state_and_rejects_regressions(
    tracking,
    initial,
    provider,
    expected,
    order_status,
):
    case = tracking
    due(case, status=initial)
    before, delivery, events = rows(case)
    case.tracker.status = provider
    outcome = poll_delivery(case.sessions, case.delivery_id, case.tracker)
    order, current, new_events = rows(case)
    assert outcome == ("updated" if initial != expected else "unchanged")
    assert current.status == expected and order.status == order_status
    assert order.payment_status == before.payment_status == "succeeded"
    assert order.payment_id == before.payment_id and order.total_minor == before.total_minor
    assert current.last_polled_at is not None
    assert current.next_poll_at > current.last_polled_at
    assert new_events == events + ([expected] if initial != expected else [])
    if initial == expected:
        assert current.updated_at == delivery.updated_at and order.updated_at == before.updated_at
    assert case.provider.calls == 1


@pytest.mark.parametrize("terminal", ["delivered", "cancelled", "failed"])
def test_terminal_state_is_never_polled_or_regressed(tracking, terminal):
    case = tracking
    due(case, status=terminal)
    before = rows(case)
    assert poll_delivery(case.sessions, case.delivery_id, case.tracker) == "skipped"
    assert poll_next(case.sessions, case.tracker) == "idle"
    assert case.tracker.calls == 0
    assert rows(case)[1].updated_at == before[1].updated_at
    assert rows(case)[2] == before[2]


def test_duplicate_snapshot_updates_schedule_without_duplicate_event(tracking):
    case = tracking
    case.tracker.status = "PICKED_UP"
    assert poll_next(case.sessions, case.tracker) == "updated"
    before = rows(case)
    assert poll_next(case.sessions, case.tracker) == "idle"
    due(case)
    assert poll_next(case.sessions, case.tracker) == "unchanged"
    assert rows(case)[1].updated_at == before[1].updated_at
    assert rows(case)[2] == before[2]


def test_concurrent_pollers_recheck_due_time_under_lock(tracking):
    case = tracking
    case.tracker.status = "COMPLETED"
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(
                lambda _: poll_delivery(case.sessions, case.delivery_id, case.tracker), range(6)
            )
        )
    assert results.count("updated") == 1
    assert results.count("skipped") == 5
    assert case.tracker.calls == 1
    assert rows(case)[2].count("delivered") == 1


def test_failure_backoff_survives_new_worker_and_success_resets_it(tracking):
    case = tracking
    before = rows(case)
    case.tracker.error = True
    assert poll_next(case.sessions, case.tracker) == "failed"
    _, failed, events = rows(case)
    assert failed.poll_attempts == 1 and failed.last_polled_at is None
    assert failed.poll_error == "provider_verification_unavailable"
    assert failed.next_poll_at >= datetime.now(timezone.utc) + timedelta(seconds=115)
    assert failed.status == before[1].status and failed.updated_at == before[1].updated_at
    assert events == before[2]
    restarted = Provider(case)
    assert poll_next(case.sessions, restarted) == "idle"
    assert restarted.calls == 0
    due(case)
    assert poll_next(case.sessions, restarted) == "unchanged"
    current = rows(case)[1]
    assert current.poll_attempts == 0 and current.poll_error is None


def test_backoff_is_bounded(tracking):
    case = tracking
    due(case, poll_attempts=20)
    case.tracker.error = True
    start = datetime.now(timezone.utc)
    assert poll_next(case.sessions, case.tracker) == "failed"
    delivery = rows(case)[1]
    assert delivery.poll_attempts == 20
    assert timedelta(seconds=3599) <= delivery.next_poll_at - start <= timedelta(seconds=3605)


@pytest.mark.parametrize(
    "changes",
    [
        {"provider_order_id": None},
        {"status": "pending"},
    ],
)
def test_no_poll_for_unsent_or_unidentified_intent(tracking, changes):
    case = tracking
    due(case, **changes)
    assert poll_next(case.sessions, case.tracker) == "idle"
    assert poll_delivery(case.sessions, case.delivery_id, case.tracker) == "skipped"
    assert case.tracker.calls == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", uuid4()),
        ("request_payload", None),
        ("send_started_at", None),
    ],
)
def test_invalid_local_linkage_never_reaches_provider(tracking, field, value):
    case = tracking
    due(case, **{field: value})
    assert poll_next(case.sessions, case.tracker) == "failed"
    assert case.tracker.calls == 0
    assert rows(case)[1].status == "submitted"


@pytest.mark.parametrize(
    "invalid",
    [
        "reference",
        "metadata",
        "quote",
        "fee",
        "route",
        "status",
        "http",
        "timeout",
    ],
)
def test_untrusted_provider_snapshot_fails_closed_with_real_adapter(tracking, invalid):
    case = tracking
    order, delivery, events = rows(case)
    data = {
        "orderId": delivery.provider_order_id,
        "quotationId": delivery.request_payload["quotationId"],
        "metadata": dict(delivery.request_payload["metadata"]),
        "priceBreakdown": {"total": "7.80", "currency": "SGD"},
        "status": "COMPLETED",
        "stops": json.loads(json.dumps(STOPS)),
    }
    if invalid == "reference":
        data["orderId"] = "3608133045767029418"
    elif invalid == "metadata":
        data["metadata"]["operation_id"] = str(uuid4())
    elif invalid == "quote":
        data["quotationId"] = "3608770529626608276"
    elif invalid == "fee":
        data["priceBreakdown"]["total"] = "7.90"
    elif invalid == "route":
        data["stops"][0]["address"] = "Different route"
    elif invalid == "status":
        data["status"] = "UNKNOWN_STATUS"

    def respond(request):
        assert request.method == "GET"
        if invalid == "timeout":
            raise httpx.ReadTimeout("Synthetic timeout")
        return httpx.Response(503 if invalid == "http" else 200, json={"data": data})

    provider = SandboxDeliveries(
        Settings(lalamove_api_key="pk_test_d06", lalamove_api_secret="sk_test_d06"),
        transport=httpx.MockTransport(respond),
    )
    try:
        assert poll_next(case.sessions, provider) == "failed"
    finally:
        provider.close()
    current_order, current, current_events = rows(case)
    assert current_order.status == order.status and current.status == delivery.status
    assert current_events == events and current.poll_attempts == 1


def test_status_order_schedule_and_outbox_rollback_together(tracking, monkeypatch):
    case = tracking
    before = rows(case)
    case.tracker.status = "COMPLETED"

    def crash(session, delivery, target):
        delivery.status = target
        session.flush()
        raise RuntimeError("Synthetic outbox failure")

    with monkeypatch.context() as patch:
        patch.setattr("app.services.tracking.change_status", crash)
        with pytest.raises(RuntimeError):
            poll_next(case.sessions, case.tracker)
    order, delivery, events = rows(case)
    assert order.status == before[0].status and delivery.status == before[1].status
    assert delivery.last_polled_at is None and events == before[2]
    assert poll_next(case.sessions, case.tracker) == "updated"
    assert rows(case)[2].count("delivered") == 1


def test_polling_requires_configured_bounded_interval():
    for seconds in (0, 29, 3601):
        with pytest.raises(ValidationError):
            Settings(delivery_poll_interval_seconds=seconds)
    assert Settings().delivery_poll_interval_seconds == 60


def test_tracking_event_payload_contains_only_operational_ids(tracking):
    case = tracking
    case.tracker.status = "COMPLETED"
    assert poll_next(case.sessions, case.tracker) == "updated"
    with case.sessions() as db:
        details = db.scalars(select(event_outbox.c.detail)).all()
        latest = [
            json.loads(raw) for raw in details if json.loads(raw)["data"]["status"] == "delivered"
        ]
    assert len(latest) == 1
    assert latest[0]["tenant_id"] == str(case.order.tenant_id)
    assert set(latest[0]["data"]) == {"delivery_id", "order_id", "status"}
