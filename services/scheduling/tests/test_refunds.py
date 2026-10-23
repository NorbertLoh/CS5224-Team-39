"""Billing-authenticated terminal-booking refund guards and independently verified completion."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.orm import Session
from telelink_common.service_auth import service_token
from test_api import api as api
from test_api import api_database as api_database
from test_appointments import record

from app.models import Appointment

SECRET = SecretStr("rf08-billing-scheduling-refund-secret-32-bytes")


def action(api, appointment, *, path="refund-review", body=None, headers=None):
    api[0].app.state.settings.billing_secret = SECRET
    return api[0].post(
        f"/internal/appointments/{appointment.appointment_id}/{path}",
        json=body
        or {
            "tenant_id": str(appointment.tenant_id),
            "patient_id": str(appointment.patient_id),
            "payment_id": str(appointment.payment_id),
        },
        headers=headers
        if headers is not None
        else {
            "Authorization": "Bearer "
            + service_token(SECRET, "billing", "telelink-scheduling-billing")
        },
    )


@pytest.mark.parametrize(
    "status,expected",
    [("confirmed", 409), ("in_progress", 409), ("completed", 200), ("no_show", 200)],
)
def test_only_terminal_booking_can_be_refunded(api, status, expected):
    appointment = record(api, status=status)
    response = action(api, appointment)
    assert response.status_code == expected, response.text
    if expected == 200:
        assert response.json()["payment_resolution"] == "refund_required"


def test_cancellation_then_refund_and_scope(api):
    appointment = record(api, status="confirmed")
    assert action(api, appointment, headers={}).status_code == 401
    assert action(api, appointment, headers=api[1]("admin")).status_code == 401
    with Session(api[-1]) as session, session.begin():
        session.get(Appointment, appointment.appointment_id).status = "cancelled"
    assert action(api, appointment).status_code == 200
    body = {
        "tenant_id": str(uuid4()),
        "patient_id": str(appointment.patient_id),
        "payment_id": str(appointment.payment_id),
    }
    assert action(api, appointment, body=body).status_code == 404
    body["tenant_id"] = str(appointment.tenant_id)
    body["payment_id"] = str(uuid4())
    assert action(api, appointment, body=body).status_code == 409


def test_completion_verifies_billing_truth_and_context(api, monkeypatch):
    appointment = record(api, status="completed")
    fact = SimpleNamespace(
        payment_id=appointment.payment_id,
        status="refund_pending",
        purpose="consultation",
        appointment_id=appointment.appointment_id,
        patient_id=appointment.patient_id,
        tenant_id=appointment.tenant_id,
        amount=SimpleNamespace(amount_minor=3210),
    )

    class Billing:
        def __init__(self, settings):
            pass

        def close(self):
            pass

        def payment(self, payment_id):
            assert payment_id == appointment.payment_id
            return fact

    monkeypatch.setattr("app.checkout.BillingClient", Billing)
    assert action(api, appointment, path="refund-complete").status_code == 409
    fact.status = "refunded"
    assert (
        action(api, appointment, path="refund-complete").json()["payment_resolution"] == "refunded"
    )
    assert action(api, appointment).json()["payment_resolution"] == "refunded"
