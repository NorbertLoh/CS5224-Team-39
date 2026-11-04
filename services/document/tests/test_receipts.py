from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from pypdf import PdfReader
from telelink_common.events import new_event
from test_worker import MemoryS3

from app.integrations.storage import PrivatePDFStore
from app.services.receipt_generation import GenerateReceipt


@pytest.mark.parametrize("medication", [False, True])
def test_paid_receipt_reuses_private_pdf_and_rejects_wrong_snapshot(medication):
    tenant, appointment, payment, patient, order = (uuid4() for _ in range(5))
    purpose = "medication_delivery" if medication else "consultation"
    reference = {"order_id": order} if medication else {"appointment_id": appointment}
    amount = {"amount_minor": 3500, "currency": "SGD"}
    paid_at = datetime.now(timezone.utc)
    event = new_event(
        "medication_payment_succeeded.v1" if medication else "consultation_payment_succeeded.v1",
        tenant_id=tenant,
        correlation_id=payment,
        occurred_at=paid_at,
        data={"payment_id": payment, "amount": amount, **reference},
    )
    snapshot = {
        "tenant_id": str(tenant),
        "appointment_id": str(appointment),
        "payment_id": str(payment),
        "patient_id": str(patient),
        "order_id": str(order) if medication else None,
        "purpose": purpose,
        "paid_at": paid_at.isoformat(),
        "clinic_name": "Synthetic Clinic",
        "patient_name": "Synthetic Patient",
        "amount": amount,
        "delivery_fee_minor": 700 if medication else 0,
    }
    storage = MemoryS3()
    session = SimpleNamespace(execute=lambda *args: None, scalar=lambda _: None, add=lambda _: None)
    settings = SimpleNamespace(
        billing_url="https://billing.test",
        billing_secret=SecretStr("test-" + "x" * 40),
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=snapshot))
    ) as client:
        generate = GenerateReceipt(settings, client, PrivatePDFStore(storage, "private"))
        generate(session, event)
        generate(session, event)  # Retry after object write and before the metadata commit.
        snapshot["amount"] = {"amount_minor": 100, "currency": "SGD"}
        with pytest.raises(RuntimeError, match="Receipt PDF processing failed"):
            generate(session, event)
    assert storage.puts == 1
    item = next(iter(storage.objects.values()))
    content = PdfReader(BytesIO(item["Body"])).pages[0].extract_text()
    assert "SGD 35.00" in content
    assert ("Delivery" in content) == medication
    assert "doctor-id" not in item["Metadata"]
