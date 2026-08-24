"""PostgreSQL row-level-security tests.

The main suite runs on in-memory SQLite for speed, where tenant isolation is
emulated by a SQLAlchemy event listener. That never exercises the *real*
production isolation mechanism — Postgres RLS policies. These tests run only
when DATABASE_URL points at PostgreSQL (CI provides a Postgres 16 service) and
verify the actual policies: tenant isolation, WITH CHECK on writes, the
platform-admin bypass, and policy coverage of every tenant-scoped table.
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import _TENANT_TABLES, RLS_SETUP_SQL, Base
from app.models import *  # noqa: F401,F403 — register all models
from app.models.client import Client
from app.models.tenant import Tenant

DATABASE_URL = os.environ.get("DATABASE_URL", "")
IS_POSTGRES = DATABASE_URL.startswith("postgresql")

pytestmark = pytest.mark.skipif(
    not IS_POSTGRES,
    reason="Requires a PostgreSQL DATABASE_URL (provided by CI's postgres service)",
)


async def _set_context(session, tenant_id: str | None, is_admin: bool = False) -> None:
    await session.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, false)"),
        {"tid": tenant_id or ""},
    )
    await session.execute(
        text("SELECT set_config('app.is_platform_admin', :adm, false)"),
        {"adm": "true" if is_admin else "false"},
    )


@pytest.fixture
async def pg():
    """Fresh schema + RLS policies on the CI Postgres database, torn down after.

    Yields a session factory connected as a NON-superuser role (`rls_app`).
    This matters: superusers (like the CI service's default user) bypass RLS
    entirely, even with FORCE — asserting through a superuser connection would
    make every isolation test pass vacuously. Production (e.g. Render managed
    Postgres) connects as a non-superuser, which is what `rls_app` simulates.
    """
    from sqlalchemy.engine.url import make_url

    admin_engine = create_async_engine(DATABASE_URL)
    async with admin_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        table_names = set(Base.metadata.tables)
        for table in sorted(_TENANT_TABLES & table_names):
            for statement in RLS_SETUP_SQL.format(table_name=table).split(";"):
                if statement.strip():
                    await conn.execute(text(statement))
        # Non-superuser app role, subject to RLS like the production role
        await conn.execute(
            text(
                "DO $$ BEGIN CREATE ROLE rls_app LOGIN PASSWORD 'rls_app'; "
                "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
            )
        )
        await conn.execute(text("GRANT USAGE ON SCHEMA public TO rls_app"))
        await conn.execute(
            text("GRANT ALL ON ALL TABLES IN SCHEMA public TO rls_app")
        )
        await conn.execute(
            text("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO rls_app")
        )

    app_url = make_url(DATABASE_URL).set(username="rls_app", password="rls_app")
    app_engine = create_async_engine(app_url)
    factory = async_sessionmaker(app_engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await app_engine.dispose()
        async with admin_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await admin_engine.dispose()


async def _seed_two_tenants_with_clients(factory) -> None:
    async with factory() as session:
        await _set_context(session, None, is_admin=True)
        session.add_all(
            [
                Tenant(id="tenant-a", name="Tenant A", code="TA", contact_email="a@x.com"),
                Tenant(id="tenant-b", name="Tenant B", code="TB", contact_email="b@x.com"),
            ]
        )
        await session.flush()
        session.add_all(
            [
                Client(id="client-a", tenant_id="tenant-a", name="Client A", code="CA"),
                Client(id="client-b", tenant_id="tenant-b", name="Client B", code="CB"),
            ]
        )
        await session.commit()


async def test_rls_policies_cover_all_tenant_tables(pg):
    """Every table in _TENANT_TABLES must carry the tenant_isolation policy."""
    async with pg() as session:
        result = await session.execute(
            text(
                "SELECT tablename FROM pg_policies "
                "WHERE policyname = 'tenant_isolation'"
            )
        )
        covered = {row[0] for row in result}
    expected = _TENANT_TABLES & set(Base.metadata.tables)
    missing = expected - covered
    assert not missing, f"Tables without tenant_isolation policy: {sorted(missing)}"
    # Regression guard for the four tables that were absent from _TENANT_TABLES
    for table in (
        "handling_units",
        "inbound_packages",
        "receiving_observed_codes",
        "wcs_task_bindings",
    ):
        assert table in covered, f"{table} lost its RLS policy"


async def test_tenant_cannot_read_other_tenants_rows(pg):
    await _seed_two_tenants_with_clients(pg)

    async with pg() as session:
        await _set_context(session, "tenant-a")
        result = await session.execute(text("SELECT id FROM clients"))
        visible = {row[0] for row in result}
    assert visible == {"client-a"}, f"tenant-a sees {visible}"

    async with pg() as session:
        await _set_context(session, "tenant-b")
        result = await session.execute(text("SELECT id FROM clients"))
        visible = {row[0] for row in result}
    assert visible == {"client-b"}, f"tenant-b sees {visible}"


async def test_with_check_blocks_cross_tenant_writes(pg):
    await _seed_two_tenants_with_clients(pg)

    async with pg() as session:
        await _set_context(session, "tenant-a")
        with pytest.raises(ProgrammingError):
            # Insert claiming to belong to tenant-b while the session is tenant-a
            await session.execute(
                text(
                    "INSERT INTO clients (id, tenant_id, name, code, billing_enabled, "
                    "portal_access, is_active, created_at, updated_at) "
                    "VALUES ('client-x', 'tenant-b', 'Sneaky', 'CX', true, true, true, "
                    "now(), now())"
                )
            )


async def test_no_context_sees_nothing(pg):
    """A session with no tenant context (empty string) must see zero rows."""
    await _seed_two_tenants_with_clients(pg)

    async with pg() as session:
        await _set_context(session, None)
        result = await session.execute(text("SELECT count(*) FROM clients"))
        assert result.scalar() == 0


async def test_platform_admin_bypass_sees_all(pg):
    await _seed_two_tenants_with_clients(pg)

    async with pg() as session:
        await _set_context(session, None, is_admin=True)
        result = await session.execute(text("SELECT count(*) FROM clients"))
        assert result.scalar() == 2
