"""Add business-task grouping for Mail2Task.

Revision ID: 024
Revises: 023
Create Date: 2026-08-25
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def _group_key_sql(dialect: str) -> str:
    raw_key = """(
        direction || ':' || COALESCE(
            NULLIF(external_reference, ''),
            NULLIF(bol_number, ''),
            NULLIF(do_number, ''),
            NULLIF(container_or_tracking, ''),
            NULLIF(load_id, ''),
            NULLIF(po, ''),
            NULLIF(dn, ''),
            'legacy:' || task_key
        )
    )"""
    if dialect == "postgresql":
        return f"""(
            CASE WHEN length({raw_key}) <= 180 THEN {raw_key}
            ELSE substr({raw_key}, 1, 145) || ':' || substr(md5({raw_key}), 1, 34)
            END
        )"""
    return f"""(
        CASE WHEN length({raw_key}) <= 180 THEN {raw_key}
        ELSE substr({raw_key}, 1, 180)
        END
    )"""


def _backfill_postgres() -> None:
    key = _group_key_sql("postgresql")
    op.execute(
        f"""
        INSERT INTO mail_task_groups (
            id, created_at, updated_at, tenant_id, task_group_key,
            title, record_type, direction, external_reference, next_action,
            task_status, task_owner, intake_owner, physical_execution_owner,
            physical_execution_status, wms_system, wms_doc_no, wms_order_id,
            wms_match_status, wms_current_status, wms_match_method,
            wms_match_confidence, approval_required, approval_type,
            approval_status, approved_by, approved_at, approval_evidence,
            exception_flag, exception_description, latest_mail_message_id,
            latest_message_at, last_updated_by, canonical_payload
        )
        SELECT DISTINCT ON (tenant_id, group_key)
            md5(tenant_id || ':' || group_key), created_at, updated_at,
            tenant_id, group_key, title, record_type, direction,
            external_reference, next_action, task_status, task_owner,
            intake_owner, physical_execution_owner, physical_execution_status,
            wms_system, wms_doc_no, wms_order_id, wms_match_status,
            wms_current_status, wms_match_method, wms_match_confidence,
            approval_required, approval_type, approval_status, approved_by,
            approved_at, approval_evidence, exception_flag,
            exception_description, mail_message_id, NULL, last_updated_by,
            canonical_payload
        FROM (
            SELECT mail_tasks.*, {key} AS group_key
            FROM mail_tasks
        ) grouped_tasks
        ORDER BY tenant_id, group_key, created_at DESC
        ON CONFLICT (tenant_id, task_group_key) DO NOTHING
        """
    )
    op.execute(
        f"""
        UPDATE mail_tasks AS task
        SET business_task_id = groups.id
        FROM mail_task_groups AS groups
        WHERE groups.tenant_id = task.tenant_id
          AND groups.task_group_key = {key.replace('external_reference', 'task.external_reference').replace('bol_number', 'task.bol_number').replace('do_number', 'task.do_number').replace('container_or_tracking', 'task.container_or_tracking').replace('load_id', 'task.load_id').replace('po', 'task.po').replace('dn', 'task.dn').replace('direction', 'task.direction').replace('task_key', 'task.task_key')}
        """
    )
    op.execute(
        """
        UPDATE mail_task_approvals AS approvals
        SET business_task_id = tasks.business_task_id
        FROM mail_tasks AS tasks
        WHERE approvals.mail_task_id = tasks.id
          AND approvals.business_task_id IS NULL
        """
    )


def _backfill_sqlite() -> None:
    key = _group_key_sql("sqlite")
    op.execute(
        f"""
        INSERT OR IGNORE INTO mail_task_groups (
            id, created_at, updated_at, tenant_id, task_group_key,
            title, record_type, direction, external_reference, next_action,
            task_status, task_owner, intake_owner, physical_execution_owner,
            physical_execution_status, wms_system, wms_doc_no, wms_order_id,
            wms_match_status, wms_current_status, wms_match_method,
            wms_match_confidence, approval_required, approval_type,
            approval_status, approved_by, approved_at, approval_evidence,
            exception_flag, exception_description, latest_mail_message_id,
            latest_message_at, last_updated_by, canonical_payload
        )
        SELECT
            lower(hex(randomblob(16))), created_at, updated_at, tenant_id,
            {key}, title, record_type, direction, external_reference,
            next_action, task_status, task_owner, intake_owner,
            physical_execution_owner, physical_execution_status, wms_system,
            wms_doc_no, wms_order_id, wms_match_status, wms_current_status,
            wms_match_method, wms_match_confidence, approval_required,
            approval_type, approval_status, approved_by, approved_at,
            approval_evidence, exception_flag, exception_description,
            mail_message_id, NULL, last_updated_by, canonical_payload
        FROM mail_tasks
        """
    )
    op.execute(
        f"""
        UPDATE mail_tasks
        SET business_task_id = (
            SELECT groups.id
            FROM mail_task_groups groups
            WHERE groups.tenant_id = mail_tasks.tenant_id
              AND groups.task_group_key = {key}
        )
        WHERE business_task_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE mail_task_approvals
        SET business_task_id = (
            SELECT mail_tasks.business_task_id
            FROM mail_tasks
            WHERE mail_tasks.id = mail_task_approvals.mail_task_id
        )
        WHERE business_task_id IS NULL
        """
    )


def upgrade() -> None:
    op.create_table(
        "mail_task_groups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("task_group_key", sa.String(length=180), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("record_type", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("external_reference", sa.String(length=255), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("task_status", sa.String(length=40), nullable=False),
        sa.Column("task_owner", sa.String(length=180), nullable=True),
        sa.Column("intake_owner", sa.String(length=180), nullable=True),
        sa.Column("physical_execution_owner", sa.String(length=180), nullable=True),
        sa.Column("physical_execution_status", sa.String(length=40), nullable=False),
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
        sa.Column("latest_mail_message_id", sa.String(length=36), nullable=True),
        sa.Column("latest_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_updated_by", sa.String(length=180), nullable=True),
        sa.Column("canonical_payload", _JSON, nullable=True),
        sa.ForeignKeyConstraint(["latest_mail_message_id"], ["mail_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "task_group_key", name="uq_mail_task_groups_tenant_key"),
    )
    op.create_index(
        "ix_mail_task_groups_tenant_status_owner",
        "mail_task_groups",
        ["tenant_id", "task_status", "task_owner"],
    )
    op.create_index(
        "ix_mail_task_groups_tenant_direction_status",
        "mail_task_groups",
        ["tenant_id", "direction", "task_status"],
    )

    op.add_column("mail_tasks", sa.Column("business_task_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_mail_tasks_business_task_id",
        "mail_tasks",
        "mail_task_groups",
        ["business_task_id"],
        ["id"],
    )
    op.create_index("ix_mail_tasks_business_task_id", "mail_tasks", ["business_task_id"])

    op.add_column(
        "mail_task_approvals", sa.Column("business_task_id", sa.String(length=36), nullable=True)
    )
    op.create_foreign_key(
        "fk_mail_task_approvals_business_task_id",
        "mail_task_approvals",
        "mail_task_groups",
        ["business_task_id"],
        ["id"],
    )
    op.create_index(
        "ix_mail_task_approvals_tenant_group",
        "mail_task_approvals",
        ["tenant_id", "business_task_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        _backfill_postgres()
        for table_name in ("mail_task_groups",):
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
    else:
        _backfill_sqlite()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON mail_task_groups")
        op.execute("DROP POLICY IF EXISTS admin_bypass ON mail_task_groups")
        op.execute("ALTER TABLE mail_task_groups DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_mail_task_approvals_tenant_group", table_name="mail_task_approvals")
    op.drop_constraint(
        "fk_mail_task_approvals_business_task_id", "mail_task_approvals", type_="foreignkey"
    )
    op.drop_column("mail_task_approvals", "business_task_id")
    op.drop_index("ix_mail_tasks_business_task_id", table_name="mail_tasks")
    op.drop_constraint("fk_mail_tasks_business_task_id", "mail_tasks", type_="foreignkey")
    op.drop_column("mail_tasks", "business_task_id")
    op.drop_index("ix_mail_task_groups_tenant_direction_status", table_name="mail_task_groups")
    op.drop_index("ix_mail_task_groups_tenant_status_owner", table_name="mail_task_groups")
    op.drop_table("mail_task_groups")
