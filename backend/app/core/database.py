"""
Multi-tenant database engine with tenant isolation.

PostgreSQL: uses Row-Level Security (RLS) — DB-level enforcement.
SQLite (dev): uses SQLAlchemy event listener — app-level enforcement.

Both ensure that queries are always filtered by tenant_id.
"""

from collections.abc import AsyncGenerator
from contextvars import ContextVar

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, ORMExecuteState, Session

from app.core.config import settings

# Context variable to hold the current tenant_id for this request
_current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)


def get_current_tenant_id() -> str | None:
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: str | None) -> None:
    _current_tenant_id.set(tenant_id)


# Detect if we're using SQLite (local dev) or PostgreSQL (production)
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")


def is_sqlite() -> bool:
    """Check if running on SQLite (dev). Used to skip FOR UPDATE which SQLite doesn't support."""
    return _is_sqlite


def is_sqlite_session(session: AsyncSession) -> bool:
    """Check the actual bound session dialect, which can differ in tests."""
    return session.get_bind().dialect.name == "sqlite"


def for_update(query):
    """Apply FOR UPDATE on PostgreSQL, no-op on SQLite."""
    return query if _is_sqlite else query.with_for_update()


# Async engine
engine_options = {"echo": settings.DEBUG}
if not _is_sqlite:
    engine_options.update(
        {
            "pool_size": settings.DATABASE_POOL_SIZE,
            "max_overflow": settings.DATABASE_MAX_OVERFLOW,
            # Managed Postgres providers recycle idle connections; pre-ping
            # replaces "server closed the connection unexpectedly" errors with
            # a transparent reconnect.
            "pool_pre_ping": True,
            "pool_recycle": 1800,
        }
    )

engine = create_async_engine(settings.DATABASE_URL, **engine_options)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


# ─── SQLite tenant isolation via SQLAlchemy event ───
# Tables that have tenant_id and need automatic filtering
_TENANT_TABLES = {
    "users",
    "clients",
    "warehouses",
    "zones",
    "locations",
    "skus",
    "inventory",
    "inventory_transactions",
    "agent_evidence",
    "idempotency_records",
    "inbound_orders",
    "inbound_order_lines",
    "inbound_packages",
    "handling_units",
    "receiving_labels",
    "receiving_observed_codes",
    "wcs_task_bindings",
    "outbound_orders",
    "outbound_order_lines",
    "pick_allocations",
    "putaway_allocations",
    "tasks",
    "rate_cards",
    "billing_periods",
    "billing_line_items",
    "invoices",
    "subscriptions",
    "return_orders",
    "return_order_lines",
    "kits",
    "kit_components",
    "pack_list_documents",
    "pack_list_lines",
    "mail_messages",
    "mail_task_groups",
    "mail_tasks",
    "mail_attachments",
    "mail_task_approvals",
}


@event.listens_for(Session, "do_orm_execute")
def _inject_tenant_filter(execute_state: ORMExecuteState):
    """
    Automatically inject WHERE tenant_id = :tid on all SELECT queries
    for tenant-scoped tables when using SQLite.

    Register this listener unconditionally and inspect the bound session's
    dialect at execution time. Tests and local tools commonly bind a SQLite
    session while the application module itself is configured for PostgreSQL.
    """
    if not execute_state.is_select or execute_state.session.get_bind().dialect.name != "sqlite":
        return

    tenant_id = get_current_tenant_id()
    if not tenant_id:
        return  # platform admin or unauthenticated — no filter

    # Check if any of the queried entities have tenant_id
    try:
        for mapper in execute_state.all_mappers:
            table_name = mapper.local_table.name
            if table_name in _TENANT_TABLES:
                tenant_col = mapper.local_table.c.get("tenant_id")
                if tenant_col is not None:
                    execute_state.statement = execute_state.statement.where(tenant_col == tenant_id)
    except Exception:
        pass  # If we can't determine mappers, skip filtering


@event.listens_for(Session, "before_flush")
def _enforce_sqlite_tenant_writes(session: Session, _flush_context, _instances) -> None:
    """Reject cross-tenant ORM writes when the local database is SQLite."""
    if session.get_bind().dialect.name != "sqlite":
        return

    tenant_id = get_current_tenant_id()
    if not tenant_id or get_is_platform_admin():
        return

    for collection in (session.new, session.dirty, session.deleted):
        for instance in collection:
            instance_tenant_id = getattr(instance, "tenant_id", None)
            if instance_tenant_id is not None and instance_tenant_id != tenant_id:
                raise ValueError("Cross-tenant write rejected by SQLite tenant isolation")


# Context var for platform admin bypass
_is_platform_admin: ContextVar[bool] = ContextVar("is_platform_admin", default=False)
_TENANT_ID_PATTERN = r"^[a-zA-Z0-9\-]+$"


def get_is_platform_admin() -> bool:
    return _is_platform_admin.get()


def set_is_platform_admin(value: bool) -> None:
    _is_platform_admin.set(value)


async def apply_session_context(
    session: AsyncSession,
    tenant_id: str | None = None,
    is_platform_admin: bool = False,
) -> None:
    """
    Apply PostgreSQL RLS session variables for an explicit DB session.

    Most request handlers get this through get_db_session(), but short-lived
    helper sessions and websocket lookups need the same context before querying
    tenant-scoped tables.
    """
    if is_sqlite_session(session):
        return

    if is_platform_admin:
        await session.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        await session.execute(text("SELECT set_config('app.current_tenant_id', '', true)"))
        return

    if tenant_id:
        import re

        if not re.match(_TENANT_ID_PATTERN, tenant_id):
            raise ValueError("Invalid tenant_id format")
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )
        await session.execute(text("SELECT set_config('app.is_platform_admin', 'false', true)"))
        return

    await session.execute(text("SELECT set_config('app.current_tenant_id', '__none__', true)"))
    await session.execute(text("SELECT set_config('app.is_platform_admin', 'false', true)"))


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields a database session with tenant context.
    - PostgreSQL: sets RLS session variables (tenant_id AND is_platform_admin)
    - SQLite: filtering handled by event listener above
    """
    async with async_session_factory() as session:
        if not _is_sqlite:
            await apply_session_context(
                session,
                tenant_id=get_current_tenant_id(),
                is_platform_admin=get_is_platform_admin(),
            )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# SQL to set up RLS on a table — called during migrations (PostgreSQL only)
RLS_SETUP_SQL = """
ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON {table_name};
CREATE POLICY tenant_isolation ON {table_name}
    USING (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));
DROP POLICY IF EXISTS admin_bypass ON {table_name};
CREATE POLICY admin_bypass ON {table_name}
    USING (current_setting('app.is_platform_admin', true) = 'true');
"""
