"""Subscription management API — plans, registration, activation, usage."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import apply_session_context, get_db_session
from app.core.deps import clear_subscription_cache, get_current_user, require_role
from app.core.security import TokenPayload, UserRole
from app.models.subscription import PlanTier
from app.models.tenant import User
from app.services.subscription_service import SubscriptionService

router = APIRouter()


# ─── Public: Plans ───


class PlanResponse(BaseModel):
    id: str
    name: str
    code: str
    price_monthly: float
    price_yearly: float
    max_clients: int
    max_skus: int
    max_orders_per_day: int
    max_users: int
    max_warehouses: int
    features: dict
    trial_days: int


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(db: AsyncSession = Depends(get_db_session)):
    """List all available subscription plans. Public endpoint."""
    svc = SubscriptionService(db)
    plans = await svc.list_plans()
    return [
        PlanResponse(
            id=p.id,
            name=p.name,
            code=p.code,
            price_monthly=float(p.price_monthly),
            price_yearly=float(p.price_yearly),
            max_clients=p.max_clients,
            max_skus=p.max_skus,
            max_orders_per_day=p.max_orders_per_day,
            max_users=p.max_users,
            max_warehouses=p.max_warehouses,
            features=p.features or {},
            trial_days=p.trial_days,
        )
        for p in plans
    ]


# ─── Public: Registration ───


class RegisterRequest(BaseModel):
    company_name: str
    company_code: str
    admin_email: EmailStr
    admin_password: str
    admin_name: str
    plan_code: str = "starter"
    accept_terms: bool
    accept_risk_notice: bool


@router.post("/register")
async def register_trial(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Self-service registration. Creates tenant + admin user + trial subscription.
    Returns a JWT token for immediate login.
    """
    if len(body.admin_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if not body.company_code.strip() or len(body.company_code) > 30:
        raise HTTPException(status_code=400, detail="Company code must be 1-30 characters")
    if not body.accept_terms or not body.accept_risk_notice:
        raise HTTPException(
            status_code=400, detail="You must accept the trial terms and operational notice"
        )
    await apply_session_context(db, is_platform_admin=True)
    svc = SubscriptionService(db)
    result = await svc.register_trial(
        company_name=body.company_name,
        company_code=body.company_code,
        admin_email=body.admin_email,
        admin_password=body.admin_password,
        admin_name=body.admin_name,
        plan_code=body.plan_code,
        accept_terms=body.accept_terms,
        accept_risk_notice=body.accept_risk_notice,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Registration failed"))
    return result


@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Verify a registration email token and activate sign-in."""
    if not token.strip():
        raise HTTPException(status_code=400, detail="Missing verification token")

    await apply_session_context(db, is_platform_admin=True)

    result = await db.execute(select(User).where(User.email_verification_token == token))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    if user.is_email_verified:
        return HTMLResponse(
            content=_verification_page(
                title="Email already verified",
                message="Your account is already active. You can return to the sign-in page and continue.",
                tone="info",
            )
        )

    user.is_email_verified = True
    user.email_verification_token = None
    user.email_verification_sent_at = datetime.now(UTC)
    await db.flush()

    return HTMLResponse(
        content=_verification_page(
            title="Email verified",
            message="Your account is now active. Return to the sign-in page and continue into your workspace.",
            tone="success",
        )
    )


def _verification_page(title: str, message: str, tone: str) -> str:
    accent = "#0f766e" if tone == "success" else "#13212c"
    sign_in_url = f"{settings.APP_BASE_URL.rstrip('/')}/login"
    return f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>{title} | WMS QuickStart</title>
      </head>
      <body style="margin:0;font-family:Arial,sans-serif;background:#f2efe8;color:#13212c;">
        <main style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;">
          <section style="max-width:560px;width:100%;background:white;border:1px solid rgba(19,33,44,0.08);border-radius:28px;padding:40px;box-shadow:0 20px 60px rgba(19,33,44,0.12);">
            <p style="margin:0 0 12px;font-size:12px;letter-spacing:0.2em;text-transform:uppercase;color:#7a8894;">WMS QuickStart</p>
            <h1 style="margin:0 0 16px;font-size:40px;line-height:1.05;color:{accent};">{title}</h1>
            <p style="margin:0 0 28px;font-size:16px;line-height:1.7;color:#50606c;">{message}</p>
            <a href="{sign_in_url}" style="display:inline-block;background:#13212c;color:#f4efe8;text-decoration:none;padding:14px 22px;border-radius:999px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;font-size:12px;">Go to sign in</a>
          </section>
        </main>
      </body>
    </html>
    """


# ─── Authenticated: Subscription Status ───


@router.get("/current")
async def current_subscription(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get current subscription status and details."""
    svc = SubscriptionService(db)
    sub = await svc.get_subscription(current_user.tenant_id)
    if not sub:
        return {"status": "none", "message": "No subscription found"}

    # Load plan details
    plan_result = await db.execute(select(PlanTier).where(PlanTier.id == sub.plan_id))
    plan = plan_result.scalar_one_or_none()

    return {
        "status": sub.status,
        "plan": plan.code if plan else None,
        "plan_name": plan.name if plan else None,
        "trial_end": sub.trial_end_date.isoformat() if sub.trial_end_date else None,
        "period_start": sub.current_period_start.isoformat() if sub.current_period_start else None,
        "period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        "stripe_customer_id": sub.stripe_customer_id,
    }


# ─── Usage ───


@router.get("/usage")
async def subscription_usage(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get current resource usage vs plan limits."""
    svc = SubscriptionService(db)
    return await svc.get_usage(current_user.tenant_id)


# ─── Activate / Upgrade / Cancel ───


class ActivateRequest(BaseModel):
    plan_code: str
    billing_cycle: str = "monthly"  # "monthly" or "yearly"
    stripe_subscription_id: str | None = None
    stripe_customer_id: str | None = None


@router.post("/activate")
async def activate_subscription(
    body: ActivateRequest,
    current_user: TokenPayload = Depends(
        require_role(UserRole.TENANT_ADMIN, UserRole.PLATFORM_ADMIN)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    """Activate a paid subscription after payment."""
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=400,
            detail="No tenant context. Platform admin cannot activate without tenant_id.",
        )
    svc = SubscriptionService(db)
    result = await svc.activate(
        tenant_id=current_user.tenant_id,
        plan_code=body.plan_code,
        billing_cycle=body.billing_cycle,
        stripe_subscription_id=body.stripe_subscription_id,
        stripe_customer_id=body.stripe_customer_id,
    )
    clear_subscription_cache(current_user.tenant_id)
    return result


class UpgradeRequest(BaseModel):
    plan_code: str


@router.post("/upgrade")
async def upgrade_plan(
    body: UpgradeRequest,
    current_user: TokenPayload = Depends(
        require_role(UserRole.TENANT_ADMIN, UserRole.PLATFORM_ADMIN)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    """Upgrade to a higher plan."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context.")
    svc = SubscriptionService(db)
    result = await svc.upgrade(current_user.tenant_id, body.plan_code)
    clear_subscription_cache(current_user.tenant_id)
    return result


class CancelRequest(BaseModel):
    reason: str = ""


@router.post("/cancel")
async def cancel_subscription(
    body: CancelRequest,
    current_user: TokenPayload = Depends(
        require_role(UserRole.TENANT_ADMIN, UserRole.PLATFORM_ADMIN)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    """Cancel subscription (access continues until period end)."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context.")
    svc = SubscriptionService(db)
    result = await svc.cancel(current_user.tenant_id, body.reason)
    clear_subscription_cache(current_user.tenant_id)
    return result


# ─── Stripe Webhook ───


@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Handle Stripe webhook events. Verifies signature when STRIPE_WEBHOOK_SECRET is configured."""
    import hashlib
    import hmac
    import json as json_mod
    import time as time_mod

    from app.core.config import settings

    raw_body = await request.body()

    # Verify Stripe signature if webhook secret is configured
    if settings.STRIPE_WEBHOOK_SECRET:
        sig_header = request.headers.get("stripe-signature", "")
        if not sig_header:
            raise HTTPException(status_code=400, detail="Missing stripe-signature header")

        # Parse Stripe signature header.
        # Format: t=timestamp,v1=sig1,v1=sig2 (multiple v1 during secret rotation)
        timestamp = ""
        their_sigs: list[str] = []
        for pair in sig_header.split(","):
            key, _, value = pair.strip().partition("=")
            if key == "t":
                timestamp = value
            elif key == "v1":
                their_sigs.append(value)

        if not timestamp or not their_sigs:
            raise HTTPException(status_code=400, detail="Malformed stripe-signature header")

        # Reject stale events (> 5 minutes old) to prevent replay attacks
        try:
            event_age = int(time_mod.time()) - int(timestamp)
            if event_age > 300:
                raise HTTPException(
                    status_code=400, detail="Webhook timestamp too old (possible replay)"
                )
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Invalid timestamp in stripe-signature"
            ) from exc

        # Compute expected signature
        signed_payload = f"{timestamp}.{raw_body.decode()}"
        expected_sig = hmac.new(
            settings.STRIPE_WEBHOOK_SECRET.encode(),
            signed_payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        # Accept if ANY of the v1 signatures match (supports secret rotation)
        if not any(hmac.compare_digest(expected_sig, sig) for sig in their_sigs):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    body = json_mod.loads(raw_body) if raw_body else await request.json()
    event_type = body.get("type", "")
    data = body.get("data", {}).get("object", {})

    svc = SubscriptionService(db)
    result = await svc.handle_stripe_webhook(event_type, data)

    # Clear cache for affected tenant
    tenant_id = data.get("metadata", {}).get("tenant_id")
    if tenant_id:
        clear_subscription_cache(tenant_id)

    return result
