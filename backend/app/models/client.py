"""Client (cargo owner / shipper) model — the second level of multi-tenancy."""

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonType, TenantMixin, TimestampMixin, generate_uuid


class Client(Base, TimestampMixin, TenantMixin):
    """
    A cargo owner / shipper that stores goods in the 3PL warehouse.
    Each tenant (3PL operator) has multiple clients.
    Client data is isolated by tenant_id (RLS) at the DB level.
    """

    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_clients_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)  # unique within tenant
    contact_email: Mapped[str | None] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[dict | None] = mapped_column(JsonType)
    notes: Mapped[str | None] = mapped_column(Text)
    billing_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    portal_access: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[dict | None] = mapped_column(JsonType, default=dict)

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="clients")  # type: ignore[name-defined]  # noqa: F821
    skus: Mapped[list["SKU"]] = relationship(back_populates="client", cascade="all, delete-orphan")  # type: ignore[name-defined]  # noqa: F821
