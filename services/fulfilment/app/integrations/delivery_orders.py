"""Fixed SG sandbox order adapter. POST orders is never retried here."""

import hashlib
import hmac
import json
import re
import time
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, Field, ValidationError
from telelink_common.errors import DomainError

from app.integrations.clinic_locations import HttpClinicLocations
from app.integrations.delivery_provider import HOST, Coordinates, Price, SandboxQuotes
from app.integrations.patient_profiles import HttpPatientProfiles, PatientContactUnavailable
from app.schemas import StrictModel


class DeliveryUnavailable(Exception):
    pass


class SubmissionRejected(Exception):
    pass


class SubmissionUncertain(Exception):
    def __init__(self, provider_order_id=None):
        super().__init__("Submission outcome requires reconciliation")
        self.provider_order_id = provider_order_id


class Contact(StrictModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f]+$")
    phone: str = Field(pattern=r"^\+65[689][0-9]{7}$")


class Contacts(StrictModel):
    senders: dict[UUID, Contact]
    recipients: dict[UUID, Contact]


class OrderStop(BaseModel):
    coordinates: Coordinates
    address: str


class ProviderOrder(BaseModel):
    orderId: str = Field(pattern=r"^[0-9]{10,30}$")
    quotationId: str = Field(pattern=r"^[0-9]{10,30}$")
    priceBreakdown: Price
    status: str
    metadata: dict[str, str]
    stops: list[OrderStop] = Field(min_length=2, max_length=2)


class SandboxDeliveries:
    def __init__(self, settings, *, transport=None):
        self.key = settings.lalamove_api_key
        self.secret = settings.lalamove_api_secret
        self.clinic_locations = HttpClinicLocations(settings) if settings.tenant_url else None
        self.patient_profiles = HttpPatientProfiles(settings) if settings.profile_secret else None
        try:
            self.contacts = (
                Contacts.model_validate_json(settings.delivery_contacts_path.read_text())
                if settings.delivery_contacts_path
                else None
            )
        except (OSError, ValidationError, ValueError):
            raise DeliveryUnavailable("Delivery contacts configuration unavailable") from None
        self.quotes = SandboxQuotes(settings)
        self.client = httpx.Client(
            timeout=15, follow_redirects=False, trust_env=False, transport=transport
        )

    def close(self):
        if self.patient_profiles is not None:
            self.patient_profiles.close()
        if self.clinic_locations is not None:
            self.clinic_locations.close()
        self.client.close()
        self.quotes.close()

    def prepare(self, order, quote, delivery):
        if self.clinic_locations is not None:
            try:
                sender = Contact.model_validate(self.clinic_locations.get_contact(order.tenant_id))
            except (DomainError, ValidationError):
                raise DeliveryUnavailable("Clinic pickup contact is unavailable") from None
        else:
            sender = self.contacts.senders.get(order.tenant_id) if self.contacts else None
        saved_recipient = quote.destination.get("recipient_contact")
        if saved_recipient is not None:
            try:
                recipient = Contact(
                    name=saved_recipient["name"], phone=saved_recipient["phone_number"]
                )
            except (ValidationError, KeyError, TypeError):
                raise DeliveryUnavailable("Saved recipient contact is unavailable") from None
        elif self.patient_profiles is not None:
            try:
                recipient = Contact.model_validate(
                    self.patient_profiles.get_contact(order.patient_id)
                )
            except (PatientContactUnavailable, ValidationError):
                raise DeliveryUnavailable("Patient recipient contact is unavailable") from None
        else:
            recipient = self.contacts.recipients.get(order.patient_id) if self.contacts else None
        context = quote.provider_context
        if (
            sender is None
            or recipient is None
            or context.get("mode") != "lalamove-sandbox"
            or context.get("service_type") != "MOTORCYCLE"
        ):
            raise DeliveryUnavailable("Delivery context is unavailable")
        # Re-quote the frozen route, not a changed clinic location or catalogue price.
        price = self.quotes.quote_route(context.get("stops", []))
        payload = {
            "quotationId": price.context["quotation_id"],
            "sender": {"stopId": price.context["stop_ids"][0], **sender.model_dump()},
            "recipients": [{"stopId": price.context["stop_ids"][1], **recipient.model_dump()}],
            "metadata": {
                "delivery_id": str(delivery.delivery_id),
                "operation_id": str(delivery.operation_id),
            },
            "isPODEnabled": False,
        }
        return price, payload

    def request(self, method, path, *, payload=None, request_id=None):
        if self.key is None or self.secret is None:
            raise DeliveryUnavailable("Sandbox credentials are unavailable")
        body = (
            ""
            if payload is None
            else json.dumps({"data": payload}, separators=(",", ":"), ensure_ascii=False)
        )
        timestamp = str(time.time_ns() // 1_000_000)
        signature = hmac.new(
            self.secret.get_secret_value().encode(),
            f"{timestamp}\r\n{method}\r\n{path}\r\n\r\n{body}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return self.client.request(
            method,
            HOST + path,
            content=body.encode(),
            headers={
                "Authorization": f"hmac {self.key.get_secret_value()}:{timestamp}:{signature}",
                "Market": "SG",
                "Content-Type": "application/json",
                "Request-ID": str(request_id or uuid4()),
            },
        )

    def verify(self, data, delivery, quote, fee):
        result = ProviderOrder.model_validate(data)
        payload = delivery.request_payload
        if (
            result.quotationId != payload["quotationId"]
            or result.metadata.get("delivery_id") != str(delivery.delivery_id)
            or result.metadata.get("operation_id") != str(delivery.operation_id)
            or int(Decimal(result.priceBreakdown.total) * 100) != fee
            or result.status
            not in {
                "ASSIGNING_DRIVER",
                "ON_GOING",
                "PICKED_UP",
                "COMPLETED",
                "CANCELED",
                "REJECTED",
                "EXPIRED",
            }
        ):
            raise ValueError("Provider order context mismatch")
        for frozen, returned in zip(quote.provider_context["stops"], result.stops, strict=True):
            if frozen["address"] != returned.address or any(
                Decimal(frozen["coordinates"][axis]) != Decimal(getattr(returned.coordinates, axis))
                for axis in ("lat", "lng")
            ):
                raise ValueError("Provider order route mismatch")
        return result

    def submit(self, delivery, quote, fee):
        provider_id = None
        try:
            response = self.request(
                "POST",
                "/v3/orders",
                payload=delivery.request_payload,
                request_id=delivery.operation_id,
            )
            if response.status_code in {400, 401, 402, 403, 404, 422, 429}:
                raise SubmissionRejected("Provider rejected order submission")
            response.raise_for_status()
            data = response.json()["data"]
            candidate = data.get("orderId")
            if isinstance(candidate, str) and re.fullmatch(r"[0-9]{10,30}", candidate):
                provider_id = candidate
            return self.verify(data, delivery, quote, fee)
        except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError, AttributeError):
            raise SubmissionUncertain(provider_id) from None

    def inspect(self, provider_id, delivery, quote, fee):
        if not re.fullmatch(r"[0-9]{10,30}", provider_id):
            raise DeliveryUnavailable("Invalid provider reference")
        try:
            response = self.request("GET", f"/v3/orders/{provider_id}")
            response.raise_for_status()
            result = self.verify(response.json()["data"], delivery, quote, fee)
            if result.orderId != provider_id:
                raise ValueError("Provider reference mismatch")
            return result
        except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError):
            raise DeliveryUnavailable("Provider reconciliation unavailable") from None
