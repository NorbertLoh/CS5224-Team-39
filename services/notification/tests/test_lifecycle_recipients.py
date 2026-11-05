from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from telelink_common.events import new_event
from test_recipients import settings

from app.integrations.recipients import RecipientDirectory, RecipientLookupError


@pytest.mark.parametrize(
    "kind,owner,key",
    [
        ("appointment_cancelled.v1", "scheduling", "appointment_id"),
        ("prescription_priced.v1", "fulfilment", "prescription_id"),
        ("payment_refunded.v1", "billing", "payment_id"),
        ("document_ready.v1", "document", "document_id"),
    ],
)
@pytest.mark.parametrize("mismatch", [False, True])
def test_new_notice_resolves_only_matching_owner_context(kind, owner, key, mismatch):
    resource, tenant, patient = uuid4(), uuid4(), uuid4()
    data = {key: resource}
    if kind == "prescription_priced.v1":
        data["patient_id"] = patient
    elif kind == "payment_refunded.v1":
        data["refund_id"] = uuid4()
    elif kind == "document_ready.v1":
        data |= {"payment_id": uuid4(), "appointment_id": uuid4()}
    event = new_event(
        kind,
        tenant_id=tenant,
        correlation_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        data=data,
    )
    cfg = settings(
        billing_url="http://billing.test", billing_secret="billing-notification-" + "x" * 40
    )

    def respond(request):
        if request.url.host == "identity.test":
            return httpx.Response(
                200, json={"recipient_id": str(patient), "email": "patient@example.test"}
            )
        assert request.url.host == owner + ".test"
        assert request.url.params["tenant_id"] == str(tenant)
        context = {
            "resource_id": str(resource),
            "tenant_id": str(uuid4() if mismatch else tenant),
            "patient_id": str(patient),
            "eligible": True,
            "status": "cancelled",
            **{k: str(v) for k, v in data.items()},
        }
        if kind == "document_ready.v1":
            context |= {"kind": "receipt_pdf", "purpose": "medication_delivery"}
        return httpx.Response(200, json=context)

    directory = RecipientDirectory(cfg, transport=httpx.MockTransport(respond))
    try:
        if mismatch:
            with pytest.raises(RecipientLookupError):
                directory.resolve(event)
        else:
            assert directory.resolve(event).subject_id == patient
    finally:
        directory.close()
