"""Customer pack-list documents and their package-level detail."""

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonType, TenantMixin, TimestampMixin, generate_uuid


class PackListDocument(Base, TimestampMixin, TenantMixin):
    """A customer-provided pack list attached to an inbound order."""

    __tablename__ = "pack_list_documents"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_checksum",
            name="uq_pack_list_documents_tenant_checksum",
        ),
        Index("ix_pack_list_documents_tenant_order", "tenant_id", "inbound_order_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    inbound_order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inbound_orders.id"), nullable=False, index=True
    )
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, default="customer_pack_list")
    source_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    container_tracking: Mapped[str | None] = mapped_column(String(120), index=True)
    package_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    serial_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text)
    imported_by: Mapped[str | None] = mapped_column(String(36))
    extra_data: Mapped[dict | None] = mapped_column(JsonType, default=dict)

    lines: Mapped[list["PackListLine"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class PackListLine(Base, TimestampMixin, TenantMixin):
    """One package row from the customer document.

    ``package_code`` is intentionally separate from ``serial_number``. A
    customer package/carton identifier is not a serial number unless the source
    explicitly supplies it as one.
    """

    __tablename__ = "pack_list_lines"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "document_id",
            "row_number",
            name="uq_pack_list_lines_tenant_document_row",
        ),
        Index("ix_pack_list_lines_tenant_package_code", "tenant_id", "package_code"),
        Index("ix_pack_list_lines_tenant_sku", "tenant_id", "sku_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pack_list_documents.id", ondelete="CASCADE"), nullable=False
    )
    inbound_package_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("inbound_packages.id"), index=True
    )
    sku_id: Mapped[str] = mapped_column(String(36), ForeignKey("skus.id"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    package_code: Mapped[str] = mapped_column(String(120), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_sku: Mapped[str | None] = mapped_column(String(100))
    item_name: Mapped[str | None] = mapped_column(String(300))
    serial_number: Mapped[str | None] = mapped_column(String(120), index=True)
    raw_data: Mapped[dict | None] = mapped_column(JsonType, default=dict)

    document: Mapped[PackListDocument] = relationship(back_populates="lines")


__all__ = ["PackListDocument", "PackListLine"]
