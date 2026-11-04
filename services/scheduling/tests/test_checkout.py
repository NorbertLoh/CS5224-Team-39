from concurrent.futures import ThreadPoolExecutor
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

SECRET = SecretStr("b02-scheduling-checkout-secret-at-least-32-bytes")


def reserve(api, appointment, *, payment=None, patient=None, auth=None):
    api[0].app.state.settings.billing_secret = SECRET
    token = service_token(SECRET, "billing", "telelink-scheduling-billing")
    return api[0].post(
        f"/internal/appointments/{appointment.appointment_id}/checkout-reservation",
        json={
            "payment_id": str(payment or uuid4()),
            "patient_id": str(patient or api[4]["patient"]),
        },
        headers=auth if auth is not None else {"Authorization": "Bearer " + token},
    )


def test_reservation_replay_trusted_price_and_unchanged_deadline(api):
    appointment = record(api)
    payment = uuid4()
    for _ in range(2):
        result = reserve(api, appointment, payment=payment)
        assert result.status_code == 200, result.text
        value = result.json()
        assert value["status"] == "pending_payment"
        assert value["payment_id"] == str(payment)
        assert value["consultation_price"]["amount_minor"] == 3210
    with Session(api[-1]) as session:
        assert (
            session.get(Appointment, appointment.appointment_id).hold_expires_at
            == appointment.hold_expires_at
        )


def test_reservation_service_scope_and_foreign_patient(api):
    appointment = record(api)
    assert reserve(api, appointment, auth={}).status_code == 401
    assert reserve(api, appointment, auth=api[1]("patient")).status_code == 401
    assert reserve(api, appointment, patient=api[4]["other_patient"]).status_code == 404
    wrong = service_token(SECRET, "billing", "another-audience")
    assert reserve(api, appointment, auth={"Authorization": "Bearer " + wrong}).status_code == 401


@pytest.mark.parametrize(
    "status,expected",
    [
        ("expired", "hold_expired"),
        ("cancelled", "invalid_appointment_transition"),
        ("confirmed", "already_paid"),
    ],
)
def test_expired_cancelled_and_paid_reservations_rejected(api, status, expected):
    result = reserve(api, record(api, status=status))
    assert result.status_code == 409 and result.json()["error"]["code"] == expected


def test_clinic_and_doctor_gate(api):
    appointment = record(api)
    api[5]["active"] = False
    assert reserve(api, appointment).status_code == 409
    api[5]["active"] = True
    api[5]["directory"] = []
    assert reserve(api, appointment).status_code == 409


@pytest.mark.parametrize(
    "previous_status,expected", [("pending", 409), ("succeeded", 409), ("failed", 200)]
)
def test_replacement_independently_checks_previous_payment(
    api, monkeypatch, previous_status, expected
):
    appointment = record(api, status="pending_payment")
    previous = SimpleNamespace(
        payment_id=appointment.payment_id,
        appointment_id=appointment.appointment_id,
        patient_id=appointment.patient_id,
        tenant_id=appointment.tenant_id,
        purpose="consultation",
        status=previous_status,
    )

    class Billing:
        def __init__(self, settings):
            pass

        def payment(self, payment_id):
            assert payment_id == previous.payment_id
            return previous

        def close(self):
            pass

    monkeypatch.setattr("app.api.checkout.BillingClient", Billing)
    assert reserve(api, appointment).status_code == expected


def test_concurrent_same_payment_reservation_is_idempotent(api):
    appointment, payment = record(api), uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reserve(api, appointment, payment=payment), [1, 2]))
    assert all(result.status_code == 200 for result in results)
    assert results[0].json()["payment_id"] == results[1].json()["payment_id"]


def test_exact_deadline_is_expired_and_does_not_bind_payment(api, monkeypatch):
    appointment = record(api)
    monkeypatch.setattr("app.api.checkout.server_now", lambda session: appointment.hold_expires_at)
    result = reserve(api, appointment)
    assert result.status_code == 409 and result.json()["error"]["code"] == "hold_expired"
    with Session(api[-1]) as session:
        stored = session.get(Appointment, appointment.appointment_id)
        assert stored.status == "expired" and stored.payment_id is None
