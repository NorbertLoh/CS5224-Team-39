import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from telelink_common.errors import DomainError

from app.integrations.delivery_provider import HOST, SandboxQuotes
from app.schemas import Destination
from app.settings import Settings

TENANT = uuid4()
DESTINATION = Destination(
    address_line="Synthetic destination", postal_code="038983", country_code="SG"
)
STOPS = [
    {"coordinates": {"lat": "1.2844", "lng": "103.8511"}, "address": "Synthetic dispatch"},
    {"coordinates": {"lat": "1.2935", "lng": "103.8572"}, "address": "Synthetic destination"},
]


def payload():
    return {
        "data": {
            "quotationId": "3608770529626608275",
            "serviceType": "MOTORCYCLE",
            "expiresAt": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "priceBreakdown": {"currency": "SGD", "total": "7.80"},
            "stops": [
                stop | {"stopId": str(1234567890123456780 + i)} for i, stop in enumerate(STOPS)
            ],
        }
    }


@pytest.fixture
def adapter(tmp_path):
    locations = tmp_path / "locations.json"
    locations.write_text(
        json.dumps(
            {
                "origins": {str(TENANT): STOPS[0]},
                "destinations": {"038983": STOPS[1]["coordinates"]},
            }
        )
    )
    provider = SandboxQuotes(
        Settings(
            environment="test",
            delivery_locations_path=locations,
            lalamove_api_key="pk_test_synthetic",
            lalamove_api_secret="sk_test_synthetic",
        )
    )
    provider.client.close()
    yield provider
    provider.close()


def test_exact_signing_and_string_identifier_precision(adapter):
    def transport(request):
        assert str(request.url) == HOST + "/v3/quotations"
        assert request.method == "POST" and request.headers["Market"] == "SG"
        scheme, credentials = request.headers["Authorization"].split(" ")
        key, timestamp, signature = credentials.split(":")
        assert scheme == "hmac" and key == "pk_test_synthetic" and timestamp.isdigit()
        raw = timestamp.encode() + b"\r\nPOST\r\n/v3/quotations\r\n\r\n" + request.content
        assert signature == hmac.new(b"sk_test_synthetic", raw, hashlib.sha256).hexdigest()
        sent = json.loads(request.content)["data"]
        assert sent["stops"][0] == STOPS[0]
        assert sent["stops"][1]["coordinates"] == STOPS[1]["coordinates"]
        assert sent["stops"][1]["address"] == "Synthetic destination, Singapore 038983"
        return httpx.Response(200, json=payload())

    adapter.client = httpx.Client(transport=httpx.MockTransport(transport))
    result = adapter.quote(TENANT, DESTINATION)
    assert result.amount_minor == 780
    assert result.context["quotation_id"] == "3608770529626608275"
    assert result.context["stop_ids"] == ["1234567890123456780", "1234567890123456781"]


@pytest.mark.parametrize(
    "changes",
    [
        {"expiresAt": None},
        {"expiresAt": "not-an-instant"},
        {"expiresAt": "2026-01-01T00:00:00"},
        {"expiresAt": "2000-01-01T00:00:00Z"},
        {"priceBreakdown": {"currency": "USD", "total": "1.00"}},
        {"priceBreakdown": {"currency": "SGD", "total": "-1"}},
        {"priceBreakdown": {"currency": "SGD", "total": "1.001"}},
        {"priceBreakdown": {"currency": "SGD", "total": "99999999999999"}},
        {"priceBreakdown": {"currency": "SGD", "total": 7.8}},
        {"quotationId": 3608770529626608275},
        {"quotationId": "not-an-id"},
        {"serviceType": "VAN"},
        {"stops": []},
        {
            "stops": [
                {"stopId": "1234567890123456780", "coordinates": STOPS[1]["coordinates"]},
                {"stopId": "1234567890123456781", "coordinates": STOPS[0]["coordinates"]},
            ]
        },
    ],
)
def test_malformed_or_mismatched_provider_data_fails_closed(adapter, changes):
    data = payload()
    data["data"].update(changes)
    adapter.client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    )
    with pytest.raises(DomainError) as error:
        adapter.quote(TENANT, DESTINATION)
    assert error.value.status_code == 503


@pytest.mark.parametrize("code", [301, 400, 401, 422, 429, 500])
def test_http_errors_no_retry_no_payload_leak(adapter, code):
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(
            code, text="PRIVATE ADDRESS AND SECRET", headers={"Location": "https://example.com"}
        )

    adapter.client = httpx.Client(transport=httpx.MockTransport(transport))
    with pytest.raises(DomainError) as error:
        adapter.quote(TENANT, DESTINATION)
    assert len(calls) == 1
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("mode", ["timeout", "json", "shape"])
def test_transport_and_json_errors(adapter, mode):
    def transport(request):
        if mode == "timeout":
            raise httpx.ReadTimeout("PRIVATE", request=request)
        return (
            httpx.Response(200, text="not-json") if mode == "json" else httpx.Response(200, json=[])
        )

    adapter.client = httpx.Client(transport=httpx.MockTransport(transport))
    with pytest.raises(DomainError):
        adapter.quote(TENANT, DESTINATION)


def test_unconfigured_and_unsupported_locations(adapter):
    with pytest.raises(DomainError) as error:
        adapter.quote(uuid4(), DESTINATION)
    assert error.value.status_code == 503
    with pytest.raises(DomainError) as error:
        adapter.quote(TENANT, DESTINATION.model_copy(update={"postal_code": "999999"}))
    assert error.value.status_code == 422
    unconfigured = SandboxQuotes(Settings(environment="test"))
    try:
        with pytest.raises(DomainError):
            unconfigured.quote(TENANT, DESTINATION)
    finally:
        unconfigured.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"lalamove_api_key": "pk_prod_private", "lalamove_api_secret": "sk_prod_private"},
        {"lalamove_api_key": "pk_test_synthetic"},
    ],
)
def test_production_and_partial_credentials_refused(changes):
    with pytest.raises(ValidationError):
        Settings(environment="test", **changes)
