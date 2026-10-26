from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from telelink_common.errors import DomainError

from app.delivery_provider import DeliveryPrice
from app.main import create_app
from app.models import CatalogueItem, Order, Quote, QuoteRequest
from app.settings import Settings
from tests.test_api import (
    MEDICATION,
    OTHER_PATIENT,
    OTHER_TENANT,
    TENANT,
    create,
    identity,
)
from tests.test_api import api as api

DESTINATION = {"address_line": "3 Temasek Boulevard", "postal_code": "038983", "country_code": "SG"}
RECIPIENT = {"name": "Synthetic recipient", "phone_number": "+6581234567"}


class Provider:
    def __init__(self):
        self.calls = 0
        self.expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
        self.amount = 780
        self.error = None

    def quote(self, tenant_id, destination):
        self.calls += 1
        if self.error:
            raise self.error
        return DeliveryPrice(
            amount_minor=self.amount,
            expires_at=self.expiry,
            context={"quotation_id": "1234567890123456789"},
        )

    def close(self):
        pass


@pytest.fixture
def quotes(api):
    client, state, app = api
    app.state.delivery_quotes.close()
    state.provider = Provider()
    app.state.delivery_quotes = state.provider
    state.order_id = create(client).json()["order_id"]
    return client, state


def quote(client, state, key="quote-key", destination=None, **extra):
    return client.post(
        f"/orders/{state.order_id}/quotes",
        headers={"Idempotency-Key": key},
        json={"destination": destination or DESTINATION, "recipient": RECIPIENT} | extra,
    )


def test_trusted_totals_refresh_snapshots_supersession_and_replay(quotes):
    client, state = quotes
    first = quote(client, state)
    assert first.status_code == 201, first.text
    data = first.json()
    assert data["medication_subtotal"]["amount_minor"] == 2468
    assert data["delivery_fee"]["amount_minor"] == 780
    assert data["total"]["amount_minor"] == 3248
    assert (
        datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")) <= state.provider.expiry
    )
    assert "Temasek" not in first.text and "1234567890123456789" not in first.text
    with state.sessions.begin() as db:
        db.get(CatalogueItem, (TENANT, MEDICATION)).unit_price_minor = 2000
    second = quote(client, state, key="new-key").json()
    assert second["medication_subtotal"]["amount_minor"] == 4000
    assert client.get(f"/quotes/{data['quote_id']}").json()["status"] == "superseded"
    assert quote(client, state).json() == data
    assert state.provider.calls == 2
    order = client.get(f"/orders/{state.order_id}").json()
    assert order["items"][0]["unit_price"]["amount_minor"] == 2000
    assert order["quote_id"] == second["quote_id"]
    with state.sessions() as db:
        old = db.get(Quote, UUID(data["quote_id"]))
        assert old.items[0]["unit_price_minor"] == 1234
        assert old.destination == DESTINATION | {"recipient_contact": RECIPIENT}
    assert (
        quote(client, state, destination=DESTINATION | {"address_line": "other"}).status_code == 409
    )
    other_order = create(client, key="other-order", rx=uuid4()).json()["order_id"]
    saved = state.order_id
    state.order_id = other_order
    assert quote(client, state).status_code == 409
    state.order_id = saved


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_quotes(quotes, same_key):
    client, state = quotes
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda i: quote(client, state, key="same" if same_key else str(i)), range(4))
        )
    assert sorted(r.status_code for r in results) == ([200] * 3 + [201] if same_key else [201] * 4)
    assert state.provider.calls == (1 if same_key else 4)
    with state.sessions() as db:
        assert (
            db.scalar(select(func.count()).select_from(Quote).where(Quote.status == "active")) == 1
        )
        assert db.scalar(select(func.count()).select_from(QuoteRequest)) == (1 if same_key else 4)


def test_expiry_equality_and_ten_minute_cap(quotes, monkeypatch):
    client, state = quotes
    now = datetime.now(timezone.utc)
    monkeypatch.setattr("app.quotes.utcnow", lambda: now)
    state.provider.expiry = now + timedelta(hours=1)
    data = quote(client, state).json()
    expiry = now + timedelta(minutes=10)
    with state.sessions() as db:
        assert db.get(Quote, UUID(data["quote_id"])).expires_at == expiry
    monkeypatch.setattr("app.quotes.utcnow", lambda: expiry)
    assert client.get(f"/quotes/{data['quote_id']}").json()["status"] == "expired"
    state.provider.expiry = expiry
    assert quote(client, state, key="expired").status_code == 409
    state.provider.expiry = expiry + timedelta(minutes=2)
    assert quote(client, state, key="expired").status_code == 201
    with state.sessions() as db:
        assert db.get(Quote, UUID(data["quote_id"])).status == "expired"


@pytest.mark.parametrize(
    "changes",
    [
        {"payment_status": "pending"},
        {"payment_status": "succeeded"},
        {"payment_status": "refund_required"},
        {"payment_status": "refunded"},
        {"payment_id": uuid4()},
        {"status": "paid"},
        {"status": "cancelled"},
        {"status": "submitting"},
        {"status": "dispatched"},
        {"status": "delivered"},
        {"status": "exception"},
    ],
)
def test_unquotable_orders(quotes, changes):
    client, state = quotes
    with state.sessions.begin() as db:
        order = db.get(Order, UUID(state.order_id))
        for key, value in changes.items():
            setattr(order, key, value)
    assert quote(client, state).status_code == 409
    assert state.provider.calls == 0


def test_accepted_quote_cannot_be_replaced(quotes):
    client, state = quotes
    data = quote(client, state).json()
    with state.sessions.begin() as db:
        db.get(Quote, UUID(data["quote_id"])).status = "accepted"
    assert quote(client, state, key="new").status_code == 409


@pytest.mark.parametrize("failure", ["provider", "inactive", "overflow", "total_overflow"])
def test_failure_rolls_back_repricing_supersession_and_key(quotes, failure):
    client, state = quotes
    first = quote(client, state).json()
    with state.sessions.begin() as db:
        item = db.get(CatalogueItem, (TENANT, MEDICATION))
        item.unit_price_minor = 2000 if failure != "overflow" else 9007199254740991
        item.active = failure != "inactive"
    if failure == "provider":
        state.provider.error = DomainError(503, "delivery_unavailable", "Unavailable.")
    if failure == "total_overflow":
        state.provider.amount = 9007199254740991
    result = quote(client, state, key="retry")
    assert result.status_code == (503 if failure == "provider" else 409)
    with state.sessions() as db:
        order = db.get(Order, UUID(state.order_id))
        assert str(order.quote_id) == first["quote_id"]
        assert order.items[0].unit_price_minor == 1234
        assert db.get(Quote, order.quote_id).status == "active"
        assert db.scalar(select(func.count()).select_from(QuoteRequest)) == 1
    state.provider.error = None
    state.provider.amount = 780
    with state.sessions.begin() as db:
        item = db.get(CatalogueItem, (TENANT, MEDICATION))
        item.active, item.unit_price_minor = True, 2000
    assert quote(client, state, key="retry").status_code == 201


@pytest.mark.parametrize(
    "who,read_code,write_code",
    [
        (identity(), 200, 201),
        (identity(subject=OTHER_PATIENT), 404, 404),
        (identity(roles=(), clinic_role="clinic_admin"), 200, 403),
        (identity(roles=(), clinic_role="clinic_admin", active=False), 404, 403),
        (identity(roles=(), clinic_role="clinic_admin", tenant=OTHER_TENANT), 404, 403),
        (identity(roles=(), clinic_role="doctor"), 404, 403),
        (identity(roles=("platform_admin",)), 404, 403),
    ],
)
def test_quote_access(quotes, who, read_code, write_code):
    client, state = quotes
    data = quote(client, state).json()
    state.identity = who
    assert client.get(f"/quotes/{data['quote_id']}").status_code == read_code
    assert quote(client, state, key="other").status_code == write_code
    assert client.get(f"/quotes/{uuid4()}").status_code == 404


@pytest.mark.parametrize(
    "destination",
    [
        DESTINATION | {"country_code": "MY"},
        DESTINATION | {"postal_code": "12345"},
        DESTINATION | {"address_line": " "},
        DESTINATION | {"address_line": "a\nb"},
        DESTINATION | {"coordinates": {"lat": "1.2", "lng": "103.2"}},
    ],
)
def test_destination_validation(quotes, destination):
    client, state = quotes
    assert quote(client, state, destination=destination).status_code == 422
    assert state.provider.calls == 0


def test_no_auth_keys_and_browser_totals(quotes):
    client, state = quotes
    assert quote(client, state, total={"amount_minor": 1, "currency": "SGD"}).status_code == 422
    path = f"/orders/{state.order_id}/quotes"
    assert client.post(path, json={"destination": DESTINATION}).status_code == 422
    assert quote(client, state, key="bad key").status_code == 422


def test_unauthenticated_quotes_fail_closed():
    app = create_app(Settings(environment="test", database_url=None))
    with TestClient(app) as client:
        assert client.get(f"/quotes/{uuid4()}").status_code == 401
        assert (
            client.post(
                f"/orders/{uuid4()}/quotes",
                json={"destination": DESTINATION},
                headers={"Idempotency-Key": "key"},
            ).status_code
            == 401
        )


def test_unpriced_catalogue_blocks_quote_without_provider_call(quotes):
    client, state = quotes
    with state.sessions.begin() as db:
        db.get(CatalogueItem, (TENANT, MEDICATION)).unit_price_minor = None
    response = quote(client, state)
    assert response.status_code == 409 and response.json()["error"]["code"] == "medication_unpriced"
    assert state.provider.calls == 0
    with state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Quote)) == 0


def test_prescription_prices_ignore_catalogue_repricing(quotes):
    from app.models import PrescriptionPrice
    from tests.test_api import ITEM, PATIENT, RX

    client, state = quotes
    with state.sessions.begin() as db:
        order = db.get(Order, UUID(state.order_id))
        order.pricing_mode = "prescription"
        db.add(
            PrescriptionPrice(
                tenant_id=TENANT,
                prescription_id=RX,
                prescription_item_id=ITEM,
                medication_id=MEDICATION,
                display_name="Typed medicine",
                quantity=2,
                unit_price_minor=250,
                priced_by=PATIENT,
            )
        )
        db.get(CatalogueItem, (TENANT, MEDICATION)).unit_price_minor = 9999
    response = quote(client, state)
    assert response.status_code == 201, response.text
    assert response.json()["medication_subtotal"]["amount_minor"] == 500
