"""Read-only provider reconciliation against the immutable B02 checkout context."""

import re


class ReceiptDeferred(Exception):
    """Safe operational code only; keep the receipt pending for retry."""


class ReceiptRejected(Exception):
    """Safe operational code only; retain a mismatched receipt for operator review."""


def require(condition, code="provider_context_mismatch"):
    if not condition:
        raise ReceiptRejected(code)


def metadata_matches(value, payment):
    resources = (
        ("order_id", "quote_id")
        if payment.purpose == "medication_delivery"
        else ("appointment_id",)
    )
    expected = {
        name: str(getattr(payment, name))
        for name in ("payment_id", "tenant_id", "patient_id", "purpose", *resources)
    }
    return isinstance(value, dict) and all(value.get(k) == v for k, v in expected.items())


def reconcile(provider, receipt, payment, attempt):
    """Return provider truth, never create/expire/refund a provider operation."""
    if payment.provider_checkout_id is None or not attempt.provider_fields:
        raise ReceiptDeferred("checkout_linkage_pending")
    require(payment.provider == "stripe" and payment.provider_account_id is None)
    require(receipt.account_id is None, "account_mismatch")
    require(
        payment.purpose in {"consultation", "medication_delivery"}, "unsupported_payment_purpose"
    )
    require(bool(re.fullmatch(r"cs_test_[A-Za-z0-9]+", payment.provider_checkout_id)))
    if payment.purpose == "medication_delivery":
        require(
            attempt.order_id == payment.order_id
            and attempt.quote_id == payment.quote_id
            and attempt.patient_id == payment.patient_id
            and attempt.quote_expires_at is not None,
            "checkout_context_mismatch",
        )
    else:
        require(
            attempt.appointment_id == payment.appointment_id
            and attempt.patient_id == payment.patient_id,
            "checkout_context_mismatch",
        )
    obj = receipt.object_data
    checkout_event = receipt.event_type.startswith("checkout.session.")
    require(
        obj.get("object") == ("checkout.session" if checkout_event else "payment_intent"),
        "event_object_mismatch",
    )
    if checkout_event:
        require(obj.get("id") == payment.provider_checkout_id, "checkout_id_mismatch")
    for field in ("amount", "amount_total"):
        if field in obj:
            require(
                type(obj[field]) is int and obj[field] == payment.amount_minor, "amount_mismatch"
            )
    if "currency" in obj:
        require(obj["currency"] == payment.currency.lower(), "currency_mismatch")
    if "client_reference_id" in obj:
        require(obj["client_reference_id"] == str(payment.payment_id), "payment_id_mismatch")
    if "metadata" in obj:
        require(obj["metadata"].get("payment_id") == str(payment.payment_id), "payment_id_mismatch")

    checkout = provider.request("GET", f"checkout/sessions/{payment.provider_checkout_id}")
    require(
        checkout.get("id") == payment.provider_checkout_id
        and checkout.get("object") == "checkout.session"
        and checkout.get("mode") == "payment"
    )
    require(
        checkout.get("client_reference_id") == str(payment.payment_id)
        and metadata_matches(checkout.get("metadata"), payment)
    )
    require(
        type(checkout.get("amount_total")) is int
        and checkout["amount_total"] == payment.amount_minor,
        "amount_mismatch",
    )
    require(checkout.get("currency") == payment.currency.lower(), "currency_mismatch")
    intent_id = checkout.get("payment_intent")
    intent = None
    if intent_id is not None:
        require(isinstance(intent_id, str) and bool(re.fullmatch(r"pi_[A-Za-z0-9]+", intent_id)))
        if payment.provider_payment_id:
            require(intent_id == payment.provider_payment_id, "intent_id_mismatch")
        if checkout_event and obj.get("payment_intent") is not None:
            require(obj["payment_intent"] == intent_id, "intent_id_mismatch")
        if not checkout_event:
            require(obj.get("id") == intent_id, "intent_id_mismatch")
        intent = provider.request("GET", f"payment_intents/{intent_id}")
        require(
            intent.get("id") == intent_id
            and intent.get("object") == "payment_intent"
            and metadata_matches(intent.get("metadata"), payment)
        )
        require(
            type(intent.get("amount")) is int and intent["amount"] == payment.amount_minor,
            "amount_mismatch",
        )
        require(intent.get("currency") == payment.currency.lower(), "currency_mismatch")
        destination = attempt.provider_fields.get("payment_intent_data[transfer_data][destination]")
        require(
            bool(destination)
            and isinstance(intent.get("transfer_data"), dict)
            and intent["transfer_data"].get("destination") == destination,
            "destination_mismatch",
        )
        require(intent["transfer_data"].get("amount") is None, "transfer_amount_mismatch")
        require(
            intent.get("application_fee_amount") == payment.commission_amount_minor
            or (
                payment.commission_amount_minor == 0
                and intent.get("application_fee_amount") is None
            ),
            "commission_mismatch",
        )
    elif not checkout_event:
        raise ReceiptDeferred("intent_linkage_pending")

    if checkout.get("status") == "complete" and checkout.get("payment_status") == "paid":
        require(
            intent is not None
            and intent.get("status") == "succeeded"
            and type(intent.get("amount_received")) is int
            and intent["amount_received"] == payment.amount_minor,
            "unverified_success",
        )
        return "succeeded", intent_id
    if checkout.get("status") == "expired" and checkout.get("payment_status") == "unpaid":
        require(
            intent is None or intent.get("status") not in {"succeeded", "processing"},
            "conflicting_provider_state",
        )
        return "failed", intent_id
    if (
        receipt.event_type == "checkout.session.async_payment_failed"
        and checkout.get("status") == "complete"
        and checkout.get("payment_status") == "unpaid"
        and intent
        and intent.get("status") in {"requires_payment_method", "canceled"}
    ):
        return "failed", intent_id
    if intent and intent.get("status") == "processing":
        raise ReceiptDeferred("provider_processing")
    if receipt.event_type in {
        "payment_intent.succeeded",
        "checkout.session.async_payment_succeeded",
    }:
        raise ReceiptDeferred("provider_state_pending")
    # A declined card can be retried inside the same open session. It is not a
    # terminal payment failure and cannot permit a second checkout attempt.
    return "pending", intent_id
