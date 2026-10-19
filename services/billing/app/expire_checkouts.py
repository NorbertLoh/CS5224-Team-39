"""Run continuously beside the API; --once supports a scheduled/operator pass."""

import argparse
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checkout import checkout_lock, expire_attempt, now
from app.database import create_database_engine
from app.models import CheckoutAttempt, MedicationCheckoutAttempt, Payment
from app.provider import ProviderRejected, ProviderUncertain, StripeCheckout
from app.settings import Settings


def expire_due(engine, provider):
    outcomes = {"closed": 0, "pending": 0}
    for model, resource, deadline in (
        (CheckoutAttempt, CheckoutAttempt.appointment_id, CheckoutAttempt.hold_expires_at),
        (
            MedicationCheckoutAttempt,
            MedicationCheckoutAttempt.order_id,
            MedicationCheckoutAttempt.quote_expires_at,
        ),
    ):
        result = expire_model(engine, provider, model, resource, deadline)
        for key in outcomes:
            outcomes[key] += result[key]
    return outcomes


def expire_model(engine, provider, model, resource, deadline):
    with Session(engine) as session:
        rows = session.execute(
            select(model.payment_id, resource)
            .where(model.closed_at.is_(None), deadline <= now())
            .order_by(deadline)
            .limit(100)
        ).all()
    outcomes = {"closed": 0, "pending": 0}
    for payment_id, appointment_id in rows:
        with checkout_lock(engine, appointment_id) as session:
            attempt = session.get(model, payment_id)
            payment = session.get(Payment, payment_id)
            if attempt.closed_at is not None:
                continue
            if payment is None:
                if model is MedicationCheckoutAttempt:
                    attempt.closed_at = now()
                    session.commit()  # No payment/provider request was ever created.
                    outcomes["closed"] += 1
                continue
            try:
                expire_attempt(session, payment, attempt, provider)
                outcomes["closed" if attempt.closed_at else "pending"] += 1
            except (ProviderRejected, ProviderUncertain):
                # A rejection during reconciliation does not prove that an earlier
                # create failed. Keep the payment pending for operator/provider review.
                session.rollback()
                outcomes["pending"] += 1
    return outcomes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    engine = create_database_engine(
        settings.database_url.get_secret_value() if settings.database_url else None
    )
    provider = StripeCheckout(settings)
    try:
        while True:
            print(expire_due(engine, provider), flush=True)
            if args.once:
                break
            time.sleep(5)
    finally:
        provider.close()
        engine.dispose()


if __name__ == "__main__":
    main()
