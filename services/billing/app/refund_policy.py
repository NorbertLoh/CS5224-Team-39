"""Public payment eligibility without exposing provider references."""

import re
from typing import Literal

RefundAvailability = Literal[
    "available", "demo_payment", "unsupported_purpose", "not_paid", "unsupported_payment"
]


def refund_availability(payment) -> RefundAvailability:
    if payment.purpose != "consultation":
        return "unsupported_purpose"
    if payment.provider == "demo_seed":
        return "demo_payment"
    if payment.status not in {"succeeded", "refund_failed"} or payment.amount_minor <= 0:
        return "not_paid"
    if (
        payment.provider != "stripe"
        or payment.provider_account_id is not None
        or not re.fullmatch(r"pi_[A-Za-z0-9]+", payment.provider_payment_id or "")
    ):
        return "unsupported_payment"
    return "available"
