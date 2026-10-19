"""SG sandbox quotations. No order submission or production endpoint exists here."""

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from telelink_common.errors import DomainError

from app.models import MAX_MONEY
from app.schemas import Destination, StrictModel

HOST = "https://rest.sandbox.lalamove.com"
PATH = "/v3/quotations"


def unavailable():
    return DomainError(503, "delivery_unavailable", "Delivery quotation is unavailable.")


class Coordinates(StrictModel):
    lat: str = Field(pattern=r"^1\.\d{1,8}$")
    lng: str = Field(pattern=r"^10[34]\.\d{1,8}$")


class Stop(StrictModel):
    coordinates: Coordinates
    address: str = Field(min_length=1, max_length=400)


class Locations(StrictModel):
    origins: dict[str, Stop]
    destinations: dict[str, Coordinates]


class ProviderStop(BaseModel):
    stopId: str = Field(pattern=r"^[0-9]{10,30}$")
    coordinates: Coordinates


class Price(BaseModel):
    currency: str = Field(pattern=r"^SGD$")
    total: str = Field(pattern=r"^[0-9]{1,14}(?:\.[0-9]{1,2})?$")


class ProviderQuote(BaseModel):
    quotationId: str = Field(pattern=r"^[0-9]{10,30}$")
    expiresAt: AwareDatetime
    serviceType: str = Field(pattern=r"^MOTORCYCLE$")
    priceBreakdown: Price
    stops: list[ProviderStop] = Field(min_length=2, max_length=2)


class DeliveryPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_minor: int = Field(strict=True, ge=0, le=MAX_MONEY)
    expires_at: AwareDatetime
    context: dict


class SandboxQuotes:
    def __init__(self, settings):
        self.key = settings.lalamove_api_key
        self.secret = settings.lalamove_api_secret
        self.locations = (
            Locations.model_validate_json(settings.delivery_locations_path.read_text())
            if settings.delivery_locations_path
            else None
        )
        self.client = httpx.Client(timeout=15, follow_redirects=False, trust_env=False)

    def close(self):
        self.client.close()

    def quote(self, tenant_id, destination: Destination):
        if self.key is None or self.secret is None or self.locations is None:
            raise unavailable()
        origin = self.locations.origins.get(str(tenant_id))
        if origin is None:
            raise unavailable()
        coordinates = self.locations.destinations.get(destination.postal_code)
        if coordinates is None:
            raise DomainError(422, "unsupported_destination", "Destination is not supported.")
        stops = [
            origin.model_dump(),
            dict(
                coordinates=coordinates.model_dump(),
                address=f"{destination.address_line}, Singapore {destination.postal_code}",
            ),
        ]
        body = json.dumps(
            {"data": {"serviceType": "MOTORCYCLE", "language": "en_SG", "stops": stops}},
            separators=(",", ":"),
            ensure_ascii=False,
        )
        timestamp = str(time.time_ns() // 1_000_000)
        signature = hmac.new(
            self.secret.get_secret_value().encode(),
            f"{timestamp}\r\nPOST\r\n{PATH}\r\n\r\n{body}".encode(),
            hashlib.sha256,
        ).hexdigest()
        try:
            response = self.client.post(
                HOST + PATH,
                content=body.encode(),
                headers={
                    "Authorization": f"hmac {self.key.get_secret_value()}:{timestamp}:{signature}",
                    "Market": "SG",
                    "Content-Type": "application/json",
                    "Request-ID": str(uuid4()),
                },
            )
            response.raise_for_status()
            quote = ProviderQuote.model_validate(response.json()["data"])
            minor = int(Decimal(quote.priceBreakdown.total) * 100)
            if minor > MAX_MONEY or quote.expiresAt <= datetime.now(timezone.utc):
                raise ValueError("Invalid quotation")
            for requested, returned in zip(stops, quote.stops, strict=True):
                if any(
                    Decimal(requested["coordinates"][key])
                    != Decimal(getattr(returned.coordinates, key))
                    for key in ("lat", "lng")
                ):
                    raise ValueError("Route mismatch")
            return DeliveryPrice(
                amount_minor=minor,
                expires_at=quote.expiresAt,
                context={
                    "quotation_id": quote.quotationId,
                    "stop_ids": [stop.stopId for stop in quote.stops],
                    "stops": stops,
                    "service_type": "MOTORCYCLE",
                    "mode": "lalamove-sandbox",
                },
            )
        except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError):
            # No response text, destination, credential or exception detail escapes.
            raise unavailable() from None
