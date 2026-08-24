"""Warehouse, Zone, and Location models — physical infrastructure."""

from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonType, TenantMixin, TimestampMixin, generate_uuid


class LocationType(StrEnum):
    STORAGE = "storage"  # Regular storage (rack, shelf, bin)
    STAGING = "staging"  # Inbound/outbound staging area
    BUFFER = "buffer"  # AGV or workflow buffer point
    DOCK = "dock"  # Loading dock
    CHARGING = "charging"  # AGV charging station
    AGV_STATION = "agv_station"  # AGV pickup/dropoff or waiting station
    DRIVE_AISLE = "drive_aisle"  # Movement lane or aisle reference
    REFERENCE = "reference"  # Non-storage layout reference
    QUALITY = "quality"  # QC inspection area
    PACKING = "packing"  # Packing station


class LocationStatus(StrEnum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    BLOCKED = "blocked"  # Maintenance or damaged


class Warehouse(Base, TimestampMixin, TenantMixin):
    """A physical warehouse facility belonging to a tenant."""

    __tablename__ = "warehouses"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[dict | None] = mapped_column(JsonType)
    timezone: Mapped[str] = mapped_column(String(50), default="America/Chicago")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="warehouses")  # type: ignore[name-defined]  # noqa: F821
    zones: Mapped[list["Zone"]] = relationship(
        back_populates="warehouse", cascade="all, delete-orphan"
    )


class Zone(Base, TimestampMixin, TenantMixin):
    """A logical zone within a warehouse (e.g., Zone A - Ambient, Zone B - Cold)."""

    __tablename__ = "zones"
    __table_args__ = (
        UniqueConstraint("tenant_id", "warehouse_id", "code", name="uq_zones_tenant_wh_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    warehouse_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("warehouses.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    is_agv_zone: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # AGV-Ready: zone supports AGV
    sequence: Mapped[int] = mapped_column(Integer, default=0)  # for pick path ordering
    zone_type: Mapped[str] = mapped_column(String(40), default=LocationType.STORAGE.value)
    coordinate_x: Mapped[float | None] = mapped_column(Numeric(10, 3))
    coordinate_y: Mapped[float | None] = mapped_column(Numeric(10, 3))
    coordinate_z: Mapped[float | None] = mapped_column(Numeric(10, 3))
    dimensions: Mapped[dict | None] = mapped_column(JsonType)
    layout_metadata: Mapped[dict | None] = mapped_column(JsonType)
    drawing_source: Mapped[dict | None] = mapped_column(JsonType)

    # Relationships
    warehouse: Mapped["Warehouse"] = relationship(back_populates="zones")
    locations: Mapped[list["Location"]] = relationship(
        back_populates="zone", cascade="all, delete-orphan"
    )


class Location(Base, TimestampMixin, TenantMixin):
    """
    A specific storage location within a zone.

    AGV-Ready design:
    - coordinate_x/y/z: physical coordinates for AGV navigation
    - is_agv_accessible: whether an AGV can reach this location
    - These fields exist from day one, even before AGV deployment.
    """

    __tablename__ = "locations"
    # Scan lookups (websocket/scanner.py, agent tools) resolve barcodes tenant-wide,
    # so barcodes must be unique per tenant, not merely per warehouse.
    __table_args__ = (
        UniqueConstraint("tenant_id", "barcode", name="uq_locations_tenant_barcode"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    warehouse_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("warehouses.id"), nullable=False
    )
    zone_id: Mapped[str] = mapped_column(String(36), ForeignKey("zones.id"), nullable=False)

    # Location addressing: Zone-Aisle-Rack-Level-Position (e.g., A-01-03-02-01)
    barcode: Mapped[str] = mapped_column(String(50), nullable=False)  # unique scannable code
    aisle: Mapped[str] = mapped_column(String(10), nullable=False)
    rack: Mapped[str] = mapped_column(String(10), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    position: Mapped[str] = mapped_column(String(10), nullable=False)

    # AGV-Ready: physical coordinates for navigation
    coordinate_x: Mapped[float | None] = mapped_column(Numeric(10, 3))
    coordinate_y: Mapped[float | None] = mapped_column(Numeric(10, 3))
    coordinate_z: Mapped[float | None] = mapped_column(Numeric(10, 3))
    is_agv_accessible: Mapped[bool] = mapped_column(Boolean, default=False)

    # Properties
    location_type: Mapped[str] = mapped_column(String(20), default=LocationType.STORAGE.value)
    current_status: Mapped[str] = mapped_column(String(20), default=LocationStatus.AVAILABLE.value)
    max_weight_kg: Mapped[float | None] = mapped_column(Numeric(10, 2))
    max_volume_m3: Mapped[float | None] = mapped_column(Numeric(10, 4))
    pick_sequence: Mapped[int] = mapped_column(Integer, default=0)  # for pick path optimization
    dimensions: Mapped[dict | None] = mapped_column(JsonType)
    layout_metadata: Mapped[dict | None] = mapped_column(JsonType)
    drawing_source: Mapped[dict | None] = mapped_column(JsonType)
    wcs_point_metadata: Mapped[dict | None] = mapped_column(JsonType)

    # Relationships
    zone: Mapped["Zone"] = relationship(back_populates="locations")
