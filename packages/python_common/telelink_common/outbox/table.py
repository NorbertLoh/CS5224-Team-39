"""The outbox table each producing service adds to its own schema and migration."""

from sqlalchemy import Column, DateTime, Index, Integer, MetaData, String, Table, Text, Uuid, func
from sqlalchemy import text as sql_text


def outbox_table(metadata: MetaData, name: str = "event_outbox") -> Table:
    """Pending and published events; `published_at` stays null until PutEvents succeeds."""
    table = Table(
        name,
        metadata,
        Column("event_id", Uuid, primary_key=True),
        Column("source", String(64), nullable=False),
        Column("detail_type", String(100), nullable=False),
        Column("event_time", String(24), nullable=False),
        Column("detail", Text, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column(
            "next_attempt_at", DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
        Column("attempts", Integer, nullable=False, server_default=sql_text("0")),
        Column("last_error", String(100)),
        Column("published_at", DateTime(timezone=True)),
    )
    Index(
        f"ix_{name}_pending",
        table.c.next_attempt_at,
        postgresql_where=table.c.published_at.is_(None),
    )
    return table
