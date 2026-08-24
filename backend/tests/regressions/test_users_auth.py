"""Regression tests: users and auth (split from tests/test_regressions.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    forgot_password,
    reset_password,
    validate_reset_password_token,
)
from app.api.v1.endpoints.maintenance import AuditTenantBootstrapRequest, bootstrap_test_tenant
from app.api.v1.endpoints.users import (
    UserCleanupAgentRequest,
    UserCleanupPreviewRequest,
    UserCreate,
    UserDeactivationAgentRequest,
    UserDeactivationPreviewRequest,
    UserManagementAgentRequest,
    UserManagementPreviewRequest,
    UserUpdate,
    confirm_non_admin_user_cleanup,
    confirm_user_deactivation,
    confirm_user_management,
    create_user,
    list_users,
    preview_non_admin_user_cleanup,
    preview_user_deactivation,
    preview_user_management,
    update_user,
)
from app.core.deps import get_current_user
from app.core.pagination import PaginationParams
from app.core.security import (
    TokenPayload,
    UserRole,
    create_access_token,
    hash_password,
    verify_password,
    verify_token,
)
from app.models.agent_evidence import AgentEvidence
from app.models.client import Client
from app.models.subscription import PlanTier, Subscription, SubscriptionStatus
from app.models.tenant import Tenant, User


@pytest.mark.asyncio
async def test_live_auth_rejects_a_deleted_user_token(monkeypatch: pytest.MonkeyPatch):
    class DeletedAccountSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def scalar(self, _query):
            return None

    async def skip_session_context(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.core.deps.async_session_factory",
        lambda: DeletedAccountSession(),
    )
    monkeypatch.setattr("app.core.deps.apply_session_context", skip_session_context)

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=create_access_token("deleted-user", UserRole.PLATFORM_ADMIN),
    )
    with pytest.raises(HTTPException) as exc:
        await get_current_user(credentials)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_forgot_password_sets_token_and_reset_password_updates_hash(
    db: AsyncSession,
    tenant_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    tenant = Tenant(
        id=tenant_id, name="Reset Tenant", code="RST", contact_email="owner@example.com"
    )
    user = User(
        id="user-reset-1",
        tenant_id=tenant_id,
        email="reset@example.com",
        hashed_password=hash_password("oldpass1"),
        full_name="Reset User",
        role=UserRole.TENANT_ADMIN.value,
        is_active=True,
        is_email_verified=True,
    )
    db.add_all([tenant, user])
    await db.flush()

    sent: dict[str, str] = {}

    async def fake_send_password_reset_email(to_email: str, company_name: str, reset_url: str):
        sent["to_email"] = to_email
        sent["company_name"] = company_name
        sent["reset_url"] = reset_url
        return {"success": True}

    monkeypatch.setattr("app.api.v1.endpoints.auth.email_delivery_enabled", lambda: True)
    monkeypatch.setattr(
        "app.api.v1.endpoints.auth.send_password_reset_email", fake_send_password_reset_email
    )

    response = await forgot_password(ForgotPasswordRequest(email="reset@example.com"), db)
    assert response.success is True

    refreshed = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
    assert refreshed.password_reset_token
    assert refreshed.password_reset_sent_at
    assert sent["to_email"] == "reset@example.com"
    assert refreshed.password_reset_token in sent["reset_url"]

    validation = await validate_reset_password_token(refreshed.password_reset_token, db)
    assert validation.valid is True

    await reset_password(
        ResetPasswordRequest(token=refreshed.password_reset_token, new_password="newpass123"),
        db,
    )

    reset_user = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
    assert verify_password("newpass123", reset_user.hashed_password) is True
    assert reset_user.password_reset_token is None
    assert reset_user.password_reset_sent_at is None


@pytest.mark.asyncio
async def test_user_management_enforces_company_child_user_hierarchy(
    db: AsyncSession,
    tenant_id: str,
):
    tenant = Tenant(
        id=tenant_id, name="Hierarchy Tenant", code="HIER", contact_email="owner@example.com"
    )
    client = Client(
        id="client-hierarchy", tenant_id=tenant_id, name="Hierarchy Client", code="HCLI"
    )
    tenant_admin = User(
        id="tenant-admin-hierarchy",
        tenant_id=tenant_id,
        email="admin-hier@example.com",
        hashed_password=hash_password("adminpass"),
        full_name="Tenant Admin",
        role=UserRole.TENANT_ADMIN.value,
        permissions=["users.manage"],
        is_active=True,
    )
    peer_admin = User(
        id="peer-admin-hierarchy",
        tenant_id=tenant_id,
        email="peer-hier@example.com",
        hashed_password=hash_password("peerpass"),
        full_name="Peer Admin",
        role=UserRole.TENANT_ADMIN.value,
        permissions=["users.manage"],
        is_active=True,
    )
    operator = User(
        id="operator-hierarchy",
        tenant_id=tenant_id,
        email="operator-hier@example.com",
        hashed_password=hash_password("operatorpass"),
        full_name="Operator",
        role=UserRole.OPERATOR.value,
        permissions=["receiving.execute", "users.manage"],
        is_active=True,
    )
    db.add_all([tenant, client, tenant_admin, peer_admin, operator])
    await db.flush()

    current_user = TokenPayload(
        sub=tenant_admin.id,
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=["users.manage"],
        exp=datetime.now(UTC),
    )

    created = await create_user(
        UserCreate(
            email="child-hier@example.com",
            full_name="Child Operator",
            password="childpass",
            role=UserRole.OPERATOR.value,
            permissions=["users.manage", "shipping.execute", "*"],
        ),
        current_user=current_user,
        db=db,
    )
    assert created.role == UserRole.OPERATOR.value
    assert created.tenant_id == tenant_id
    assert created.permissions == ["shipping.execute"]

    with pytest.raises(HTTPException) as exc:
        await create_user(
            UserCreate(
                email="new-admin-hier@example.com",
                full_name="New Admin",
                password="adminpass",
                role=UserRole.TENANT_ADMIN.value,
            ),
            current_user=current_user,
            db=db,
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await update_user(
            operator.id,
            UserUpdate(role=UserRole.TENANT_ADMIN.value),
            current_user=current_user,
            db=db,
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await update_user(
            operator.id,
            UserUpdate(role=UserRole.CLIENT_VIEWER.value),
            current_user=current_user,
            db=db,
        )
    assert exc.value.status_code == 400

    updated_viewer = await update_user(
        operator.id,
        UserUpdate(
            role=UserRole.CLIENT_VIEWER.value,
            client_id=client.id,
            permissions=["shipping.execute", "users.manage", "*"],
        ),
        current_user=current_user,
        db=db,
    )
    assert updated_viewer.role == UserRole.CLIENT_VIEWER.value
    assert updated_viewer.client_id == client.id
    assert updated_viewer.permissions == ["portal.view"]

    operator_actor = TokenPayload(
        sub=operator.id,
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.OPERATOR,
        permissions=["users.manage"],
        exp=datetime.now(UTC),
    )
    with pytest.raises(HTTPException) as exc:
        await create_user(
            UserCreate(
                email="operator-created-user@example.com",
                full_name="Operator Created User",
                password="operatorpass",
                role=UserRole.OPERATOR.value,
            ),
            current_user=operator_actor,
            db=db,
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await update_user(
            peer_admin.id,
            UserUpdate(is_active=False),
            current_user=current_user,
            db=db,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_platform_admin_can_manage_users_across_tenants(db: AsyncSession):
    platform_tenant = Tenant(
        id="platform-tenant",
        name="Platform Tenant",
        code="PLATFORM",
        contact_email="platform@example.com",
    )
    tenant_a = Tenant(id="tenant-a", name="Tenant A", code="TA", contact_email="a@example.com")
    tenant_b = Tenant(id="tenant-b", name="Tenant B", code="TB", contact_email="b@example.com")
    db.add_all(
        [
            platform_tenant,
            tenant_a,
            tenant_b,
            User(
                id="platform-admin",
                tenant_id=platform_tenant.id,
                email="platform@example.com",
                hashed_password=hash_password("platformpass"),
                full_name="Platform Admin",
                role=UserRole.PLATFORM_ADMIN.value,
                permissions=["*"],
                is_active=True,
            ),
            User(
                id="tenant-a-operator",
                tenant_id=tenant_a.id,
                email="operator-a@example.com",
                hashed_password=hash_password("operatorpass"),
                full_name="Operator A",
                role=UserRole.OPERATOR.value,
                is_active=True,
            ),
        ]
    )
    await db.flush()

    current_user = TokenPayload(
        sub="platform-admin",
        tenant_id=None,
        client_id=None,
        role=UserRole.PLATFORM_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC),
    )

    created = await create_user(
        UserCreate(
            email="admin-b@example.com",
            full_name="Tenant B Admin",
            password="adminpass",
            role=UserRole.TENANT_ADMIN.value,
            tenant_id=tenant_b.id,
        ),
        current_user=current_user,
        db=db,
    )

    assert created.role == UserRole.TENANT_ADMIN.value
    assert created.tenant_id == tenant_b.id

    page = await list_users(PaginationParams(offset=0, limit=500), current_user=current_user, db=db)
    emails = {item.email for item in page["items"]}
    assert {
        "platform@example.com",
        "operator-a@example.com",
        "admin-b@example.com",
    }.issubset(emails)
    assert page["total"] == 3
    assert page["total_is_estimate"] is False


@pytest.mark.asyncio
async def test_platform_admin_can_edit_cross_tenant_user_and_cannot_disable_self(
    db: AsyncSession,
):
    tenant = Tenant(
        id="edit-tenant",
        name="Edit Tenant",
        code="EDIT",
        contact_email="edit@example.com",
    )
    platform_admin = User(
        id="edit-platform-admin",
        tenant_id=tenant.id,
        email="edit-platform@example.com",
        hashed_password=hash_password("platformpass"),
        full_name="Platform Admin",
        role=UserRole.PLATFORM_ADMIN.value,
        permissions=["*"],
        is_active=True,
    )
    operator = User(
        id="edit-operator",
        tenant_id=tenant.id,
        email="edit-operator@example.com",
        hashed_password=hash_password("operatorpass"),
        full_name="Old Operator",
        role=UserRole.OPERATOR.value,
        job_title="Warehouse",
        permissions=["receiving.execute"],
        is_active=True,
    )
    db.add_all([tenant, platform_admin, operator])
    await db.flush()

    current_user = TokenPayload(
        sub=platform_admin.id,
        tenant_id=None,
        client_id=None,
        role=UserRole.PLATFORM_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    updated = await update_user(
        operator.id,
        UserUpdate(
            full_name="Updated Operator",
            job_title=None,
            role=UserRole.TENANT_ADMIN.value,
            permissions=["users.manage", "billing.manage", "*"],
            is_active=False,
        ),
        current_user=current_user,
        db=db,
    )
    assert updated.full_name == "Updated Operator"
    assert updated.job_title is None
    assert updated.role == UserRole.TENANT_ADMIN.value
    assert updated.permissions == ["users.manage", "billing.manage"]
    assert updated.is_active is False
    assert updated.tenant_name == "Edit Tenant"

    with pytest.raises(HTTPException) as exc:
        await update_user(
            platform_admin.id,
            UserUpdate(is_active=False),
            current_user=current_user,
            db=db,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_platform_admin_cleanup_previews_preserves_admins_and_confirms_idempotently(
    db: AsyncSession,
):
    platform_tenant = Tenant(
        id="platform-cleanup-tenant",
        name="Platform Cleanup Host",
        code="PLATCLEAN",
        contact_email="platform-cleanup@example.com",
    )
    platform_admin = User(
        id="platform-cleanup-admin",
        tenant_id=platform_tenant.id,
        email="platform-cleanup-admin@example.com",
        hashed_password=hash_password("platformpass"),
        full_name="Platform Cleanup Admin",
        role=UserRole.PLATFORM_ADMIN.value,
        permissions=["*"],
        is_active=True,
    )
    tenant_admin = User(
        id="platform-cleanup-tenant-admin",
        tenant_id="customer-cleanup-tenant",
        email="customer-admin@example.com",
        hashed_password=hash_password("tenantpass"),
        full_name="Customer Admin",
        role=UserRole.TENANT_ADMIN.value,
        permissions=["users.manage"],
        is_active=False,
    )
    operator = User(
        id="platform-cleanup-operator",
        tenant_id="customer-cleanup-tenant",
        email="customer-operator@example.com",
        hashed_password=hash_password("operatorpass"),
        full_name="Customer Operator",
        role=UserRole.OPERATOR.value,
        is_active=True,
    )
    viewer = User(
        id="platform-cleanup-viewer",
        tenant_id="customer-cleanup-tenant",
        email="customer-viewer@example.com",
        hashed_password=hash_password("viewerpass"),
        full_name="Customer Viewer",
        role=UserRole.CLIENT_VIEWER.value,
        is_active=False,
    )
    db.add_all(
        [
            platform_tenant,
            Tenant(
                id="customer-cleanup-tenant",
                name="Customer Cleanup Tenant",
                code="CUSCLEAN",
                contact_email="customer-cleanup@example.com",
            ),
            platform_admin,
            tenant_admin,
            operator,
            viewer,
        ]
    )
    await db.flush()

    current_user = TokenPayload(
        sub=platform_admin.id,
        tenant_id=None,
        client_id=None,
        role=UserRole.PLATFORM_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    preview = await preview_non_admin_user_cleanup(
        UserCleanupPreviewRequest(),
        current_user=current_user,
        db=db,
    )
    assert preview["writes"] is False
    assert preview["confirmation_required_for_write"] is True
    assert preview["summary"]["delete_count"] == 2
    assert preview["preserved"]["count"] == 2
    assert preview["preserved"]["roles"] == ["platform_admin", "tenant_admin"]

    evidence = await db.scalar(
        select(AgentEvidence).where(AgentEvidence.id == preview["evidence_id"])
    )
    assert evidence is not None
    assert evidence.status == "previewed"
    assert evidence.confirmation_payload["confirmation_token"] == "[redacted]"

    db.add(
        User(
            id="platform-cleanup-late-operator",
            tenant_id="customer-cleanup-tenant",
            email="late-operator@example.com",
            hashed_password=hash_password("latepass"),
            full_name="Late Operator",
            role=UserRole.OPERATOR.value,
            is_active=True,
        )
    )
    await db.flush()

    with pytest.raises(HTTPException) as stale_preview:
        await confirm_non_admin_user_cleanup(
            UserCleanupAgentRequest(
                confirmation_token=preview["confirmation_payload"]["confirmation_token"],
            ),
            x_idempotency_key="platform-cleanup-stale-confirm",
            current_user=current_user,
            db=db,
        )
    assert stale_preview.value.status_code == 409

    preview = await preview_non_admin_user_cleanup(
        UserCleanupPreviewRequest(),
        current_user=current_user,
        db=db,
    )
    assert preview["summary"]["delete_count"] == 3
    evidence = await db.scalar(
        select(AgentEvidence).where(AgentEvidence.id == preview["evidence_id"])
    )
    assert evidence is not None

    confirmed = await confirm_non_admin_user_cleanup(
        UserCleanupAgentRequest(
            confirmation_token=preview["confirmation_payload"]["confirmation_token"],
        ),
        x_idempotency_key="platform-cleanup-confirm-1",
        current_user=current_user,
        db=db,
    )
    assert confirmed["deleted_count"] == 3
    assert confirmed["preserved_admin_count"] == 2

    remaining = list((await db.execute(select(User).order_by(User.email))).scalars())
    assert {user.role for user in remaining} == {"platform_admin", "tenant_admin"}
    assert {user.id for user in remaining} == {platform_admin.id, tenant_admin.id}
    assert evidence.status == "executed"
    assert evidence.idempotency_key == "platform-cleanup-confirm-1"

    replayed = await confirm_non_admin_user_cleanup(
        UserCleanupAgentRequest(
            confirmation_token=preview["confirmation_payload"]["confirmation_token"],
        ),
        x_idempotency_key="platform-cleanup-confirm-1",
        current_user=current_user,
        db=db,
    )
    assert replayed == confirmed


@pytest.mark.asyncio
async def test_platform_admin_singleton_cleanup_keeps_only_requested_admin(
    db: AsyncSession,
):
    platform_tenant = Tenant(
        id="singleton-platform-tenant",
        name="Singleton Platform Host",
        code="SINGLETON",
        contact_email="wuqingxin1978@icloud.com",
    )
    customer_tenant = Tenant(
        id="singleton-customer-tenant",
        name="Singleton Customer",
        code="SINGLECUS",
        contact_email="customer-singleton@example.com",
    )
    keep_admin = User(
        id="singleton-keep-admin",
        tenant_id=platform_tenant.id,
        email="wuqingxin1978@icloud.com",
        hashed_password=hash_password("platformpass"),
        full_name="Wuqingxin",
        role=UserRole.PLATFORM_ADMIN.value,
        permissions=["*"],
        is_active=True,
    )
    duplicate_admin = User(
        id="singleton-duplicate-admin",
        tenant_id=platform_tenant.id,
        email="duplicate-admin@example.com",
        hashed_password=hash_password("platformpass"),
        full_name="Duplicate Admin",
        role=UserRole.PLATFORM_ADMIN.value,
        permissions=["*"],
        is_active=True,
    )
    tenant_admin = User(
        id="singleton-tenant-admin",
        tenant_id=customer_tenant.id,
        email="singleton-tenant-admin@example.com",
        hashed_password=hash_password("tenantpass"),
        full_name="Tenant Admin",
        role=UserRole.TENANT_ADMIN.value,
        permissions=["users.manage"],
        is_active=True,
    )
    operator = User(
        id="singleton-operator",
        tenant_id=customer_tenant.id,
        email="singleton-operator@example.com",
        hashed_password=hash_password("operatorpass"),
        full_name="Operator",
        role=UserRole.OPERATOR.value,
        is_active=False,
    )
    db.add_all([platform_tenant, customer_tenant, keep_admin, duplicate_admin, tenant_admin, operator])
    await db.flush()

    current_user = TokenPayload(
        sub=keep_admin.id,
        tenant_id=None,
        client_id=None,
        role=UserRole.PLATFORM_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    cleanup_request = UserCleanupPreviewRequest(
        scope="keep_one_platform_admin",
        keep_platform_admin_email="wuqingxin1978@icloud.com",
    )

    preview = await preview_non_admin_user_cleanup(
        cleanup_request,
        current_user=current_user,
        db=db,
    )
    assert preview["summary"]["delete_count"] == 3
    assert preview["summary"]["preserve_count"] == 1
    assert preview["summary"]["keep_platform_admin_email"] == "wuqingxin1978@icloud.com"
    assert preview["state_after"]["total_users"] == 1

    confirmed = await confirm_non_admin_user_cleanup(
        UserCleanupAgentRequest(
            **cleanup_request.model_dump(),
            confirmation_token=preview["confirmation_payload"]["confirmation_token"],
            evidence_id=preview["evidence_id"],
        ),
        x_idempotency_key="singleton-cleanup-confirm-1",
        current_user=current_user,
        db=db,
    )
    assert confirmed["deleted_count"] == 3
    assert confirmed["preserved_admin_count"] == 1

    remaining = list((await db.execute(select(User))).scalars())
    assert [(user.id, user.email, user.role, user.is_active) for user in remaining] == [
        (keep_admin.id, keep_admin.email, UserRole.PLATFORM_ADMIN.value, True)
    ]


@pytest.mark.asyncio
async def test_platform_admin_singleton_is_enforced_for_management_flows(db: AsyncSession):
    tenant = Tenant(
        id="singleton-management-tenant",
        name="Singleton Management Tenant",
        code="SINGLEMAN",
        contact_email="singleton-management@example.com",
    )
    platform_admin = User(
        id="singleton-management-admin",
        tenant_id=tenant.id,
        email="existing-admin@example.com",
        hashed_password=hash_password("platformpass"),
        full_name="Existing Admin",
        role=UserRole.PLATFORM_ADMIN.value,
        permissions=["*"],
        is_active=True,
    )
    tenant_admin = User(
        id="singleton-management-tenant-admin",
        tenant_id=tenant.id,
        email="tenant-admin@example.com",
        hashed_password=hash_password("tenantpass"),
        full_name="Tenant Admin",
        role=UserRole.TENANT_ADMIN.value,
        permissions=["users.manage"],
        is_active=True,
    )
    db.add_all([tenant, platform_admin, tenant_admin])
    await db.flush()
    current_user = TokenPayload(
        sub=platform_admin.id,
        tenant_id=None,
        client_id=None,
        role=UserRole.PLATFORM_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    with pytest.raises(HTTPException) as create_error:
        await preview_user_management(
            UserManagementPreviewRequest(
                action="create",
                user=UserCreate(
                    email="new-admin@example.com",
                    full_name="New Admin",
                    password="newadminpass",
                    role=UserRole.PLATFORM_ADMIN.value,
                    tenant_id=tenant.id,
                ),
            ),
            current_user=current_user,
            db=db,
        )
    assert create_error.value.status_code == 409

    with pytest.raises(HTTPException) as promote_error:
        await update_user(
            tenant_admin.id,
            UserUpdate(role=UserRole.PLATFORM_ADMIN.value),
            current_user=current_user,
            db=db,
        )
    assert promote_error.value.status_code == 409


@pytest.mark.asyncio
async def test_platform_admin_deactivation_keeps_user_rows_and_only_target_active(
    db: AsyncSession,
):
    tenant = Tenant(
        id="deactivation-tenant",
        name="Deactivation Tenant",
        code="DEACT",
        contact_email="deactivation@example.com",
    )
    keep_admin = User(
        id="deactivation-keep-admin",
        tenant_id=tenant.id,
        email="wuqingxin1978@icloud.com",
        hashed_password=hash_password("platformpass"),
        full_name="Wuqingxin",
        role=UserRole.PLATFORM_ADMIN.value,
        permissions=["*"],
        is_active=True,
    )
    duplicate_admin = User(
        id="deactivation-duplicate-admin",
        tenant_id=tenant.id,
        email="deactivation-admin@example.com",
        hashed_password=hash_password("platformpass"),
        full_name="Duplicate Admin",
        role=UserRole.PLATFORM_ADMIN.value,
        permissions=["*"],
        is_active=True,
    )
    operator = User(
        id="deactivation-operator",
        tenant_id=tenant.id,
        email="deactivation-operator@example.com",
        hashed_password=hash_password("operatorpass"),
        full_name="Operator",
        role=UserRole.OPERATOR.value,
        is_active=True,
    )
    already_inactive = User(
        id="deactivation-inactive",
        tenant_id=tenant.id,
        email="deactivation-inactive@example.com",
        hashed_password=hash_password("inactivepass"),
        full_name="Already Inactive",
        role=UserRole.TENANT_ADMIN.value,
        permissions=["users.manage"],
        is_active=False,
    )
    db.add_all([tenant, keep_admin, duplicate_admin, operator, already_inactive])
    await db.flush()

    current_user = TokenPayload(
        sub=keep_admin.id,
        tenant_id=None,
        client_id=None,
        role=UserRole.PLATFORM_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    request = UserDeactivationPreviewRequest(
        keep_platform_admin_email="wuqingxin1978@icloud.com",
    )
    preview = await preview_user_deactivation(
        request,
        current_user=current_user,
        db=db,
    )
    assert preview["summary"]["delete_count"] == 0
    assert preview["summary"]["deactivate_count"] == 2
    assert preview["state_before"]["total_users"] == 4
    assert preview["state_before"]["active_users"] == 3
    assert preview["state_after"]["total_users"] == 4
    assert preview["state_after"]["active_users"] == 1

    confirmed = await confirm_user_deactivation(
        UserDeactivationAgentRequest(
            **request.model_dump(),
            confirmation_token=preview["confirmation_payload"]["confirmation_token"],
            evidence_id=preview["evidence_id"],
        ),
        x_idempotency_key="deactivation-confirm-1",
        current_user=current_user,
        db=db,
    )
    assert confirmed["deleted_count"] == 0
    assert confirmed["deactivated_count"] == 2

    remaining = list((await db.execute(select(User).order_by(User.email))).scalars())
    assert len(remaining) == 4
    assert {user.id for user in remaining if user.is_active} == {keep_admin.id}
    assert {user.id for user in remaining if not user.is_active} == {
        duplicate_admin.id,
        operator.id,
        already_inactive.id,
    }


@pytest.mark.asyncio
async def test_platform_admin_bootstraps_verified_active_test_tenant(db: AsyncSession):
    plan = PlanTier(
        id="plan-enterprise",
        name="Enterprise",
        code="enterprise",
        price_monthly=499,
        price_yearly=4990,
        max_clients=50,
        max_skus=100000,
        max_orders_per_day=10000,
        max_users=100,
        max_warehouses=10,
        features={"qa": True},
        trial_days=14,
        is_active=True,
    )
    db.add(plan)
    await db.flush()

    current_user = TokenPayload(
        sub="platform-admin",
        tenant_id=None,
        client_id=None,
        role=UserRole.PLATFORM_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC),
    )

    result = await bootstrap_test_tenant(
        AuditTenantBootstrapRequest(
            company_name="QA Bootstrap Tenant",
            company_code="qaboot",
            admin_email="qa-bootstrap@example.com",
            admin_password="adminpass",
            admin_name="QA Bootstrap Admin",
            plan_code="enterprise",
            active_days=30,
        ),
        current_user=current_user,
        db=db,
    )

    assert result["success"] is True
    assert result["tenant_code"] == "QABOOT"
    assert result["verification_required"] is False
    assert result["subscription_status"] == SubscriptionStatus.ACTIVE.value

    token_payload = verify_token(result["access_token"])
    assert token_payload is not None
    assert token_payload.role == UserRole.TENANT_ADMIN
    assert token_payload.tenant_id == result["tenant_id"]

    tenant = await db.scalar(select(Tenant).where(Tenant.id == result["tenant_id"]))
    user = await db.scalar(select(User).where(User.id == result["user_id"]))
    subscription = await db.scalar(
        select(Subscription).where(Subscription.tenant_id == result["tenant_id"])
    )

    assert tenant is not None
    assert tenant.contact_email == "qa-bootstrap@example.com"
    assert tenant.settings["test_bootstrap"]["created_by"] == "platform-admin"
    assert user is not None
    assert user.is_email_verified is True
    assert user.role == UserRole.TENANT_ADMIN.value
    assert subscription is not None
    assert subscription.status == SubscriptionStatus.ACTIVE.value
    assert subscription.trial_end_date is None


@pytest.mark.asyncio
async def test_validate_reset_password_token_rejects_expired_token(
    db: AsyncSession,
    tenant_id: str,
):
    tenant = Tenant(
        id=tenant_id, name="Expired Tenant", code="EXP", contact_email="owner@example.com"
    )
    user = User(
        id="user-reset-expired",
        tenant_id=tenant_id,
        email="expired@example.com",
        hashed_password=hash_password("expired1"),
        full_name="Expired User",
        role=UserRole.TENANT_ADMIN.value,
        is_active=True,
        is_email_verified=True,
        password_reset_token="expired-token",
        password_reset_sent_at=datetime.now(UTC) - timedelta(hours=2),
    )
    db.add_all([tenant, user])
    await db.flush()

    validation = await validate_reset_password_token("expired-token", db)
    assert validation.valid is False


@pytest.mark.asyncio
async def test_governed_user_management_preview_and_confirmation(
    db: AsyncSession,
):
    db.add_all(
        [
            Tenant(
                id="platform-audit-tenant",
                name="Platform Audit",
                code="PLAT",
                contact_email="platform@example.com",
            ),
            Tenant(
                id="managed-tenant",
                name="Managed Tenant",
                code="MNG",
                contact_email="tenant@example.com",
            ),
            User(
                id="platform-admin-management",
                tenant_id="platform-audit-tenant",
                email="platform-management@example.com",
                hashed_password=hash_password("platformpass"),
                full_name="Platform Admin",
                role=UserRole.PLATFORM_ADMIN.value,
                permissions=["*"],
                is_active=True,
            ),
        ]
    )
    await db.flush()

    current_user = TokenPayload(
        sub="platform-admin-management",
        tenant_id="platform-audit-tenant",
        client_id=None,
        role=UserRole.PLATFORM_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC),
    )
    create_body = UserManagementPreviewRequest(
        action="create",
        user=UserCreate(
            email="cli-operator@example.com",
            full_name="CLI Operator",
            password="secret123",
            role=UserRole.OPERATOR.value,
            tenant_id="managed-tenant",
        ),
    )

    preview = await preview_user_management(create_body, current_user=current_user, db=db)
    assert preview["confirmation_required_for_write"] is True
    assert preview["state_after"]["tenant_id"] == "managed-tenant"
    assert "secret123" not in str(preview)
    evidence_id = preview["evidence_id"]
    confirmation_token = preview["confirmation_payload"]["confirmation_token"]

    confirmed = await confirm_user_management(
        UserManagementAgentRequest(
            **create_body.model_dump(),
            confirmation_token=confirmation_token,
            evidence_id=evidence_id,
        ),
        x_idempotency_key="cli-user-create-1",
        current_user=current_user,
        db=db,
    )
    created = await db.scalar(select(User).where(User.email == "cli-operator@example.com"))
    assert created is not None
    assert created.tenant_id == "managed-tenant"
    assert confirmed["evidence_id"] == evidence_id
    assert verify_password("secret123", created.hashed_password)

    update_body = UserManagementPreviewRequest(
        action="update",
        user_id=created.id,
        changes=UserUpdate(job_title="Shift Lead", is_active=False),
    )
    update_preview = await preview_user_management(
        update_body, current_user=current_user, db=db
    )
    await confirm_user_management(
        UserManagementAgentRequest(
            **update_body.model_dump(exclude_none=True),
            confirmation_token=update_preview["confirmation_payload"]["confirmation_token"],
            evidence_id=update_preview["evidence_id"],
        ),
        x_idempotency_key="cli-user-update-1",
        current_user=current_user,
        db=db,
    )
    await db.refresh(created)
    assert created.job_title == "Shift Lead"
    assert created.is_active is False

    reset_body = UserManagementPreviewRequest(
        action="reset_password",
        user_id=created.id,
        new_password="resetpass123",
    )
    reset_preview = await preview_user_management(reset_body, current_user=current_user, db=db)
    await confirm_user_management(
        UserManagementAgentRequest(
            **reset_body.model_dump(exclude_none=True),
            confirmation_token=reset_preview["confirmation_payload"]["confirmation_token"],
            evidence_id=reset_preview["evidence_id"],
        ),
        x_idempotency_key="cli-user-reset-1",
        current_user=current_user,
        db=db,
    )
    await db.refresh(created)
    assert verify_password("resetpass123", created.hashed_password)
