"""Mail2Task intake, internal task queue, and outbound approval gates."""

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import (
    get_mailtask_ingest_context,
    require_permission,
)
from app.core.security import TokenPayload, UserPermission
from app.models.agent_evidence import AgentEvidence
from app.models.mail_task import (
    MailAttachment,
    MailMessage,
    MailTask,
    MailTaskApproval,
    MailTaskApprovalStatus,
    MailTaskDirection,
    MailTaskGroup,
    MailTaskRecordType,
    MailTaskStatus,
    PhysicalExecutionStatus,
)
from app.services.agent_evidence_service import AgentEvidenceService
from app.services.idempotency_service import IdempotencyService

router = APIRouter()


class CanonicalModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")


class EmailRecordPayload(CanonicalModel):
    source_message_key: str = Field(min_length=1, max_length=255, alias="SourceMessageKey")
    mailbox: str = Field(min_length=1, max_length=254, alias="Mailbox")
    folder: str = Field(default="INBOX", max_length=120, alias="Folder")
    received_at: datetime = Field(alias="ReceivedAt")
    sender: str = Field(min_length=1, max_length=512, alias="Sender")
    subject: str = Field(default="", max_length=1000, alias="Subject")
    thread_id: str | None = Field(default=None, max_length=255, alias="ThreadID")
    recipients: list[str] | None = Field(default=None, alias="Recipients")
    cc: list[str] | None = Field(default=None, alias="Cc")
    source_summary: str | None = Field(default=None, alias="SourceSummary")
    body_text: str | None = Field(default=None, alias="BodyText")
    body_hash: str | None = Field(default=None, min_length=64, max_length=64, alias="BodyHash")
    decision: str = Field(default="Accepted", max_length=24, alias="Decision")
    classification: str | None = Field(default=None, max_length=80, alias="Classification")
    attachment_names: list[str] = Field(default_factory=list, alias="AttachmentNames")
    attachment_read_status: str | None = Field(default=None, alias="AttachmentReadStatus")
    reader_run_id: str | None = Field(default=None, max_length=128, alias="ReaderRunID")
    dedup_status: str | None = Field(default=None, alias="DedupStatus")
    filter_decision: str | None = Field(default=None, alias="FilterDecision")


class MailAttachmentPayload(CanonicalModel):
    attachment_name: str = Field(min_length=1, max_length=512, alias="AttachmentName")
    task_key: str | None = Field(default=None, max_length=180, alias="TaskKey")
    content_type: str | None = Field(default=None, max_length=160, alias="ContentType")
    size_bytes: int | None = Field(default=None, ge=0, alias="SizeBytes")
    sha256: str = Field(min_length=64, max_length=64, alias="SHA256")
    storage_uri: str | None = Field(default=None, max_length=1000, alias="StorageURI")
    read_status: str | None = Field(default=None, max_length=40, alias="ReadStatus")
    source_evidence: dict | list | str | None = Field(default=None, alias="SourceEvidence")


class MailTaskPayload(CanonicalModel):
    task_key: str = Field(min_length=1, max_length=180, alias="TaskKey")
    business_task_key: str | None = Field(
        default=None, max_length=180, alias="BusinessTaskKey"
    )
    source_message_key: str = Field(min_length=1, max_length=255, alias="SourceMessageKey")
    thread_id: str | None = Field(default=None, max_length=255, alias="ThreadID")
    source_document_id: str = Field(default="message", max_length=180, alias="SourceDocumentID")
    source_attachment: str | None = Field(default=None, max_length=512, alias="SourceAttachment")
    source_evidence: dict | list | str = Field(alias="SourceEvidence")

    record_type: MailTaskRecordType = Field(alias="RecordType")
    direction: MailTaskDirection = Field(alias="Direction")
    title: str | None = Field(default=None, max_length=500, alias="Title")
    customer_owner: str | None = Field(default=None, max_length=255, alias="CustomerOwner")
    supplier_or_origin_party: str | None = Field(
        default=None, max_length=255, alias="SupplierOrOriginParty"
    )
    external_reference: str | None = Field(default=None, max_length=255, alias="ExternalReference")
    po: str | None = Field(default=None, max_length=120, alias="PO")
    dn: str | None = Field(default=None, max_length=120, alias="DN")
    group_number: str | None = Field(default=None, max_length=120, alias="GroupNumber")
    load_id: str | None = Field(default=None, max_length=120, alias="LoadID")
    container_or_tracking: str | None = Field(
        default=None, max_length=180, alias="ContainerOrTracking"
    )
    mawb: str | None = Field(default=None, max_length=120, alias="MAWB")
    hawb: str | None = Field(default=None, max_length=120, alias="HAWB")
    bol_number: str | None = Field(default=None, max_length=120, alias="BOLNumber")
    do_number: str | None = Field(default=None, max_length=120, alias="DONumber")

    sku_or_item: str | None = Field(default=None, max_length=255, alias="SKUOrItem")
    description: str | None = Field(default=None, alias="Description")
    package_quantity: Decimal | None = Field(default=None, alias="PackageQuantity")
    package_unit: str | None = Field(default=None, max_length=40, alias="PackageUnit")
    product_quantity: Decimal | None = Field(default=None, alias="ProductQuantity")
    product_unit: str | None = Field(default=None, max_length=40, alias="ProductUnit")
    weight: Decimal | None = Field(default=None, alias="Weight")
    origin: str | None = Field(default=None, max_length=255, alias="Origin")
    destination: str | None = Field(default=None, max_length=255, alias="Destination")
    origin_dock: str | None = Field(default=None, max_length=120, alias="OriginDock")
    destination_dock: str | None = Field(default=None, max_length=120, alias="DestinationDock")
    carrier: str | None = Field(default=None, max_length=255, alias="Carrier")
    transport_mode: str | None = Field(default=None, max_length=80, alias="TransportMode")
    pickup_appointment: datetime | None = Field(default=None, alias="PickupAppointment")
    delivery_appointment: datetime | None = Field(default=None, alias="DeliveryAppointment")
    original_plan_date: datetime | None = Field(default=None, alias="OriginalPlanDate")
    proposed_plan_date: datetime | None = Field(default=None, alias="ProposedPlanDate")
    actual_pickup_at: datetime | None = Field(default=None, alias="ActualPickupAt")
    actual_delivery_at: datetime | None = Field(default=None, alias="ActualDeliveryAt")

    task_status: MailTaskStatus = Field(
        default=MailTaskStatus.NEEDS_MAGGIE_PROCESSING, alias="TaskStatus"
    )
    next_action: str | None = Field(default=None, alias="NextAction")
    source_party: str | None = Field(default=None, max_length=255, alias="SourceParty")
    external_contact_mode: str | None = Field(
        default=None, max_length=40, alias="ExternalContactMode"
    )
    intake_owner: str | None = Field(default=None, max_length=180, alias="IntakeOwner")
    task_owner: str | None = Field(default=None, max_length=180, alias="TaskOwner")
    delegated_by: str | None = Field(default=None, max_length=180, alias="DelegatedBy")
    delegated_at: datetime | None = Field(default=None, alias="DelegatedAt")
    customer_action_owner: str | None = Field(
        default=None, max_length=180, alias="CustomerActionOwner"
    )
    warehouse_owner: str | None = Field(default=None, max_length=180, alias="WarehouseOwner")
    receiving_owner: str | None = Field(default=None, max_length=180, alias="ReceivingOwner")
    shipping_owner: str | None = Field(default=None, max_length=180, alias="ShippingOwner")
    physical_execution_owner: str | None = Field(
        default=None, max_length=180, alias="PhysicalExecutionOwner"
    )
    physical_execution_status: PhysicalExecutionStatus = Field(
        default=PhysicalExecutionStatus.NOT_ASSIGNED, alias="PhysicalExecutionStatus"
    )
    physical_execution_at: datetime | None = Field(default=None, alias="PhysicalExecutionAt")
    physical_execution_evidence: dict | list | str | None = Field(
        default=None, alias="PhysicalExecutionEvidence"
    )
    logistics_owner: str | None = Field(default=None, max_length=180, alias="LogisticsOwner")
    cio_owner: str | None = Field(default=None, max_length=180, alias="CIOOwner")
    due_at: datetime | None = Field(default=None, alias="DueAt")

    wms_system: str | None = Field(default=None, max_length=40, alias="WMSSystem")
    wms_doc_no: str | None = Field(default=None, max_length=180, alias="WMSDocNo")
    wms_order_id: str | None = Field(default=None, max_length=120, alias="WMSOrderID")
    wms_match_status: str | None = Field(default=None, max_length=40, alias="WMSMatchStatus")
    wms_current_status: str | None = Field(default=None, max_length=80, alias="WMSCurrentStatus")
    wms_match_method: str | None = Field(default=None, max_length=80, alias="WMSMatchMethod")
    wms_match_confidence: Decimal | None = Field(default=None, alias="WMSMatchConfidence")

    approval_required: bool = Field(default=False, alias="ApprovalRequired")
    approval_type: str | None = Field(default=None, max_length=80, alias="ApprovalType")
    approval_status: str | None = Field(default=None, max_length=24, alias="ApprovalStatus")
    approved_by: str | None = Field(default=None, max_length=180, alias="ApprovedBy")
    approved_at: datetime | None = Field(default=None, alias="ApprovedAt")
    approval_evidence: dict | list | str | None = Field(default=None, alias="ApprovalEvidence")
    exception_flag: bool = Field(default=False, alias="ExceptionFlag")
    exception_description: str | None = Field(default=None, alias="ExceptionDescription")
    last_updated_by: str | None = Field(default=None, max_length=180, alias="LastUpdatedBy")


class MailTaskIntakeRequest(CanonicalModel):
    email: EmailRecordPayload = Field(alias="EmailRecord")
    tasks: list[MailTaskPayload] = Field(default_factory=list, alias="TaskRecords")
    attachments: list[MailAttachmentPayload] = Field(default_factory=list, alias="Attachments")


class MailTaskSummary(BaseModel):
    id: str
    task_key: str
    business_task_key: str
    source_message_key: str
    subject: str
    title: str | None
    next_action: str | None
    external_reference: str | None
    record_type: str
    direction: str
    task_status: str
    task_owner: str | None
    physical_execution_owner: str | None
    approval_status: str
    exception_flag: bool
    wms_system: str | None
    wms_doc_no: str | None
    linked_message_count: int
    latest_message_subject: str
    latest_message_at: datetime | None
    latest_source_message_key: str | None


class MailTaskMessageSummary(BaseModel):
    source_message_key: str
    subject: str
    sender: str
    received_at: datetime
    thread_id: str | None
    decision: str
    attachment_names: list[str] | None
    attachment_read_status: str | None


class MailTaskDetail(MailTaskSummary):
    messages: list[MailTaskMessageSummary]


class MailTaskIntakeResponse(BaseModel):
    source_message_key: str
    message_id: str
    decision: str
    created_tasks: int
    updated_tasks: int
    unchanged_tasks: int
    attachment_count: int
    tasks: list[MailTaskSummary]


class MailTaskStatusRequest(BaseModel):
    task_status: MailTaskStatus = Field(alias="TaskStatus")
    note: str | None = Field(default=None, alias="Note")

    model_config = ConfigDict(populate_by_name=True)


class OutboundApprovalRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = None
    evidence: dict | list | str | None = None


_TASK_COLUMNS = {
    column.name
    for column in MailTask.__table__.columns
    if column.name
    not in {
        "id",
        "tenant_id",
        "task_key",
        "mail_message_id",
        "source_message_key",
        "created_at",
        "updated_at",
    }
}


_STATUS_TRANSITIONS: dict[MailTaskStatus, set[MailTaskStatus]] = {
    MailTaskStatus.NEW: {
        MailTaskStatus.EXTRACTED,
        MailTaskStatus.NEEDS_MAGGIE_PROCESSING,
        MailTaskStatus.NEEDS_REVIEW,
        MailTaskStatus.BLOCKED,
        MailTaskStatus.EXCLUDED,
    },
    MailTaskStatus.EXTRACTED: {
        MailTaskStatus.NEEDS_MAGGIE_PROCESSING,
        MailTaskStatus.NEEDS_SUNNY_REVIEW,
        MailTaskStatus.NEEDS_FIELD_COMPLETION,
        MailTaskStatus.NEEDS_REVIEW,
        MailTaskStatus.BLOCKED,
    },
    MailTaskStatus.NEEDS_MAGGIE_PROCESSING: {
        MailTaskStatus.NEEDS_SUNNY_REVIEW,
        MailTaskStatus.NEEDS_FIELD_COMPLETION,
        MailTaskStatus.NEEDS_CUSTOMER_CONFIRMATION,
        MailTaskStatus.READY_FOR_WMS,
        MailTaskStatus.NEEDS_REVIEW,
        MailTaskStatus.BLOCKED,
    },
    MailTaskStatus.NEEDS_SUNNY_REVIEW: {
        MailTaskStatus.AWAITING_SUNNY_APPROVAL,
        MailTaskStatus.NEEDS_MAGGIE_PROCESSING,
        MailTaskStatus.NEEDS_REVIEW,
        MailTaskStatus.BLOCKED,
    },
    MailTaskStatus.AWAITING_SUNNY_APPROVAL: {
        MailTaskStatus.READY_FOR_WMS,
        MailTaskStatus.NEEDS_REVIEW,
        MailTaskStatus.BLOCKED,
    },
    MailTaskStatus.NEEDS_CUSTOMER_CONFIRMATION: {
        MailTaskStatus.NEEDS_MAGGIE_PROCESSING,
        MailTaskStatus.NEEDS_REVIEW,
        MailTaskStatus.BLOCKED,
    },
    MailTaskStatus.NEEDS_FIELD_COMPLETION: {
        MailTaskStatus.NEEDS_MAGGIE_PROCESSING,
        MailTaskStatus.NEEDS_REVIEW,
        MailTaskStatus.BLOCKED,
    },
    MailTaskStatus.READY_FOR_WMS: {MailTaskStatus.WMS_IN_PROGRESS, MailTaskStatus.BLOCKED},
    MailTaskStatus.WMS_IN_PROGRESS: {
        MailTaskStatus.EXECUTED,
        MailTaskStatus.NEEDS_REVIEW,
        MailTaskStatus.BLOCKED,
    },
    MailTaskStatus.EXECUTED: {
        MailTaskStatus.AWAITING_POD,
        MailTaskStatus.CLOSED,
        MailTaskStatus.NEEDS_REVIEW,
    },
    MailTaskStatus.AWAITING_POD: {MailTaskStatus.CLOSED, MailTaskStatus.NEEDS_REVIEW},
    MailTaskStatus.NEEDS_REVIEW: {
        MailTaskStatus.NEEDS_MAGGIE_PROCESSING,
        MailTaskStatus.BLOCKED,
        MailTaskStatus.EXCLUDED,
    },
    MailTaskStatus.BLOCKED: {
        MailTaskStatus.NEEDS_MAGGIE_PROCESSING,
        MailTaskStatus.NEEDS_REVIEW,
        MailTaskStatus.EXCLUDED,
    },
    MailTaskStatus.CLOSED: set(),
    MailTaskStatus.EXCLUDED: set(),
}


def _tenant_id(current_user: TokenPayload) -> str:
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="A tenant scope is required")
    return current_user.tenant_id


def _normalized_status(payload: MailTaskPayload) -> MailTaskStatus:
    if payload.task_status in {MailTaskStatus.NEW, MailTaskStatus.EXTRACTED}:
        return MailTaskStatus.NEEDS_MAGGIE_PROCESSING
    return payload.task_status


def _group_key(payload: MailTaskPayload) -> str:
    """Return the stable business identity supplied/derived by Mail2Task."""
    if payload.business_task_key:
        raw_key = payload.business_task_key.strip()
        return raw_key
    reference = next(
        (
            value.strip()
            for value in (
                payload.external_reference,
                payload.bol_number,
                payload.do_number,
                payload.container_or_tracking,
                payload.load_id,
                payload.po,
                payload.dn,
            )
            if value and value.strip()
        ),
        None,
    )
    if reference:
        raw_key = f"{payload.direction.value}:{reference}"
    elif payload.thread_id:
        raw_key = f"{payload.direction.value}:thread:{payload.thread_id}"
    else:
        # No reference means we must not merge messages on subject text alone.
        raw_key = f"{payload.direction.value}:message:{payload.source_message_key}"
    if len(raw_key) <= 180:
        return raw_key
    # Keep the DB key bounded while preserving deterministic identity.
    return f"{raw_key[:145]}:{sha256(raw_key.encode()).hexdigest()[:34]}"


def _group_summary(
    group: MailTaskGroup,
    *,
    source_message_key: str,
    subject: str,
    linked_message_count: int,
    latest_message_at: datetime | None,
) -> MailTaskSummary:
    return MailTaskSummary(
        id=group.id,
        task_key=group.task_group_key,
        business_task_key=group.task_group_key,
        source_message_key=source_message_key,
        subject=subject,
        title=group.title,
        next_action=group.next_action,
        external_reference=group.external_reference,
        record_type=group.record_type,
        direction=group.direction,
        task_status=group.task_status,
        task_owner=group.task_owner,
        physical_execution_owner=group.physical_execution_owner,
        approval_status=group.approval_status,
        exception_flag=group.exception_flag,
        wms_system=group.wms_system,
        wms_doc_no=group.wms_doc_no,
        linked_message_count=linked_message_count,
        latest_message_subject=subject,
        latest_message_at=latest_message_at,
        latest_source_message_key=source_message_key,
    )


async def _load_group_summary(db: AsyncSession, group: MailTaskGroup) -> MailTaskSummary:
    linked_message_count = int(
        await db.scalar(
            select(func.count(MailTask.id)).where(
                MailTask.tenant_id == group.tenant_id,
                MailTask.business_task_id == group.id,
            )
        )
        or 0
    )
    latest = await db.execute(
        select(MailMessage.source_message_key, MailMessage.subject, MailMessage.received_at)
        .join(MailTask, MailTask.mail_message_id == MailMessage.id)
        .where(
            MailTask.tenant_id == group.tenant_id,
            MailTask.business_task_id == group.id,
        )
        .order_by(MailMessage.received_at.desc(), MailMessage.created_at.desc())
        .limit(1)
    )
    latest_row = latest.first()
    return _group_summary(
        group,
        source_message_key=(latest_row.source_message_key if latest_row else ""),
        subject=(latest_row.subject if latest_row else group.title or group.task_group_key),
        linked_message_count=linked_message_count,
        latest_message_at=(latest_row.received_at if latest_row else group.latest_message_at),
    )


async def _load_group_detail(db: AsyncSession, group: MailTaskGroup) -> MailTaskDetail:
    summary = await _load_group_summary(db, group)
    rows = await db.execute(
        select(MailMessage)
        .join(MailTask, MailTask.mail_message_id == MailMessage.id)
        .where(
            MailTask.tenant_id == group.tenant_id,
            MailTask.business_task_id == group.id,
        )
        .order_by(MailMessage.received_at.desc(), MailMessage.created_at.desc())
    )
    return MailTaskDetail(
        **summary.model_dump(),
        messages=[
            MailTaskMessageSummary(
                source_message_key=message.source_message_key,
                subject=message.subject,
                sender=message.sender,
                received_at=message.received_at,
                thread_id=message.thread_id,
                decision=message.decision,
                attachment_names=message.attachment_names,
                attachment_read_status=message.attachment_read_status,
            )
            for message in rows.scalars()
        ],
    )


async def _upsert_message(
    db: AsyncSession,
    tenant_id: str,
    email: EmailRecordPayload,
) -> tuple[MailMessage, bool]:
    message = await db.scalar(
        select(MailMessage).where(
            MailMessage.tenant_id == tenant_id,
            MailMessage.source_message_key == email.source_message_key,
        )
    )
    values = email.model_dump(exclude_none=True)
    values["source_payload"] = jsonable_encoder(email.model_dump(by_alias=True, exclude_none=True))
    if message is None:
        message = MailMessage(tenant_id=tenant_id, **values)
        db.add(message)
        await db.flush()
        return message, True

    for field_name, value in values.items():
        if field_name not in {"source_message_key"}:
            setattr(message, field_name, value)
    await db.flush()
    return message, False


async def _upsert_group(
    db: AsyncSession,
    tenant_id: str,
    message: MailMessage,
    payload: MailTaskPayload,
    actor_user_id: str,
) -> tuple[MailTaskGroup, bool]:
    group_key = _group_key(payload)
    group = await db.scalar(
        select(MailTaskGroup).where(
            MailTaskGroup.tenant_id == tenant_id,
            MailTaskGroup.task_group_key == group_key,
        )
    )
    status_value = _normalized_status(payload).value
    approval_required = payload.direction == MailTaskDirection.OUTBOUND or payload.approval_required
    approval_status = (
        MailTaskApprovalStatus.PENDING.value
        if approval_required
        else MailTaskApprovalStatus.NOT_REQUIRED.value
    )
    canonical_payload = jsonable_encoder(payload.model_dump(by_alias=True, exclude_none=True))
    if group is None:
        group = MailTaskGroup(
            tenant_id=tenant_id,
            task_group_key=group_key,
            title=payload.title,
            record_type=payload.record_type.value,
            direction=payload.direction.value,
            external_reference=payload.external_reference
            or payload.bol_number
            or payload.do_number
            or payload.container_or_tracking,
            next_action=payload.next_action,
            task_status=status_value,
            task_owner=payload.task_owner or "Maggie",
            intake_owner=payload.intake_owner or "Sunny",
            physical_execution_owner=payload.physical_execution_owner
            or ("Mark" if payload.record_type in {MailTaskRecordType.IB, MailTaskRecordType.OB} else None),
            physical_execution_status=payload.physical_execution_status.value,
            wms_system=payload.wms_system,
            wms_doc_no=payload.wms_doc_no,
            wms_order_id=payload.wms_order_id,
            wms_match_status=payload.wms_match_status,
            wms_current_status=payload.wms_current_status,
            wms_match_method=payload.wms_match_method,
            wms_match_confidence=payload.wms_match_confidence,
            approval_required=approval_required,
            approval_type=payload.approval_type,
            approval_status=approval_status,
            approved_by=payload.approved_by,
            approved_at=payload.approved_at,
            approval_evidence=jsonable_encoder(payload.approval_evidence)
            if payload.approval_evidence is not None
            else None,
            exception_flag=payload.exception_flag,
            exception_description=payload.exception_description,
            latest_mail_message_id=message.id,
            latest_message_at=message.received_at,
            last_updated_by=actor_user_id,
            canonical_payload=canonical_payload,
        )
        db.add(group)
        await db.flush()
        return group, True

    if group.record_type != payload.record_type.value or group.direction != payload.direction.value:
        group.exception_flag = True
        group.exception_description = (
            "Different emails were matched to this business task with conflicting record type "
            "or direction; manual review required"
        )

    if group.task_status in {MailTaskStatus.CLOSED.value, MailTaskStatus.EXCLUDED.value}:
        group.exception_flag = True
        group.exception_description = (
            "A new source update was received for a closed/excluded business task; manual review required"
        )
    else:
        for field_name, value in {
            "title": payload.title,
            "external_reference": payload.external_reference
            or payload.bol_number
            or payload.do_number
            or payload.container_or_tracking,
            "next_action": payload.next_action,
        }.items():
            if value:
                setattr(group, field_name, value)
        if approval_required:
            group.approval_required = True
            if group.approval_status == MailTaskApprovalStatus.NOT_REQUIRED.value:
                group.approval_status = MailTaskApprovalStatus.PENDING.value
        for field_name, value in {
            "wms_system": payload.wms_system,
            "wms_doc_no": payload.wms_doc_no,
            "wms_order_id": payload.wms_order_id,
            "wms_match_status": payload.wms_match_status,
            "wms_current_status": payload.wms_current_status,
            "wms_match_method": payload.wms_match_method,
            "wms_match_confidence": payload.wms_match_confidence,
        }.items():
            if value is not None:
                setattr(group, field_name, value)

    received_at = message.received_at.replace(tzinfo=None)
    latest_message_at = (
        group.latest_message_at.replace(tzinfo=None) if group.latest_message_at else None
    )
    if latest_message_at is None or received_at >= latest_message_at:
        group.latest_mail_message_id = message.id
        group.latest_message_at = message.received_at
    group.last_updated_by = actor_user_id
    group.canonical_payload = canonical_payload
    await db.flush()
    return group, False


def _sync_task_from_group(task: MailTask, group: MailTaskGroup) -> None:
    """Keep the legacy per-message projection aligned with the group authority."""
    task.business_task_id = group.id
    task.task_status = group.task_status
    task.task_owner = group.task_owner
    task.intake_owner = group.intake_owner
    task.physical_execution_owner = group.physical_execution_owner
    task.physical_execution_status = group.physical_execution_status
    task.wms_system = group.wms_system
    task.wms_doc_no = group.wms_doc_no
    task.wms_order_id = group.wms_order_id
    task.wms_match_status = group.wms_match_status
    task.wms_current_status = group.wms_current_status
    task.wms_match_method = group.wms_match_method
    task.wms_match_confidence = group.wms_match_confidence
    task.approval_required = group.approval_required
    task.approval_type = group.approval_type
    task.approval_status = group.approval_status
    task.approved_by = group.approved_by
    task.approved_at = group.approved_at
    task.approval_evidence = group.approval_evidence
    task.exception_flag = task.exception_flag or group.exception_flag
    if group.exception_description:
        task.exception_description = group.exception_description
    task.last_updated_by = group.last_updated_by


async def _upsert_task(
    db: AsyncSession,
    tenant_id: str,
    message: MailMessage,
    payload: MailTaskPayload,
    actor_user_id: str,
) -> tuple[MailTask, bool, bool]:
    if payload.source_message_key != message.source_message_key:
        raise HTTPException(
            status_code=422,
            detail=f"Task {payload.task_key} does not belong to the submitted source message",
        )
    task = await db.scalar(
        select(MailTask).where(
            MailTask.tenant_id == tenant_id,
            MailTask.task_key == payload.task_key,
        )
    )
    if task and (
        task.source_message_key != payload.source_message_key
        or task.source_document_id != payload.source_document_id
    ):
        raise HTTPException(
            status_code=409,
            detail=f"TaskKey {payload.task_key} is already bound to another source document",
        )

    group, _group_created = await _upsert_group(
        db, tenant_id, message, payload, actor_user_id
    )
    if task is not None and task.business_task_id and task.business_task_id != group.id:
        raise HTTPException(
            status_code=409,
            detail=f"TaskKey {payload.task_key} is already bound to another business task",
        )

    status_value = group.task_status
    approval_required = group.approval_required
    approval_status = group.approval_status
    canonical_payload = jsonable_encoder(payload.model_dump(by_alias=True, exclude_none=True))

    if task is None:
        task = MailTask(
            tenant_id=tenant_id,
            task_key=payload.task_key,
            business_task_id=group.id,
            mail_message_id=message.id,
            source_message_key=payload.source_message_key,
            source_document_id=payload.source_document_id,
            record_type=payload.record_type.value,
            direction=payload.direction.value,
            task_status=status_value,
            physical_execution_status=group.physical_execution_status,
            approval_required=approval_required,
            approval_status=approval_status,
            canonical_payload=canonical_payload,
            last_updated_by=actor_user_id,
        )
        db.add(task)
        await db.flush()
        created = True
        unchanged = False
    else:
        created = False
        unchanged = task.canonical_payload == canonical_payload
        if group.task_status in {MailTaskStatus.CLOSED.value, MailTaskStatus.EXCLUDED.value}:
            if not unchanged:
                task.exception_flag = True
                task.exception_description = "A new source update was received for a closed/excluded business task; manual review required"
                task.last_updated_by = actor_user_id
                task.canonical_payload = canonical_payload
                task.business_task_id = group.id
            return task, created, unchanged

    task_values = payload.model_dump(exclude_none=True)
    task_values["record_type"] = payload.record_type.value
    task_values["direction"] = payload.direction.value
    task_values["task_status"] = status_value
    task_values["physical_execution_status"] = payload.physical_execution_status.value
    task_values["approval_required"] = approval_required
    task_values["approval_status"] = approval_status
    task_values["canonical_payload"] = canonical_payload
    task_values["last_updated_by"] = actor_user_id
    task_values.pop("task_key", None)
    task_values.pop("source_message_key", None)
    task_values.pop("source_document_id", None)
    task.source_evidence = jsonable_encoder(payload.source_evidence)
    task.thread_id = payload.thread_id
    task.source_attachment = payload.source_attachment
    task_values.pop("source_evidence", None)
    task_values.pop("thread_id", None)
    task_values.pop("source_attachment", None)
    task_values.pop("business_task_key", None)
    if not created:
        for field_name in {
            "task_status",
            "physical_execution_status",
            "approval_required",
            "approval_status",
            "approved_by",
            "approved_at",
            "approval_evidence",
            "wms_system",
            "wms_doc_no",
            "wms_order_id",
            "wms_match_status",
            "wms_current_status",
            "wms_match_method",
            "wms_match_confidence",
        }:
            task_values.pop(field_name, None)
    task_values = {key: value for key, value in task_values.items() if key in _TASK_COLUMNS}
    for field_name, value in task_values.items():
        setattr(task, field_name, value)

    if not task.task_owner:
        task.task_owner = "Maggie"
    if not task.intake_owner:
        task.intake_owner = "Sunny"
    if not task.physical_execution_owner and payload.record_type in {
        MailTaskRecordType.IB,
        MailTaskRecordType.OB,
    }:
        task.physical_execution_owner = "Mark"
    _sync_task_from_group(task, group)
    await db.flush()
    return task, created, unchanged


async def _record_agent_evidence(
    db: AsyncSession,
    tenant_id: str,
    task: MailTask,
    payload: MailTaskPayload,
    actor_user_id: str,
) -> AgentEvidence:
    token = AgentEvidenceService.issue_token("mailtask-intake")
    service = AgentEvidenceService(db, tenant_id)
    evidence = await service.persist_preview(
        action="mailtask.intake",
        risk="low",
        required_permission=UserPermission.MAILTASK_EXECUTE.value,
        entity_type="mail_task",
        entity_id=task.id,
        actor_user_id=actor_user_id,
        payload_hash=service.payload_hash(payload.model_dump(by_alias=True, exclude_none=True)),
        confirmation_token=token,
        planned_endpoint="POST /api/v1/mailtasks/intake",
        state_before=None,
        state_after={"task_status": task.task_status, "task_key": task.task_key},
        planned_request=jsonable_encoder(payload.model_dump(by_alias=True, exclude_none=True)),
        confirmation_payload={"source_message_key": payload.source_message_key},
        ttl_minutes=60 * 24 * 30,
    )
    await service.mark_executed(
        evidence,
        actor_user_id=actor_user_id,
        idempotency_key=None,
        state_after={"task_status": task.task_status, "task_key": task.task_key},
        result={"accepted": True, "task_key": task.task_key},
        success=True,
    )
    return evidence


async def _ingest(
    db: AsyncSession,
    tenant_id: str,
    body: MailTaskIntakeRequest,
    actor_user_id: str,
) -> dict[str, Any]:
    message, _message_created = await _upsert_message(db, tenant_id, body.email)
    tasks: list[MailTask] = []
    group_ids: list[str] = []
    created_tasks = 0
    updated_tasks = 0
    unchanged_tasks = 0

    for payload in body.tasks:
        task, created, unchanged = await _upsert_task(
            db, tenant_id, message, payload, actor_user_id
        )
        if created:
            created_tasks += 1
        elif unchanged:
            unchanged_tasks += 1
        else:
            updated_tasks += 1
        await _record_agent_evidence(db, tenant_id, task, payload, actor_user_id)
        tasks.append(task)
        if task.business_task_id and task.business_task_id not in group_ids:
            group_ids.append(task.business_task_id)

    attachment_count = 0
    for attachment in body.attachments:
        existing = await db.scalar(
            select(MailAttachment).where(
                MailAttachment.tenant_id == tenant_id,
                MailAttachment.mail_message_id == message.id,
                MailAttachment.attachment_name == attachment.attachment_name,
                MailAttachment.sha256 == attachment.sha256,
            )
        )
        if existing is None:
            values = attachment.model_dump(exclude_none=True)
            values["source_evidence"] = jsonable_encoder(
                attachment.model_dump(by_alias=True, exclude_none=True)
            )
            db.add(MailAttachment(tenant_id=tenant_id, mail_message_id=message.id, **values))
            attachment_count += 1
    await db.flush()
    groups = []
    for group_id in group_ids:
        group = await db.scalar(
            select(MailTaskGroup).where(
                MailTaskGroup.tenant_id == tenant_id,
                MailTaskGroup.id == group_id,
            )
        )
        if group is not None:
            groups.append(await _load_group_summary(db, group))

    return MailTaskIntakeResponse(
        source_message_key=body.email.source_message_key,
        message_id=message.id,
        decision=body.email.decision,
        created_tasks=created_tasks,
        updated_tasks=updated_tasks,
        unchanged_tasks=unchanged_tasks,
        attachment_count=attachment_count,
        tasks=groups,
    ).model_dump()


@router.post("/intake", response_model=MailTaskIntakeResponse)
async def ingest_mailtasks(
    body: MailTaskIntakeRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(get_mailtask_ingest_context),
    db: AsyncSession = Depends(get_db_session),
) -> MailTaskIntakeResponse:
    """Accept structured output from the read-only Agent mailbox Skill."""
    tenant_id = _tenant_id(current_user)
    result = await IdempotencyService(db, tenant_id).run(
        key=x_idempotency_key,
        operation="mailtasks.intake",
        request_payload=jsonable_encoder(body.model_dump(by_alias=True, exclude_none=True)),
        handler=lambda: _ingest(db, tenant_id, body, current_user.sub),
    )
    return MailTaskIntakeResponse.model_validate(result)


async def _resolve_group(
    db: AsyncSession, tenant_id: str, task_key: str
) -> MailTaskGroup | None:
    group = await db.scalar(
        select(MailTaskGroup).where(
            MailTaskGroup.tenant_id == tenant_id,
            MailTaskGroup.task_group_key == task_key,
        )
    )
    if group is not None:
        return group
    task = await db.scalar(
        select(MailTask).where(
            MailTask.tenant_id == tenant_id,
            MailTask.task_key == task_key,
        )
    )
    if task is None or task.business_task_id is None:
        return None
    return await db.scalar(
        select(MailTaskGroup).where(
            MailTaskGroup.tenant_id == tenant_id,
            MailTaskGroup.id == task.business_task_id,
        )
    )


async def _sync_group_children(db: AsyncSession, group: MailTaskGroup) -> None:
    children = await db.scalars(
        select(MailTask).where(
            MailTask.tenant_id == group.tenant_id,
            MailTask.business_task_id == group.id,
        )
    )
    for child in children:
        _sync_task_from_group(child, group)


@router.get("/", response_model=list[MailTaskSummary])
async def list_mailtasks(
    task_status: str | None = Query(default=None, alias="status"),
    direction: str | None = None,
    task_owner: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    current_user: TokenPayload = Depends(
        require_permission(
            UserPermission.MAILTASK_MANAGE.value,
            UserPermission.MAILTASK_EXECUTE.value,
        )
    ),
    db: AsyncSession = Depends(get_db_session),
) -> list[MailTaskSummary]:
    tenant_id = _tenant_id(current_user)
    # Direct function calls in regression tests do not pass FastAPI's resolved Query default.
    if not isinstance(limit, int):
        limit = 100
    if not isinstance(task_status, str):
        task_status = None
    if not isinstance(direction, str):
        direction = None
    if not isinstance(task_owner, str):
        task_owner = None
    query = select(MailTaskGroup).where(MailTaskGroup.tenant_id == tenant_id)
    if task_status:
        query = query.where(MailTaskGroup.task_status == task_status)
    if direction:
        query = query.where(MailTaskGroup.direction == direction)
    if task_owner:
        query = query.where(MailTaskGroup.task_owner == task_owner)
    groups = (
        await db.scalars(query.order_by(MailTaskGroup.updated_at.desc()).limit(limit))
    ).all()
    return [await _load_group_summary(db, group) for group in groups]


@router.get("/{task_key}", response_model=MailTaskDetail)
async def get_mailtask(
    task_key: str,
    current_user: TokenPayload = Depends(
        require_permission(
            UserPermission.MAILTASK_MANAGE.value,
            UserPermission.MAILTASK_EXECUTE.value,
        )
    ),
    db: AsyncSession = Depends(get_db_session),
) -> MailTaskDetail:
    tenant_id = _tenant_id(current_user)
    group = await _resolve_group(db, tenant_id, task_key)
    if group is None:
        raise HTTPException(status_code=404, detail="Business MailTask not found")
    return await _load_group_detail(db, group)


@router.patch("/{task_key}/status", response_model=MailTaskSummary)
async def update_mailtask_status(
    task_key: str,
    body: MailTaskStatusRequest,
    current_user: TokenPayload = Depends(require_permission(UserPermission.MAILTASK_EXECUTE.value)),
    db: AsyncSession = Depends(get_db_session),
) -> MailTaskSummary:
    tenant_id = _tenant_id(current_user)
    group = await _resolve_group(db, tenant_id, task_key)
    if group is None:
        raise HTTPException(status_code=404, detail="Business MailTask not found")
    next_status = body.task_status
    current_status = MailTaskStatus(group.task_status)
    if next_status == current_status:
        return await _load_group_summary(db, group)
    if next_status not in _STATUS_TRANSITIONS.get(current_status, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Invalid MailTask transition: {current_status.value} -> {next_status.value}",
        )
    if (
        next_status == MailTaskStatus.READY_FOR_WMS
        and group.direction == MailTaskDirection.OUTBOUND.value
        and group.approval_status != MailTaskApprovalStatus.APPROVED.value
    ):
        raise HTTPException(
            status_code=409,
            detail="Outbound task requires Sunny approval before it is ready for WMS",
        )
    group.task_status = next_status.value
    group.last_updated_by = current_user.sub
    if body.note:
        group.exception_description = body.note
    await _sync_group_children(db, group)
    await db.flush()
    return await _load_group_summary(db, group)


@router.post("/{task_key}/outbound-approval", response_model=MailTaskSummary)
async def decide_outbound_approval(
    task_key: str,
    body: OutboundApprovalRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.MAILTASK_APPROVE_OUTBOUND.value)
    ),
    db: AsyncSession = Depends(get_db_session),
) -> MailTaskSummary:
    tenant_id = _tenant_id(current_user)
    group = await _resolve_group(db, tenant_id, task_key)
    if group is None:
        raise HTTPException(status_code=404, detail="Business MailTask not found")
    if group.direction != MailTaskDirection.OUTBOUND.value:
        raise HTTPException(status_code=409, detail="Only outbound MailTasks require this approval")
    if group.task_status != MailTaskStatus.AWAITING_SUNNY_APPROVAL.value:
        raise HTTPException(
            status_code=409,
            detail="Outbound task must be Awaiting Sunny Approval before approval decision",
        )

    now = datetime.now(UTC)
    decision_status = (
        MailTaskApprovalStatus.APPROVED
        if body.decision == "approve"
        else MailTaskApprovalStatus.REJECTED
    )
    task = await db.scalar(
        select(MailTask)
        .where(
            MailTask.tenant_id == tenant_id,
            MailTask.business_task_id == group.id,
        )
        .order_by(MailTask.updated_at.desc())
    )
    if task is None:
        raise HTTPException(status_code=409, detail="Business MailTask has no email evidence")
    approval = MailTaskApproval(
        tenant_id=tenant_id,
        mail_task_id=task.id,
        business_task_id=group.id,
        approval_type="outbound_execution",
        status=decision_status.value,
        approver_user_id=current_user.sub,
        decision_note=body.note,
        evidence=jsonable_encoder(body.evidence),
        decided_at=now,
    )
    db.add(approval)
    group.approval_status = decision_status.value
    group.approved_by = current_user.sub if body.decision == "approve" else None
    group.approved_at = now if body.decision == "approve" else None
    group.approval_evidence = jsonable_encoder(body.evidence)
    group.task_status = (
        MailTaskStatus.READY_FOR_WMS.value
        if body.decision == "approve"
        else MailTaskStatus.NEEDS_REVIEW.value
    )
    group.last_updated_by = current_user.sub
    await _sync_group_children(db, group)
    await db.flush()
    return await _load_group_summary(db, group)
