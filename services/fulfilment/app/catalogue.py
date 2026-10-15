from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from telelink_common.access import CurrentIdentity, require_identity
from telelink_common.errors import ErrorEnvelope

from app.access import permission_fingerprint, require_clinic
from app.database import get_session
from app.models import CatalogueItem
from app.pagination import decode, encode
from app.schemas import CataloguePage, CataloguePublic, CatalogueWrite, Money

router = APIRouter(
    tags=["catalogue"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 422, 502, 503)},
)
Identity = Annotated[CurrentIdentity, Depends(require_identity)]
DB = Annotated[object, Depends(get_session)]


def public_item(item):
    return CataloguePublic(
        tenant_id=item.tenant_id,
        medication_id=item.medication_id,
        display_name=item.display_name,
        unit_label=item.unit_label,
        unit_price=Money(currency="SGD", amount_minor=item.unit_price_minor),
        active=item.active,
        updated_at=item.updated_at,
    )


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
