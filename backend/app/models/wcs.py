"""WCS integration records for outbound task dispatch and callbacks."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JsonType, TenantMixin, TimestampMixin, generate_uuid


class WcsTaskBindingStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class WcsTaskBinding(Base, TimestampMixin, TenantMixin):
    """Maps one internal WMS task to one WCS transport task."""

    __tablename__ = "wcs_task_bindings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "task_id", name="uq_wcs_binding_tenant_task"),
        UniqueConstraint("tenant_id", "wcs_task_id", name="uq_wcs_binding_tenant_wcs_task"),
        Index("ix_wcs_bindings_tenant_status", "tenant_id", "status"),
        Index("ix_wcs_bindings_tenant_psn", "tenant_id", "task_psn"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False)
    warehouse_id: Mapped[str] = mapped_column(String(36), ForeignKey("warehouses.id"), nullable=False)

    wcs_task_id: Mapped[str | None] = mapped_column(String(80), index=True)
    wcs_step_id: Mapped[str | None] = mapped_column(String(80), index=True)
    task_psn: Mapped[str | None] = mapped_column(String(120), index=True)
    agv_unit_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24), default=WcsTaskBindingStatus.CREATED.value)

    start_pos: Mapped[str] = mapped_column(String(120), nullable=False)
    end_pos: Mapped[str] = mapped_column(String(120), nullable=False)
    task_type: Mapped[str | None] = mapped_column(String(80))
    last_step_status: Mapped[int | None] = mapped_column()
    last_step_status_name: Mapped[str | None] = mapped_column(String(80))
    last_callback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)

    request_payload: Mapped[dict | None] = mapped_column(JsonType)
    response_payload: Mapped[dict | None] = mapped_column(JsonType)
    last_callback_payload: Mapped[dict | None] = mapped_column(JsonType)


__all__ = ["WcsTaskBinding", "WcsTaskBindingStatus"]
