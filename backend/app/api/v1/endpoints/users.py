"""User management — CRUD, password reset, role assignment, and cleanup."""

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_permission, require_role
from app.core.pagination import PaginationParams
from app.core.plan_limits import check_limit
from app.core.security import (
    TokenPayload,
    UserPermission,
    UserRole,
    default_permissions_for_role,
    hash_password,
    normalize_email,
    normalize_permissions,
    validate_password,
)
from app.models.client import Client
from app.models.tenant import Tenant, User
from app.services.agent_evidence_service import AgentEvidenceService
from app.services.idempotency_service import IdempotencyService

router = APIRouter()

TENANT_MANAGED_ROLES = {
    UserRole.OPERATOR.value,
    UserRole.CLIENT_VIEWER.value,
}
PLATFORM_MANAGED_ROLES = {
    UserRole.PLATFORM_ADMIN.value,
    UserRole.TENANT_ADMIN.value,
    UserRole.OPERATOR.value,
    UserRole.CLIENT_VIEWER.value,
}
USER_MANAGER_ROLES = {
    UserRole.PLATFORM_ADMIN,
    UserRole.TENANT_ADMIN,
}

# Cleanup is deliberately narrower than a generic user delete. Admin accounts
# are always retained by the legacy scope; the explicit singleton scope below
# requires an exact keep-email and is separately previewed and confirmed.
USER_CLEANUP_ACTION = "users.cleanup_non_admin"
USER_SINGLE_ADMIN_CLEANUP_SCOPE = "keep_one_platform_admin"
USER_SINGLE_ADMIN_CLEANUP_ACTION = "users.cleanup_keep_platform_admin"
USER_DEACTIVATE_SCOPE = "deactivate_except_platform_admin"
USER_DEACTIVATE_ACTION = "users.deactivate_except_platform_admin"
USER_CLEANUP_ENTITY_TYPE = "user_collection"
USER_CLEANUP_ENTITY_ID = "global"
USER_CLEANUP_ADMIN_ROLES = frozenset(
    {UserRole.PLATFORM_ADMIN.value, UserRole.TENANT_ADMIN.value}
)
USER_CLEANUP_DELETABLE_ROLES = frozenset(
    {UserRole.OPERATOR.value, UserRole.CLIENT_VIEWER.value}
)
USER_CLEANUP_PERMISSION = "platform_admin"
USER_CLEANUP_RISK = "critical"

USER_MANAGEMENT_RISK = "high"
USER_MANAGEMENT_PERMISSION = UserPermission.USERS_MANAGE.value
USER_MANAGEMENT_ENTITY_TYPE = "user"


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: str = "operator"  # operator | tenant_admin | client_viewer
    job_title: str | None = None
    permissions: list[str] | None = None
    client_id: str | None = None  # required for client_viewer
    tenant_id: str | None = None  # required for platform_admin creating tenant-scoped users


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    job_title: str | None = None
    permissions: list[str] | None = None
    client_id: str | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: str


class UserCleanupPreviewRequest(BaseModel):
    scope: Literal["non_admin_users", "keep_one_platform_admin"] = "non_admin_users"
    keep_platform_admin_email: EmailStr | None = None


class UserCleanupAgentRequest(UserCleanupPreviewRequest):
    confirmation_token: str
    evidence_id: str | None = None


class UserDeactivationPreviewRequest(BaseModel):
    scope: Literal["deactivate_except_platform_admin"] = USER_DEACTIVATE_SCOPE
    keep_platform_admin_email: EmailStr


class UserDeactivationAgentRequest(UserDeactivationPreviewRequest):
    confirmation_token: str
    evidence_id: str | None = None


UserCleanupRequest = UserCleanupPreviewRequest | UserDeactivationPreviewRequest
UserCleanupConfirmationRequest = UserCleanupAgentRequest | UserDeactivationAgentRequest


class UserManagementPreviewRequest(BaseModel):
    action: Literal["create", "update", "reset_password"]
    user: UserCreate | None = None
    user_id: str | None = None
    changes: UserUpdate | None = None
    new_password: str | None = None


class UserManagementAgentRequest(UserManagementPreviewRequest):
    confirmation_token: str
    evidence_id: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    job_title: str | None
    permissions: list[str] = []
    is_active: bool
    client_id: str | None
    tenant_id: str | None = None
    tenant_name: str | None = None


def _validate_role(value: str) -> str:
    if value not in PLATFORM_MANAGED_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    return value


def _assert_actor_can_manage_users(current_user: TokenPayload) -> None:
    """Role gate layered on top of require_permission(USERS_MANAGE).

    An operator granted the users.manage permission directly in the database
    must still not manage users. Deliberately kept as an in-body assertion
    (not a Depends() guard) so it also applies when the endpoint functions
    are invoked directly, as the regression tests do.
    """
    if current_user.role not in USER_MANAGER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only super admins and company admins can manage users",
        )


def _assert_actor_can_assign_role(current_user: TokenPayload, role: str) -> None:
    if current_user.role == UserRole.PLATFORM_ADMIN:
        return
    if role not in TENANT_MANAGED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Company admins can only manage operator and client viewer users",
        )


async def _assert_platform_admin_slot_available(
    db: AsyncSession,
    *,
    excluding_user_id: str | None = None,
) -> None:
    query = select(User.id).where(User.role == UserRole.PLATFORM_ADMIN.value)
    if excluding_user_id:
        query = query.where(User.id != excluding_user_id)
    existing_id = await db.scalar(query.limit(1))
    if existing_id:
        raise HTTPException(
            status_code=409,
            detail="Only one platform admin account is allowed",
        )


async def _validate_platform_admin_transition(
    db: AsyncSession,
    user: User,
    *,
    requested_role: str,
    requested_active: bool,
) -> None:
    if requested_role == UserRole.PLATFORM_ADMIN.value and not requested_active:
        raise HTTPException(
            status_code=409,
            detail="A platform admin account must remain active",
        )
    if user.role == UserRole.PLATFORM_ADMIN.value and (
        requested_role != UserRole.PLATFORM_ADMIN.value or not requested_active
    ):
        raise HTTPException(
            status_code=409,
            detail="The platform admin account cannot be demoted or deactivated",
        )
    if requested_role == UserRole.PLATFORM_ADMIN.value and user.role != requested_role:
        await _assert_platform_admin_slot_available(db, excluding_user_id=user.id)


def _assert_actor_can_manage_user(current_user: TokenPayload, user: User) -> None:
    if current_user.role == UserRole.PLATFORM_ADMIN:
        return
    if user.role not in TENANT_MANAGED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Company admins can only manage child users in their own company",
        )


def _assignable_permissions_for_role(role: str, permissions: list[str] | None) -> list[str]:
    if role == UserRole.PLATFORM_ADMIN.value:
        return ["*"]

    default_permissions = default_permissions_for_role(role)
    if role == UserRole.CLIENT_VIEWER.value:
        return list(default_permissions)

    allowed_permissions = set(default_permissions)
    if permissions is None:
        return list(default_permissions)

    assigned_permissions: list[str] = []
    for permission in permissions:
        if permission in allowed_permissions and permission not in assigned_permissions:
            assigned_permissions.append(permission)
    return assigned_permissions


def _assert_platform_cleanup_actor(current_user: TokenPayload) -> None:
    if current_user.role != UserRole.PLATFORM_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only platform admins can run global user cleanup",
        )


async def _user_cleanup_snapshot(
    db: AsyncSession,
    current_user: TokenPayload,
    body: UserCleanupRequest,
) -> dict:
    _assert_platform_cleanup_actor(current_user)
    actor = await db.scalar(select(User).where(User.id == current_user.sub))
    if not actor or actor.role != UserRole.PLATFORM_ADMIN.value or not actor.is_active:
        raise HTTPException(
            status_code=403,
            detail="The signed-in platform admin account is not active",
        )

    users = list(
        (
            await db.execute(
                select(User).order_by(User.role, User.email, User.id)
            )
        ).scalars()
    )
    if body.scope in {USER_SINGLE_ADMIN_CLEANUP_SCOPE, USER_DEACTIVATE_SCOPE}:
        if not body.keep_platform_admin_email:
            raise HTTPException(
                status_code=400,
                detail="keep_platform_admin_email is required for singleton cleanup",
            )
        keep_email = normalize_email(str(body.keep_platform_admin_email))
        keep_user = await db.scalar(
            select(User).where(
                func.lower(User.email) == keep_email,
                User.role == UserRole.PLATFORM_ADMIN.value,
            )
        )
        if not keep_user:
            raise HTTPException(
                status_code=404,
                detail="The requested platform admin account was not found",
            )
        if not keep_user.is_active:
            raise HTTPException(
                status_code=409,
                detail="The requested platform admin account is inactive",
            )
        if keep_user.id != current_user.sub:
            raise HTTPException(
                status_code=409,
                detail="The signed-in platform admin must be the account being preserved",
            )
        preserved = [keep_user]
        if body.scope == USER_DEACTIVATE_SCOPE:
            candidates = [
                user for user in users if user.id != keep_user.id and user.is_active
            ]
        else:
            candidates = [user for user in users if user.id != keep_user.id]
        unknown = []
        keep_user_id = keep_user.id
    else:
        preserved = [user for user in users if user.role in USER_CLEANUP_ADMIN_ROLES]
        candidates = [user for user in users if user.role in USER_CLEANUP_DELETABLE_ROLES]
        unknown = [
            user
            for user in users
            if user.role not in USER_CLEANUP_ADMIN_ROLES
            and user.role not in USER_CLEANUP_DELETABLE_ROLES
        ]
        keep_user_id = None

    def role_counts(rows: list[User]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for user in rows:
            counts[user.role] = counts.get(user.role, 0) + 1
        return counts

    return {
        "actor": actor,
        "users": users,
        "preserved": preserved,
        "candidates": candidates,
        "unknown": unknown,
        "keep_user_id": keep_user_id,
        "state_before": {
            "total_users": len(users),
            "active_users": sum(1 for user in users if user.is_active),
            "inactive_users": sum(1 for user in users if not user.is_active),
            "preserved_admin_users": len(preserved),
            "deletable_users": len(candidates),
            "unknown_role_users": len(unknown),
            "preserved_by_role": role_counts(preserved),
            "deletable_by_role": role_counts(candidates),
        },
    }


def _user_cleanup_payload_hash(scope: str, snapshot: dict) -> str:
    return AgentEvidenceService.payload_hash(
        {
            "action": _user_cleanup_action(scope),
            "scope": scope,
            "candidate_ids": sorted(user.id for user in snapshot["candidates"]),
            "preserved_ids": sorted(user.id for user in snapshot["preserved"]),
            "unknown_ids": sorted(user.id for user in snapshot["unknown"]),
            "keep_user_id": snapshot.get("keep_user_id"),
        }
    )


def _user_cleanup_action(scope: str) -> str:
    if scope == USER_DEACTIVATE_SCOPE:
        return USER_DEACTIVATE_ACTION
    if scope == USER_SINGLE_ADMIN_CLEANUP_SCOPE:
        return USER_SINGLE_ADMIN_CLEANUP_ACTION
    return USER_CLEANUP_ACTION


def _user_cleanup_risk(scope: str) -> str:
    return "high" if scope == USER_DEACTIVATE_SCOPE else USER_CLEANUP_RISK


def _user_cleanup_endpoints(scope: str) -> tuple[str, str]:
    if scope == USER_DEACTIVATE_SCOPE:
        return (
            "POST /api/v1/users/deactivation/preview",
            "POST /api/v1/users/deactivation/agent",
        )
    return (
        "POST /api/v1/users/cleanup/preview",
        "POST /api/v1/users/cleanup/agent",
    )


def _user_cleanup_examples(rows: list[User]) -> list[dict]:
    return [
        {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "tenant_id": user.tenant_id,
        }
        for user in rows[:20]
    ]


async def _build_user_cleanup_preview(
    db: AsyncSession,
    current_user: TokenPayload,
    body: UserCleanupRequest,
    *,
    persist_evidence: bool,
) -> tuple[dict, dict]:
    _assert_platform_cleanup_actor(current_user)
    snapshot = await _user_cleanup_snapshot(db, current_user, body)
    cleanup_action = _user_cleanup_action(body.scope)
    cleanup_risk = _user_cleanup_risk(body.scope)
    preview_endpoint, agent_endpoint = _user_cleanup_endpoints(body.scope)
    blocking_errors = []
    if snapshot["unknown"]:
        blocking_errors.append(
            {
                "code": "unknown_user_roles",
                "message": "Unknown user roles must be reviewed before cleanup.",
                "roles": sorted({user.role for user in snapshot["unknown"]}),
                "count": len(snapshot["unknown"]),
            }
        )

    state_after = {
        "total_users": len(snapshot["preserved"]) + len(snapshot["unknown"]),
        "active_users": len(snapshot["preserved"]),
        "inactive_users": len(snapshot["unknown"]),
        "preserved_admin_users": len(snapshot["preserved"]),
        "deletable_users": 0,
        "unknown_role_users": len(snapshot["unknown"]),
    }
    if body.scope == USER_DEACTIVATE_SCOPE:
        state_after = {
            "total_users": snapshot["state_before"]["total_users"],
            "active_users": len(snapshot["preserved"]),
            "inactive_users": snapshot["state_before"]["total_users"] - len(snapshot["preserved"]),
            "preserved_admin_users": len(snapshot["preserved"]),
            "deactivatable_users": 0,
            "unknown_role_users": 0,
        }
    summary = {
        "delete_count": (
            len(snapshot["candidates"]) if body.scope != USER_DEACTIVATE_SCOPE else 0
        ),
        "preserve_count": len(snapshot["preserved"]),
        "preserve_roles": sorted({user.role for user in snapshot["preserved"]}),
        "delete_roles": sorted({user.role for user in snapshot["candidates"]}),
        "delete_by_role": (
            snapshot["state_before"]["deletable_by_role"]
            if body.scope != USER_DEACTIVATE_SCOPE
            else {}
        ),
    }
    if body.scope == USER_DEACTIVATE_SCOPE:
        summary.update(
            {
                "deactivate_count": len(snapshot["candidates"]),
                "deactivate_roles": sorted({user.role for user in snapshot["candidates"]}),
                "deactivate_by_role": snapshot["state_before"]["deletable_by_role"],
            }
        )
    if snapshot.get("keep_user_id"):
        summary["keep_platform_admin_email"] = snapshot["preserved"][0].email
    preview = {
        "ok": not blocking_errors,
        "dry_run": True,
        "preview": True,
        "writes": False,
        "action": cleanup_action,
        "risk": cleanup_risk,
        "permission": USER_CLEANUP_PERMISSION,
        "entity": {"type": USER_CLEANUP_ENTITY_TYPE, "id": USER_CLEANUP_ENTITY_ID},
        "scope": body.scope,
        "state_before": snapshot["state_before"],
        "state_after": state_after,
        "summary": summary,
        "preserved": {
            "roles": sorted({user.role for user in snapshot["preserved"]}),
            "count": len(snapshot["preserved"]),
            "examples": _user_cleanup_examples(snapshot["preserved"]),
        },
        "delete_candidates": {
            "roles": sorted({user.role for user in snapshot["candidates"]}),
            "count": len(snapshot["candidates"]),
            "examples": _user_cleanup_examples(snapshot["candidates"]),
        },
        "blocking_errors": blocking_errors,
        "confirmation_required_for_write": False,
    }
    if blocking_errors:
        preview["next_action"] = "review_unknown_user_roles"
        return preview, snapshot
    if not snapshot["candidates"]:
        preview["next_action"] = "no_cleanup_required"
        return preview, snapshot
    if not persist_evidence:
        preview["next_action"] = "submit_with_confirm_token_after_review"
        return preview, snapshot

    planned_request = {
        "endpoint": preview_endpoint,
        "agent_endpoint": agent_endpoint,
        "body": body.model_dump(mode="json"),
        "idempotency_key_required_for_write": True,
    }
    confirmation_token = AgentEvidenceService.issue_token(
        "users-deactivation" if body.scope == USER_DEACTIVATE_SCOPE else "users-cleanup"
    )
    confirmation_payload = {
        "confirmation_token": confirmation_token,
        "required_permission": USER_CLEANUP_PERMISSION,
        "evidence_id": None,
        "impact": summary,
        "records": [
            {
                "type": USER_CLEANUP_ENTITY_TYPE,
                "id": USER_CLEANUP_ENTITY_ID,
                "delete_count": summary["delete_count"],
                "deactivate_count": summary.get("deactivate_count", 0),
                "preserve_count": len(snapshot["preserved"]),
            }
        ],
    }
    evidence = await AgentEvidenceService(db, snapshot["actor"].tenant_id).persist_preview(
        action=cleanup_action,
        risk=cleanup_risk,
        required_permission=USER_CLEANUP_PERMISSION,
        entity_type=USER_CLEANUP_ENTITY_TYPE,
        entity_id=USER_CLEANUP_ENTITY_ID,
        actor_user_id=current_user.sub,
        payload_hash=_user_cleanup_payload_hash(body.scope, snapshot),
        confirmation_token=confirmation_token,
        planned_endpoint=planned_request["endpoint"],
        state_before=preview["state_before"],
        state_after=preview["state_after"],
        planned_request=planned_request,
        confirmation_payload=confirmation_payload,
    )
    confirmation_payload["evidence_id"] = evidence.id
    preview.update(
        {
            "confirmation_required_for_write": True,
            "planned_request": planned_request,
            "confirmation_payload": confirmation_payload,
            "evidence_id": evidence.id,
            "next_action": "submit_with_confirm_token_after_review",
        }
    )
    return preview, snapshot


async def _apply_user_cleanup(
    db: AsyncSession,
    current_user: TokenPayload,
    body: UserCleanupConfirmationRequest,
    idempotency_key: str,
) -> dict:
    preview, snapshot = await _build_user_cleanup_preview(
        db,
        current_user,
        body,
        persist_evidence=False,
    )
    if preview["blocking_errors"]:
        raise HTTPException(status_code=409, detail=preview["blocking_errors"])
    if not snapshot["candidates"]:
        raise HTTPException(status_code=409, detail="No users remain to clean up")

    evidence_service = AgentEvidenceService(db, snapshot["actor"].tenant_id)
    cleanup_action = _user_cleanup_action(body.scope)
    cleanup_risk = _user_cleanup_risk(body.scope)
    evidence = await evidence_service.find_preview(
        action=cleanup_action,
        entity_type=USER_CLEANUP_ENTITY_TYPE,
        entity_id=USER_CLEANUP_ENTITY_ID,
        payload_hash=_user_cleanup_payload_hash(body.scope, snapshot),
        confirmation_token=body.confirmation_token,
    )
    if not evidence:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "confirmation_mismatch",
                "message": "The user cleanup confirmation does not match the latest preview.",
            },
        )
    if body.evidence_id and body.evidence_id != evidence.id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "evidence_mismatch",
                "message": "The user cleanup evidence does not match the latest preview.",
            },
        )

    candidate_ids = [user.id for user in snapshot["candidates"]]
    deleted_count = 0
    deactivated_count = 0
    if body.scope == USER_DEACTIVATE_SCOPE:
        for user in snapshot["candidates"]:
            user.is_active = False
        deactivated_count = len(snapshot["candidates"])
    else:
        deleted_result = await db.execute(delete(User).where(User.id.in_(candidate_ids)))
        deleted_count = int(deleted_result.rowcount or 0)
    await db.flush()
    after_snapshot = await _user_cleanup_snapshot(db, current_user, body)
    result = {
        "ok": True,
        "action": cleanup_action,
        "risk": cleanup_risk,
        "entity": {"type": USER_CLEANUP_ENTITY_TYPE, "id": USER_CLEANUP_ENTITY_ID},
        "state_before": snapshot["state_before"],
        "state_after": after_snapshot["state_before"],
        "deleted_count": deleted_count,
        "deactivated_count": deactivated_count,
        "preserved_admin_count": len(after_snapshot["preserved"]),
        "confirmation_token": "[accepted]",
        "evidence_id": evidence.id,
        "idempotency_key": idempotency_key,
        "next_action": "review_user_list",
    }
    await evidence_service.mark_executed(
        evidence,
        actor_user_id=current_user.sub,
        idempotency_key=idempotency_key,
        state_after=after_snapshot["state_before"],
        result=result,
        success=True,
    )
    return result


def _tenant_scoped_user_query(user_id: str, current_user: TokenPayload):
    """Look up a user; platform admins see all tenants, others only their own."""
    query = select(User).where(User.id == user_id)
    if current_user.role != UserRole.PLATFORM_ADMIN:
        query = query.where(User.tenant_id == current_user.tenant_id)
    return query


async def _require_client_in_tenant(db: AsyncSession, client_id: str, tenant_id: str | None) -> None:
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context is required for client viewers")
    client_result = await db.execute(
        select(Client).where(Client.id == client_id, Client.tenant_id == tenant_id)
    )
    if not client_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Client does not belong to the selected tenant")


def _user_response(user: User, tenant_name: str | None = None) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        job_title=user.job_title,
        permissions=normalize_permissions(user.role, user.permissions),
        is_active=user.is_active,
        client_id=user.client_id,
        tenant_id=user.tenant_id,
        tenant_name=tenant_name,
    )


def _management_user_state(user: User, tenant_name: str | None = None) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "job_title": user.job_title,
        "permissions": normalize_permissions(user.role, user.permissions),
        "is_active": user.is_active,
        "client_id": user.client_id,
        "tenant_id": user.tenant_id,
        "tenant_name": tenant_name,
    }


async def _management_actor(db: AsyncSession, current_user: TokenPayload) -> User:
    _assert_actor_can_manage_users(current_user)
    actor = await db.scalar(select(User).where(User.id == current_user.sub))
    if not actor or not actor.is_active:
        raise HTTPException(status_code=403, detail="The signed-in admin account is not active")
    if not actor.tenant_id:
        raise HTTPException(status_code=400, detail="Admin audit tenant context is required")
    return actor


async def _prepare_create_management(
    db: AsyncSession,
    current_user: TokenPayload,
    body: UserCreate,
) -> dict:
    try:
        validate_password(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    normalized_email = normalize_email(str(body.email))
    existing = await db.scalar(select(User).where(func.lower(User.email) == normalized_email))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    requested_role = _validate_role(body.role)
    _assert_actor_can_assign_role(current_user, requested_role)
    if requested_role == UserRole.PLATFORM_ADMIN.value:
        await _assert_platform_admin_slot_available(db)

    target_tenant_id = current_user.tenant_id
    if current_user.role == UserRole.PLATFORM_ADMIN:
        if not body.tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id is required for platform admin")
        target_tenant_id = body.tenant_id
    elif body.tenant_id and body.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=403, detail="Tenant admin cannot create users outside this tenant"
        )

    tenant = await db.scalar(select(Tenant).where(Tenant.id == target_tenant_id))
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    client_id = body.client_id if requested_role == UserRole.CLIENT_VIEWER.value else None
    if requested_role == UserRole.CLIENT_VIEWER.value:
        if not client_id:
            raise HTTPException(status_code=400, detail="client_id is required for client_viewer")
        await _require_client_in_tenant(db, client_id, target_tenant_id)

    proposed = {
        "id": "[assigned_on_confirm]",
        "email": normalized_email,
        "full_name": body.full_name,
        "role": requested_role,
        "job_title": body.job_title,
        "permissions": _assignable_permissions_for_role(requested_role, body.permissions),
        "is_active": True,
        "client_id": client_id,
        "tenant_id": target_tenant_id,
        "tenant_name": tenant.name,
    }
    return {
        "entity_id": f"new:{normalized_email}",
        "state_before": {"exists": False, "email": normalized_email},
        "state_after": proposed,
        "changed_fields": [
            "email",
            "full_name",
            "role",
            "job_title",
            "permissions",
            "is_active",
            "client_id",
            "tenant_id",
        ],
        "target_tenant_id": target_tenant_id,
        "target_tenant_name": tenant.name,
        "proposed": proposed,
    }


async def _prepare_update_management(
    db: AsyncSession,
    current_user: TokenPayload,
    body: UserManagementPreviewRequest,
) -> dict:
    if not body.user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if not body.changes or not body.changes.model_fields_set:
        raise HTTPException(status_code=400, detail="At least one user change is required")

    user = await db.scalar(_tenant_scoped_user_query(body.user_id, current_user))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _assert_actor_can_manage_user(current_user, user)
    changes = body.changes
    if user.id == current_user.sub and any(
        field in changes.model_fields_set for field in ("role", "is_active")
    ):
        raise HTTPException(
            status_code=400,
            detail="The sole platform admin account cannot change its own role or active status",
        )

    tenant_name = await db.scalar(select(Tenant.name).where(Tenant.id == user.tenant_id))
    current = _management_user_state(user, tenant_name)
    requested_role = user.role
    if changes.role is not None:
        requested_role = _validate_role(changes.role)
        _assert_actor_can_assign_role(current_user, requested_role)

    requested_client_id = changes.client_id if "client_id" in changes.model_fields_set else user.client_id
    if requested_role == UserRole.CLIENT_VIEWER.value:
        if not requested_client_id:
            raise HTTPException(status_code=400, detail="client_id is required for client_viewer")
        await _require_client_in_tenant(db, requested_client_id, user.tenant_id)
    else:
        requested_client_id = None

    proposed = dict(current)
    if "full_name" in changes.model_fields_set:
        if not changes.full_name or not changes.full_name.strip():
            raise HTTPException(status_code=400, detail="Full name cannot be empty")
        proposed["full_name"] = changes.full_name.strip()
    if changes.role is not None:
        proposed["role"] = requested_role
    proposed["client_id"] = requested_client_id
    if "job_title" in changes.model_fields_set:
        proposed["job_title"] = changes.job_title
    if changes.permissions is not None or changes.role is not None:
        proposed["permissions"] = _assignable_permissions_for_role(
            requested_role, changes.permissions
        )
    if "is_active" in changes.model_fields_set:
        proposed["is_active"] = changes.is_active

    await _validate_platform_admin_transition(
        db,
        user,
        requested_role=requested_role,
        requested_active=proposed["is_active"],
    )

    changed_fields = [
        field
        for field in ("full_name", "role", "job_title", "permissions", "client_id", "is_active")
        if current[field] != proposed[field]
    ]
    if not changed_fields:
        raise HTTPException(status_code=400, detail="The requested user changes are a no-op")
    return {
        "entity_id": user.id,
        "state_before": current,
        "state_after": proposed,
        "changed_fields": changed_fields,
        "user": user,
        "proposed": proposed,
    }


async def _prepare_reset_management(
    db: AsyncSession,
    current_user: TokenPayload,
    body: UserManagementPreviewRequest,
) -> dict:
    if not body.user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if not body.new_password:
        raise HTTPException(status_code=400, detail="new_password is required")
    try:
        validate_password(body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = await db.scalar(_tenant_scoped_user_query(body.user_id, current_user))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _assert_actor_can_manage_user(current_user, user)
    tenant_name = await db.scalar(select(Tenant.name).where(Tenant.id == user.tenant_id))
    state = _management_user_state(user, tenant_name)
    return {
        "entity_id": user.id,
        "state_before": state,
        "state_after": state,
        "changed_fields": ["password"],
        "user": user,
    }


def _redacted_management_body(body: UserManagementPreviewRequest) -> dict:
    payload = body.model_dump(mode="json", exclude_none=True)
    if payload.get("user", {}).get("password"):
        payload["user"]["password"] = "[provided_at_confirmation]"
    if payload.get("new_password"):
        payload["new_password"] = "[provided_at_confirmation]"
    return payload


async def _build_user_management_preview(
    db: AsyncSession,
    current_user: TokenPayload,
    body: UserManagementPreviewRequest,
    *,
    persist_evidence: bool,
) -> tuple[dict, dict]:
    actor = await _management_actor(db, current_user)
    if body.action == "create":
        if not body.user:
            raise HTTPException(status_code=400, detail="user is required for create")
        await check_limit("users")(current_user=current_user, db=db)
        plan = await _prepare_create_management(db, current_user, body.user)
    elif body.action == "update":
        plan = await _prepare_update_management(db, current_user, body)
    else:
        plan = await _prepare_reset_management(db, current_user, body)

    action = f"users.{body.action}"
    payload_hash = AgentEvidenceService.payload_hash(
        {
            "action": action,
            "entity_id": plan["entity_id"],
            "state_before": plan["state_before"],
            "request": _redacted_management_body(body),
        }
    )
    changed_fields = plan["changed_fields"]
    preview = {
        "ok": True,
        "dry_run": True,
        "preview": True,
        "writes": False,
        "action": action,
        "risk": USER_MANAGEMENT_RISK,
        "permission": USER_MANAGEMENT_PERMISSION,
        "entity": {"type": USER_MANAGEMENT_ENTITY_TYPE, "id": plan["entity_id"]},
        "state_before": plan["state_before"],
        "state_after": plan["state_after"],
        "changes": [
            {
                "field": field,
                "before": plan["state_before"].get(field),
                "after": plan["state_after"].get(field),
            }
            for field in changed_fields
        ],
        "changed_count": len(changed_fields),
        "confirmation_required_for_write": False,
    }
    if not persist_evidence:
        preview["next_action"] = "submit_with_confirm_token_after_review"
        return preview, {**plan, "actor": actor, "action": action, "payload_hash": payload_hash}

    planned_request = {
        "endpoint": "POST /api/v1/users/management/preview",
        "agent_endpoint": "POST /api/v1/users/management/agent",
        "body": _redacted_management_body(body),
        "idempotency_key_required_for_write": True,
        "secret_fields_required_at_confirmation": [
            field
            for field in ("user.password", "new_password")
            if field == "user.password" and body.user and body.user.password
            or field == "new_password" and body.new_password
        ],
    }
    confirmation_token = AgentEvidenceService.issue_token("users-management")
    confirmation_payload = {
        "confirmation_token": confirmation_token,
        "required_permission": USER_MANAGEMENT_PERMISSION,
        "evidence_id": None,
        "impact": {"changed_count": len(changed_fields), "changed_fields": changed_fields},
        "records": [
            {
                "type": USER_MANAGEMENT_ENTITY_TYPE,
                "id": plan["entity_id"],
                "changed_fields": changed_fields,
            }
        ],
    }
    evidence = await AgentEvidenceService(db, actor.tenant_id).persist_preview(
        action=action,
        risk=USER_MANAGEMENT_RISK,
        required_permission=USER_MANAGEMENT_PERMISSION,
        entity_type=USER_MANAGEMENT_ENTITY_TYPE,
        entity_id=plan["entity_id"],
        actor_user_id=current_user.sub,
        payload_hash=payload_hash,
        confirmation_token=confirmation_token,
        planned_endpoint=planned_request["endpoint"],
        state_before=plan["state_before"],
        state_after=plan["state_after"],
        planned_request=planned_request,
        confirmation_payload=confirmation_payload,
    )
    confirmation_payload["evidence_id"] = evidence.id
    preview.update(
        {
            "confirmation_required_for_write": True,
            "planned_request": planned_request,
            "confirmation_payload": confirmation_payload,
            "evidence_id": evidence.id,
            "next_action": "submit_with_confirm_token_after_review",
        }
    )
    return preview, {**plan, "actor": actor, "action": action, "payload_hash": payload_hash}


async def _apply_user_management(
    db: AsyncSession,
    current_user: TokenPayload,
    body: UserManagementAgentRequest,
    idempotency_key: str,
) -> dict:
    preview, plan = await _build_user_management_preview(
        db,
        current_user,
        UserManagementPreviewRequest(
            action=body.action,
            user=body.user,
            user_id=body.user_id,
            changes=body.changes,
            new_password=body.new_password,
        ),
        persist_evidence=False,
    )
    evidence_service = AgentEvidenceService(db, plan["actor"].tenant_id)
    evidence = await evidence_service.find_preview(
        action=plan["action"],
        entity_type=USER_MANAGEMENT_ENTITY_TYPE,
        entity_id=plan["entity_id"],
        payload_hash=plan["payload_hash"],
        confirmation_token=body.confirmation_token,
    )
    if not evidence or evidence.id != body.evidence_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "confirmation_mismatch",
                "message": "The user management confirmation or evidence id does not match the latest preview.",
            },
        )

    if body.action == "create":
        user_body = body.user
        assert user_body is not None
        await check_limit("users")(current_user=current_user, db=db)
        proposed = plan["proposed"]
        user = User(
            tenant_id=proposed["tenant_id"],
            email=proposed["email"],
            hashed_password=hash_password(user_body.password),
            full_name=proposed["full_name"],
            role=proposed["role"],
            job_title=proposed["job_title"],
            permissions=proposed["permissions"],
            client_id=proposed["client_id"],
            is_active=True,
        )
        db.add(user)
        await db.flush()
        state_after = _management_user_state(user, plan.get("target_tenant_name"))
        changed_fields = plan["changed_fields"]
        entity_id = user.id
    elif body.action == "update":
        user = plan["user"]
        proposed = plan["proposed"]
        changed_fields = plan["changed_fields"]
        for field in changed_fields:
            if field in {"full_name", "role", "job_title", "permissions", "client_id", "is_active"}:
                setattr(user, field, proposed[field])
        await db.flush()
        state_after = _management_user_state(user, proposed.get("tenant_name"))
        entity_id = user.id
    else:
        user = plan["user"]
        user.hashed_password = hash_password(body.new_password or "")
        await db.flush()
        state_after = plan["state_after"]
        changed_fields = plan["changed_fields"]
        entity_id = user.id

    result = {
        "ok": True,
        "action": plan["action"],
        "risk": USER_MANAGEMENT_RISK,
        "entity": {"type": USER_MANAGEMENT_ENTITY_TYPE, "id": entity_id},
        "state_before": plan["state_before"],
        "state_after": state_after,
        "changed_fields": changed_fields,
        "confirmation_token": "[accepted]",
        "evidence_id": evidence.id,
        "idempotency_key": idempotency_key,
        "next_action": "review_user_audit",
    }
    await evidence_service.mark_executed(
        evidence,
        actor_user_id=current_user.sub,
        idempotency_key=idempotency_key,
        state_after=state_after,
        result=result,
        success=True,
    )
    return result


@router.get("/")
async def list_users(
    page: PaginationParams = Depends(),
    current_user: TokenPayload = Depends(require_permission(UserPermission.USERS_MANAGE.value)),
    db: AsyncSession = Depends(get_db_session),
):
    _assert_actor_can_manage_users(current_user)
    base_query = select(User, Tenant.name.label("tenant_name")).outerjoin(
        Tenant, Tenant.id == User.tenant_id
    )
    if current_user.role != UserRole.PLATFORM_ADMIN:
        base_query = base_query.where(User.tenant_id == current_user.tenant_id)

    total_query = select(func.count(User.id)).select_from(User)
    if current_user.role != UserRole.PLATFORM_ADMIN:
        total_query = total_query.where(User.tenant_id == current_user.tenant_id)
    total = int((await db.execute(total_query)).scalar() or 0)

    rows = (
        await db.execute(
            base_query.order_by(func.coalesce(Tenant.name, ""), User.full_name, User.id)
            .offset(page.offset)
            .limit(page.limit)
        )
    ).all()
    has_more = page.offset + len(rows) < total

    return {
        "items": [
            _user_response(user, tenant_name)
            for user, tenant_name in rows
        ],
        "total": total,
        "total_is_estimate": False,
        "limit": page.limit,
        "offset": page.offset,
        "has_more": has_more,
    }


@router.post("/cleanup/preview")
async def preview_non_admin_user_cleanup(
    body: UserCleanupPreviewRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Preview a governed global user cleanup without deleting any account."""
    preview, _snapshot = await _build_user_cleanup_preview(
        db,
        current_user,
        body,
        persist_evidence=True,
    )
    await db.flush()
    return preview


@router.post("/cleanup/agent")
async def confirm_non_admin_user_cleanup(
    body: UserCleanupAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Confirm a previously previewed governed global user cleanup."""
    _assert_platform_cleanup_actor(current_user)
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for user cleanup",
            },
        )

    actor = await db.scalar(select(User).where(User.id == current_user.sub))
    if not actor:
        raise HTTPException(status_code=403, detail="Platform admin account not found")

    async def execute():
        return await _apply_user_cleanup(db, current_user, body, x_idempotency_key)

    return await IdempotencyService(db, actor.tenant_id).run(
        key=x_idempotency_key,
        operation=f"{_user_cleanup_action(body.scope)}.agent_confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/deactivation/preview")
async def preview_user_deactivation(
    body: UserDeactivationPreviewRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Preview reversible deactivation of active users except one platform admin."""
    preview, _snapshot = await _build_user_cleanup_preview(
        db,
        current_user,
        body,
        persist_evidence=True,
    )
    await db.flush()
    return preview


@router.post("/deactivation/agent")
async def confirm_user_deactivation(
    body: UserDeactivationAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Confirm reversible deactivation from a previously persisted preview."""
    _assert_platform_cleanup_actor(current_user)
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for user deactivation",
            },
        )

    actor = await db.scalar(select(User).where(User.id == current_user.sub))
    if not actor:
        raise HTTPException(status_code=403, detail="Platform admin account not found")

    async def execute():
        return await _apply_user_cleanup(db, current_user, body, x_idempotency_key)

    return await IdempotencyService(db, actor.tenant_id).run(
        key=x_idempotency_key,
        operation=f"{USER_DEACTIVATE_ACTION}.agent_confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/management/preview")
async def preview_user_management(
    body: UserManagementPreviewRequest,
    current_user: TokenPayload = Depends(require_permission(UserPermission.USERS_MANAGE.value)),
    db: AsyncSession = Depends(get_db_session),
):
    """Preview one governed user-management mutation without changing users."""
    preview, _plan = await _build_user_management_preview(
        db,
        current_user,
        body,
        persist_evidence=True,
    )
    await db.flush()
    return preview


@router.post("/management/agent")
async def confirm_user_management(
    body: UserManagementAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_permission(UserPermission.USERS_MANAGE.value)),
    db: AsyncSession = Depends(get_db_session),
):
    """Apply a previously previewed user-management mutation."""
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for user management",
            },
        )
    actor = await _management_actor(db, current_user)

    async def execute():
        return await _apply_user_management(db, current_user, body, x_idempotency_key)

    return await IdempotencyService(db, actor.tenant_id).run(
        key=x_idempotency_key,
        operation=f"users.{body.action}.agent_confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    _limits=Depends(check_limit("users")),
    current_user: TokenPayload = Depends(require_permission(UserPermission.USERS_MANAGE.value)),
    db: AsyncSession = Depends(get_db_session),
):
    _assert_actor_can_manage_users(current_user)
    normalized_email = normalize_email(str(body.email))

    # Check uniqueness
    existing = await db.execute(select(User).where(func.lower(User.email) == normalized_email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    requested_role = _validate_role(body.role)
    _assert_actor_can_assign_role(current_user, requested_role)
    if requested_role == UserRole.PLATFORM_ADMIN.value:
        await _assert_platform_admin_slot_available(db)

    target_tenant_id = current_user.tenant_id
    if current_user.role == UserRole.PLATFORM_ADMIN:
        if not body.tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id is required for platform admin")
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == body.tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        target_tenant_id = tenant.id
    elif body.tenant_id and body.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=403, detail="Tenant admin cannot create users outside this tenant"
        )

    if requested_role == UserRole.CLIENT_VIEWER.value:
        if not body.client_id:
            raise HTTPException(status_code=400, detail="client_id is required for client_viewer")
        await _require_client_in_tenant(db, body.client_id, target_tenant_id)

    user = User(
        tenant_id=target_tenant_id,
        email=normalized_email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=requested_role,
        job_title=body.job_title,
        permissions=_assignable_permissions_for_role(requested_role, body.permissions),
        client_id=body.client_id if requested_role == UserRole.CLIENT_VIEWER.value else None,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    tenant_name = await db.scalar(select(Tenant.name).where(Tenant.id == user.tenant_id))
    return _user_response(user, tenant_name)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UserUpdate,
    current_user: TokenPayload = Depends(require_permission(UserPermission.USERS_MANAGE.value)),
    db: AsyncSession = Depends(get_db_session),
):
    _assert_actor_can_manage_users(current_user)
    result = await db.execute(_tenant_scoped_user_query(user_id, current_user))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _assert_actor_can_manage_user(current_user, user)
    if user.id == current_user.sub and any(
        field in body.model_fields_set for field in ("role", "is_active")
    ):
        raise HTTPException(
            status_code=400,
            detail="Use a separate account to change your own role or active status",
        )

    requested_role = user.role
    if body.role is not None:
        requested_role = _validate_role(body.role)
        _assert_actor_can_assign_role(current_user, requested_role)

    client_id_provided = "client_id" in body.model_fields_set
    requested_client_id = body.client_id if client_id_provided else user.client_id
    if requested_role == UserRole.CLIENT_VIEWER.value:
        if not requested_client_id:
            raise HTTPException(status_code=400, detail="client_id is required for client_viewer")
        await _require_client_in_tenant(db, requested_client_id, user.tenant_id)
    else:
        requested_client_id = None

    requested_active = body.is_active if "is_active" in body.model_fields_set else user.is_active
    await _validate_platform_admin_transition(
        db,
        user,
        requested_role=requested_role,
        requested_active=requested_active,
    )

    if "full_name" in body.model_fields_set:
        if not body.full_name or not body.full_name.strip():
            raise HTTPException(status_code=400, detail="Full name cannot be empty")
        user.full_name = body.full_name.strip()
    if body.role is not None:
        user.role = requested_role
    user.client_id = requested_client_id
    if "job_title" in body.model_fields_set:
        user.job_title = body.job_title
    if body.permissions is not None or body.role is not None:
        user.permissions = _assignable_permissions_for_role(requested_role, body.permissions)
    if "is_active" in body.model_fields_set:
        user.is_active = body.is_active

    await db.flush()
    tenant_name = await db.scalar(select(Tenant.name).where(Tenant.id == user.tenant_id))
    return _user_response(user, tenant_name)


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    body: PasswordReset,
    current_user: TokenPayload = Depends(require_permission(UserPermission.USERS_MANAGE.value)),
    db: AsyncSession = Depends(get_db_session),
):
    _assert_actor_can_manage_users(current_user)
    result = await db.execute(_tenant_scoped_user_query(user_id, current_user))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _assert_actor_can_manage_user(current_user, user)

    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user.hashed_password = hash_password(body.new_password)
    await db.flush()
    return {"success": True, "message": "Password reset successfully"}


class BatchUserAction(BaseModel):
    user_ids: list[str]
    action: str  # "activate" | "deactivate"


@router.post("/batch")
async def batch_user_action(
    body: BatchUserAction,
    current_user: TokenPayload = Depends(require_permission(UserPermission.USERS_MANAGE.value)),
    db: AsyncSession = Depends(get_db_session),
):
    """Batch activate/deactivate users (e.g. disable all temp workers at once)."""
    _assert_actor_can_manage_users(current_user)
    if body.action not in {"activate", "deactivate"}:
        raise HTTPException(status_code=400, detail="Unsupported batch action")
    is_active = body.action == "activate"
    target_users: list[User] = []
    for uid in body.user_ids:
        result = await db.execute(_tenant_scoped_user_query(uid, current_user))
        user = result.scalar_one_or_none()
        if user:
            _assert_actor_can_manage_user(current_user, user)
            if user.role == UserRole.PLATFORM_ADMIN.value:
                raise HTTPException(
                    status_code=409,
                    detail="Platform admin accounts cannot be batch activated or deactivated",
                )
            if user.id == current_user.sub:
                raise HTTPException(
                    status_code=400,
                    detail="Use a separate account to change your own active status",
                )
            target_users.append(user)

    for user in target_users:
        user.is_active = is_active

    await db.flush()
    return {"updated": len(target_users), "action": body.action}
