"""Consistent literal search and timezone-aware date filters for collection queries."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy import String, cast, or_

from telelink_common.errors import DomainError


@dataclass
class ListFilters:
    q: str = ""
    from_at: datetime | None = None
    to_at: datetime | None = None

    def __post_init__(self):
        self.q = self.q.strip().lower()
        for field in ("from_at", "to_at"):
            value = getattr(self, field)
            if value is not None:
                if value.utcoffset() is None:
                    raise DomainError(422, "validation_error", "Use timezone-aware date filters.")
                setattr(self, field, value.astimezone(timezone.utc))
        if self.from_at is not None and self.to_at is not None and self.from_at >= self.to_at:
            raise DomainError(422, "validation_error", "from must precede to.")

    @property
    def scope(self):
        return {
            key: value
            for key, value in {
                "q": self.q,
                "from": self.from_at.isoformat() if self.from_at else None,
                "to": self.to_at.isoformat() if self.to_at else None,
            }.items()
            if value
        }


def list_filters(
    q: Annotated[str, Query(max_length=200)] = "",
    from_at: Annotated[datetime | None, Query(alias="from")] = None,
    to_at: Annotated[datetime | None, Query(alias="to")] = None,
):
    return ListFilters(q, from_at, to_at)


Filters = Annotated[ListFilters, Depends(list_filters)]


def filter_query(query, filters, date_column, search_columns):
    if filters.q:
        query = query.where(
            or_(
                *[
                    cast(column, String).icontains(filters.q, autoescape=True)
                    for column in search_columns
                ]
            )
        )
    if filters.from_at is not None:
        query = query.where(date_column >= filters.from_at)
    if filters.to_at is not None:
        query = query.where(date_column < filters.to_at)
    return query
