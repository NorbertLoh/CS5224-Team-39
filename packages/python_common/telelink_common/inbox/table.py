"""The inbox table each consuming service adds to its own schema and migration."""

from sqlalchemy import Column, DateTime, MetaData, String, Table, Uuid, func


def inbox_table(metadata: MetaData, name: str = "event_inbox") -> Table:
    """One row per handled `(consumer, event_id)`; its presence marks a duplicate."""
    return Table(
        name,
        metadata,
        Column("consumer", String(32), primary_key=True),
        Column("event_id", Uuid, primary_key=True),
        Column("detail_type", String(100), nullable=False),
        Column("processed_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
