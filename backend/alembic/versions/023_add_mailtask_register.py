"""Add MailTask email, task, attachment, and approval registers.

Revision ID: 023
Revises: 022
Create Date: 2026-08-24
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def _enable_rls(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")
    op.execute(f"DROP POLICY IF EXISTS admin_bypass ON {table_name}")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {table_name}
            USING (tenant_id::text = current_setting('app.current_tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
        """
    )
    op.execute(
        f"""
        CREATE POLICY admin_bypass ON {table_name}
            USING (current_setting('app.is_platform_admin', true) = 'true')
        """
    )


def _disable_rls(table_name: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")
    op.execute(f"DROP POLICY IF EXISTS admin_bypass ON {table_name}")
    op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.create_table(
        "mail_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("source_message_key", sa.String(length=255), nullable=False),
        sa.Column("mailbox", sa.String(length=254), nullable=False),
        sa.Column("folder", sa.String(length=120), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sender", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=1000), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=True),
        sa.Column("recipients", _JSON, nullable=True),
        sa.Column("cc", _JSON, nullable=True),
        sa.Column("source_summary", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_hash", sa.String(length=64), nullable=True),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("classification", sa.String(length=80), nullable=True),
        sa.Column("attachment_names", _JSON, nullable=True),
        sa.Column("attachment_read_status", sa.String(length=40), nullable=True),
        sa.Column("reader_run_id", sa.String(length=128), nullable=True),
        sa.Column("dedup_status", sa.String(length=40), nullable=True),
        sa.Column("filter_decision", sa.String(length=80), nullable=True),
        sa.Column("source_payload", _JSON, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_message_key", name="uq_mail_messages_tenant_source"
        ),
    )
    op.create_index(
        "ix_mail_messages_tenant_received", "mail_messages", ["tenant_id", "received_at"]
    )
    op.create_index("ix_mail_messages_tenant_decision", "mail_messages", ["tenant_id", "decision"])

    op.create_table(
        "mail_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("task_key", sa.String(length=180), nullable=False),
        sa.Column("mail_message_id", sa.String(length=36), nullable=False),
        sa.Column("source_message_key", sa.String(length=255), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=True),
        sa.Column("source_document_id", sa.String(length=180), nullable=False),
        sa.Column("source_attachment", sa.String(length=512), nullable=True),
        sa.Column("source_evidence", _JSON, nullable=True),
        sa.Column("record_type", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("customer_owner", sa.String(length=255), nullable=True),
        sa.Column("supplier_or_origin_party", sa.String(length=255), nullable=True),
        sa.Column("external_reference", sa.String(length=255), nullable=True),
        sa.Column("po", sa.String(length=120), nullable=True),
        sa.Column("dn", sa.String(length=120), nullable=True),
        sa.Column("group_number", sa.String(length=120), nullable=True),
        sa.Column("load_id", sa.String(length=120), nullable=True),
        sa.Column("container_or_tracking", sa.String(length=180), nullable=True),
        sa.Column("mawb", sa.String(length=120), nullable=True),
        sa.Column("hawb", sa.String(length=120), nullable=True),
        sa.Column("bol_number", sa.String(length=120), nullable=True),
        sa.Column("do_number", sa.String(length=120), nullable=True),
        sa.Column("sku_or_item", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("package_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("package_unit", sa.String(length=40), nullable=True),
        sa.Column("product_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("product_unit", sa.String(length=40), nullable=True),
        sa.Column("weight", sa.Numeric(18, 4), nullable=True),
        sa.Column("origin", sa.String(length=255), nullable=True),
        sa.Column("destination", sa.String(length=255), nullable=True),
        sa.Column("origin_dock", sa.String(length=120), nullable=True),
        sa.Column("destination_dock", sa.String(length=120), nullable=True),
        sa.Column("carrier", sa.String(length=255), nullable=True),
        sa.Column("transport_mode", sa.String(length=80), nullable=True),
        sa.Column("pickup_appointment", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_appointment", sa.DateTime(timezone=True), nullable=True),
        sa.Column("original_plan_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proposed_plan_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_pickup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_status", sa.String(length=40), nullable=False),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("source_party", sa.String(length=255), nullable=True),
        sa.Column("external_contact_mode", sa.String(length=40), nullable=True),
        sa.Column("intake_owner", sa.String(length=180), nullable=True),
        sa.Column("task_owner", sa.String(length=180), nullable=True),
        sa.Column("delegated_by", sa.String(length=180), nullable=True),
        sa.Column("delegated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customer_action_owner", sa.String(length=180), nullable=True),
        sa.Column("warehouse_owner", sa.String(length=180), nullable=True),
        sa.Column("receiving_owner", sa.String(length=180), nullable=True),
        sa.Column("shipping_owner", sa.String(length=180), nullable=True),
        sa.Column("physical_execution_owner", sa.String(length=180), nullable=True),
        sa.Column("physical_execution_status", sa.String(length=40), nullable=False),
        sa.Column("physical_execution_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("physical_execution_evidence", _JSON, nullable=True),
        sa.Column("logistics_owner", sa.String(length=180), nullable=True),
        sa.Column("cio_owner", sa.String(length=180), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wms_system", sa.String(length=40), nullable=True),
        sa.Column("wms_doc_no", sa.String(length=180), nullable=True),
        sa.Column("wms_order_id", sa.String(length=120), nullable=True),
        sa.Column("wms_match_status", sa.String(length=40), nullable=True),
        sa.Column("wms_current_status", sa.String(length=80), nullable=True),
        sa.Column("wms_match_method", sa.String(length=80), nullable=True),
        sa.Column("wms_match_confidence", sa.Numeric(6, 4), nullable=True),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("approval_type", sa.String(length=80), nullable=True),
        sa.Column("approval_status", sa.String(length=24), nullable=False),
        sa.Column("approved_by", sa.String(length=180), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_evidence", _JSON, nullable=True),
        sa.Column("exception_flag", sa.Boolean(), nullable=False),
        sa.Column("exception_description", sa.Text(), nullable=True),
        sa.Column("last_updated_by", sa.String(length=180), nullable=True),
        sa.Column("canonical_payload", _JSON, nullable=False),
        sa.ForeignKeyConstraint(["mail_message_id"], ["mail_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "task_key", name="uq_mail_tasks_tenant_task_key"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_message_key",
            "source_document_id",
            name="uq_mail_tasks_tenant_source_document",
        ),
    )
    op.create_index(
        "ix_mail_tasks_tenant_status_owner",
        "mail_tasks",
        ["tenant_id", "task_status", "task_owner"],
    )
    op.create_index(
        "ix_mail_tasks_tenant_direction_status",
        "mail_tasks",
        ["tenant_id", "direction", "task_status"],
    )
    op.create_index(
        "ix_mail_tasks_tenant_source", "mail_tasks", ["tenant_id", "source_message_key"]
    )
    op.create_index(
        "ix_mail_tasks_tenant_wms_ref", "mail_tasks", ["tenant_id", "wms_system", "wms_doc_no"]
    )

    op.create_table(
        "mail_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("mail_message_id", sa.String(length=36), nullable=False),
        sa.Column("task_key", sa.String(length=180), nullable=True),
        sa.Column("attachment_name", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.String(length=1000), nullable=True),
        sa.Column("read_status", sa.String(length=40), nullable=True),
        sa.Column("source_evidence", _JSON, nullable=True),
        sa.ForeignKeyConstraint(["mail_message_id"], ["mail_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mail_attachments_tenant_message", "mail_attachments", ["tenant_id", "mail_message_id"]
    )
    op.create_index(
        "ix_mail_attachments_tenant_sha256", "mail_attachments", ["tenant_id", "sha256"]
    )

    op.create_table(
        "mail_task_approvals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("mail_task_id", sa.String(length=36), nullable=False),
        sa.Column("approval_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("approver_user_id", sa.String(length=180), nullable=False),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("evidence", _JSON, nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["mail_task_id"], ["mail_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mail_task_approvals_tenant_task",
        "mail_task_approvals",
        ["tenant_id", "mail_task_id"],
    )
    op.create_index(
        "ix_mail_task_approvals_tenant_status", "mail_task_approvals", ["tenant_id", "status"]
    )

    if op.get_bind().dialect.name == "postgresql":
        for table_name in (
            "mail_messages",
            "mail_tasks",
            "mail_attachments",
            "mail_task_approvals",
        ):
            _enable_rls(table_name)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table_name in (
            "mail_task_approvals",
            "mail_attachments",
            "mail_tasks",
            "mail_messages",
        ):
            _disable_rls(table_name)

    op.drop_index("ix_mail_task_approvals_tenant_status", table_name="mail_task_approvals")
    op.drop_index("ix_mail_task_approvals_tenant_task", table_name="mail_task_approvals")
    op.drop_table("mail_task_approvals")
    op.drop_index("ix_mail_attachments_tenant_sha256", table_name="mail_attachments")
    op.drop_index("ix_mail_attachments_tenant_message", table_name="mail_attachments")
    op.drop_table("mail_attachments")
    op.drop_index("ix_mail_tasks_tenant_wms_ref", table_name="mail_tasks")
    op.drop_index("ix_mail_tasks_tenant_source", table_name="mail_tasks")
    op.drop_index("ix_mail_tasks_tenant_direction_status", table_name="mail_tasks")
    op.drop_index("ix_mail_tasks_tenant_status_owner", table_name="mail_tasks")
    op.drop_table("mail_tasks")
    op.drop_index("ix_mail_messages_tenant_decision", table_name="mail_messages")
    op.drop_index("ix_mail_messages_tenant_received", table_name="mail_messages")
    op.drop_table("mail_messages")
