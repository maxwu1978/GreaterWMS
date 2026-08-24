"""Regression tests: tenant registration approval gate."""

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import LoginRequest, login
from app.api.v1.endpoints.tenants import (
    TenantApprovalRequest,
    decide_tenant_approval,
    list_tenant_approvals,
)
from app.core.config import settings
from app.core.security import TokenPayload, UserRole
from app.models.subscription import PlanTier
from app.models.tenant import Tenant
from app.services.subscription_service import SubscriptionService


def _platform_admin() -> TokenPayload:
    return TokenPayload(
        sub="platform-admin-1",
        tenant_id=None,
        role=UserRole.PLATFORM_ADMIN.value,
        email="root@platform.test",
        exp=datetime.now(UTC),
    )


async def _register(db: AsyncSession, code: str = "APPRCO") -> dict:
    if not await db.scalar(select(PlanTier).where(PlanTier.code == "starter")):
        db.add(
            PlanTier(
                id="plan-starter",
                name="Starter",
                code="starter",
                price_monthly=149,
                price_yearly=1490,
                max_clients=5,
                max_skus=1000,
                max_orders_per_day=200,
                max_users=5,
                max_warehouses=1,
                trial_days=14,
                sort_order=1,
                features={},
            )
        )
        await db.flush()
    svc = SubscriptionService(db)
    return await svc.register_trial(
        company_name="Approval Test Co",
        company_code=code,
        admin_email=f"{code.lower()}@example.com",
        admin_password="Secret#123",
        admin_name="Admin",
        accept_terms=True,
        accept_risk_notice=True,
    )


@pytest.mark.asyncio
async def test_registration_pending_blocks_login_until_approved(
    db: AsyncSession, monkeypatch
):
    monkeypatch.setattr(settings, "REGISTRATION_APPROVAL_REQUIRED", True)

    result = await _register(db)
    assert result["success"] is True
    assert result.get("pending_approval") is True
    assert "access_token" not in result

    tenant = await db.scalar(select(Tenant).where(Tenant.id == result["tenant_id"]))
    assert tenant.approval_status == "pending"

    # Login must be blocked while pending
    with pytest.raises(HTTPException) as exc:
        await login(
            LoginRequest(email="apprco@example.com", password="Secret#123"), db=db
        )
    assert exc.value.status_code == 403
    assert "approval" in str(exc.value.detail).lower()

    # Platform admin sees it in the queue and approves
    queue = await list_tenant_approvals(
        approval_status="pending", current_user=_platform_admin(), db=db
    )
    assert any(item.id == result["tenant_id"] for item in queue)

    decided = await decide_tenant_approval(
        tenant_id=result["tenant_id"],
        body=TenantApprovalRequest(action="approve"),
        current_user=_platform_admin(),
        db=db,
    )
    assert decided.approval_status == "approved"

    # Login now succeeds
    token = await login(
        LoginRequest(email="apprco@example.com", password="Secret#123"), db=db
    )
    assert token.access_token
    assert token.role == UserRole.TENANT_ADMIN.value

    refreshed = await db.scalar(select(Tenant).where(Tenant.id == result["tenant_id"]))
    assert refreshed.approved_by == "platform-admin-1"
    assert refreshed.approved_at is not None


@pytest.mark.asyncio
async def test_rejected_registration_stays_blocked(db: AsyncSession, monkeypatch):
    monkeypatch.setattr(settings, "REGISTRATION_APPROVAL_REQUIRED", True)

    result = await _register(db, code="REJCO")
    await decide_tenant_approval(
        tenant_id=result["tenant_id"],
        body=TenantApprovalRequest(action="reject"),
        current_user=_platform_admin(),
        db=db,
    )

    with pytest.raises(HTTPException) as exc:
        await login(LoginRequest(email="rejco@example.com", password="Secret#123"), db=db)
    assert exc.value.status_code == 403
    assert "declined" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_approval_flag_off_keeps_immediate_login(db: AsyncSession, monkeypatch):
    monkeypatch.setattr(settings, "REGISTRATION_APPROVAL_REQUIRED", False)

    result = await _register(db, code="AUTOCO")
    assert result["success"] is True
    assert result.get("pending_approval") is None
    assert result.get("access_token")

    tenant = await db.scalar(select(Tenant).where(Tenant.id == result["tenant_id"]))
    assert tenant.approval_status == "approved"
