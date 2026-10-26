from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from pydantic import SecretStr
from telelink_common.errors import DomainError
from telelink_common.service_auth import service_token

from app.integrations.dispensing import HttpDispensing
from app.models import CatalogueItem, Order, Quote
from app.settings import Settings
from tests.test_api import MEDICATION, PATIENT, TENANT, context, identity
from tests.test_api import api as api
from tests.test_quotes import quote
from tests.test_quotes import quotes as quotes

KEY = SecretStr("billing-fulfilment-d07-test-secret-32-bytes")


def reservation(client, state, payment=None, **changes):
    return client.post(
        f"/internal/orders/{state.order_id}/checkout-reservation",
        json={
            "patient_id": str(PATIENT),
            "quote_id": state.quote_id,
            "payment_id": str(payment or state.payment_id),
        }
        | changes,
        headers={
            "Authorization": "Bearer "
            + service_token(KEY, "billing", "telelink-fulfilment-billing")
        },
    )


def prepare(quotes):
    client, state = quotes
    client.app.state.settings.billing_secret = KEY
    state.quote_id = quote(client, state).json()["quote_id"]
    state.payment_id = uuid4()
    return client, state


def test_reservation_is_atomic_trusted_and_stable_on_replay(quotes):
    client, state = prepare(quotes)
    result = reservation(client, state)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["payment_status"] == "pending" and data["quote_status"] == "accepted"
    assert data["total"]["amount_minor"] == 3248
    assert "destination" not in result.text and "instructions" not in result.text
    with state.sessions.begin() as session:
        session.get(CatalogueItem, (TENANT, MEDICATION)).unit_price_minor = 9999
    assert reservation(client, state).json() == data
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: reservation(client, state), range(4)))
    assert all(response.json() == data for response in results)


def test_reservation_rejects_browser_foreign_tampered_and_expired_context(quotes):
    client, state = prepare(quotes)
    path = f"/internal/orders/{state.order_id}/checkout-reservation"
    assert client.post(path, json={}).status_code == 401
    assert reservation(client, state, patient_id=str(uuid4())).status_code == 404
    assert reservation(client, state, total=1).status_code == 422
    state.source.context = context(status="draft")
    assert reservation(client, state).status_code == 409
    state.source.context = context()
    with state.sessions.begin() as session:
        row = session.get(Quote, UUID(state.quote_id))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        row.created_at = row.expires_at - timedelta(minutes=1)
    assert reservation(client, state).status_code == 409
    with state.sessions() as session:
        assert session.get(Order, UUID(state.order_id)).payment_id is None


@pytest.mark.parametrize("status", ["pending", "succeeded", "failed"])
def test_only_authoritative_failed_attempt_releases_old_binding(quotes, monkeypatch, status):
    client, state = prepare(quotes)
    assert reservation(client, state).status_code == 200
    from app.api import checkout

    class Billing:
        def __init__(self, settings):
            pass

        def close(self):
            pass

        def checkout_attempt(self, payment_id):
            return dict(
                payment_id=str(payment_id),
                order_id=state.order_id,
                patient_id=str(PATIENT),
                quote_id=state.quote_id,
                status=status,
            )

    monkeypatch.setattr(checkout, "BillingClient", Billing)
    client.app.state.settings.billing_url = "http://billing.test"
    result = reservation(client, state, payment=uuid4())
    assert result.status_code == (200 if status == "failed" else 409)


@pytest.mark.parametrize("status", ["pending", "succeeded", "failed", "foreign"])
def test_patient_reconciliation_requires_own_order_and_authoritative_failure(
    quotes, monkeypatch, status
):
    client, state = prepare(quotes)
    assert reservation(client, state).status_code == 200
    from app.api import checkout

    class Billing:
        def __init__(self, settings):
            pass

        def close(self):
            pass

        def checkout_attempt(self, payment_id):
            return dict(
                payment_id=str(payment_id),
                order_id=str(uuid4()) if status == "foreign" else state.order_id,
                patient_id=str(PATIENT),
                quote_id=state.quote_id,
                status=status,
            )

    monkeypatch.setattr(checkout, "BillingClient", Billing)
    client.app.state.settings.billing_url = "http://billing.test"
    path = f"/orders/{state.order_id}/reconcile-payment"
    state.identity = identity(subject=uuid4())
    assert client.post(path, json={}).status_code == 404
    state.identity = identity()
    assert client.post(path, json={"status": "failed"}).status_code == 422
    result = client.post(path, json={})
    assert result.status_code == (
        200 if status == "failed" else 502 if status == "foreign" else 409
    )
    with state.sessions() as session:
        order = session.get(Order, UUID(state.order_id))
        assert order.payment_status == ("unpaid" if status == "failed" else "pending")
        assert (order.payment_id is None) == (status == "failed")


@pytest.mark.parametrize("mode", ["valid", "foreign", "private_extra", "down", "draft", "timeout"])
def test_dispensing_http_adapter_auth_context_and_safe_errors(mode):
    value = context().model_dump(mode="json")

    def response(request):
        claims = jwt.decode(
            request.headers["Authorization"].split()[1],
            "r" * 32,
            algorithms=["HS256"],
            audience="telelink-records-fulfilment",
        )
        assert claims["sub"] == "fulfilment"
        assert request.url.params["patient_id"] == str(PATIENT)
        if mode == "timeout":
            raise httpx.ReadTimeout("private clinical content")
        body = value | ({"patient_id": str(uuid4())} if mode == "foreign" else {})
        if mode == "private_extra":
            body["instructions"] = "private"
        return httpx.Response(503 if mode == "down" else 409 if mode == "draft" else 200, json=body)

    source = HttpDispensing(
        Settings(
            _env_file=None,
            environment="test",
            records_url="http://records.test/api/v1/clinical-records",
            records_secret="r" * 32,
        ),
        transport=httpx.MockTransport(response),
    )
    try:
        if mode == "valid":
            assert source.get(UUID(value["prescription_id"]), PATIENT, "d07").patient_id == PATIENT
        else:
            with pytest.raises(DomainError) as error:
                source.get(UUID(value["prescription_id"]), PATIENT, "d07")
            assert "private" not in str(error.value)
    finally:
        source.close()
