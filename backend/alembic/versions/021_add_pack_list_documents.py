"""Add customer pack-list documents and package-level rows."""

import sqlalchemy as sa

from alembic import op


revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pack_list_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("inbound_order_id", sa.String(length=36), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False, server_default="customer_pack_list"),
        sa.Column("source_checksum", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("container_tracking", sa.String(length=120), nullable=True),
        sa.Column("package_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("serial_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("imported_by", sa.String(length=36), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["inbound_order_id"], ["inbound_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "source_checksum", name="uq_pack_list_documents_tenant_checksum"),
    )
    op.create_index("ix_pack_list_documents_tenant_id", "pack_list_documents", ["tenant_id"])
    op.create_index(
        "ix_pack_list_documents_inbound_order_id", "pack_list_documents", ["inbound_order_id"]
    )
    op.create_index(
        "ix_pack_list_documents_tenant_order",
        "pack_list_documents",
        ["tenant_id", "inbound_order_id"],
    )
    op.create_index(
        "ix_pack_list_documents_container_tracking",
        "pack_list_documents",
        ["container_tracking"],
    )

    op.create_table(
        "pack_list_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("inbound_package_id", sa.String(length=36), nullable=True),
        sa.Column("sku_id", sa.String(length=36), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("package_code", sa.String(length=120), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("customer_sku", sa.String(length=100), nullable=True),
        sa.Column("item_name", sa.String(length=300), nullable=True),
        sa.Column("serial_number", sa.String(length=120), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["pack_list_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inbound_package_id"], ["inbound_packages.id"]),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "row_number",
            name="uq_pack_list_lines_tenant_document_row",
        ),
    )
    op.create_index("ix_pack_list_lines_tenant_id", "pack_list_lines", ["tenant_id"])
    op.create_index("ix_pack_list_lines_document_id", "pack_list_lines", ["document_id"])
    op.create_index("ix_pack_list_lines_inbound_package_id", "pack_list_lines", ["inbound_package_id"])
    op.create_index("ix_pack_list_lines_sku_id", "pack_list_lines", ["sku_id"])
    op.create_index("ix_pack_list_lines_serial_number", "pack_list_lines", ["serial_number"])
    op.create_index(
        "ix_pack_list_lines_tenant_package_code",
        "pack_list_lines",
        ["tenant_id", "package_code"],
    )
    op.create_index("ix_pack_list_lines_tenant_sku", "pack_list_lines", ["tenant_id", "sku_id"])


def downgrade() -> None:
    op.drop_index("ix_pack_list_lines_tenant_sku", table_name="pack_list_lines")
    op.drop_index("ix_pack_list_lines_tenant_package_code", table_name="pack_list_lines")
    op.drop_index("ix_pack_list_lines_serial_number", table_name="pack_list_lines")
    op.drop_index("ix_pack_list_lines_sku_id", table_name="pack_list_lines")
    op.drop_index("ix_pack_list_lines_inbound_package_id", table_name="pack_list_lines")
    op.drop_index("ix_pack_list_lines_document_id", table_name="pack_list_lines")
    op.drop_index("ix_pack_list_lines_tenant_id", table_name="pack_list_lines")
    op.drop_table("pack_list_lines")
    op.drop_index("ix_pack_list_documents_container_tracking", table_name="pack_list_documents")
    op.drop_index("ix_pack_list_documents_tenant_order", table_name="pack_list_documents")
    op.drop_index("ix_pack_list_documents_inbound_order_id", table_name="pack_list_documents")
    op.drop_index("ix_pack_list_documents_tenant_id", table_name="pack_list_documents")
    op.drop_table("pack_list_documents")
