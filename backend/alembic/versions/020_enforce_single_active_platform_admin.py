"""Enforce a single active platform administrator."""

from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_users_single_active_platform_admin"


def upgrade() -> None:
    # Existing inactive duplicate test admins remain auditable and reversible.
    op.execute(
        f"CREATE UNIQUE INDEX {INDEX_NAME} ON users (role) "
        "WHERE role = 'platform_admin' AND is_active = true"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
