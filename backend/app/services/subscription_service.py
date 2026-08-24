"""
Subscription Service — trial, activation, upgrade, cancellation, Stripe integration.
"""

import secrets
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import UserRole, hash_password, normalize_email
from app.models.client import Client
from app.models.inventory import SKU
from app.models.subscription import PlanTier, Subscription, SubscriptionStatus
from app.models.tenant import Tenant, User
from app.models.warehouse import Warehouse
from app.services.email_service import email_delivery_enabled, send_verification_email


class SubscriptionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Plan Queries ───

    async def list_plans(self) -> list[PlanTier]:
        result = await self.db.execute(
            select(PlanTier)
            .where(PlanTier.is_active == True)  # noqa: E712
            .order_by(PlanTier.sort_order)
        )
        return list(result.scalars())

    async def get_plan_by_code(self, code: str) -> PlanTier | None:
        result = await self.db.execute(select(PlanTier).where(PlanTier.code == code))
        return result.scalar_one_or_none()

    # ─── Registration + Trial ───

    async def register_trial(
        self,
        company_name: str,
        company_code: str,
        admin_email: str,
        admin_password: str,
        admin_name: str,
        plan_code: str = "starter",
        accept_terms: bool = False,
        accept_risk_notice: bool = False,
    ) -> dict:
        """
        Self-service registration: creates Tenant + Admin User + Trial Subscription.
        Returns tenant_id and a JWT token for immediate login.
        """
        normalized_email = normalize_email(admin_email)
        normalized_code = company_code.strip().upper()

        # Check uniqueness
        existing = await self.db.execute(
            select(Tenant.id).where(
                or_(
                    Tenant.code == normalized_code,
                    func.lower(Tenant.contact_email) == normalized_email,
                )
            )
        )
        if existing.scalar_one_or_none():
            return {"success": False, "error": "Company code or email already registered"}

        existing_user = await self.db.execute(
            select(User.id).where(func.lower(User.email) == normalized_email)
        )
        if existing_user.scalar_one_or_none():
            return {"success": False, "error": "Company code or email already registered"}

        # Get plan
        plan = await self.get_plan_by_code(plan_code)
        if not plan:
            return {"success": False, "error": f"Plan '{plan_code}' not found"}

        # Create tenant
        approval_required = settings.REGISTRATION_APPROVAL_REQUIRED
        tenant = Tenant(
            name=company_name,
            code=normalized_code,
            contact_email=normalized_email,
            plan_tier=plan_code,
            is_active=True,
            approval_status="pending" if approval_required else "approved",
            settings={
                "legal_acceptance": {
                    "terms_accepted": accept_terms,
                    "risk_notice_accepted": accept_risk_notice,
                    "accepted_at": datetime.now(UTC).isoformat(),
                }
            },
        )
        self.db.add(tenant)
        await self.db.flush()

        # Create admin user
        email_verification_required = (
            settings.EMAIL_VERIFICATION_REQUIRED and email_delivery_enabled()
        )
        verification_token = secrets.token_urlsafe(32) if email_verification_required else None
        user = User(
            tenant_id=tenant.id,
            email=normalized_email,
            hashed_password=hash_password(admin_password),
            full_name=admin_name,
            role=UserRole.TENANT_ADMIN.value,
            is_active=True,
            is_email_verified=not email_verification_required,
            email_verification_token=verification_token,
            email_verification_sent_at=datetime.now(UTC) if email_verification_required else None,
        )
        self.db.add(user)

        # Create trial subscription
        trial_end = date.today() + timedelta(days=plan.trial_days)
        subscription = Subscription(
            tenant_id=tenant.id,
            plan_id=plan.id,
            status=SubscriptionStatus.TRIAL.value,
            trial_end_date=trial_end,
            current_period_start=date.today(),
            current_period_end=trial_end,
        )
        self.db.add(subscription)
        await self.db.flush()
        # Commit the account BEFORE any external email call: a verification link must
        # never be emailed for an account that could still roll back. (Email failure
        # after this point leaves a valid account; the user can request a resend.)
        await self.db.commit()

        if email_verification_required and verification_token:
            verification_url = (
                f"{settings.API_BASE_URL.rstrip('/')}{settings.API_V1_PREFIX}/subscriptions/verify-email"
                f"?token={verification_token}"
            )
            send_result = await send_verification_email(
                to_email=normalized_email,
                company_name=company_name,
                verification_url=verification_url,
            )
            if not send_result.get("success"):
                return {
                    "success": False,
                    "error": "Failed to send verification email. Please try again.",
                }

            return {
                "success": True,
                "tenant_id": tenant.id,
                "user_id": user.id,
                "plan": plan_code,
                "trial_ends": trial_end.isoformat(),
                "verification_required": True,
                "message": f"Verification email sent to {normalized_email}. Please verify before signing in.",
            }

        if approval_required:
            # No login token while pending: the login gate rejects the whole
            # tenant until a platform admin approves it.
            return {
                "success": True,
                "tenant_id": tenant.id,
                "user_id": user.id,
                "plan": plan_code,
                "trial_ends": trial_end.isoformat(),
                "verification_required": False,
                "pending_approval": True,
                "message": (
                    "Registration received. A platform administrator will review your "
                    "workspace; you can sign in once it is approved."
                ),
            }

        # Generate token for immediate login
        from app.core.security import create_access_token

        token = create_access_token(
            user_id=user.id,
            role=UserRole.TENANT_ADMIN,
            tenant_id=tenant.id,
        )

        return {
            "success": True,
            "tenant_id": tenant.id,
            "user_id": user.id,
            "access_token": token,
            "plan": plan_code,
            "trial_ends": trial_end.isoformat(),
            "verification_required": False,
        }

    # ─── Subscription Status ───

    async def get_subscription(self, tenant_id: str) -> Subscription | None:
        result = await self.db.execute(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def check_subscription_active(self, tenant_id: str) -> dict:
        """
        Check if a tenant has an active/trial subscription.
        Returns status info used by deps.py to gate access.
        """
        sub = await self.get_subscription(tenant_id)
        if not sub:
            return {
                "allowed": False,
                "status": "no_subscription",
                "message": "No subscription found. Please sign up.",
            }

        today = date.today()

        if sub.status == SubscriptionStatus.TRIAL.value:
            if sub.trial_end_date and today <= sub.trial_end_date:
                days_left = (sub.trial_end_date - today).days
                return {
                    "allowed": True,
                    "status": "trial",
                    "days_left": days_left,
                    "plan_id": sub.plan_id,
                }
            else:
                # Trial expired
                sub.status = SubscriptionStatus.EXPIRED.value
                await self.db.flush()
                return {
                    "allowed": False,
                    "status": "trial_expired",
                    "message": "Your free trial has expired. Please choose a plan to continue.",
                }

        if sub.status == SubscriptionStatus.ACTIVE.value:
            if sub.current_period_end and today > sub.current_period_end:
                sub.status = SubscriptionStatus.EXPIRED.value
                await self.db.flush()
                return {
                    "allowed": False,
                    "status": "expired",
                    "message": "Your subscription has expired. Please renew to continue.",
                }
            return {"allowed": True, "status": "active", "plan_id": sub.plan_id}

        if sub.status == SubscriptionStatus.PAST_DUE.value:
            return {
                "allowed": True,
                "status": "past_due",
                "message": "Payment past due. Please update your payment method.",
                "plan_id": sub.plan_id,
            }

        if sub.status in (SubscriptionStatus.CANCELLED.value, SubscriptionStatus.EXPIRED.value):
            # Cancelled but still in paid period?
            if sub.current_period_end and today <= sub.current_period_end:
                return {
                    "allowed": True,
                    "status": "cancelled_active",
                    "ends": sub.current_period_end.isoformat(),
                    "plan_id": sub.plan_id,
                }
            return {
                "allowed": False,
                "status": sub.status,
                "message": "Your subscription is no longer active. Please renew to continue.",
            }

        return {"allowed": False, "status": "unknown"}

    # ─── Activation / Upgrade / Cancel ───

    async def activate(
        self,
        tenant_id: str,
        plan_code: str,
        billing_cycle: str = "monthly",  # "monthly" or "yearly"
        stripe_subscription_id: str | None = None,
        stripe_customer_id: str | None = None,
    ) -> dict:
        """Activate a paid subscription (after Stripe payment confirmed)."""
        plan = await self.get_plan_by_code(plan_code)
        if not plan:
            return {"success": False, "error": "Plan not found"}

        sub = await self.get_subscription(tenant_id)
        if not sub:
            return {"success": False, "error": "No subscription record found"}

        today = date.today()
        if billing_cycle == "yearly":
            period_end = today + timedelta(days=365)
        else:
            period_end = today + timedelta(days=30)

        sub.plan_id = plan.id
        sub.status = SubscriptionStatus.ACTIVE.value
        sub.current_period_start = today
        sub.current_period_end = period_end
        sub.stripe_subscription_id = stripe_subscription_id
        sub.stripe_customer_id = stripe_customer_id

        # Update tenant plan_tier
        tenant_result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = tenant_result.scalar_one()
        tenant.plan_tier = plan_code

        await self.db.flush()
        return {
            "success": True,
            "plan": plan_code,
            "status": "active",
            "period_end": period_end.isoformat(),
        }

    async def upgrade(self, tenant_id: str, new_plan_code: str) -> dict:
        """Upgrade to a higher plan (immediate effect)."""
        return await self.activate(tenant_id, new_plan_code)

    async def cancel(self, tenant_id: str, reason: str = "") -> dict:
        """Cancel subscription (remains active until period end)."""
        sub = await self.get_subscription(tenant_id)
        if not sub:
            return {"success": False, "error": "No subscription found"}

        sub.status = SubscriptionStatus.CANCELLED.value
        sub.cancelled_at = datetime.now(UTC)
        sub.cancel_reason = reason

        await self.db.flush()
        return {
            "success": True,
            "status": "cancelled",
            "access_until": sub.current_period_end.isoformat() if sub.current_period_end else "now",
        }

    # ─── Usage Check ───

    async def get_usage(self, tenant_id: str) -> dict:
        """Get current usage vs plan limits for a tenant."""
        sub = await self.get_subscription(tenant_id)
        if not sub:
            return {"error": "No subscription"}

        plan_result = await self.db.execute(select(PlanTier).where(PlanTier.id == sub.plan_id))
        plan = plan_result.scalar_one()

        # Count current usage
        clients = (
            await self.db.execute(
                select(func.count(Client.id)).where(Client.tenant_id == tenant_id, Client.is_active)  # noqa
            )
        ).scalar() or 0

        skus = (
            await self.db.execute(select(func.count(SKU.id)).where(SKU.tenant_id == tenant_id))
        ).scalar() or 0

        users = (
            await self.db.execute(
                select(func.count(User.id)).where(User.tenant_id == tenant_id, User.is_active)  # noqa
            )
        ).scalar() or 0

        warehouses = (
            await self.db.execute(
                select(func.count(Warehouse.id)).where(
                    Warehouse.tenant_id == tenant_id, Warehouse.is_active
                )  # noqa
            )
        ).scalar() or 0

        return {
            "plan": plan.code,
            "plan_name": plan.name,
            "status": sub.status,
            "usage": {
                "clients": {
                    "used": clients,
                    "limit": plan.max_clients,
                    "pct": round(clients / max(plan.max_clients, 1) * 100),
                },
                "skus": {
                    "used": skus,
                    "limit": plan.max_skus,
                    "pct": round(skus / max(plan.max_skus, 1) * 100),
                },
                "users": {
                    "used": users,
                    "limit": plan.max_users,
                    "pct": round(users / max(plan.max_users, 1) * 100),
                },
                "warehouses": {
                    "used": warehouses,
                    "limit": plan.max_warehouses,
                    "pct": round(warehouses / max(plan.max_warehouses, 1) * 100),
                },
            },
            "features": plan.features or {},
            "trial_ends": sub.trial_end_date.isoformat() if sub.trial_end_date else None,
            "period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        }

    # ─── Stripe Webhook ───

    async def handle_stripe_webhook(self, event_type: str, data: dict) -> dict:
        """Process Stripe webhook events."""
        if event_type == "checkout.session.completed":
            # New subscription created via Stripe Checkout
            tenant_id = data.get("metadata", {}).get("tenant_id")
            stripe_sub_id = data.get("subscription")
            stripe_cust_id = data.get("customer")
            plan_code = data.get("metadata", {}).get("plan_code", "starter")
            if tenant_id:
                return await self.activate(
                    tenant_id,
                    plan_code,
                    stripe_subscription_id=stripe_sub_id,
                    stripe_customer_id=stripe_cust_id,
                )

        elif event_type == "invoice.payment_succeeded":
            stripe_sub_id = data.get("subscription")
            if stripe_sub_id:
                result = await self.db.execute(
                    select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
                )
                sub = result.scalar_one_or_none()
                if sub:
                    sub.status = SubscriptionStatus.ACTIVE.value
                    sub.current_period_end = date.today() + timedelta(days=30)
                    await self.db.flush()
                    return {"success": True, "action": "renewed"}

        elif event_type == "invoice.payment_failed":
            stripe_sub_id = data.get("subscription")
            if stripe_sub_id:
                result = await self.db.execute(
                    select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
                )
                sub = result.scalar_one_or_none()
                if sub:
                    sub.status = SubscriptionStatus.PAST_DUE.value
                    await self.db.flush()
                    return {"success": True, "action": "marked_past_due"}

        elif event_type == "customer.subscription.deleted":
            stripe_sub_id = data.get("id")
            if stripe_sub_id:
                result = await self.db.execute(
                    select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
                )
                sub = result.scalar_one_or_none()
                if sub:
                    sub.status = SubscriptionStatus.EXPIRED.value
                    await self.db.flush()
                    return {"success": True, "action": "expired"}

        return {"success": True, "action": "ignored", "event": event_type}
