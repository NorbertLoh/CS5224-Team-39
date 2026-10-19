"""Only fulfilment-owned tables. External resource IDs have no cross-service FKs."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from telelink_common.inbox import inbox_table
from telelink_common.outbox import outbox_table

SERVICE_SCHEMA = "fulfilment"
MAX_MONEY = 9007199254740991


class Base(DeclarativeBase):
    metadata = MetaData(schema=SERVICE_SCHEMA)


event_inbox = inbox_table(Base.metadata)
event_outbox = outbox_table(Base.metadata)


class CatalogueItem(Base):
    __tablename__ = "catalogue_items"
    __table_args__ = (
        CheckConstraint(f"unit_price_minor BETWEEN 0 AND {MAX_MONEY}", name="ck_catalogue_price"),
        CheckConstraint("length(trim(display_name)) > 0", name="ck_catalogue_name"),
        CheckConstraint("length(trim(unit_label)) > 0", name="ck_catalogue_unit"),
        Index("ix_catalogue_page", "tenant_id", "display_name", "medication_id"),
    )
    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    medication_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))
    unit_label: Mapped[str] = mapped_column(String(80))
    unit_price_minor: Mapped[int] = mapped_column(BigInteger)
    active: Mapped[bool]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("prescription_id", name="uq_orders_prescription"),
        CheckConstraint(
            "status IN ('awaiting_payment','paid','submitting','dispatched','delivered',"
            "'cancelled','exception')",
            name="ck_order_status",
        ),
        CheckConstraint("medicine_status IN ('not_ready','ready')", name="ck_order_medicine"),
        CheckConstraint(
            "payment_status IN ('unpaid','pending','succeeded','refund_required','refunded')",
            name="ck_order_payment",
        ),
        CheckConstraint(
            f"medication_subtotal_minor BETWEEN 0 AND {MAX_MONEY}", name="ck_order_subtotal"
        ),
        CheckConstraint(
            "(delivery_fee_minor IS NULL AND total_minor IS NULL) OR "
            "(delivery_fee_minor IS NOT NULL AND total_minor IS NOT NULL AND "
            f"delivery_fee_minor BETWEEN 0 AND {MAX_MONEY} AND "
            f"total_minor BETWEEN 0 AND {MAX_MONEY} AND "
            "total_minor = medication_subtotal_minor + delivery_fee_minor)",
            name="ck_order_total",
        ),
        Index("ix_orders_patient_page", "patient_id", "created_at", "order_id"),
        Index("ix_orders_tenant_page", "tenant_id", "created_at", "order_id"),
    )
    order_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    prescription_id: Mapped[UUID] = mapped_column(Uuid)
    appointment_id: Mapped[UUID] = mapped_column(Uuid)
    patient_id: Mapped[UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(30), default="awaiting_payment")
    medicine_status: Mapped[str] = mapped_column(String(20), default="not_ready")
    payment_status: Mapped[str] = mapped_column(String(30), default="unpaid")
    payment_id: Mapped[UUID | None] = mapped_column(Uuid)
    quote_id: Mapped[UUID | None] = mapped_column(Uuid)
    delivery_id: Mapped[UUID | None] = mapped_column(Uuid)
    medication_subtotal_minor: Mapped[int] = mapped_column(BigInteger)
    delivery_fee_minor: Mapped[int | None] = mapped_column(BigInteger)
    total_minor: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    items: Mapped[list["OrderItem"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OrderItem.position",
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "position", name="uq_order_item_position"),
        CheckConstraint("quantity > 0 AND position >= 0", name="ck_order_item_quantity"),
        CheckConstraint(f"unit_price_minor BETWEEN 0 AND {MAX_MONEY}", name="ck_order_item_price"),
        CheckConstraint(
            f"line_total_minor BETWEEN 0 AND {MAX_MONEY} AND "
            "line_total_minor = quantity * unit_price_minor",
            name="ck_order_item_total",
        ),
    )
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("fulfilment.orders.order_id", ondelete="CASCADE"),
        primary_key=True,
    )
    prescription_item_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    position: Mapped[int]
    medication_id: Mapped[UUID] = mapped_column(Uuid)
    display_name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(BigInteger)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger)
    line_total_minor: Mapped[int] = mapped_column(BigInteger)


class OrderRequest(Base):
    """Persistent subject/operation key; retained indefinitely in D01."""

    __tablename__ = "order_requests"
    subject_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    prescription_id: Mapped[UUID] = mapped_column(Uuid)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("fulfilment.orders.order_id"))
    response_payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','accepted','expired','superseded')", name="ck_quote_status"
        ),
        CheckConstraint(
            f"medication_subtotal_minor BETWEEN 0 AND {MAX_MONEY} AND "
            f"delivery_fee_minor BETWEEN 0 AND {MAX_MONEY} AND "
            f"total_minor BETWEEN 0 AND {MAX_MONEY} "
            "AND total_minor = medication_subtotal_minor + delivery_fee_minor",
            name="ck_quote_total",
        ),
        CheckConstraint("expires_at > created_at", name="ck_quote_expiry"),
        Index("ix_quotes_order", "order_id"),
        Index(
            "uq_quotes_active_order",
            "order_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )
    quote_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("fulfilment.orders.order_id"))
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(20), default="active")
    medication_subtotal_minor: Mapped[int] = mapped_column(BigInteger)
    delivery_fee_minor: Mapped[int] = mapped_column(BigInteger)
    total_minor: Mapped[int] = mapped_column(BigInteger)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Private snapshots for checkout/delivery consumers; never public or logged.
    items: Mapped[list] = mapped_column(JSON)
    destination: Mapped[dict] = mapped_column(JSON)
    provider_context: Mapped[dict] = mapped_column(JSON)


class QuoteRequest(Base):
    __tablename__ = "quote_requests"
    subject_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    quote_id: Mapped[UUID] = mapped_column(ForeignKey("fulfilment.quotes.quote_id"))
    response_payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_delivery_order"),
        UniqueConstraint("operation_id", name="uq_delivery_operation"),
        UniqueConstraint("provider_order_id", name="uq_delivery_provider_order"),
        CheckConstraint(
            "status IN ('pending','submitted','picked_up','delivered',"
            "'cancelled','failed','unknown')",
            name="ck_delivery_status",
        ),
        Index("ix_delivery_pending", "status", "created_at"),
    )
    delivery_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("fulfilment.orders.order_id"))
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    operation_id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    provider_order_id: Mapped[str | None] = mapped_column(String(30))
    # Private immutable submission request, including provider quote and minimal contacts.
    request_payload: Mapped[dict | None] = mapped_column(JSON)
    provider_quote_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    send_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(40))
    resolution_reason: Mapped[str | None] = mapped_column(String(40))
    resolution_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciled_by: Mapped[str | None] = mapped_column(String(80))
    next_poll_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    poll_attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    poll_error: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
