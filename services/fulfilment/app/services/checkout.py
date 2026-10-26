from datetime import datetime, timezone

from telelink_common.errors import DomainError

from app.integrations.billing import BillingClient
from app.models import Quote


def release_failed(session, order, settings):
    """Only billing's terminal operation fact can release an accepted attempt."""
    if order.payment_status != "pending" or order.payment_id is None:
        return
    if not settings.billing_url or not settings.billing_secret:
        raise DomainError(503, "unavailable", "Payment verification is not configured.")
    client = BillingClient(settings)
    try:
        fact = client.checkout_attempt(order.payment_id)
    finally:
        client.close()
    expected = {
        "payment_id": str(order.payment_id),
        "order_id": str(order.order_id),
        "patient_id": str(order.patient_id),
        "quote_id": str(order.quote_id),
    }
    if any(fact.get(key) != value for key, value in expected.items()):
        raise DomainError(502, "upstream_error", "Invalid payment context.")
    if fact.get("status") != "failed":
        raise DomainError(409, "payment_attempt_pending", "Existing payment needs reconciliation.")
    quote = session.get(Quote, order.quote_id)
    quote.status = "expired" if datetime.now(timezone.utc) >= quote.expires_at else "active"
    order.payment_id = None
    order.payment_status = "unpaid"
    order.updated_at = datetime.now(timezone.utc)
    session.flush()
