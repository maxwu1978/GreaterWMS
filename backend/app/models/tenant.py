"""Tenant (3PL warehouse operator) and User models."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonType, TenantMixin, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.warehouse import Warehouse


class Tenant(Base, TimestampMixin):
    """
    A 3PL warehouse operator — the top-level entity in the multi-tenant model.
    Each tenant is a separate company that uses WMS QuickStart.
    """

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # short identifier
    subdomain: Mapped[str | None] = mapped_column(
        String(63), unique=True
    )  # tenant.wmsquickstart.com
    contact_email: Mapped[str] = mapped_column(String(254), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[dict | None] = mapped_column(JsonType)  # {street, city, state, zip, country}
    plan_tier: Mapped[str] = mapped_column(
        String(20), default="starter"
    )  # starter/growth/enterprise
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Registration approval gate: approved (default) / pending / rejected.
    # Login is blocked while pending or rejected (see auth.login).
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, default="approved")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(36))
    settings: Mapped[dict | None] = mapped_column(JsonType, default=dict)  # tenant-level config

    # Relationships
    users: Mapped[list["User"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    clients: Mapped[list["Client"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )  # type: ignore[name-defined]  # noqa: F821
    warehouses: Mapped[list["Warehouse"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )  # type: ignore[name-defined]  # noqa: F821


class User(Base, TimestampMixin, TenantMixin):
    """
    A user of the WMS system. Can be:
    - tenant_admin: manages the 3PL operation
    - operator: warehouse floor staff
    - client_viewer: cargo owner with portal access
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # UserRole enum value
    job_title: Mapped[str | None] = mapped_column(String(120))
    permissions: Mapped[list | None] = mapped_column(JsonType, default=list)
    client_id: Mapped[str | None] = mapped_column(String(36))  # only for client_viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verification_token: Mapped[str | None] = mapped_column(String(128))
    email_verification_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_reset_token: Mapped[str | None] = mapped_column(String(128))
    password_reset_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="users")
