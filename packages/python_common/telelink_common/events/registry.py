"""Event type registry: DetailType to source, payload model and routed consumers."""

from dataclasses import dataclass

from telelink_common.events.payloads import (
    AppointmentConfirmed,
    ConsultationPaymentSucceeded,
    DeliveryStatusChanged,
    DocumentReady,
    EventData,
    MedicalCertificateIssued,
    MedicationPaymentSucceeded,
    PrescriptionIssued,
)

CONSUMERS = frozenset({"scheduling", "fulfilment", "document", "notification"})


@dataclass(frozen=True)
class EventType:
    detail_type: str
    source: str
    data_model: type[EventData]
    consumers: frozenset[str]


EVENT_TYPES = {
    spec.detail_type: spec
    for spec in (
        EventType(
            "consultation_payment_succeeded.v1",
            "telelink.billing",
            ConsultationPaymentSucceeded,
            frozenset({"scheduling"}),
        ),
        EventType(
            "medication_payment_succeeded.v1",
            "telelink.billing",
            MedicationPaymentSucceeded,
            frozenset({"fulfilment"}),
        ),
        EventType(
            "appointment_confirmed.v1",
            "telelink.scheduling",
            AppointmentConfirmed,
            frozenset({"notification"}),
        ),
        EventType(
            "prescription_issued.v1",
            "telelink.clinical-records",
            PrescriptionIssued,
            frozenset({"document"}),
        ),
        EventType(
            "medical_certificate_issued.v1",
            "telelink.clinical-records",
            MedicalCertificateIssued,
            frozenset({"document"}),
        ),
        EventType(
            "document_ready.v1",
            "telelink.document",
            DocumentReady,
            frozenset({"notification"}),
        ),
        EventType(
            "delivery_status_changed.v1",
            "telelink.fulfilment",
            DeliveryStatusChanged,
            frozenset({"notification"}),
        ),
    )
}
