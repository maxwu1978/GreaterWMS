"""
Plan limit enforcement — dependency injection for checking usage against plan limits.

Usage in endpoints:
    @router.post("/clients/")
    async def create_client(
        _limits = Depends(check_limit("clients")),
        ...
    ):
"""

from fastapi import Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user
from app.core.security import TokenPayload, UserRole
from app.models.client import Client
from app.models.inventory import SKU
from app.models.subscription import PlanTier, Subscription
from app.models.tenant import User
from app.models.warehouse import Warehouse


async def _get_plan_for_tenant(db: AsyncSession, tenant_id: str) -> PlanTier | None:
    """Get the plan tier for a tenant's active subscription."""
    result = await db.execute(
        select(PlanTier)
        .join(Subscription, Subscription.plan_id == PlanTier.id)
        .where(Subscription.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


# Resource type → (model class, count filter field, plan limit field)
_RESOURCE_MAP = {
    "clients": (Client, Client.is_active == True, "max_clients"),  # noqa: E712
    "skus": (SKU, None, "max_skus"),
    "users": (User, User.is_active == True, "max_users"),  # noqa: E712
    "warehouses": (Warehouse, Warehouse.is_active == True, "max_warehouses"),  # noqa: E712
}


def check_limit(resource: str):
    """
    FastAPI dependency that checks if tenant has room to create more of a resource.
    Raises 403 if at or over the plan limit.

    Usage: Depends(check_limit("clients"))
    """

    async def _check(
        current_user: TokenPayload = Depends(get_current_user),
        db: AsyncSession = Depends(get_db_session),
    ):
        # Platform admin bypasses limits
        if current_user.role == UserRole.PLATFORM_ADMIN:
            return

        tenant_id = current_user.tenant_id
        if not tenant_id:
            return

        plan = await _get_plan_for_tenant(db, tenant_id)
        if not plan:
            raise HTTPException(
                status_code=402,
                detail="No active subscription. Please subscribe to a plan.",
            )

        if resource not in _RESOURCE_MAP:
            return

        model_class, filter_expr, limit_field = _RESOURCE_MAP[resource]
        max_allowed = getattr(plan, limit_field, 999999)

        # Count current usage
        query = select(func.count(model_class.id)).where(model_class.tenant_id == tenant_id)
        if filter_expr is not None:
            query = query.where(filter_expr)

        current_count = (await db.execute(query)).scalar() or 0

        if current_count >= max_allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "plan_limit_exceeded",
                    "resource": resource,
                    "current": current_count,
                    "limit": max_allowed,
                    "plan": plan.code,
                    "message": f"Your {plan.name} plan allows up to {max_allowed} {resource}. "
                    f"You currently have {current_count}. Please upgrade your plan.",
                    "upgrade_url": "/subscriptions/plans",
                },
            )

    return _check


async def check_feature(feature_name: str, current_user: TokenPayload, db: AsyncSession):
    """
    Check if a feature is enabled for the tenant's plan.
    Call directly in endpoint logic (not as Depends).

    Usage:
        await check_feature("shopify", current_user, db)
    """
    if current_user.role == UserRole.PLATFORM_ADMIN:
        return

    tenant_id = current_user.tenant_id
    if not tenant_id:
        return

    plan = await _get_plan_for_tenant(db, tenant_id)
    if not plan:
        raise HTTPException(status_code=402, detail="No active subscription.")

    features = plan.features or {}
    if not features.get(feature_name, False):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "feature_not_available",
                "feature": feature_name,
                "plan": plan.code,
                "message": f"The '{feature_name}' feature is not available on your {plan.name} plan. Please upgrade.",
                "upgrade_url": "/subscriptions/plans",
            },
        )
