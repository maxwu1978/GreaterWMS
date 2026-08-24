"""Test fixtures — in-memory SQLite for fast unit tests."""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, set_current_tenant_id, set_is_platform_admin
from app.core.security import UserRole, create_access_token
from app.models import *  # noqa: F401,F403 — register all models


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh in-memory database for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture(autouse=True)
def reset_request_context():
    """Prevent ContextVar leakage between tests."""
    set_current_tenant_id(None)
    set_is_platform_admin(False)
    yield
    set_current_tenant_id(None)
    set_is_platform_admin(False)


@pytest.fixture
def tenant_id() -> str:
    return "test-tenant-001"


@pytest.fixture
def client_id() -> str:
    return "test-client-001"


@pytest.fixture
def warehouse_id() -> str:
    return "test-warehouse-001"


@pytest.fixture
def user_id() -> str:
    return "test-user-001"


@pytest.fixture
def operator_token(tenant_id: str) -> str:
    return create_access_token(
        user_id="test-user-001",
        role=UserRole.OPERATOR,
        tenant_id=tenant_id,
    )


@pytest.fixture
def admin_token() -> str:
    return create_access_token(
        user_id="platform-admin",
        role=UserRole.PLATFORM_ADMIN,
    )
