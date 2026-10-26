from uuid import uuid4

import httpx
import jwt
import pytest
from telelink_common.errors import DomainError

from app.clinic_locations import HttpClinicLocations
from app.delivery_provider import SandboxQuotes, Stop
from app.schemas import Destination
from app.settings import Settings
from tests.test_api import api as api
from tests.test_api import create

SECRET = "tenant-location-secret-at-least-32-bytes"
TENANT = uuid4()
LOCATION = {
    "address_line": "1 Raffles Place",
    "postal_code": "048616",
    "country_code": "SG",
    "coordinates": {"lat": "1.2844", "lng": "103.8511"},
}


def test_service_location_projection_and_signed_identity():
    def handler(request):
        assert request.url.path == f"/internal/clinics/{TENANT}/delivery-location"
        claims = jwt.decode(
            request.headers["Authorization"].split()[1],
            SECRET,
            algorithms=["HS256"],
            issuer="telelink-service:fulfilment",
            audience="telelink-tenant-delivery",
        )
        assert claims["sub"] == "fulfilment"
        return httpx.Response(200, json={"tenant_id": str(TENANT), "location": LOCATION})

    source = HttpClinicLocations(
        Settings(
            _env_file=None,
            environment="test",
            tenant_url="http://tenant.test",
            tenant_secret=SECRET,
        ),
        transport=httpx.MockTransport(handler),
    )
    assert source.get(TENANT).model_dump() == {
        "address": "1 Raffles Place, Singapore 048616",
        "coordinates": LOCATION["coordinates"],
    }
    source.close()


@pytest.mark.parametrize(
    "status,data,code",
    [
        (200, {"tenant_id": str(TENANT), "location": None}, "clinic_location_missing"),
        (200, {"tenant_id": str(uuid4()), "location": LOCATION}, "clinic_location_unavailable"),
        (200, {"tenant_id": str(TENANT), "location": {}}, "clinic_location_unavailable"),
        (503, {}, "clinic_location_unavailable"),
    ],
)
def test_location_fails_closed(status, data, code):
    source = HttpClinicLocations(
        Settings(
            _env_file=None,
            environment="test",
            tenant_url="http://tenant.test",
            tenant_secret=SECRET,
        ),
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=data)),
    )
    with pytest.raises(DomainError) as error:
        source.get(TENANT)
    assert error.value.code == code
    source.close()


def test_service_pickup_contact_and_missing_contact():
    data = {
        "tenant_id": str(TENANT),
        "location": LOCATION | {"pickup_contact": {"name": "Clinic desk", "phone": "+6581234567"}},
    }
    source = HttpClinicLocations(
        Settings(
            _env_file=None,
            environment="test",
            tenant_url="http://tenant.test",
            tenant_secret=SECRET,
        ),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data)),
    )
    assert source.get_contact(TENANT) == data["location"]["pickup_contact"]
    data["location"].pop("pickup_contact")
    with pytest.raises(DomainError) as error:
        source.get_contact(TENANT)
    assert error.value.code == "clinic_contact_missing"
    source.close()


def test_saved_origin_overrides_file_and_is_snapshotted(tmp_path):
    import json

    path = tmp_path / "locations.json"
    path.write_text(
        json.dumps(
            {"origins": {}, "destinations": {"038983": {"lat": "1.2935", "lng": "103.8572"}}}
        )
    )
    provider = SandboxQuotes(
        Settings(
            _env_file=None,
            environment="test",
            lalamove_api_key="pk_test_demo",
            lalamove_api_secret="sk_test_demo",
            delivery_locations_path=path,
        )
    )
    origin = Stop(address="Saved clinic pickup", coordinates=LOCATION["coordinates"])
    provider.quote_route = lambda stops: stops
    route = provider.quote(
        TENANT,
        Destination(address_line="3 Temasek Boulevard", postal_code="038983", country_code="SG"),
        origin=origin,
    )
    assert route[0] == origin.model_dump()
    assert route[1]["address"] == "3 Temasek Boulevard, Singapore 038983"
    provider.close()


def test_new_quotes_read_saved_location_and_replay_preserves_snapshot(api):
    from datetime import datetime, timedelta, timezone

    from app.delivery_provider import DeliveryPrice

    client, state, app = api
    order_id = create(client).json()["order_id"]
    app.state.settings.tenant_url = "http://tenant.test"
    origins = []
    saved = Stop(address="First saved pickup", coordinates=LOCATION["coordinates"])

    class Locations:
        def get(self, tenant_id):
            return saved

    class Provider:
        def quote(self, tenant_id, destination, *, origin):
            origins.append(origin.address)
            return DeliveryPrice(
                amount_minor=780,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                context={"stops": [origin.model_dump()]},
            )

        def close(self):
            pass

    app.state.clinic_locations.close()
    app.state.clinic_locations = Locations()
    app.state.clinic_locations.close = lambda: None
    app.state.delivery_quotes.close()
    app.state.delivery_quotes = Provider()
    path = f"/orders/{order_id}/quotes"
    destination = {
        "address_line": "3 Temasek Boulevard",
        "postal_code": "038983",
        "country_code": "SG",
    }
    first = client.post(
        path, json={"destination": destination}, headers={"Idempotency-Key": "first-location"}
    )
    assert first.status_code == 201, first.text
    saved = saved.model_copy(update={"address": "Changed saved pickup"})
    replay = client.post(
        path, json={"destination": destination}, headers={"Idempotency-Key": "first-location"}
    )
    assert replay.json() == first.json()
    second = client.post(
        path, json={"destination": destination}, headers={"Idempotency-Key": "second-location"}
    )
    assert second.status_code == 201
    assert origins == ["First saved pickup", "Changed saved pickup"]
    from sqlalchemy import select

    from app.models import Quote

    with state.sessions() as db:
        quotes = db.scalars(select(Quote).order_by(Quote.created_at)).all()
        assert quotes[0].provider_context["stops"][0]["address"] == "First saved pickup"
        assert quotes[1].provider_context["stops"][0]["address"] == "Changed saved pickup"
