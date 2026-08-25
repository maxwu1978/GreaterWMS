"""MailTask intake, deduplication, routing, and outbound approval regressions."""

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.mailtasks import (
    MailTaskIntakeRequest,
    MailTaskStatusRequest,
    OutboundApprovalRequest,
    decide_outbound_approval,
    ingest_mailtasks,
    list_mailtasks,
    update_mailtask_status,
)
from app.core.config import settings
from app.core.database import set_current_tenant_id
from app.core.deps import get_mailtask_ingest_context
from app.core.security import TokenPayload, UserPermission, UserRole
from app.models.agent_evidence import AgentEvidence
from app.models.mail_task import (
    MailAttachment,
    MailTask,
    MailTaskApproval,
    MailTaskGroup,
    MailTaskStatus,
)


def _user(
    tenant_id: str,
    user_id: str = "service-user",
    permissions: list[str] | None = None,
) -> TokenPayload:
    return TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.OPERATOR,
        permissions=permissions or [UserPermission.MAILTASK_EXECUTE.value],
        exp=datetime.now(UTC),
    )


def _outbound_payload(message_key: str = "mac-mail:msg-001") -> MailTaskIntakeRequest:
    task_key = f"{message_key}:BOL-001"
    return MailTaskIntakeRequest.model_validate(
        {
            "EmailRecord": {
                "SourceMessageKey": message_key,
                "Mailbox": "psreceiving@peaksmartlogistics.com",
                "Folder": "INBOX",
                "ReceivedAt": "2026-08-24T12:00:00Z",
                "Sender": "forwarder@example.com",
                "Subject": "OB shipment release",
                "ThreadID": "thread-001",
                "Decision": "Accepted",
                "Classification": "OB",
                "AttachmentNames": ["BOL-001.pdf"],
            },
            "TaskRecords": [
                {
                    "TaskKey": task_key,
                    "SourceMessageKey": message_key,
                    "SourceDocumentID": "BOL-001",
                    "SourceAttachment": "BOL-001.pdf",
                    "SourceEvidence": {"message": message_key, "attachment": "BOL-001.pdf"},
                    "RecordType": "OB",
                    "Direction": "Outbound",
                    "BOLNumber": "BOL-001",
                    "PackageQuantity": 4,
                    "PackageUnit": "PALLET",
                    "TaskStatus": "Extracted",
                    "NextAction": "Maggie complete WMS fields",
                }
            ],
            "Attachments": [
                {
                    "AttachmentName": "BOL-001.pdf",
                    "TaskKey": task_key,
                    "ContentType": "application/pdf",
                    "SizeBytes": 1024,
                    "SHA256": "a" * 64,
                    "ReadStatus": "Read",
                }
            ],
        }
    )


@pytest.mark.asyncio
async def test_mailtask_intake_is_deduplicated_and_keeps_source_evidence(
    db: AsyncSession, tenant_id: str
):
    set_current_tenant_id(tenant_id)
    current_user = _user(tenant_id, user_id="service:mailtask-skill")
    body = _outbound_payload()

    first = await ingest_mailtasks(
        body=body,
        x_idempotency_key="mailtask-intake-001",
        current_user=current_user,
        db=db,
    )
    second = await ingest_mailtasks(
        body=body,
        x_idempotency_key="mailtask-intake-001",
        current_user=current_user,
        db=db,
    )
    third = await ingest_mailtasks(
        body=body,
        x_idempotency_key="mailtask-intake-002",
        current_user=current_user,
        db=db,
    )

    assert first.created_tasks == 1
    assert first.attachment_count == 1
    assert second == first
    assert third.created_tasks == 0
    assert third.unchanged_tasks == 1
    assert await db.scalar(select(func.count()).select_from(MailTask)) == 1
    assert await db.scalar(select(func.count()).select_from(MailAttachment)) == 1
    assert await db.scalar(select(func.count()).select_from(AgentEvidence)) == 2

    task = await db.scalar(select(MailTask).where(MailTask.task_key == "mac-mail:msg-001:BOL-001"))
    assert task is not None
    assert task.task_status == MailTaskStatus.NEEDS_MAGGIE_PROCESSING.value
    assert task.task_owner == "Maggie"
    assert task.physical_execution_owner == "Mark"
    assert task.intake_owner == "Sunny"
    assert task.approval_status == "Pending"
    assert task.source_evidence == {"message": "mac-mail:msg-001", "attachment": "BOL-001.pdf"}


@pytest.mark.asyncio
async def test_mailtask_ingest_token_is_disabled_by_default_and_tenant_bound(monkeypatch):
    monkeypatch.setattr(settings, "MAILTASK_INGEST_ENABLED", False)
    monkeypatch.setattr(settings, "MAILTASK_INGEST_TOKEN", "")
    monkeypatch.setattr(settings, "MAILTASK_INGEST_TENANT_ID", "")
    with pytest.raises(HTTPException) as disabled:
        await get_mailtask_ingest_context(x_mailtask_token="staging-mailtask-token")
    assert disabled.value.status_code == 503

    monkeypatch.setattr(settings, "MAILTASK_INGEST_ENABLED", True)
    monkeypatch.setattr(settings, "MAILTASK_INGEST_TOKEN", "staging-mailtask-token")
    monkeypatch.setattr(settings, "MAILTASK_INGEST_TENANT_ID", "first-agv-tenant")

    with pytest.raises(HTTPException) as invalid:
        await get_mailtask_ingest_context(x_mailtask_token="wrong-token")
    assert invalid.value.status_code == 401

    context = await get_mailtask_ingest_context(x_mailtask_token="staging-mailtask-token")
    assert context.sub == "service:mailtask-skill"
    assert context.tenant_id == "first-agv-tenant"
    assert UserPermission.MAILTASK_EXECUTE.value in context.permissions


@pytest.mark.asyncio
async def test_related_emails_share_one_business_task_and_status_propagates(
    db: AsyncSession, tenant_id: str
):
    set_current_tenant_id(tenant_id)
    processor = _user(tenant_id, user_id="maggie")
    first_body = _outbound_payload("mac-mail:msg-101")
    first_body.tasks[0].business_task_key = "OB:DELTA-OUT-001"
    first_body.tasks[0].external_reference = "DELTA-OUT-001"
    second_body = _outbound_payload("mac-mail:msg-102")
    second_body.tasks[0].task_key = "mac-mail:msg-102:BOL-001-UPDATE"
    second_body.tasks[0].business_task_key = "OB:DELTA-OUT-001"
    second_body.tasks[0].external_reference = "DELTA-OUT-001"

    await ingest_mailtasks(
        body=first_body,
        x_idempotency_key="mailtask-group-001",
        current_user=_user(tenant_id, user_id="service:mailtask-skill"),
        db=db,
    )
    await ingest_mailtasks(
        body=second_body,
        x_idempotency_key="mailtask-group-002",
        current_user=_user(tenant_id, user_id="service:mailtask-skill"),
        db=db,
    )

    assert await db.scalar(select(func.count()).select_from(MailTaskGroup)) == 1
    assert await db.scalar(select(func.count()).select_from(MailTask)) == 2
    rows = await list_mailtasks(current_user=processor, db=db)
    assert len(rows) == 1
    assert rows[0].task_key == "OB:DELTA-OUT-001"
    assert rows[0].business_task_key == "OB:DELTA-OUT-001"
    assert rows[0].linked_message_count == 2

    updated = await update_mailtask_status(
        task_key="OB:DELTA-OUT-001",
        body=MailTaskStatusRequest(task_status=MailTaskStatus.NEEDS_SUNNY_REVIEW),
        current_user=processor,
        db=db,
    )
    assert updated.task_status == MailTaskStatus.NEEDS_SUNNY_REVIEW.value
    children = (await db.scalars(select(MailTask).order_by(MailTask.task_key))).all()
    assert [child.task_status for child in children] == [
        MailTaskStatus.NEEDS_SUNNY_REVIEW.value,
        MailTaskStatus.NEEDS_SUNNY_REVIEW.value,
    ]

    # Legacy child task keys still resolve to the same business-task authority.
    await update_mailtask_status(
        task_key="mac-mail:msg-102:BOL-001-UPDATE",
        body=MailTaskStatusRequest(task_status=MailTaskStatus.AWAITING_SUNNY_APPROVAL),
        current_user=processor,
        db=db,
    )
    group = await db.scalar(
        select(MailTaskGroup).where(MailTaskGroup.task_group_key == "OB:DELTA-OUT-001")
    )
    assert group is not None
    assert group.task_status == MailTaskStatus.AWAITING_SUNNY_APPROVAL.value


@pytest.mark.asyncio
async def test_outbound_task_requires_separate_sunny_approval_before_wms(
    db: AsyncSession, tenant_id: str
):
    set_current_tenant_id(tenant_id)
    processor = _user(tenant_id, user_id="maggie")
    sunny = _user(
        tenant_id,
        user_id="sunny",
        permissions=[UserPermission.MAILTASK_APPROVE_OUTBOUND.value],
    )
    body = _outbound_payload("mac-mail:msg-002")
    await ingest_mailtasks(
        body=body,
        x_idempotency_key="mailtask-intake-003",
        current_user=_user(tenant_id, user_id="service:mailtask-skill"),
        db=db,
    )

    task_key = "mac-mail:msg-002:BOL-001"
    with pytest.raises(HTTPException) as exc_info:
        await update_mailtask_status(
            task_key=task_key,
            body=MailTaskStatusRequest(task_status=MailTaskStatus.READY_FOR_WMS),
            current_user=processor,
            db=db,
        )
    assert "requires Sunny approval" in str(exc_info.value.detail)

    await update_mailtask_status(
        task_key=task_key,
        body=MailTaskStatusRequest(task_status=MailTaskStatus.NEEDS_SUNNY_REVIEW),
        current_user=processor,
        db=db,
    )
    await update_mailtask_status(
        task_key=task_key,
        body=MailTaskStatusRequest(task_status=MailTaskStatus.AWAITING_SUNNY_APPROVAL),
        current_user=processor,
        db=db,
    )
    approved = await decide_outbound_approval(
        task_key=task_key,
        body=OutboundApprovalRequest(
            decision="approve",
            note="Sunny approved outbound execution",
            evidence={"source": "dashboard"},
        ),
        current_user=sunny,
        db=db,
    )

    assert approved.task_status == MailTaskStatus.READY_FOR_WMS.value
    assert approved.approval_status == "Approved"
    assert await db.scalar(select(func.count()).select_from(MailTaskApproval)) == 1
