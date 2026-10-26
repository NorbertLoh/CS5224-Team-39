from telelink_common.errors import DomainError

from app.models import Clinic


def clinic_or_404(session, tenant_id):
    clinic = session.get(Clinic, tenant_id)
    if clinic is None:
        raise DomainError(404, "not_found", "Resource not found.")
    return clinic


def editable_fields(body):
    fields = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.branding is not None:
        fields.update(body.branding.model_dump())
    if body.consultation_price is not None:
        fields.update(
            consultation_price_minor=body.consultation_price.amount_minor,
            currency=body.consultation_price.currency,
        )
    return fields
