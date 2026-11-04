"""Consultation orchestration. Locks survive commits on a pinned PostgreSQL connection."""

from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from telelink_common.errors import DomainError

from app.integrations.stripe import ProviderRejected, ProviderUncertain
from app.models import CheckoutAttempt, CheckoutKey, Payment
from app.schemas import CheckoutPublic, payment_public


def now():
    return datetime.now(timezone.utc)


@contextmanager
def checkout_lock(engine, *names):
    # Do not return a session-level lock to the pool. Always unlock on this exact
    # connection; invalidate on failure so a leaked lock cannot survive pooling.
    with engine.connect() as connection:
        try:
            for name in names:
                connection.execute(
                    text("SELECT pg_advisory_lock(hashtextextended(:name, 0))"),
                    {"name": "billing-checkout:" + str(name)},
                )
            connection.commit()
            with Session(connection, expire_on_commit=False) as session:
                yield session
        finally:
            try:
                connection.rollback()
                for name in reversed(names):
                    connection.execute(
                        text("SELECT pg_advisory_unlock(hashtextextended(:name, 0))"),
                        {"name": "billing-checkout:" + str(name)},
                    )
                connection.commit()
            except Exception:
                connection.invalidate()
                raise


def pending(payment_id):
    raise DomainError(
        503,
        "payment_pending_reconciliation",
        "Payment outcome needs reconciliation; retry with the same key.",
        [{"field": "payment_id", "code": "pending", "message": str(payment_id)}],
    )


def create_checkout(
    engine, sources, provider, settings, patient_id, appointment_id, key, request_id
):
    with checkout_lock(engine, f"{patient_id}:{key}", appointment_id) as session:
        alias = session.get(CheckoutKey, (patient_id, key))
        if alias and alias.appointment_id != appointment_id:
            raise DomainError(
                409, "idempotency_conflict", "Key already used for another appointment."
            )
        attempt = session.get(CheckoutAttempt, alias.payment_id) if alias else None
        replay = alias is not None
        if attempt is not None and attempt.response is not None:
            return attempt.response, True
        paid = session.scalar(
            select(Payment).where(
                Payment.appointment_id == appointment_id,
                Payment.status.in_(("succeeded", "refund_pending", "refunded", "refund_failed")),
            )
        )
        if paid:
            if paid.patient_id != patient_id:
                raise DomainError(404, "not_found", "Resource not found.")
            raise DomainError(409, "already_paid", "Appointment is already paid.")
        if attempt is None:
            attempt = session.scalar(
                select(CheckoutAttempt)
                .where(
                    CheckoutAttempt.appointment_id == appointment_id,
                    CheckoutAttempt.closed_at.is_(None),
                )
                .order_by(CheckoutAttempt.created_at)
                .limit(1)
            )
            if attempt and attempt.patient_id != patient_id:
                raise DomainError(404, "not_found", "Resource not found.")
            if attempt is None:
                existing = session.scalar(
                    select(Payment).where(
                        Payment.appointment_id == appointment_id, Payment.status == "pending"
                    )
                )
                if existing is not None:
                    if existing.patient_id != patient_id:
                        raise DomainError(404, "not_found", "Resource not found.")
                    pending(existing.payment_id)
                attempt = CheckoutAttempt(
                    payment_id=uuid4(), appointment_id=appointment_id, patient_id=patient_id
                )
                session.add(attempt)
                session.flush()
            else:
                replay = True
            session.add(
                CheckoutKey(
                    patient_id=patient_id,
                    key=key,
                    appointment_id=appointment_id,
                    payment_id=attempt.payment_id,
                )
            )
            session.commit()  # durable operation before any upstream mutation
        payment = session.get(Payment, attempt.payment_id)
        if attempt.closed_at is not None:
            if payment is None:
                raise DomainError(404, "not_found", "Resource not found.")
            if payment.status == "failed" and payment.provider_checkout_id is None:
                raise DomainError(502, "checkout_rejected", "Provider rejected checkout.")
            raise DomainError(409, "hold_expired", "The booking hold has expired.")
        try:
            reservation = sources.reserve(
                appointment_id, patient_id, attempt.payment_id, request_id
            )
        except DomainError as error:
            if error.status_code == 404 and payment is None:
                # A foreign caller must not leave a live attempt that blocks the owner.
                attempt.closed_at = now()
                session.commit()
            raise
        profile = sources.profile(reservation.tenant_id, request_id)
        if reservation.hold_expires_at <= now():
            raise DomainError(409, "hold_expired", "The booking hold has expired.")
        if payment is None:
            amount = reservation.consultation_price.amount_minor
            destination = settings.stripe_destinations.get(reservation.tenant_id)
            if not destination or not settings.stripe_secret_key:
                raise DomainError(503, "unavailable", "Clinic payment provider is not configured.")
            if not 50 <= amount <= 99999999:
                raise DomainError(409, "price_not_payable", "Price is outside Stripe SGD limits.")
            fee = amount * profile.commission_bps // 10000
            payment = Payment(
                payment_id=attempt.payment_id,
                tenant_id=reservation.tenant_id,
                patient_id=patient_id,
                purpose="consultation",
                appointment_id=appointment_id,
                status="pending",
                amount_minor=amount,
                currency="SGD",
                commissionable_minor=amount,
                delivery_fee_minor=0,
                commission_bps=profile.commission_bps,
                commission_amount_minor=fee,
                clinic_amount_minor=amount - fee,
                provider="stripe",
                provider_account_id=None,
                provider_idempotency_key="B02-create-" + str(attempt.payment_id),
            )
            session.add(payment)
            attempt.hold_expires_at = reservation.hold_expires_at
            attempt.provider_fields = provider.fields(payment, destination)
            session.commit()  # financial snapshot and exact parameters before Stripe POST
        elif (
            payment.tenant_id != reservation.tenant_id
            or payment.amount_minor != reservation.consultation_price.amount_minor
            or attempt.hold_expires_at != reservation.hold_expires_at
        ):
            pending(payment.payment_id)
        if attempt.response is not None:
            return attempt.response, True
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
        # Keep the provider ID durable even when creation crossed the deadline.
        if now() >= attempt.hold_expires_at:
            try:
                expire_attempt(session, payment, attempt, provider)
            except (ProviderRejected, ProviderUncertain):
                pending(payment.payment_id)
            raise DomainError(409, "hold_expired", "The booking hold has expired.")
        result = CheckoutPublic(
            payment=payment_public(payment),
            checkout_url=value["url"],
            expires_at=attempt.hold_expires_at,
        ).model_dump(mode="json")
        attempt.response = result
        session.commit()
        return result, replay


def expire_attempt(session, payment, attempt, provider):
    if payment.provider_checkout_id is None:
        # Lost create response: reconcile the same persisted operation before expiry.
        value = provider.create(payment, attempt)
        payment.provider_checkout_id = value["id"]
        session.commit()
    value = provider.expire(payment.provider_checkout_id, payment.payment_id)
    # Webhooks/reconciliation may have changed payment truth during the HTTP call.
    payment = session.scalar(
        select(Payment)
        .where(Payment.payment_id == payment.payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if value.get("status") == "expired" and value.get("payment_status") == "unpaid":
        if payment.status == "pending":
            payment.status = "failed"
        attempt.closed_at = now()
    elif value.get("status") == "complete":
        # B03/B04 establish payment truth. No local expiry may erase a success.
        attempt.closed_at = now()
    session.commit()
