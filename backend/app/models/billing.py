"""Billing models — rate cards, billing periods, invoices."""

from datetime import date
from enum import StrEnum

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonType, TenantMixin, TimestampMixin, generate_uuid


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class RateCard(Base, TimestampMixin, TenantMixin):
    """
    Billing rate configuration for a specific client.
    Uses JsonType for flexible rate definitions — each 3PL has different billing structures.

    Example rules JsonType:
    {
        "storage_per_pallet_day": 0.85,
        "storage_per_case_day": 0.15,
        "receiving_per_unit": 0.25,
        "receiving_per_pallet": 3.50,
        "pick_per_order": 2.00,
        "pick_per_line": 0.50,
        "pick_per_unit": 0.10,
        "shipping_handling_per_order": 1.50,
        "minimum_monthly": 500.00,
        "special_handling": {
            "hazmat_surcharge_pct": 15,
            "oversize_per_unit": 1.00
        }
    }
    """

    __tablename__ = "rate_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(36), ForeignKey("clients.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    rules: Mapped[dict] = mapped_column(JsonType, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class BillingPeriod(Base, TimestampMixin, TenantMixin):
    """A billing cycle (typically monthly) for a specific client."""

    __tablename__ = "billing_periods"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(36), ForeignKey("clients.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open, closed, invoiced

    # Relationships
    line_items: Mapped[list["BillingLineItem"]] = relationship(
        back_populates="billing_period", cascade="all, delete-orphan"
    )
    invoice: Mapped["Invoice | None"] = relationship(back_populates="billing_period")


class BillingLineItem(Base, TenantMixin):
    """Individual charge line within a billing period."""

    __tablename__ = "billing_line_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    billing_period_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("billing_periods.id"), nullable=False
    )

    charge_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # storage, receiving, pick, shipping, etc.
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    extra_data: Mapped[dict | None] = mapped_column(JsonType)  # detailed breakdown

    # Relationships
    billing_period: Mapped["BillingPeriod"] = relationship(back_populates="line_items")


class Invoice(Base, TimestampMixin, TenantMixin):
    """Generated invoice for a billing period."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_number", name="uq_invoices_tenant_number"),
        Index("ix_invoices_tenant_created", "tenant_id", "created_at"),
        Index("ix_invoices_tenant_status_created", "tenant_id", "status", "created_at"),
        Index("ix_invoices_tenant_client_created", "tenant_id", "client_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)  # covered by tenant-leading composite
    client_id: Mapped[str] = mapped_column(String(36), ForeignKey("clients.id"), nullable=False)
    billing_period_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("billing_periods.id"), nullable=False, unique=True
    )

    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=InvoiceStatus.DRAFT.value)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    issued_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    paid_date: Mapped[date | None] = mapped_column(Date)

    pdf_path: Mapped[str | None] = mapped_column(String(500))  # S3 key
    notes: Mapped[str | None] = mapped_column(Text)

    # Relationships
    billing_period: Mapped["BillingPeriod"] = relationship(back_populates="invoice")
