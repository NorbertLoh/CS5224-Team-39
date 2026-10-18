"""C04 checkout against a trusted, atomic fulfilment reservation."""

from uuid import uuid4

from sqlalchemy import select
from telelink_common.errors import DomainError

from app.checkout import checkout_lock, expire_attempt, now, pending
from app.models import MedicationCheckoutAttempt, MedicationCheckoutKey, Payment
from app.provider import ProviderRejected, ProviderUncertain
from app.schemas import CheckoutPublic, payment_public


def create_medication_checkout(
    engine, sources, provider, settings, patient_id, order_id, quote_id, key, request_id
):
    with checkout_lock(engine, f"medication:{patient_id}:{key}", order_id) as session:
        alias = session.get(MedicationCheckoutKey, (patient_id, key))
        if alias and (alias.order_id, alias.quote_id) != (order_id, quote_id):
            raise DomainError(409, "idempotency_conflict", "Key already used for another request.")
        attempt = session.get(MedicationCheckoutAttempt, alias.payment_id) if alias else None
        replay = alias is not None
        if attempt is not None and attempt.response is not None:
            return attempt.response, True
        paid = session.scalar(
            select(Payment).where(
                Payment.order_id == order_id,
                Payment.status.in_(("succeeded", "refund_pending", "refunded", "refund_failed")),
            )
        )
        if paid:
            if paid.patient_id != patient_id:
                raise DomainError(404, "not_found", "Resource not found.")
            raise DomainError(409, "already_paid", "Order is already paid.")
        if attempt is None:
            attempt = session.scalar(
                select(MedicationCheckoutAttempt).where(
                    MedicationCheckoutAttempt.order_id == order_id,
                    MedicationCheckoutAttempt.closed_at.is_(None),
                )
            )
            if attempt:
                if attempt.patient_id != patient_id:
                    raise DomainError(404, "not_found", "Resource not found.")
                if attempt.quote_id != quote_id:
                    raise DomainError(
                        409, "payment_attempt_pending", "Order has a pending checkout."
                    )
                replay = True
            else:
                existing = session.scalar(
                    select(Payment).where(Payment.order_id == order_id, Payment.status == "pending")
                )
                if existing:
                    if existing.patient_id != patient_id:
                        raise DomainError(404, "not_found", "Resource not found.")
                    pending(existing.payment_id)
                attempt = MedicationCheckoutAttempt(
                    payment_id=uuid4(), order_id=order_id, quote_id=quote_id, patient_id=patient_id
                )
                session.add(attempt)
                session.flush()
            session.add(
                MedicationCheckoutKey(
                    patient_id=patient_id,
                    key=key,
                    order_id=order_id,
                    quote_id=quote_id,
                    payment_id=attempt.payment_id,
                )
            )
            session.commit()  # Persist operation identity before mutating fulfilment.
        payment = session.get(Payment, attempt.payment_id)
        if attempt.closed_at is not None:
            if (
                payment is not None
                and payment.provider_checkout_id is None
                and payment.status == "failed"
            ):
                raise DomainError(502, "checkout_rejected", "Provider rejected checkout.")
            raise DomainError(409, "quote_expired", "Checkout is closed; obtain a current quote.")
        if attempt.response is not None:
            return attempt.response, True
        try:
            reservation = sources.reserve_medication(
                order_id, quote_id, patient_id, attempt.payment_id, request_id
            )
        except DomainError as error:
            if error.status_code in {404, 409} and payment is None:
                attempt.closed_at = now()  # A foreign caller cannot block the owner.
                session.commit()
            raise
        if reservation.expires_at <= now():
            if payment is None:
                attempt.closed_at = now()
                session.commit()
            raise DomainError(409, "quote_expired", "The delivery quote has expired.")
        snapshot = reservation.model_dump(mode="json")
        if payment is None:
            profile = sources.profile(reservation.tenant_id, request_id)
            destination = settings.stripe_destinations.get(reservation.tenant_id)
            if not destination or not settings.stripe_secret_key:
                raise DomainError(503, "unavailable", "Clinic payment provider is not configured.")
            amount = reservation.total.amount_minor
            if not 50 <= amount <= 99999999:
                raise DomainError(409, "price_not_payable", "Price is outside Stripe SGD limits.")
            subtotal = reservation.medication_subtotal.amount_minor
            fee = subtotal * profile.commission_bps // 10000
            payment = Payment(
                payment_id=attempt.payment_id,
                tenant_id=reservation.tenant_id,
                patient_id=patient_id,
                purpose="medication_delivery",
                order_id=order_id,
                quote_id=quote_id,
                status="pending",
                amount_minor=amount,
                currency="SGD",
                commissionable_minor=subtotal,
                delivery_fee_minor=reservation.delivery_fee.amount_minor,
                commission_bps=profile.commission_bps,
                commission_amount_minor=fee,
                clinic_amount_minor=amount - fee,
                provider="stripe",
                provider_account_id=None,
                provider_idempotency_key="B06-create-" + str(attempt.payment_id),
            )
            session.add(payment)
            attempt.quote_expires_at = reservation.expires_at
            attempt.reservation = snapshot
            attempt.provider_fields = provider.fields(payment, destination)
            session.commit()  # Immutable money and exact Stripe parameters before network I/O.
        elif attempt.reservation != snapshot:
            pending(payment.payment_id)
        # Profile/network latency must not start a checkout beyond the quote deadline.
        if now() >= attempt.quote_expires_at:
            raise DomainError(409, "quote_expired", "The delivery quote has expired.")
        try:
            value = provider.create(payment, attempt)
        except ProviderRejected:
            payment.status = "failed"
            attempt.closed_at = now()
            session.commit()
            raise DomainError(502, "checkout_rejected", "Provider rejected checkout.") from None
        except ProviderUncertain:
            pending(payment.payment_id)
        payment.provider_checkout_id = value["id"]
        session.commit()
        if now() >= attempt.quote_expires_at:
            try:
                expire_attempt(session, payment, attempt, provider)
            except (ProviderRejected, ProviderUncertain):
                pending(payment.payment_id)
            raise DomainError(409, "quote_expired", "The delivery quote has expired.")
        result = CheckoutPublic(
            payment=payment_public(payment),
            checkout_url=value["url"],
            expires_at=attempt.quote_expires_at,
        ).model_dump(mode="json")
        attempt.response = result
        session.commit()
        return result, replay
