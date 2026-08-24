"""Kit/Bundle models — composite products made from multiple SKUs."""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin, generate_uuid


class Kit(Base, TimestampMixin, TenantMixin):
    """
    A composite product (kit/bundle) that consists of multiple component SKUs.
    When an order contains a kit, the system picks the individual components.
    """

    __tablename__ = "kits"
    __table_args__ = (UniqueConstraint("tenant_id", "sku_id", name="uq_kits_tenant_sku"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(36), ForeignKey("clients.id"), nullable=False)
    sku_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skus.id"), nullable=False, unique=True
    )  # The kit's own SKU (e.g. "GIFT-SET-A")
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)

    # Relationships
    components: Mapped[list["KitComponent"]] = relationship(
        back_populates="kit", cascade="all, delete-orphan"
    )


class KitComponent(Base, TenantMixin):
    """A single component inside a kit — one SKU + quantity."""

    __tablename__ = "kit_components"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kit_id: Mapped[str] = mapped_column(String(36), ForeignKey("kits.id"), nullable=False)
    component_sku_id: Mapped[str] = mapped_column(String(36), ForeignKey("skus.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Relationships
    kit: Mapped["Kit"] = relationship(back_populates="components")
