"""Stripe test-mode destination Checkout, with stable persisted create parameters."""

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx


class ProviderUncertain(Exception):
    pass


class ProviderRejected(Exception):
    pass


class StripeCheckout:
    def __init__(self, settings, *, transport=None):
        self.settings = settings
        self.client = httpx.Client(
            base_url="https://api.stripe.com/v1/",
            timeout=10,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def close(self):
        self.client.close()

    def fields(self, payment, destination):
        # Hosted Stripe's minimum is 30 minutes. The worker enforces the shorter
        # application deadline; the original hold never changes. Five-minute margin
        # allows recovery after a process interruption before the first POST.
        fields = {
            "mode": "payment",
            "payment_method_types[0]": "card",
            "client_reference_id": str(payment.payment_id),
            "line_items[0][price_data][currency]": "sgd",
            "line_items[0][price_data][unit_amount]": str(payment.amount_minor),
            "line_items[0][price_data][product_data][name]": "TeleLink consultation",
            "line_items[0][quantity]": "1",
            "payment_intent_data[transfer_data][destination]": destination,
            "success_url": self.settings.checkout_success_url,
            "cancel_url": self.settings.checkout_cancel_url,
            "expires_at": str(
                int((datetime.now(timezone.utc) + timedelta(minutes=35)).timestamp())
            ),
        }
        if payment.commission_amount_minor:
            fields["payment_intent_data[application_fee_amount]"] = str(
                payment.commission_amount_minor
            )
        for prefix in ("metadata", "payment_intent_data[metadata]"):
            for name in ("payment_id", "appointment_id", "tenant_id", "patient_id"):
                fields[f"{prefix}[{name}]"] = str(getattr(payment, name))
            fields[f"{prefix}[purpose]"] = "consultation"
        return fields

    def request(self, method, path, *, fields=None, key=None):
        secret = self.settings.stripe_secret_key
        if not secret:
            raise ProviderUncertain("Stripe is not configured")
        headers = {
            "Authorization": "Bearer " + secret.get_secret_value(),
            "Stripe-Version": "2024-06-20",
        }
        if key:
            headers["Idempotency-Key"] = key
        try:
            result = self.client.request(method, path, data=fields, headers=headers)
            if result.status_code == 400:
                error = result.json().get("error", {})
                if error.get("type") == "invalid_request_error" and error.get("code") not in {
                    "idempotency_key_in_use",
                    "idempotency_error",
                }:
                    raise ProviderRejected("Stripe rejected checkout parameters")
            if result.status_code != 200:
                raise ProviderUncertain("Stripe outcome needs reconciliation")
            value = result.json()
            if not isinstance(value, dict) or value.get("livemode") is not False:
                raise ProviderUncertain("Stripe test-mode response required")
            return value
        except (httpx.RequestError, ValueError, TypeError, AttributeError):
            raise ProviderUncertain("Stripe outcome needs reconciliation") from None

    def create(self, payment, attempt):
        # Stripe may prune idempotency keys after 24h. Never recreate an uncertain
        # operation once the safe retry period has passed, even after a restart.
        if datetime.now(timezone.utc) - attempt.created_at >= timedelta(hours=23):
            raise ProviderUncertain("Operator reconciliation required")
        value = self.request(
            "POST",
            "checkout/sessions",
            fields=dict(sorted(attempt.provider_fields.items())),
            key=payment.provider_idempotency_key,
        )
        if (
            not isinstance(value.get("id"), str)
            or not re.fullmatch(r"cs_test_[A-Za-z0-9]+", value["id"])
            or value.get("client_reference_id") != str(payment.payment_id)
            or value.get("amount_total") != payment.amount_minor
            or value.get("currency") != "sgd"
            or not isinstance(value.get("metadata"), dict)
            or value["metadata"].get("payment_id") != str(payment.payment_id)
        ):
            raise ProviderUncertain("Invalid Stripe checkout context")
        try:
            url = urlsplit(value.get("url") or "")
            port = url.port
        except (ValueError, TypeError, AttributeError):
            raise ProviderUncertain("Invalid Stripe checkout URL") from None
        if (
            url.scheme != "https"
            or url.hostname != "checkout.stripe.com"
            or url.username
            or url.password
            or port not in {None, 443}
        ):
            raise ProviderUncertain("Invalid Stripe checkout URL")
        return value

    def expire(self, checkout_id, payment_id):
        if not re.fullmatch(r"cs_test_[A-Za-z0-9]+", checkout_id):
            raise ProviderUncertain("Invalid stored Stripe session")
        value = self.request("GET", f"checkout/sessions/{checkout_id}")
        if value.get("id") != checkout_id or value.get("client_reference_id") != str(payment_id):
            raise ProviderUncertain("Stripe session context mismatch")
        if value.get("status") == "open":
            # A concurrent payment/expiry can make this return an error. Retry GET
            # on the next worker pass rather than guessing that it failed.
            self.request(
                "POST",
                f"checkout/sessions/{checkout_id}/expire",
                fields={},
                key=f"B02-expire-{payment_id}",
            )
            value = self.request("GET", f"checkout/sessions/{checkout_id}")
        if value.get("id") != checkout_id or value.get("client_reference_id") != str(payment_id):
            raise ProviderUncertain("Stripe session context mismatch")
        return value
