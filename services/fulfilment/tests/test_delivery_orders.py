import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import jwt
import pytest

from app.billing import BillingClient
from app.delivery_orders import (
    Contacts,
    DeliveryUnavailable,
    SandboxDeliveries,
    SubmissionRejected,
    SubmissionUncertain,
)
from app.settings import Settings
from tests.test_deliveries import STOPS

KEY, SECRET = "pk_test_d05", "sk_test_d05"
QUOTE, PROVIDER = "3608770529626608275", "3608133045767029417"


@pytest.fixture
def adapter():
    delivery = SimpleNamespace(
        delivery_id=uuid4(),
        operation_id=uuid4(),
        request_payload={"quotationId": QUOTE, "metadata": {}},
    )
    delivery.request_payload["metadata"] = {
        "delivery_id": str(delivery.delivery_id),
        "operation_id": str(delivery.operation_id),
    }
    quote = SimpleNamespace(
        provider_context={"mode": "lalamove-sandbox", "service_type": "MOTORCYCLE", "stops": STOPS}
    )
    data = {
        "orderId": PROVIDER,
        "quotationId": QUOTE,
        "metadata": delivery.request_payload["metadata"],
        "priceBreakdown": {"total": "7.80", "currency": "SGD"},
        "status": "ASSIGNING_DRIVER",
        "stops": STOPS,
    }
    state = SimpleNamespace(status=200, data=data, calls=0, error=None)

    def transport(request):
        state.calls += 1
        auth_key, timestamp, signature = request.headers["Authorization"][5:].split(":")
        assert auth_key == KEY
        raw = f"{timestamp}\r\n{request.method}\r\n{request.url.path}\r\n\r\n".encode()
        assert hmac.compare_digest(
            signature, hmac.new(SECRET.encode(), raw + request.content, hashlib.sha256).hexdigest()
        )
        assert request.headers["Market"] == "SG"
        assert request.url.host == "rest.sandbox.lalamove.com"
        assert request.url.scheme == "https"
        if request.method == "POST":
            assert request.headers["Request-ID"] == str(delivery.operation_id)
            assert json.loads(request.content) == {"data": delivery.request_payload}
        else:
            assert request.url.path == f"/v3/orders/{PROVIDER}"
        if state.error:
            raise state.error
        return httpx.Response(state.status, json={"data": state.data})

    client = SandboxDeliveries(
        Settings(lalamove_api_key=KEY, lalamove_api_secret=SECRET),
        transport=httpx.MockTransport(transport),
    )
    yield client, delivery, quote, state
    client.close()


def test_outbound_signing_and_verified_provider_reference(adapter):
    client, delivery, quote, state = adapter
    assert client.submit(delivery, quote, 780).orderId == PROVIDER
    assert client.inspect(PROVIDER, delivery, quote, 780).orderId == PROVIDER
    assert state.calls == 2


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 422, 429])
def test_explicit_provider_rejection_is_not_retried(adapter, status):
    client, delivery, quote, state = adapter
    state.status = status
    with pytest.raises(SubmissionRejected):
        client.submit(delivery, quote, 780)
    assert state.calls == 1


@pytest.mark.parametrize("status", [302, 408, 500, 502, 503])
def test_ambiguous_http_outcomes_remain_uncertain(adapter, status):
    client, delivery, quote, state = adapter
    state.status = status
    with pytest.raises(SubmissionUncertain):
        client.submit(delivery, quote, 780)
    assert state.calls == 1


def test_timeout_never_retries_post(adapter):
    client, delivery, quote, state = adapter
    state.error = httpx.ReadTimeout("Synthetic timeout, possibly after acceptance")
    with pytest.raises(SubmissionUncertain) as error:
        client.submit(delivery, quote, 780)
    assert error.value.provider_order_id is None
    assert state.calls == 1


@pytest.mark.parametrize("change", ["quote", "metadata", "price", "route", "status", "numeric_id"])
def test_unverifiable_acceptance_cannot_be_treated_as_success(adapter, change):
    client, delivery, quote, state = adapter
    data = json.loads(json.dumps(state.data))
    if change == "quote":
        data["quotationId"] = "3608770529626608276"
    elif change == "metadata":
        data["metadata"]["operation_id"] = str(uuid4())
    elif change == "price":
        data["priceBreakdown"]["total"] = "7.90"
    elif change == "route":
        data["stops"][1]["coordinates"]["lat"] = "1.31"
    elif change == "status":
        data["status"] = "UNRECOGNIZED"
    else:
        data["orderId"] = int(PROVIDER)
    state.data = data
    with pytest.raises(SubmissionUncertain):
        client.submit(delivery, quote, 780)
    with pytest.raises(DeliveryUnavailable):
        client.inspect(PROVIDER, delivery, quote, 780)
    assert state.calls == 2


def test_invalid_reconciliation_reference_never_reaches_network(adapter):
    client, delivery, quote, state = adapter
    with pytest.raises(DeliveryUnavailable):
        client.inspect("../untrusted", delivery, quote, 780)
    assert state.calls == 0


def test_invalid_private_contact_configuration_does_not_leak_contents(tmp_path):
    path = tmp_path / "contacts.json"
    path.write_text('{"senders":{"private contact":"invalid private phone"}}')
    with pytest.raises(DeliveryUnavailable) as error:
        SandboxDeliveries(Settings(delivery_contacts_path=path))
    assert str(error.value) == "Delivery contacts configuration unavailable"
    assert error.value.__suppress_context__


def test_prepare_uses_frozen_route_and_current_typed_contacts(adapter):
    client, delivery, quote, _ = adapter
    order = SimpleNamespace(tenant_id=uuid4(), patient_id=uuid4())
    client.contacts = Contacts(
        senders={order.tenant_id: {"name": "Synthetic clinic", "phone": "+6580000000"}},
        recipients={order.patient_id: {"name": "Synthetic recipient", "phone": "+6580000001"}},
    )

    def quotation(request):
        assert request.url.path == "/v3/quotations"
        assert json.loads(request.content)["data"]["stops"] == STOPS
        return httpx.Response(
            200,
            json={
                "data": {
                    "quotationId": QUOTE,
                    "serviceType": "MOTORCYCLE",
                    "expiresAt": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                    "priceBreakdown": {"total": "7.80", "currency": "SGD"},
                    "stops": [
                        {"stopId": str(3608770529626608280 + i), **stop}
                        for i, stop in enumerate(STOPS)
                    ],
                }
            },
        )

    client.quotes.client.close()
    client.quotes.client = httpx.Client(transport=httpx.MockTransport(quotation))
    price, payload = client.prepare(order, quote, delivery)
    assert price.amount_minor == 780
    assert payload["sender"]["phone"] == "+6580000000"
    assert payload["recipients"][0]["phone"] == "+6580000001"
    assert payload["metadata"]["operation_id"] == str(delivery.operation_id)
    assert payload["quotationId"] == QUOTE
    client.contacts = None
    with pytest.raises(DeliveryUnavailable):
        client.prepare(order, quote, delivery)


def test_prepare_uses_saved_clinic_contact_and_preserves_recipient_requirement(adapter):
    client, delivery, quote, _ = adapter
    order = SimpleNamespace(tenant_id=uuid4(), patient_id=uuid4())
    contact = {"name": "Settings pickup contact", "phone": "+6581234567"}
    client.clinic_locations = SimpleNamespace(
        get_contact=lambda tenant_id: contact, close=lambda: None
    )
    client.contacts = Contacts(
        senders={order.tenant_id: {"name": "Old directory contact", "phone": "+6580000000"}},
        recipients={order.patient_id: {"name": "Synthetic patient", "phone": "+6580000001"}},
    )
    client.quotes.quote_route = lambda stops: SimpleNamespace(
        context={"quotation_id": QUOTE, "stop_ids": ["pickup", "dropoff"]}
    )
    _, payload = client.prepare(order, quote, delivery)
    assert payload["sender"] == {"stopId": "pickup", **contact}
    assert payload["recipients"][0]["phone"] == "+6580000001"
    client.contacts = None
    with pytest.raises(DeliveryUnavailable):
        client.prepare(order, quote, delivery)


def test_invalid_saved_contact_never_falls_back_to_file_contact(adapter):
    client, delivery, quote, _ = adapter
    order = SimpleNamespace(tenant_id=uuid4(), patient_id=uuid4())
    client.clinic_locations = SimpleNamespace(
        get_contact=lambda tenant_id: {"name": "Bad contact", "phone": "bad"}, close=lambda: None
    )
    client.contacts = Contacts(
        senders={order.tenant_id: {"name": "Old directory contact", "phone": "+6580000000"}},
        recipients={order.patient_id: {"name": "Synthetic patient", "phone": "+6580000001"}},
    )
    with pytest.raises(DeliveryUnavailable, match="Clinic pickup contact is unavailable"):
        client.prepare(order, quote, delivery)


def test_prepare_uses_patient_profile_contact_without_file_directory(adapter):
    client, delivery, quote, _ = adapter
    order = SimpleNamespace(tenant_id=uuid4(), patient_id=uuid4())
    sender = {"name": "Clinic desk", "phone": "+6580000000"}
    recipient = {"name": "Saved profile name", "phone": "+6581234567"}
    client.clinic_locations = SimpleNamespace(
        get_contact=lambda tenant_id: sender, close=lambda: None
    )
    client.patient_profiles = SimpleNamespace(
        get_contact=lambda patient_id: recipient, close=lambda: None
    )
    client.contacts = None
    client.quotes.quote_route = lambda stops: SimpleNamespace(
        context={"quotation_id": QUOTE, "stop_ids": ["pickup", "dropoff"]}
    )
    _, payload = client.prepare(order, quote, delivery)
    assert payload["sender"] == {"stopId": "pickup", **sender}
    assert payload["recipients"] == [{"stopId": "dropoff", **recipient}]
    recipient["phone"] = "invalid"
    with pytest.raises(DeliveryUnavailable, match="Patient recipient contact is unavailable"):
        client.prepare(order, quote, delivery)


def test_refund_resolution_request_uses_billing_service_scope():
    secret = "d05-synthetic-billing-secret-at-least-32-bytes"
    payment, order, tenant, patient, quote = [uuid4() for _ in range(5)]

    def respond(request):
        assert (
            request.method == "POST"
            and request.url.path == f"/internal/payments/{payment}/resolution"
        )
        assert json.loads(request.content) == {
            "resolution": "refund_required",
            "resource_id": str(order),
            "reason": "delivery_price_changed",
        }
        jwt.decode(
            request.headers["Authorization"].split()[1],
            secret,
            algorithms=["HS256"],
            audience="telelink-billing-fulfilment",
            issuer="telelink-service:fulfilment",
        )
        return httpx.Response(
            200,
            json={
                "payment_id": str(payment),
                "order_id": str(order),
                "quote_id": str(quote),
                "tenant_id": str(tenant),
                "patient_id": str(patient),
                "purpose": "medication_delivery",
                "status": "succeeded",
                "resolution": "refund_required",
                "amount": {"currency": "SGD", "amount_minor": 2780},
            },
        )

    client = BillingClient(
        Settings(environment="test", billing_url="http://billing.test", billing_secret=secret),
        transport=httpx.MockTransport(respond),
    )
    try:
        assert (
            client.refund_required(payment, order, "delivery_price_changed").resolution
            == "refund_required"
        )
    finally:
        client.close()
