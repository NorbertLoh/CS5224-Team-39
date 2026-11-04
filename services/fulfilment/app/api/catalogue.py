from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import func, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert
from telelink_common.errors import DomainError, ErrorEnvelope

from app.access import permission_fingerprint, require_clinic
from app.api.dependencies import DB, Identity
from app.models import CatalogueItem
from app.pagination import decode, encode
from app.schemas import CataloguePage, CataloguePublic, CatalogueWrite, MedicationRegister, Money

router = APIRouter(
    tags=["catalogue"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 422, 502, 503)},
)


def public_item(item):
    return CataloguePublic(
        tenant_id=item.tenant_id,
        medication_id=item.medication_id,
        display_name=item.display_name,
        unit_label=item.unit_label,
        unit_price=(
            Money(currency="SGD", amount_minor=item.unit_price_minor)
            if item.unit_price_minor is not None
            else None
        ),
        active=item.active,
        updated_at=item.updated_at,
    )


@router.post("/clinics/{tenant_id}/catalogue", response_model=CataloguePublic, status_code=201)
def register_medication(
    tenant_id: UUID, body: MedicationRegister, identity: Identity, session: DB, response: Response
):
    require_clinic(identity, tenant_id, {"doctor", "clinic_admin"})
    name = body.display_name.strip()
    # Retried autosaves and simultaneous doctors reuse the clinic's same reference.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"catalogue-register:{tenant_id}"},
    )
    item = session.scalar(
        select(CatalogueItem)
        .where(
            CatalogueItem.tenant_id == tenant_id,
            func.lower(func.btrim(CatalogueItem.display_name)) == func.lower(name),
        )
        .order_by(CatalogueItem.medication_id)
        .limit(1)
        .with_for_update()
    )
    if item is not None:
        if not item.active:
            raise DomainError(409, "medication_unavailable", "Medication is inactive.")
        response.status_code = 200
    else:
        item = CatalogueItem(
            tenant_id=tenant_id,
            medication_id=uuid4(),
            display_name=name,
            unit_label="unit",
            unit_price_minor=None,
            active=True,
        )
        session.add(item)
        session.flush()
    session.commit()
    return public_item(item)


@router.put("/clinics/{tenant_id}/catalogue/{medication_id}", response_model=CataloguePublic)
def put_item(
    tenant_id: UUID,
    medication_id: UUID,
    body: CatalogueWrite,
    identity: Identity,
    session: DB,
    response: Response,
):
    require_clinic(identity, tenant_id, {"clinic_admin"})
    values = dict(
        tenant_id=tenant_id,
        medication_id=medication_id,
        display_name=body.display_name,
        unit_label=body.unit_label,
        unit_price_minor=body.unit_price.amount_minor,
        active=body.active,
    )
    # ON CONFLICT serializes simultaneous first writes without a read/insert race.
    inserted = session.execute(
        insert(CatalogueItem)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=[CatalogueItem.tenant_id, CatalogueItem.medication_id]
        )
        .returning(CatalogueItem)
    ).scalar_one_or_none()
    if inserted is not None:
        response.status_code = 201
        item = inserted
    else:
        item = session.scalar(
            select(CatalogueItem)
            .where(
                CatalogueItem.tenant_id == tenant_id, CatalogueItem.medication_id == medication_id
            )
            .with_for_update()
        )
        for field, value in values.items():
            setattr(item, field, value)
        item.updated_at = session.scalar(select(func.clock_timestamp()))
    session.commit()
    return public_item(item)


@router.get("/clinics/{tenant_id}/catalogue", response_model=CataloguePage)
def list_catalogue(
    tenant_id: UUID,
    request: Request,
    identity: Identity,
    session: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
):
    require_clinic(identity, tenant_id, {"doctor", "clinic_admin"})
    scope = ["catalogue", str(tenant_id), permission_fingerprint(identity), limit]
    query = select(CatalogueItem).where(
        CatalogueItem.tenant_id == tenant_id, CatalogueItem.active.is_(True)
    )
    if cursor:
        name, resource_id = decode(request.app.state.settings, scope, cursor)
        query = query.where(
            tuple_(CatalogueItem.display_name, CatalogueItem.medication_id)
            > tuple_(name, resource_id)
        )
    rows = session.scalars(
        query.order_by(CatalogueItem.display_name, CatalogueItem.medication_id).limit(limit + 1)
    ).all()
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode(
            request.app.state.settings, scope, last.display_name, last.medication_id
        )
    return CataloguePage(
        items=[public_item(item) for item in rows[:limit]], next_cursor=next_cursor
    )
