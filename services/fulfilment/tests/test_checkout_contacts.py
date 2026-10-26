from uuid import UUID, uuid4

import pytest

from app.models import Order, Quote
from tests.test_api import OTHER_PATIENT, identity
from tests.test_api import api as api
from tests.test_checkout_reservation import prepare, reservation
from tests.test_quotes import DESTINATION, RECIPIENT, quote
from tests.test_quotes import quotes as quotes


def test_confirmed_details_are_normalized_private_and_replayed(quotes):
    client, state = quotes
    recipient = {"name": "  Order recipient  ", "phone_number": "8123 4567"}
    response = quote(client, state, recipient=recipient)
    assert response.status_code == 201, response.text
    assert response.json()["contact_confirmed"] is True
    for private in ("8123", "Order recipient", "Temasek"):
        assert private not in response.text
    path = f"/orders/{state.order_id}/delivery-details"
    details = client.get(path)
    assert details.status_code == 200
    assert details.headers["cache-control"] == "no-store"
    assert details.json()["destination"] == DESTINATION
    assert details.json()["recipient"] == {"name": "Order recipient", "phone_number": "+6581234567"}
    assert quote(client, state, recipient=recipient).json() == response.json()
    assert (
        quote(client, state, recipient=recipient | {"phone_number": "91234567"}).status_code == 409
    )
    later = quote(
        client, state, key="changed-contact", recipient=RECIPIENT | {"phone_number": "91234567"}
    )
    assert later.status_code == 201
    assert client.get(path).json()["recipient"]["phone_number"] == "+6591234567"
    with state.sessions() as session:
        original = session.get(Quote, UUID(response.json()["quote_id"]))
        assert original.destination["recipient_contact"]["phone_number"] == "+6581234567"


@pytest.mark.parametrize(
    "recipient",
    [
        None,
        {},
        {"name": "  ", "phone_number": "81234567"},
        {"name": "Patient", "phone_number": "12345678"},
        {"name": "Patient", "phone_number": "+441234567890"},
    ],
)
def test_missing_or_invalid_contact_never_requests_quote(quotes, recipient):
    client, state = quotes
    assert quote(client, state, recipient=recipient).status_code == 422
    assert state.provider.calls == 0


def test_delivery_details_are_patient_only_and_owner_scoped(quotes):
    client, state = quotes
    path = f"/orders/{state.order_id}/delivery-details"
    assert client.get(path).json()["quote_id"] is None
    quote(client, state)
    for caller in [
        identity(subject=OTHER_PATIENT),
        identity(subject=OTHER_PATIENT, roles=(), clinic_role="clinic_admin"),
        identity(subject=OTHER_PATIENT, roles=("platform_admin",)),
    ]:
        state.identity = caller
        result = client.get(path)
        assert result.status_code in (403, 404)
        assert "8123" not in result.text
    state.identity = identity()
    assert client.get(f"/orders/{uuid4()}/delivery-details").status_code == 404


def test_legacy_quote_requires_contact_before_first_payment(quotes):
    client, state = prepare(quotes)
    with state.sessions.begin() as session:
        saved = session.get(Quote, UUID(state.quote_id))
        saved.destination = {k: v for k, v in saved.destination.items() if k != "recipient_contact"}
    response = reservation(client, state)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "delivery_contact_required"
    with state.sessions() as session:
        assert session.get(Order, UUID(state.order_id)).payment_id is None


def test_existing_payment_replay_does_not_rewrite_legacy_contact(quotes):
    client, state = prepare(quotes)
    first = reservation(client, state)
    assert first.status_code == 200
    with state.sessions.begin() as session:
        saved = session.get(Quote, UUID(state.quote_id))
        saved.destination = {k: v for k, v in saved.destination.items() if k != "recipient_contact"}
    assert reservation(client, state).json() == first.json()
