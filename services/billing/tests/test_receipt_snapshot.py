from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import Response
from telelink_common.errors import DomainError

from app.api.receipts import receipt_snapshot


@pytest.mark.parametrize("medication", [False, True])
def test_receipt_snapshot_requires_verified_payment_and_matches_order_context(medication):
    tenant, appointment, patient, payment_id, order = (uuid4() for _ in range(5))
    payment = SimpleNamespace(
        payment_id=payment_id,
        tenant_id=tenant,
        appointment_id=None if medication else appointment,
        patient_id=patient,
        order_id=order if medication else None,
        purpose="medication_delivery" if medication else "consultation",
        amount_minor=3500,
        currency="SGD",
        delivery_fee_minor=700 if medication else 0,
    )
    responses = {
        f"/internal/orders/{order}/receipt-context": {
            "tenant_id": str(tenant),
            "patient_id": str(patient),
            "order_id": str(order),
            "appointment_id": str(appointment),
        },
        f"/internal/clinics/{tenant}/receipt-profile": {
            "tenant_id": str(tenant),
            "clinic_name": "Synthetic Clinic",
        },
        f"/internal/receipt-patients/{patient}": {
            "patient_id": str(patient),
            "patient_name": "Synthetic Patient",
        },
    }
    sources = SimpleNamespace(request=lambda *args: httpx.Response(200, json=responses[args[4]]))
    settings = SimpleNamespace(
        fulfilment_url="https://fulfilment.test",
        fulfilment_secret=None,
        tenant_url="https://tenant.test",
        tenant_secret=None,
        identity_url="https://identity.test",
        identity_secret=None,
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(sources=sources, settings=settings)),
        state=SimpleNamespace(request_id="receipt-test"),
    )
    session = SimpleNamespace(get=lambda *_: payment, scalar=lambda _: None)
    with pytest.raises(DomainError) as error:
        receipt_snapshot(payment_id, request, Response(), session)
    assert error.value.status_code == 404
    paid_at = datetime.now(timezone.utc)
    session.scalar = lambda _: paid_at.isoformat()
    response = Response()
    result = receipt_snapshot(payment_id, request, response, session)
    assert result.appointment_id == appointment
    assert result.paid_at == paid_at
    assert result.amount.amount_minor == 3500
    assert response.headers["cache-control"] == "no-store"
