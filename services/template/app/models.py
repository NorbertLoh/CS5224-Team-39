"""Example service-owned model; replace with domain models when copying the template."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Each copied service chooses its own fixed schema before its first migration.
SERVICE_SCHEMA = "template"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SERVICE_SCHEMA)


class ExampleItem(Base):
    __tablename__ = "example_items"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
