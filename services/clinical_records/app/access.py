"""Clinical policy is narrower than scheduling's operational metadata policy."""

from sqlalchemy import false, or_
from telelink_common.access import has_tenant_role
from telelink_common.errors import DomainError

from app.integrations.upstream import not_found
from app.models import Prescription


def assigned_doctor(identity, appointment):
    membership = next(
        (item for item in identity.memberships if item.tenant_id == appointment.tenant_id), None
    )
    return identity.subject_id == appointment.doctor_id and has_tenant_role(
        membership, appointment.tenant_id, "doctor"
    )


def authorize(identity, appointment, *, write=False, record=None):
    own = "patient" in identity.global_roles and identity.subject_id == appointment.patient_id
    doctor = assigned_doctor(identity, appointment)
    if not (doctor if write else own or doctor):
        not_found()
    if record is not None and any(
        getattr(record, field) != getattr(appointment, field)
        for field in ("tenant_id", "appointment_id", "patient_id", "doctor_id")
    ):
        not_found()
    if write and appointment.status != "in_progress":
        raise DomainError(409, "consultation_not_in_progress", "Consultation is not in progress.")


def prescription_scope(identity):
    predicates = [false()]
    if "patient" in identity.global_roles:
        predicates.append(Prescription.patient_id == identity.subject_id)
    for item in identity.memberships:
        if item.status == "active" and "doctor" in item.roles:
            predicates.append(
                (Prescription.tenant_id == item.tenant_id)
                & (Prescription.doctor_id == identity.subject_id)
            )
    return or_(*predicates)
