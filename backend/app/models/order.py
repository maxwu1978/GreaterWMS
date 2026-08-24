"""Inbound and Outbound order models."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
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


class InboundStatus(StrEnum):
    DRAFT = "draft"
    EXPECTED = "expected"  # ASN received, waiting for arrival
    ARRIVED = "arrived"  # Truck at dock
    RECEIVING = "receiving"  # Being unloaded and checked
    PUTAWAY = "putaway"  # Being put to storage locations
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OutboundStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"  # Awaiting wave assignment
    ALLOCATED = "allocated"  # Inventory allocated
    PICKING = "picking"
    PICKED = "picked"
    PACKING = "packing"
    PACKED = "packed"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class InboundPackageStatus(StrEnum):
    EXPECTED = "expected"
    RECEIVING = "receiving"
    RECEIVED = "received"
    STAGED = "staged"
    PUTAWAY_PENDING = "putaway_pending"
    STORED = "stored"


class InboundOrder(Base, TimestampMixin, TenantMixin):
    """Purchase order / ASN — goods coming into the warehouse."""

    __tablename__ = "inbound_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "order_number", name="uq_inbound_orders_tenant_order_number"),
        Index("ix_inbound_orders_tenant_created", "tenant_id", "created_at"),
        Index("ix_inbound_orders_tenant_status_created", "tenant_id", "status", "created_at"),
        Index(
            "ix_inbound_orders_tenant_warehouse_created",
            "tenant_id",
            "warehouse_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id"), nullable=False, index=True
    )
    warehouse_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("warehouses.id"), nullable=False
    )

    order_number: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(100))  # client's PO number
    status: Mapped[str] = mapped_column(String(20), default=InboundStatus.DRAFT.value)
    expected_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    extra_data: Mapped[dict | None] = mapped_column(JsonType, default=dict)

    # Relationships
    lines: Mapped[list["InboundOrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class InboundOrderLine(Base, TenantMixin):
    """Line item on an inbound order."""

    __tablename__ = "inbound_order_lines"
    __table_args__ = (
        Index("ix_inbound_order_lines_tenant_order", "tenant_id", "order_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inbound_orders.id"), nullable=False
    )
    sku_id: Mapped[str] = mapped_column(String(36), ForeignKey("skus.id"), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    quantity_expected: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_received: Mapped[int] = mapped_column(Integer, default=0)
    quantity_damaged: Mapped[int] = mapped_column(Integer, default=0)
    external_tracking_number: Mapped[str | None] = mapped_column(String(120), index=True)
    external_carton_mark: Mapped[str | None] = mapped_column(String(120), index=True)
    external_customer_barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    staging_location_id: Mapped[str | None] = mapped_column(String(36))
    package_count: Mapped[int | None] = mapped_column(Integer)
    pallet_count: Mapped[int | None] = mapped_column(Integer)
    rent_free_days: Mapped[int | None] = mapped_column(Integer)
    measured_weight_kg: Mapped[float | None] = mapped_column(Numeric(10, 3))
    measured_length_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    measured_width_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    measured_height_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    receiving_note: Mapped[str | None] = mapped_column(Text)
    lot_number: Mapped[str | None] = mapped_column(String(100))
    expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    order: Mapped["InboundOrder"] = relationship(back_populates="lines")


class InboundPackage(Base, TimestampMixin, TenantMixin):
    """Package/MU execution layer under an inbound order line."""

    __tablename__ = "inbound_packages"
    __table_args__ = (
        Index("ix_inbound_packages_tenant_order_status", "tenant_id", "order_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inbound_orders.id"), nullable=False, index=True
    )
    order_line_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inbound_order_lines.id"), nullable=False, index=True
    )
    package_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    label_sequence: Mapped[int | None] = mapped_column(Integer, index=True)
    package_type: Mapped[str] = mapped_column(String(20), nullable=False, default="carton")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=InboundPackageStatus.EXPECTED.value, index=True
    )
    expected_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    received_qty: Mapped[int] = mapped_column(Integer, default=0)
    damaged_qty: Mapped[int] = mapped_column(Integer, default=0)
    staging_location_id: Mapped[str | None] = mapped_column(String(36))
    external_tracking_number: Mapped[str | None] = mapped_column(String(120), index=True)
    external_carton_mark: Mapped[str | None] = mapped_column(String(120), index=True)
    external_customer_barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    package_count: Mapped[int | None] = mapped_column(Integer)
    pallet_count: Mapped[int | None] = mapped_column(Integer)
    rent_free_days: Mapped[int | None] = mapped_column(Integer)
    measured_weight_kg: Mapped[float | None] = mapped_column(Numeric(10, 3))
    measured_length_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    measured_width_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    measured_height_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    note: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReceivingLabel(Base, TimestampMixin, TenantMixin):
    """System-generated receiving label for inbound receipt execution."""

    __tablename__ = "receiving_labels"
    __table_args__ = (
        UniqueConstraint("tenant_id", "label_code", name="uq_receiving_labels_tenant_label_code"),
        Index("ix_receiving_labels_tenant_order_status", "tenant_id", "order_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inbound_orders.id"), nullable=False, index=True
    )
    order_line_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inbound_order_lines.id"), nullable=False, index=True
    )
    inbound_package_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("inbound_packages.id"), index=True
    )
    sku_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skus.id"), nullable=False, index=True
    )
    label_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    external_tracking_number: Mapped[str | None] = mapped_column(String(120), index=True)
    external_carton_mark: Mapped[str | None] = mapped_column(String(120), index=True)
    external_customer_barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    label_type: Mapped[str] = mapped_column(String(20), default="line")
    expected_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    received_qty: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    lot_number: Mapped[str | None] = mapped_column(String(100))
    expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra_data: Mapped[dict | None] = mapped_column(JsonType, default=dict)


class HandlingUnit(Base, TimestampMixin, TenantMixin):
    """Physical handling unit attached to a receiving label, ready for future AGV use."""

    __tablename__ = "handling_units"
    __table_args__ = (
        UniqueConstraint("tenant_id", "unit_code", name="uq_handling_units_tenant_unit_code"),
        Index("ix_handling_units_tenant_order", "tenant_id", "order_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inbound_orders.id"), nullable=False, index=True
    )
    order_line_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inbound_order_lines.id"), nullable=False, index=True
    )
    inbound_package_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("inbound_packages.id"), index=True
    )
    receiving_label_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("receiving_labels.id"), index=True
    )
    sku_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skus.id"), nullable=False, index=True
    )
    unit_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    unit_type: Mapped[str] = mapped_column(String(20), default="carton")
    expected_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    received_qty: Mapped[int] = mapped_column(Integer, default=0)
    damaged_qty: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="expected", index=True)
    staging_location_id: Mapped[str | None] = mapped_column(String(36))
    lot_number: Mapped[str | None] = mapped_column(String(100))
    expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_tracking_number: Mapped[str | None] = mapped_column(String(120), index=True)
    external_carton_mark: Mapped[str | None] = mapped_column(String(120), index=True)
    external_customer_barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    measured_weight_kg: Mapped[float | None] = mapped_column(Numeric(10, 3))
    measured_length_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    measured_width_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    measured_height_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    package_count: Mapped[int | None] = mapped_column(Integer)
    pallet_count: Mapped[int | None] = mapped_column(Integer)
    rent_free_days: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)


class ReceivingObservedCode(Base, TimestampMixin, TenantMixin):
    """Captured external or reference code observed during receiving before final confirmation."""

    __tablename__ = "receiving_observed_codes"
    __table_args__ = (
        Index("ix_receiving_observed_codes_tenant_order", "tenant_id", "order_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inbound_orders.id"), nullable=False, index=True
    )
    order_line_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("inbound_order_lines.id"), index=True
    )
    inbound_package_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("inbound_packages.id"), index=True
    )
    receiving_label_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("receiving_labels.id"), index=True
    )
    handling_unit_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("handling_units.id"), index=True
    )
    code_value: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    code_type: Mapped[str] = mapped_column(String(40), nullable=False, default="other")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="scan")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class OutboundOrder(Base, TimestampMixin, TenantMixin):
    """Ship order — goods leaving the warehouse."""

    __tablename__ = "outbound_orders"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "order_number", name="uq_outbound_orders_tenant_order_number"
        ),
        Index("ix_outbound_orders_tenant_created", "tenant_id", "created_at"),
        Index(
            "ix_outbound_orders_tenant_warehouse_created",
            "tenant_id",
            "warehouse_id",
            "created_at",
        ),
        Index("ix_outbound_orders_tenant_status_created", "tenant_id", "status", "created_at"),
        Index(
            "ix_outbound_orders_tenant_warehouse_status_created",
            "tenant_id",
            "warehouse_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_outbound_orders_tenant_pick_readiness_created_desc",
            "tenant_id",
            "pick_readiness_rank",
            text("created_at DESC"),
        ),
        Index(
            "ix_outbound_orders_tenant_warehouse_pick_readiness_created_desc",
            "tenant_id",
            "warehouse_id",
            "pick_readiness_rank",
            text("created_at DESC"),
        ),
        Index(
            "ix_outbound_orders_tenant_shipping_readiness_created_desc",
            "tenant_id",
            "shipping_readiness_rank",
            text("created_at DESC"),
        ),
        # Migration 008 names this ix_outbound_orders_tenant_warehouse_shipping_readiness_created_desc
        # (67 chars); PostgreSQL truncates identifiers to 63 chars, so the index that actually
        # exists in migrated databases carries the truncated name below. Declare the truncated
        # name here so create_all and Alembic-managed databases match exactly.
        Index(
            "ix_outbound_orders_tenant_warehouse_shipping_readiness_created_",
            "tenant_id",
            "warehouse_id",
            "shipping_readiness_rank",
            text("created_at DESC"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id"), nullable=False, index=True
    )
    warehouse_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("warehouses.id"), nullable=False
    )

    order_number: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(100))  # client's SO number
    status: Mapped[str] = mapped_column(String(20), default=OutboundStatus.DRAFT.value)
    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1=highest, 10=lowest
    channel: Mapped[str | None] = mapped_column(String(50))  # shopify, amazon, manual
    pick_readiness_rank: Mapped[int] = mapped_column(
        Integer, nullable=False, default=90, server_default="90"
    )
    shipping_readiness_rank: Mapped[int] = mapped_column(
        Integer, nullable=False, default=90, server_default="90"
    )

    # Shipping
    ship_to_name: Mapped[str | None] = mapped_column(String(200))
    ship_to_address: Mapped[dict | None] = mapped_column(JsonType)
    carrier: Mapped[str | None] = mapped_column(String(50))  # UPS, FedEx, USPS
    service_level: Mapped[str | None] = mapped_column(String(50))  # ground, express, overnight
    tracking_number: Mapped[str | None] = mapped_column(String(100))
    shipping_cost: Mapped[float | None] = mapped_column(Numeric(10, 2))

    # Dates
    required_ship_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    notes: Mapped[str | None] = mapped_column(Text)
    extra_data: Mapped[dict | None] = mapped_column(JsonType, default=dict)

    # Relationships
    lines: Mapped[list["OutboundOrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OutboundOrderLine(Base, TenantMixin):
    """Line item on an outbound order."""

    __tablename__ = "outbound_order_lines"
    __table_args__ = (
        Index("ix_outbound_order_lines_tenant_order", "tenant_id", "order_id"),
        Index("ix_outbound_order_lines_tenant_sku_order", "tenant_id", "sku_id", "order_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("outbound_orders.id"), nullable=False
    )
    sku_id: Mapped[str] = mapped_column(String(36), ForeignKey("skus.id"), nullable=False)
    quantity_ordered: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_allocated: Mapped[int] = mapped_column(Integer, default=0)
    quantity_picked: Mapped[int] = mapped_column(Integer, default=0)
    quantity_shipped: Mapped[int] = mapped_column(Integer, default=0)
    pick_location_id: Mapped[str | None] = mapped_column(String(36))  # assigned pick location

    # Relationships
    order: Mapped["OutboundOrder"] = relationship(back_populates="lines")
