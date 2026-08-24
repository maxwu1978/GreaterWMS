"""Mail2Task intake records and human-controlled warehouse task workflow."""

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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JsonType, TenantMixin, TimestampMixin, generate_uuid


class MailDecision(StrEnum):
    ACCEPTED = "Accepted"
    EXCLUDED = "Excluded"
    NEEDS_REVIEW = "Needs Review"


class MailTaskRecordType(StrEnum):
    IB = "IB"
    OB = "OB"
    TRANSFER = "TRANSFER"
    TRANSPORT = "TRANSPORT"
    EVIDENCE = "EVIDENCE"


class MailTaskDirection(StrEnum):
    INBOUND = "Inbound"
    OUTBOUND = "Outbound"
    TRANSFER = "Transfer"
    UNKNOWN = "Unknown"


class MailTaskStatus(StrEnum):
    NEW = "New"
    EXTRACTED = "Extracted"
    NEEDS_MAGGIE_PROCESSING = "Needs Maggie Processing"
    NEEDS_SUNNY_REVIEW = "Needs Sunny Review"
    AWAITING_SUNNY_APPROVAL = "Awaiting Sunny Approval"
    NEEDS_CUSTOMER_CONFIRMATION = "Needs Customer Confirmation"
    NEEDS_FIELD_COMPLETION = "Needs Field Completion"
    READY_FOR_WMS = "Ready for WMS"
    WMS_IN_PROGRESS = "WMS In Progress"
    EXECUTED = "Executed"
    AWAITING_POD = "Awaiting POD"
    CLOSED = "Closed"
    NEEDS_REVIEW = "Needs Review"
    BLOCKED = "Blocked"
    EXCLUDED = "Excluded"


class PhysicalExecutionStatus(StrEnum):
    NOT_ASSIGNED = "Not Assigned"
    SCHEDULED = "Scheduled"
    IN_PROGRESS = "In Progress"
    EXECUTED = "Executed"
    DISPUTED = "Disputed"
    CANCELLED = "Cancelled"


class MailTaskApprovalStatus(StrEnum):
    NOT_REQUIRED = "Not Required"
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class MailMessage(Base, TimestampMixin, TenantMixin):
    """Immutable mailbox identity plus safe, auditable source metadata."""

    __tablename__ = "mail_messages"
    __table_args__ = (
        Index("ix_mail_messages_tenant_received", "tenant_id", "received_at"),
        Index("ix_mail_messages_tenant_decision", "tenant_id", "decision"),
        UniqueConstraint("tenant_id", "source_message_key", name="uq_mail_messages_tenant_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_message_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=False)
    mailbox: Mapped[str] = mapped_column(String(254), nullable=False)
    folder: Mapped[str] = mapped_column(String(120), nullable=False, default="INBOX")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sender: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[str] = mapped_column(String(1000), nullable=False)
    thread_id: Mapped[str | None] = mapped_column(String(255))
    recipients: Mapped[list | None] = mapped_column(JsonType)
    cc: Mapped[list | None] = mapped_column(JsonType)
    source_summary: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    body_hash: Mapped[str | None] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(
        String(24), nullable=False, default=MailDecision.ACCEPTED.value
    )
    classification: Mapped[str | None] = mapped_column(String(80))
    attachment_names: Mapped[list | None] = mapped_column(JsonType)
    attachment_read_status: Mapped[str | None] = mapped_column(String(40))
    reader_run_id: Mapped[str | None] = mapped_column(String(128))
    dedup_status: Mapped[str | None] = mapped_column(String(40))
    filter_decision: Mapped[str | None] = mapped_column(String(80))
    source_payload: Mapped[dict | None] = mapped_column(JsonType)


class MailTask(Base, TimestampMixin, TenantMixin):
    """Canonical task projection created from one relevant source message."""

    __tablename__ = "mail_tasks"
    __table_args__ = (
        Index("ix_mail_tasks_tenant_status_owner", "tenant_id", "task_status", "task_owner"),
        Index("ix_mail_tasks_tenant_direction_status", "tenant_id", "direction", "task_status"),
        Index("ix_mail_tasks_tenant_source", "tenant_id", "source_message_key"),
        Index("ix_mail_tasks_tenant_wms_ref", "tenant_id", "wms_system", "wms_doc_no"),
        UniqueConstraint("tenant_id", "task_key", name="uq_mail_tasks_tenant_task_key"),
        UniqueConstraint(
            "tenant_id",
            "source_message_key",
            "source_document_id",
            name="uq_mail_tasks_tenant_source_document",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_key: Mapped[str] = mapped_column(String(180), nullable=False)
    mail_message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mail_messages.id"), nullable=False
    )
    source_message_key: Mapped[str] = mapped_column(String(255), nullable=False)
    thread_id: Mapped[str | None] = mapped_column(String(255))
    source_document_id: Mapped[str] = mapped_column(String(180), nullable=False, default="message")
    source_attachment: Mapped[str | None] = mapped_column(String(512))
    source_evidence: Mapped[dict | list | str | None] = mapped_column(JsonType)

    record_type: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    customer_owner: Mapped[str | None] = mapped_column(String(255))
    supplier_or_origin_party: Mapped[str | None] = mapped_column(String(255))
    external_reference: Mapped[str | None] = mapped_column(String(255))
    po: Mapped[str | None] = mapped_column(String(120))
    dn: Mapped[str | None] = mapped_column(String(120))
    group_number: Mapped[str | None] = mapped_column(String(120))
    load_id: Mapped[str | None] = mapped_column(String(120))
    container_or_tracking: Mapped[str | None] = mapped_column(String(180))
    mawb: Mapped[str | None] = mapped_column(String(120))
    hawb: Mapped[str | None] = mapped_column(String(120))
    bol_number: Mapped[str | None] = mapped_column(String(120))
    do_number: Mapped[str | None] = mapped_column(String(120))

    sku_or_item: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    package_quantity: Mapped[float | None] = mapped_column(Numeric(18, 4))
    package_unit: Mapped[str | None] = mapped_column(String(40))
    product_quantity: Mapped[float | None] = mapped_column(Numeric(18, 4))
    product_unit: Mapped[str | None] = mapped_column(String(40))
    weight: Mapped[float | None] = mapped_column(Numeric(18, 4))
    origin: Mapped[str | None] = mapped_column(String(255))
    destination: Mapped[str | None] = mapped_column(String(255))
    origin_dock: Mapped[str | None] = mapped_column(String(120))
    destination_dock: Mapped[str | None] = mapped_column(String(120))
    carrier: Mapped[str | None] = mapped_column(String(255))
    transport_mode: Mapped[str | None] = mapped_column(String(80))
    pickup_appointment: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_appointment: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    original_plan_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proposed_plan_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_pickup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default=MailTaskStatus.NEW.value
    )
    next_action: Mapped[str | None] = mapped_column(Text)
    source_party: Mapped[str | None] = mapped_column(String(255))
    external_contact_mode: Mapped[str | None] = mapped_column(String(40))
    intake_owner: Mapped[str | None] = mapped_column(String(180))
    task_owner: Mapped[str | None] = mapped_column(String(180))
    delegated_by: Mapped[str | None] = mapped_column(String(180))
    delegated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_action_owner: Mapped[str | None] = mapped_column(String(180))
    warehouse_owner: Mapped[str | None] = mapped_column(String(180))
    receiving_owner: Mapped[str | None] = mapped_column(String(180))
    shipping_owner: Mapped[str | None] = mapped_column(String(180))
    physical_execution_owner: Mapped[str | None] = mapped_column(String(180))
    physical_execution_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default=PhysicalExecutionStatus.NOT_ASSIGNED.value
    )
    physical_execution_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    physical_execution_evidence: Mapped[dict | list | str | None] = mapped_column(JsonType)
    logistics_owner: Mapped[str | None] = mapped_column(String(180))
    cio_owner: Mapped[str | None] = mapped_column(String(180))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    wms_system: Mapped[str | None] = mapped_column(String(40))
    wms_doc_no: Mapped[str | None] = mapped_column(String(180))
    wms_order_id: Mapped[str | None] = mapped_column(String(120))
    wms_match_status: Mapped[str | None] = mapped_column(String(40))
    wms_current_status: Mapped[str | None] = mapped_column(String(80))
    wms_match_method: Mapped[str | None] = mapped_column(String(80))
    wms_match_confidence: Mapped[float | None] = mapped_column(Numeric(6, 4))

    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_type: Mapped[str | None] = mapped_column(String(80))
    approval_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=MailTaskApprovalStatus.NOT_REQUIRED.value
    )
    approved_by: Mapped[str | None] = mapped_column(String(180))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_evidence: Mapped[dict | list | str | None] = mapped_column(JsonType)

    exception_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exception_description: Mapped[str | None] = mapped_column(Text)
    last_updated_by: Mapped[str | None] = mapped_column(String(180))
    canonical_payload: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)


class MailAttachment(Base, TimestampMixin, TenantMixin):
    """Attachment metadata and hash; binary storage remains outside the DB."""

    __tablename__ = "mail_attachments"
    __table_args__ = (
        Index("ix_mail_attachments_tenant_message", "tenant_id", "mail_message_id"),
        Index("ix_mail_attachments_tenant_sha256", "tenant_id", "sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    mail_message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mail_messages.id"), nullable=False
    )
    task_key: Mapped[str | None] = mapped_column(String(180))
    attachment_name: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(160))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_uri: Mapped[str | None] = mapped_column(String(1000))
    read_status: Mapped[str | None] = mapped_column(String(40))
    source_evidence: Mapped[dict | list | str | None] = mapped_column(JsonType)


class MailTaskApproval(Base, TimestampMixin, TenantMixin):
    """Independent approval audit record; approval is not a task boolean only."""

    __tablename__ = "mail_task_approvals"
    __table_args__ = (
        Index("ix_mail_task_approvals_tenant_task", "tenant_id", "mail_task_id"),
        Index("ix_mail_task_approvals_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    mail_task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mail_tasks.id"), nullable=False
    )
    approval_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    approver_user_id: Mapped[str] = mapped_column(String(180), nullable=False)
    decision_note: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict | list | str | None] = mapped_column(JsonType)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = [
    "MailAttachment",
    "MailDecision",
    "MailMessage",
    "MailTask",
    "MailTaskApproval",
    "MailTaskApprovalStatus",
    "MailTaskDirection",
    "MailTaskRecordType",
    "MailTaskStatus",
    "PhysicalExecutionStatus",
]
