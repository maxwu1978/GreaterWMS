"""Idempotency records for mutation endpoints."""

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JsonType, TenantMixin, TimestampMixin, generate_uuid


class IdempotencyRecord(Base, TimestampMixin, TenantMixin):
    """Cached response for one tenant-scoped idempotency key."""

    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_idempotency_tenant_key"),
        Index("ix_idempotency_tenant_operation", "tenant_id", "operation"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(160), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    response_status_code: Mapped[int | None] = mapped_column(Integer)
    response_json: Mapped[dict | list | None] = mapped_column(JsonType)
