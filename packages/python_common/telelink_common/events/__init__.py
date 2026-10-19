"""C05 workflow event envelope, routing registry and transport validation.

Pure validation only: publication/retry tracking is M02 and SQS acknowledgement and
inbox deduplication are M03. Errors never echo payload values.
"""

from telelink_common.events.envelope import WorkflowEvent, format_timestamp, new_event
from telelink_common.events.errors import EventValidationError
from telelink_common.events.payloads import (
    AppointmentConfirmed,
    ConsultationPaymentSucceeded,
    DeliveryStatusChanged,
    DocumentReady,
    EventData,
    MedicalCertificateIssued,
    MedicationPaymentSucceeded,
    Money,
    PrescriptionIssued,
)
from telelink_common.events.registry import CONSUMERS, EVENT_TYPES, EventType
from telelink_common.events.transport import (
    parse_put_events_entry,
    parse_sqs_body,
    to_put_events_entry,
)

__all__ = [
    "CONSUMERS",
    "EVENT_TYPES",
    "AppointmentConfirmed",
    "ConsultationPaymentSucceeded",
    "DeliveryStatusChanged",
    "DocumentReady",
    "EventData",
    "EventType",
    "EventValidationError",
    "MedicationPaymentSucceeded",
    "MedicalCertificateIssued",
    "Money",
    "PrescriptionIssued",
    "WorkflowEvent",
    "format_timestamp",
    "new_event",
    "parse_put_events_entry",
    "parse_sqs_body",
    "to_put_events_entry",
]
