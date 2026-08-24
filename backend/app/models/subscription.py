"""
SaaS subscription models — plan tiers, tenant subscriptions, payment tracking.

Two-level billing:
1. Platform → Tenant: subscription fees (this module)
2. Tenant → Client: usage-based warehouse fees (billing.py)
"""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonType, TenantMixin, TimestampMixin, generate_uuid


class SubscriptionStatus(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PlanTier(Base, TimestampMixin):
    """
    Subscription plan definition — platform-level, not tenant-scoped.
    Managed by platform_admin.
    """

    __tablename__ = "plan_tiers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # "Starter", "Growth", "Enterprise"
    code: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False
    )  # "starter", "growth", "enterprise"

    # Pricing
    price_monthly: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    price_yearly: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    stripe_price_monthly_id: Mapped[str | None] = mapped_column(String(100))  # Stripe Price ID
    stripe_price_yearly_id: Mapped[str | None] = mapped_column(String(100))

    # Limits
    max_clients: Mapped[int] = mapped_column(Integer, default=5)
    max_skus: Mapped[int] = mapped_column(Integer, default=1000)
    max_orders_per_day: Mapped[int] = mapped_column(Integer, default=200)
    max_users: Mapped[int] = mapped_column(Integer, default=5)
    max_warehouses: Mapped[int] = mapped_column(Integer, default=1)

    # Feature flags
    features: Mapped[dict] = mapped_column(JsonType, default=dict)
    # Example: {"shopify": true, "amazon": true, "agv": false, "api_full": true, "portal": true}

    trial_days: Mapped[int] = mapped_column(Integer, default=14)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text)


class Subscription(Base, TimestampMixin, TenantMixin):
    """
    A tenant's active subscription. One subscription per tenant at a time.
    """

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False, unique=True, index=True
    )
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plan_tiers.id"), nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), default=SubscriptionStatus.TRIAL.value, nullable=False
    )

    # Billing period
    current_period_start: Mapped[date | None] = mapped_column(Date)
    current_period_end: Mapped[date | None] = mapped_column(Date)
    trial_end_date: Mapped[date | None] = mapped_column(Date)

    # Stripe
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100))

    # Cancellation
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)

    # Relationships
    plan: Mapped["PlanTier"] = relationship()
