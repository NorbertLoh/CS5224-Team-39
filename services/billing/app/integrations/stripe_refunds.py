"""Verify the original destination charge, then create/reconcile one full refund."""

import re
from datetime import timedelta

from app.integrations.stripe import ProviderUncertain
from app.models import CheckoutAttempt
from app.services.reconciliation import metadata_matches, require


def checked_refund(value, payment, attempt):
    require(value.get("object") == "refund")
    require("livemode" not in value or value["livemode"] is False)
    require(bool(re.fullmatch(r"re_[A-Za-z0-9]+", value.get("id", ""))))
    require(value.get("payment_intent") == payment.provider_payment_id)
    require(type(value.get("amount")) is int and value["amount"] == payment.amount_minor)
    require(value.get("currency") == payment.currency.lower())
    require(isinstance(value.get("metadata"), dict))
    require(value["metadata"].get("refund_id") == str(attempt.refund_id))
    require(value.get("metadata", {}).get("payment_id") == str(payment.payment_id))
    require(
        value.get("status") in {"pending", "requires_action", "succeeded", "failed", "canceled"}
    )
    return value["status"], value["id"]


def reconcile_refund(provider, payment, attempt, now):
    require(payment.provider == "stripe" and payment.provider_account_id is None)
    require(payment.purpose == "consultation" and payment.amount_minor > 0)
    require(bool(re.fullmatch(r"pi_[A-Za-z0-9]+", payment.provider_payment_id or "")))
    if attempt.provider_refund_id:
        value = provider.request("GET", f"refunds/{attempt.provider_refund_id}")
        require(value.get("id") == attempt.provider_refund_id)
        return checked_refund(value, payment, attempt)
    intent = provider.request("GET", f"payment_intents/{payment.provider_payment_id}")
    require(
        intent.get("id") == payment.provider_payment_id and intent.get("object") == "payment_intent"
    )
    require(
        intent.get("status") == "succeeded" and intent.get("currency") == payment.currency.lower()
    )
    require(
        intent.get("amount_received") == payment.amount_minor
        and intent.get("amount") == payment.amount_minor
    )
    require(metadata_matches(intent.get("metadata"), payment))
    # Persisted checkout fields, rather than today's clinic configuration, are authoritative.
    from sqlalchemy.orm import object_session

    checkout = object_session(attempt).get(CheckoutAttempt, payment.payment_id)
    require(checkout is not None and bool(checkout.provider_fields))
    destination = checkout.provider_fields.get("payment_intent_data[transfer_data][destination]")
    require(
        bool(destination)
        and isinstance(intent.get("transfer_data"), dict)
        and intent["transfer_data"].get("destination") == destination
    )
    require(
        intent.get("application_fee_amount") == payment.commission_amount_minor
        or (payment.commission_amount_minor == 0 and intent.get("application_fee_amount") is None)
    )
    existing = provider.request(
        "GET", f"refunds?payment_intent={payment.provider_payment_id}&limit=100"
    )
    require(
        existing.get("object") == "list"
        and existing.get("has_more") is False
        and isinstance(existing.get("data"), list)
    )
    for refund in existing["data"]:
        require(isinstance(refund, dict) and isinstance(refund.get("metadata"), dict))
        if refund.get("metadata", {}).get("refund_id") == str(attempt.refund_id):
            return checked_refund(refund, payment, attempt)
        require(refund.get("status") in {"failed", "canceled"}, "external_refund_review")
    if now - attempt.created_at >= timedelta(hours=23):
        # Stripe may prune idempotency keys after 24h. Never POST an old unknown operation.
        from app.services.reconciliation import ReceiptRejected

        raise ReceiptRejected("refund_idempotency_window_expired")
    try:
        value = provider.request(
            "POST",
            "refunds",
            fields={
                "payment_intent": payment.provider_payment_id,
                "amount": str(payment.amount_minor),
                "reason": "requested_by_customer",
                "reverse_transfer": "true",
                **({"refund_application_fee": "true"} if payment.commission_amount_minor else {}),
                "metadata[refund_id]": str(attempt.refund_id),
                "metadata[payment_id]": str(payment.payment_id),
            },
            key=f"RF08-refund-{attempt.refund_id}",
        )
    except ProviderUncertain:
        # A lost response remains pending; the next pass lists before replaying the same key.
        raise
    return checked_refund(value, payment, attempt)
