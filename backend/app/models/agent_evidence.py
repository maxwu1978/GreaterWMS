"""Agent operation evidence for governed CLI writes."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JsonType, TenantMixin, TimestampMixin, generate_uuid


class AgentEvidence(Base, TimestampMixin, TenantMixin):
    """Persisted proof for agent previews and confirmed writes."""

    __tablename__ = "agent_evidence"
    __table_args__ = (
        UniqueConstraint("tenant_id", "confirmation_token_hash", name="uq_agent_evidence_token"),
        Index("ix_agent_evidence_tenant_action_status", "tenant_id", "action", "status"),
        Index("ix_agent_evidence_tenant_payload", "tenant_id", "payload_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    risk: Mapped[str] = mapped_column(String(20), nullable=False)
    required_permission: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="previewed")
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmation_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    planned_endpoint: Mapped[str] = mapped_column(String(260), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    state_before: Mapped[dict | None] = mapped_column(JsonType)
    state_after: Mapped[dict | None] = mapped_column(JsonType)
    planned_request: Mapped[dict | None] = mapped_column(JsonType)
    confirmation_payload: Mapped[dict | None] = mapped_column(JsonType)
    result: Mapped[dict | list | None] = mapped_column(JsonType)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
