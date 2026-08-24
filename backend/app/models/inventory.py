"""SKU, Inventory, and InventoryTransaction models — the core domain."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonType, TenantMixin, TimestampMixin, generate_uuid


class TransactionType(StrEnum):
    RECEIVE = "receive"
    PUTAWAY = "putaway"
    PICK = "pick"
    PACK = "pack"
    SHIP = "ship"
    ADJUST = "adjust"  # manual adjustment
    MOVE = "move"  # location transfer
    CYCLE_COUNT = "cycle_count"
    RETURN = "return"


class SKU(Base, TimestampMixin, TenantMixin):
    """A product/item definition owned by a client."""

    __tablename__ = "skus"
    __table_args__ = (
        UniqueConstraint("tenant_id", "client_id", "sku_code", name="uq_skus_tenant_client_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id"), nullable=False, index=True
    )

    sku_code: Mapped[str] = mapped_column(String(100), nullable=False)  # client's product code
    barcode: Mapped[str | None] = mapped_column(String(100))  # UPC/EAN
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Dimensions & weight
    weight_kg: Mapped[float | None] = mapped_column(Numeric(10, 3))
    length_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    width_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    height_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))

    # Inventory control
    requires_lot: Mapped[bool] = mapped_column(default=False)
    requires_expiry: Mapped[bool] = mapped_column(default=False)  # FEFO tracking
    is_hazmat: Mapped[bool] = mapped_column(default=False)

    # Packing
    units_per_case: Mapped[int | None] = mapped_column(Integer)
    cases_per_pallet: Mapped[int | None] = mapped_column(Integer)

    attributes: Mapped[dict | None] = mapped_column(
        JsonType, default=dict
    )  # flexible custom fields

    # Relationships
    client: Mapped["Client"] = relationship(back_populates="skus")  # type: ignore[name-defined]  # noqa: F821


class Inventory(Base, TimestampMixin, TenantMixin):
    """
    Current inventory at a specific location.
    One row per (location, SKU, LPN, lot) combination.
    """

    __tablename__ = "inventory"
    __table_args__ = (
        # Enforce the documented natural key "one row per stock position".
        # NULLable dims (lpn/lot/expiry) are coalesced so Postgres treats them
        # as equal instead of always-distinct; expiry is part of the key because
        # putaway may legitimately split rows by expiry date.
        Index(
            "uq_inventory_stock_position",
            "tenant_id",
            "location_id",
            "sku_id",
            text("coalesce(lpn, '')"),
            text("coalesce(lot_number, '')"),
            text("coalesce(expiry_date, '1970-01-01')"),
            unique=True,
        ),
        Index(
            "ix_inventory_tenant_warehouse_location_sku",
            "tenant_id",
            "warehouse_id",
            "location_id",
            "sku_id",
        ),
        Index(
            "ix_inventory_tenant_warehouse_sku",
            "tenant_id",
            "warehouse_id",
            "sku_id",
        ),
        Index(
            "ix_inventory_tenant_live_order",
            "tenant_id",
            "warehouse_id",
            "sku_id",
            "location_id",
            "lot_number",
            "id",
            sqlite_where=text("quantity_on_hand > 0"),
            postgresql_where=text("quantity_on_hand > 0"),
        ),
        Index(
            "ix_inventory_tenant_warehouse_live_metrics",
            "tenant_id",
            "warehouse_id",
            "sku_id",
            "location_id",
            "quantity_on_hand",
            sqlite_where=text("quantity_on_hand > 0"),
            postgresql_where=text("quantity_on_hand > 0"),
        ),
        Index(
            "ix_inventory_tenant_live_metrics",
            "tenant_id",
            "sku_id",
            "location_id",
            "warehouse_id",
            "quantity_on_hand",
            sqlite_where=text("quantity_on_hand > 0"),
            postgresql_where=text("quantity_on_hand > 0"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    warehouse_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    location_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("locations.id"), nullable=False, index=True
    )
    sku_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skus.id"), nullable=False, index=True
    )

    # License Plate Number — unique identifier for a pallet/container
    lpn: Mapped[str | None] = mapped_column(String(50))
    lot_number: Mapped[str | None] = mapped_column(String(100))
    expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Quantities
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    quantity_allocated: Mapped[int] = mapped_column(Integer, default=0)  # reserved for orders
    quantity_damaged: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def quantity_available(self) -> int:
        return self.quantity_on_hand - self.quantity_allocated - self.quantity_damaged


class InventoryTransaction(Base, TenantMixin):
    """
    Immutable audit log of every inventory movement.
    This is the double-entry ledger of the warehouse.

    - NEVER updated, only appended
    - Partitioned by tenant_id for performance at scale
    - Critical for billing accuracy (operations counted here)
    - AGV reads from this to confirm task completion
    """

    __tablename__ = "inventory_transactions"
    __table_args__ = (
        Index(
            "ix_invtx_tenant_client_type_performed",
            "tenant_id",
            "client_id",
            "transaction_type",
            "performed_at",
        ),
        Index("ix_invtx_tenant_performed", "tenant_id", "performed_at"),
        Index(
            "ix_inventory_transactions_tenant_reference",
            "tenant_id",
            "reference_type",
            "reference_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sku_id: Mapped[str] = mapped_column(String(36), nullable=False)
    location_id: Mapped[str] = mapped_column(String(36), nullable=False)
    quantity_change: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # positive=in, negative=out

    # For moves: track both source and destination
    from_location_id: Mapped[str | None] = mapped_column(String(36))
    to_location_id: Mapped[str | None] = mapped_column(String(36))

    # Reference to source document (order, adjustment, etc.)
    reference_type: Mapped[str | None] = mapped_column(
        String(50)
    )  # 'inbound_order', 'outbound_order', 'adjustment'
    reference_id: Mapped[str | None] = mapped_column(String(36))

    # Who and when
    performed_by: Mapped[str | None] = mapped_column(String(36))  # user_id or 'agv:{agv_id}'
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    lot_number: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
