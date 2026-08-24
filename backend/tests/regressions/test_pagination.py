"""Regression tests: pagination (split from tests/test_regressions.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.clients import list_clients
from app.core.pagination import PaginationParams, paginate, paginate_window
from app.core.security import TokenPayload, UserRole
from app.models.client import Client
from app.models.tenant import Tenant


@pytest.mark.asyncio
async def test_paginate_returns_items_total_offset_and_has_more(db: AsyncSession, tenant_id: str):
    """Pagination helper should expose metadata needed by clients."""
    db.add(Tenant(id=tenant_id, name="Test 3PL", code="TST", contact_email="test@example.com"))
    for i in range(6):
        db.add(Client(id=f"client-{i}", tenant_id=tenant_id, name=f"Client {i}", code=f"C{i}"))
    await db.flush()

    first_page = await paginate(
        db,
        select(Client).order_by(Client.code),
        PaginationParams(offset=0, limit=2),
    )
    last_page = await paginate(
        db,
        select(Client).order_by(Client.code),
        PaginationParams(offset=4, limit=2),
    )

    assert len(first_page["items"]) == 2
    assert first_page["total"] == 6
    assert first_page["limit"] == 2
    assert first_page["offset"] == 0
    assert first_page["has_more"] is True
    assert [c.code for c in first_page["items"]] == ["C0", "C1"]

    assert len(last_page["items"]) == 2
    assert last_page["total"] == 6
    assert last_page["offset"] == 4
    assert last_page["has_more"] is False
    assert [c.code for c in last_page["items"]] == ["C4", "C5"]


@pytest.mark.asyncio
async def test_paginate_window_avoids_exact_count(db: AsyncSession, tenant_id: str):
    """Window pagination should use limit+1 instead of a separate count query."""
    db.add(Tenant(id=tenant_id, name="Test 3PL", code="TST", contact_email="test@example.com"))
    for i in range(4):
        db.add(Client(id=f"window-client-{i}", tenant_id=tenant_id, name=f"Client {i}", code=f"W{i}"))
    await db.flush()

    statements: list[str] = []

    def capture_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement.lower())

    sync_bind = db.sync_session.get_bind()
    event.listen(sync_bind, "before_cursor_execute", capture_selects)
    try:
        first_page = await paginate_window(
            db,
            select(Client).order_by(Client.code),
            PaginationParams(offset=0, limit=2),
        )
    finally:
        event.remove(sync_bind, "before_cursor_execute", capture_selects)

    assert [c.code for c in first_page["items"]] == ["W0", "W1"]
    assert first_page["total"] == 3
    assert first_page["total_is_estimate"] is True
    assert first_page["has_more"] is True
    assert len(statements) == 1
    assert "count(" not in statements[0]


@pytest.mark.asyncio
async def test_client_list_uses_window_pagination_without_exact_count(
    db: AsyncSession,
    tenant_id: str,
):
    """Master-data lists should avoid exact counts when a next-page flag is enough."""
    db.add(Tenant(id=tenant_id, name="Window Tenant", code="WNT", contact_email="w@example.com"))
    for i in range(4):
        db.add(
            Client(
                id=f"client-window-{i}",
                tenant_id=tenant_id,
                name=f"Window Client {i}",
                code=f"WC{i}",
            )
        )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin-window",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    statements: list[str] = []

    def capture_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement.lower())

    sync_bind = db.sync_session.get_bind()
    event.listen(sync_bind, "before_cursor_execute", capture_selects)
    try:
        page = await list_clients(
            page=PaginationParams(offset=0, limit=2),
            current_user=current_user,
            db=db,
        )
    finally:
        event.remove(sync_bind, "before_cursor_execute", capture_selects)

    assert [item.code for item in page["items"]] == ["WC0", "WC1"]
    assert page["total"] == 3
    assert page["total_is_estimate"] is True
    assert page["has_more"] is True
    assert len(statements) == 1
    assert "count(" not in statements[0]
