"""Return/RMA models — reverse logistics flow."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin, generate_uuid


class ReturnStatus(StrEnum):
    REQUESTED = "requested"  # RMA created, waiting for items
    RECEIVED = "received"  # Items arrived back at warehouse
    INSPECTING = "inspecting"  # Quality inspection in progress
    COMPLETED = "completed"  # Disposition done (restocked/scrapped)
    CANCELLED = "cancelled"


class DispositionType(StrEnum):
    RESTOCK = "restock"  # Put back on shelf
    DAMAGED = "damaged"  # Move to damaged area
    SCRAP = "scrap"  # Dispose
    RETURN_TO_VENDOR = "return_to_vendor"


class ReturnOrder(Base, TimestampMixin, TenantMixin):
    """Return Merchandise Authorization (RMA)."""

    __tablename__ = "return_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "rma_number", name="uq_return_orders_tenant_rma"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id"), nullable=False, index=True
    )
    warehouse_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("warehouses.id"), nullable=False
    )

    rma_number: Mapped[str] = mapped_column(String(50), nullable=False)
    original_order_id: Mapped[str | None] = mapped_column(String(36))  # Link to outbound order
    status: Mapped[str] = mapped_column(String(20), default=ReturnStatus.REQUESTED.value)
    reason: Mapped[str | None] = mapped_column(String(200))
    customer_name: Mapped[str | None] = mapped_column(String(200))
    tracking_number: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    received_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    lines: Mapped[list["ReturnOrderLine"]] = relationship(
        back_populates="return_order", cascade="all, delete-orphan"
    )


class ReturnOrderLine(Base, TenantMixin):
    """Individual item on a return order."""

    __tablename__ = "return_order_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    return_order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("return_orders.id"), nullable=False
    )
    sku_id: Mapped[str] = mapped_column(String(36), ForeignKey("skus.id"), nullable=False)
    quantity_expected: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_received: Mapped[int] = mapped_column(Integer, default=0)
    quantity_restocked: Mapped[int] = mapped_column(Integer, default=0)
    quantity_damaged: Mapped[int] = mapped_column(Integer, default=0)
    quantity_scrapped: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(String(200))
    disposition: Mapped[str | None] = mapped_column(String(30))  # DispositionType
    notes: Mapped[str | None] = mapped_column(Text)

    # Relationships
    return_order: Mapped["ReturnOrder"] = relationship(back_populates="lines")
