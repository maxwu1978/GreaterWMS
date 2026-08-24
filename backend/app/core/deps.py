"""
FastAPI dependency injection for authentication, tenant context, and subscription check.

CRITICAL DESIGN: get_current_user does NOT depend on get_db_session.
It validates the JWT, sets ContextVars (tenant_id, is_platform_admin), and
uses a separate short-lived session to verify that the account still exists
and matches the token. This ensures that when get_db_session runs later (in
the endpoint), the ContextVars are already set and the PostgreSQL session is
initialized with the correct RLS parameters.

Dependency order in an endpoint:
  1. get_current_user → validates JWT → sets ContextVars
  2. get_db_session → reads ContextVars → sets PostgreSQL SET commands
  3. endpoint logic → queries run under correct RLS context
"""

import hmac
import time
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.core.config import settings
from app.core.database import (
    apply_session_context,
    async_session_factory,
    get_db_session,
    set_current_tenant_id,
    set_is_platform_admin,
)
from app.core.security import (
    TokenPayload,
    UserRole,
    has_permission,
    normalize_permissions,
    verify_token,
)

bearer_scheme = HTTPBearer()

# In-memory subscription cache with 5-minute TTL
_CACHE_TTL = 300
_subscription_cache: dict[str, dict] = {}


async def get_mailtask_ingest_context(
    x_mailtask_token: str | None = Header(default=None, alias="X-MailTask-Token"),
) -> TokenPayload:
    """Authenticate the read-only mailbox Skill's controlled intake boundary.

    This is deliberately separate from human JWT authentication. The token is
    tenant-bound, can be revoked by rotating the deployment secret, and is
    disabled by default until the mailbox Skill is ready for a staging run.
    """
    if (
        not settings.MAILTASK_INGEST_ENABLED
        or not settings.MAILTASK_INGEST_TOKEN
        or not settings.MAILTASK_INGEST_TENANT_ID
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MailTask intake is not enabled",
        )
    if not x_mailtask_token or not hmac.compare_digest(
        x_mailtask_token.strip(), settings.MAILTASK_INGEST_TOKEN.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MailTask intake token",
        )

    set_current_tenant_id(settings.MAILTASK_INGEST_TENANT_ID)
    set_is_platform_admin(False)
    return TokenPayload(
        sub="service:mailtask-skill",
        tenant_id=settings.MAILTASK_INGEST_TENANT_ID,
        role=UserRole.OPERATOR,
        permissions=[
            "mailtask.execute",
            "mailtask.manage",
        ],
        exp=datetime.now(UTC),
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> TokenPayload:
    """
    Extract and validate JWT token, set tenant context for RLS.

    This dependency does NOT take the request's db session parameter — it must
    set ContextVars before get_db_session initializes its PostgreSQL SET
    commands. Its account check uses a separate short-lived session.
    """
    token_data = verify_token(credentials.credentials)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Set tenant context for RLS + platform admin flag
    if token_data.role == UserRole.PLATFORM_ADMIN:
        set_current_tenant_id(None)
        set_is_platform_admin(True)
    else:
        set_current_tenant_id(token_data.tenant_id)
        set_is_platform_admin(False)

    # JWTs are intentionally long-lived for warehouse shifts, so validate the
    # account record on every request. This makes deletion, deactivation, and
    # role/tenant changes take effect immediately instead of after token expiry.
    from app.models.tenant import User

    async with async_session_factory() as db:
        await apply_session_context(
            db,
            tenant_id=token_data.tenant_id,
            is_platform_admin=token_data.role == UserRole.PLATFORM_ADMIN,
        )
        user = await db.scalar(select(User).where(User.id == token_data.sub))

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is no longer active",
        )
    if (
        user.role != token_data.role.value
        or user.tenant_id != token_data.tenant_id
        or user.client_id != token_data.client_id
        or normalize_permissions(user.role, user.permissions)
        != normalize_permissions(token_data.role, token_data.permissions)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is no longer valid; please sign in again",
        )

    if token_data.role == UserRole.PLATFORM_ADMIN:
        return token_data  # Platform admin bypasses subscription check

    # Check subscription status (creates its own short-lived session)
    if token_data.tenant_id:
        await _check_subscription(token_data.tenant_id)

    return token_data


async def _check_subscription(tenant_id: str):
    """
    Verify tenant has an active subscription. Raises 402 if not.
    Uses its own session (not the request's session) to avoid
    contaminating the RLS context.
    """
    from datetime import date

    from app.models.subscription import Subscription, SubscriptionStatus

    # Check cache first (with TTL)
    cached = _subscription_cache.get(tenant_id)
    if cached and cached.get("allowed") and (time.time() - cached.get("cached_at", 0)) < _CACHE_TTL:
        return

    # Create a short-lived session just for subscription lookup.
    # This session has is_platform_admin=false and tenant_id set,
    # so it correctly reads only this tenant's subscription.
    async with async_session_factory() as db:
        await apply_session_context(db, tenant_id=tenant_id)
        result = await db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
        sub = result.scalar_one_or_none()

    if not sub:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "no_subscription",
                "message": "No active subscription. Please sign up for a plan.",
                "plans_url": "/api/v1/subscriptions/plans",
            },
        )

    today = date.today()

    if sub.status == SubscriptionStatus.TRIAL.value:
        if sub.trial_end_date and today <= sub.trial_end_date:
            _subscription_cache[tenant_id] = {
                "allowed": True,
                "cached_at": time.time(),
                "status": "trial",
            }
            return
        raise HTTPException(
            status_code=402,
            detail={
                "error": "trial_expired",
                "message": "Your free trial has expired. Please choose a plan to continue.",
            },
        )

    if sub.status == SubscriptionStatus.ACTIVE.value:
        if sub.current_period_end and today > sub.current_period_end:
            raise HTTPException(
                status_code=402, detail={"error": "expired", "message": "Subscription expired."}
            )
        _subscription_cache[tenant_id] = {
            "allowed": True,
            "cached_at": time.time(),
            "status": "active",
        }
        return

    if sub.status == SubscriptionStatus.PAST_DUE.value:
        _subscription_cache[tenant_id] = {
            "allowed": True,
            "cached_at": time.time(),
            "status": "past_due",
        }
        return

    if sub.status == SubscriptionStatus.CANCELLED.value:
        if sub.current_period_end and today <= sub.current_period_end:
            _subscription_cache[tenant_id] = {
                "allowed": True,
                "cached_at": time.time(),
                "status": "cancelled_active",
            }
            return
        raise HTTPException(
            status_code=402,
            detail={"error": "cancelled", "message": "Subscription cancelled and expired."},
        )

    raise HTTPException(
        status_code=402, detail={"error": "inactive", "message": "Subscription is not active."}
    )


def require_role(*allowed_roles: UserRole):
    """Dependency factory that enforces role-based access."""

    async def _check_role(
        current_user: TokenPayload = Depends(get_current_user),
    ) -> TokenPayload:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' not authorized. Required: {[r.value for r in allowed_roles]}",
            )
        return current_user

    return _check_role


def client_scope_filter(current_user: TokenPayload) -> str | None:
    """
    Data scoping (not authorization): return the client_id the user's queries
    must be restricted to, or None when the user may see all clients.

    Client viewers are limited to their own client's rows; every other role
    (and a client viewer without a client_id claim) is unrestricted.
    """
    if current_user.role == UserRole.CLIENT_VIEWER and current_user.client_id:
        return current_user.client_id
    return None


def require_permission(*required_permissions: str):
    """Dependency factory that enforces fine-grained user permissions."""

    async def _check_permission(
        current_user: TokenPayload = Depends(get_current_user),
        db=Depends(get_db_session),
    ) -> TokenPayload:
        if current_user.role == UserRole.PLATFORM_ADMIN:
            return current_user

        from app.models.tenant import User

        result = await db.execute(select(User).where(User.id == current_user.sub))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        permissions = getattr(user, "permissions", None) or current_user.permissions
        for required_permission in required_permissions:
            if has_permission(current_user.role, permissions, required_permission):
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission. Need one of: {list(required_permissions)}",
        )

    return _check_permission


def clear_subscription_cache(tenant_id: str | None = None):
    """Clear subscription cache (call after plan changes)."""
    if tenant_id:
        _subscription_cache.pop(tenant_id, None)
    else:
        _subscription_cache.clear()
