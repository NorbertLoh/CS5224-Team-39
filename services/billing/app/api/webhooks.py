"""Signature-authenticated, bounded Stripe snapshot event inbox (B03)."""

import re
import time

import stripe
from fastapi import APIRouter, Request
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from telelink_common.errors import DomainError

from app.models import StripeWebhookEvent

router = APIRouter()
MAX_BODY_BYTES = 256 * 1024
TOLERANCE_SECONDS = 300
PAYMENT_EVENTS = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
    "checkout.session.expired",
    "payment_intent.succeeded",
    "payment_intent.payment_failed",
}


def verify_event(body: bytes, signature: str, secret: str) -> dict:
    try:
        event = stripe.Webhook.construct_event(
            body, signature, secret, tolerance=TOLERANCE_SECONDS
        ).to_dict()
        timestamp = int(next(p[2:] for p in signature.split(",") if p.startswith("t=")))
        if timestamp > time.time() + TOLERANCE_SECONDS:
            raise ValueError("Future signature")
        obj = event.get("data", {}).get("object")
        if (
            event.get("object") != "event"
            or event.get("livemode") is not False
            or not isinstance(event.get("id"), str)
            or not re.fullmatch(r"evt_[A-Za-z0-9]{1,250}", event["id"])
            or not isinstance(event.get("type"), str)
            or not re.fullmatch(r"[a-z0-9_.]{1,255}", event["type"])
            or type(event.get("created")) is not int
            or not 0 <= event["created"] <= 9007199254740991
            or not isinstance(obj, dict)
            or not isinstance(obj.get("id"), str)
            or not 1 <= len(obj["id"]) <= 255
            or not isinstance(obj.get("object"), str)
        ):
            raise ValueError("Invalid snapshot event")
        for field in ("account", "api_version"):
            value = event.get(field)
            if value is not None and (not isinstance(value, str) or not 1 <= len(value) <= 255):
                raise ValueError("Invalid event context")
    except (
        stripe.SignatureVerificationError,
        ValueError,
        TypeError,
        AttributeError,
        StopIteration,
        RecursionError,
    ):
        raise DomainError(400, "invalid_webhook", "Invalid webhook.") from None

    # Retain only identifiers and payment signals; no raw body, customer, card,
    # address, arbitrary metadata or provider error messages. B04 must validate
    # linkage, account, amounts and legal transitions against trusted payments.
    projection = {}
    for field in (
        "id",
        "object",
        "amount",
        "amount_total",
        "amount_received",
        "currency",
        "status",
        "payment_status",
        "payment_intent",
        "client_reference_id",
    ):
        value = obj.get(field)
        if (isinstance(value, str) and len(value) <= 255) or (
            type(value) is int and 0 <= value <= 9007199254740991
        ):
            projection[field] = value
    metadata = obj.get("metadata")
    if isinstance(metadata, dict):
        payment_id = metadata.get("payment_id")
        if isinstance(payment_id, str) and len(payment_id) <= 64:
            projection["metadata"] = {"payment_id": payment_id}
    return {
        "event_id": event["id"],
        "event_type": event["type"],
        "account_id": event.get("account"),
        "api_version": event.get("api_version"),
        "provider_created_at": event["created"],
        "object_data": projection,
        "status": "pending" if event["type"] in PAYMENT_EVENTS else "ignored",
    }


def persist_receipt(engine, values):
    try:
        # A conflicting insert waits for the first transaction to commit/rollback.
        # Only a committed receipt is acknowledged; retries never overwrite it.
        with engine.begin() as connection:
            connection.execute(
                insert(StripeWebhookEvent)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[StripeWebhookEvent.event_id])
            )
    except SQLAlchemyError:
        raise DomainError(503, "unavailable", "Webhook storage is unavailable.") from None


@router.post("/webhooks/stripe", tags=["webhooks"])
async def stripe_webhook(request: Request):
    state = request.app.state
    secret = state.settings.stripe_webhook_secret
    if not secret or state.database_engine is None:
        raise DomainError(503, "unavailable", "Webhook receiver is not configured.")
    headers = request.headers.getlist("stripe-signature")
    if len(headers) != 1 or not headers[0]:
        raise DomainError(400, "invalid_webhook", "Invalid webhook.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise DomainError(413, "webhook_too_large", "Webhook is too large.")
        body.extend(chunk)
    values = verify_event(bytes(body), headers[0], secret.get_secret_value())
    await run_in_threadpool(persist_receipt, state.database_engine, values)
    return {"received": True}
