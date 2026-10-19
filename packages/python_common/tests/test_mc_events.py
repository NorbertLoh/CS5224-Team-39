from datetime import datetime, timezone
from uuid import uuid4

import pytest

from telelink_common.events import EventValidationError, new_event


def test_mc_ready_metadata_is_source_specific_and_prescription_shape_is_preserved():
    links = {"document_id": uuid4(), "appointment_id": uuid4()}
    context = {
        "tenant_id": uuid4(),
        "correlation_id": uuid4(),
        "occurred_at": datetime.now(timezone.utc),
    }
    prescription = new_event(
        "document_ready.v1", data=links | {"prescription_id": uuid4()}, **context
    )
    assert set(prescription.detail()["data"]) == {
        "document_id",
        "appointment_id",
        "prescription_id",
    }
    mc = new_event("document_ready.v1", data=links | {"medical_certificate_id": uuid4()}, **context)
    assert set(mc.detail()["data"]) == {"document_id", "appointment_id", "medical_certificate_id"}
    for invalid in (links, links | {"prescription_id": uuid4(), "medical_certificate_id": uuid4()}):
        with pytest.raises(EventValidationError):
            new_event("document_ready.v1", data=invalid, **context)
