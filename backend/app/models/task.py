"""
Task model — the bridge between WMS and AGV.

Tasks represent units of work (pick, putaway, move, replenish, cycle count).
Each task has a source and destination location, enabling AGV path planning.
The assigned_type field allows the same task model to drive both human and AGV work.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, generate_uuid


class TaskType(StrEnum):
    PICK = "pick"
    PUTAWAY = "putaway"
    REPLENISH = "replenish"
    MOVE = "move"
    CYCLE_COUNT = "cycle_count"
    LOAD = "load"  # dock loading
    UNLOAD = "unload"  # dock unloading


class TaskStatus(StrEnum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AssignedType(StrEnum):
    UNASSIGNED = "unassigned"
    HUMAN = "human"
    AGV = "agv"


class Task(Base, TimestampMixin, TenantMixin):
    """
    A unit of warehouse work. Designed to be consumed by both human operators
    and AGV systems through the same API.

    AGV integration flow:
    1. WMS creates task with assigned_type='unassigned'
    2. AGV scheduler queries pending tasks via API
    3. AGV scheduler assigns task (assigned_type='agv', assigned_to='agv:unit-003')
    4. AGV navigates using source/dest coordinates from Location model
    5. AGV reports completion → WMS updates inventory via InventoryTransaction
    """

    __tablename__ = "tasks"
    __table_args__ = (
        Index(
            "uq_tasks_inbound_putaway_handling_unit",
            "tenant_id",
            "task_type",
            "reference_type",
            "reference_id",
            "handling_unit_id",
            unique=True,
            sqlite_where=text(
                "task_type = 'putaway' "
                "AND reference_type = 'inbound_order' "
                "AND reference_id IS NOT NULL "
                "AND handling_unit_id IS NOT NULL"
            ),
            postgresql_where=text(
                "task_type = 'putaway' "
                "AND reference_type = 'inbound_order' "
                "AND reference_id IS NOT NULL "
                "AND handling_unit_id IS NOT NULL"
            ),
        ),
        Index(
            "ix_tasks_tenant_queue",
            "tenant_id",
            "status",
            "task_type",
            "assigned_type",
            "warehouse_id",
            "priority",
            "created_at",
        ),
        Index("ix_tasks_tenant_reference", "tenant_id", "reference_type", "reference_id"),
        Index(
            "ix_tasks_tenant_warehouse_queue",
            "tenant_id",
            "warehouse_id",
            "status",
            "assigned_type",
            "priority",
            "created_at",
        ),
        Index("ix_tasks_tenant_assigned_status", "tenant_id", "assigned_to", "status"),
        Index(
            "ix_tasks_tenant_status_type_priority_created",
            "tenant_id",
            "status",
            "task_type",
            "priority",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    warehouse_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("warehouses.id"), nullable=False
    )

    task_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.PENDING.value, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1=highest

    # What to move
    sku_id: Mapped[str | None] = mapped_column(String(36))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    lpn: Mapped[str | None] = mapped_column(String(50))
    handling_unit_id: Mapped[str | None] = mapped_column(String(36), index=True)
    execution_mode: Mapped[str] = mapped_column(String(20), default=AssignedType.HUMAN.value)

    # Where: source and destination locations
    source_location_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("locations.id"))
    destination_location_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("locations.id")
    )

    # Who: human or AGV
    assigned_type: Mapped[str] = mapped_column(String(20), default=AssignedType.UNASSIGNED.value)
    assigned_to: Mapped[str | None] = mapped_column(String(36))  # user_id or 'agv:{unit_id}'

    # Source reference
    reference_type: Mapped[str | None] = mapped_column(
        String(50)
    )  # 'inbound_order', 'outbound_order', 'wave'
    reference_id: Mapped[str | None] = mapped_column(String(36))

    # Timestamps
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Error tracking
    failure_reason: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)


class PutawayAllocation(Base, TimestampMixin, TenantMixin):
    """Optional split allocations for a putaway task across multiple destinations."""

    __tablename__ = "putaway_allocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id"), nullable=False, index=True
    )
    location_id: Mapped[str] = mapped_column(String(36), ForeignKey("locations.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class PickAllocation(Base, TimestampMixin, TenantMixin):
    """Reserved outbound stock for a specific order line and source location."""

    __tablename__ = "pick_allocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("outbound_orders.id"), nullable=False, index=True
    )
    order_line_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("outbound_order_lines.id"), nullable=False, index=True
    )
    warehouse_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("warehouses.id"), nullable=False
    )
    sku_id: Mapped[str] = mapped_column(String(36), ForeignKey("skus.id"), nullable=False)
    location_id: Mapped[str] = mapped_column(String(36), ForeignKey("locations.id"), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tasks.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_picked: Mapped[int] = mapped_column(Integer, default=0)
