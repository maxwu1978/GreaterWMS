import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import set_current_tenant_id, set_is_platform_admin
from app.models.pack_list import PackListDocument


@pytest.mark.asyncio
async def test_pack_list_rows_are_filtered_by_tenant_in_sqlite(db: AsyncSession) -> None:
    db.add_all(
        [
            PackListDocument(
                id="pack-doc-tenant-a",
                tenant_id="tenant-a",
                inbound_order_id="inbound-a",
                source_file_name="a.csv",
                source_checksum="a" * 64,
            ),
            PackListDocument(
                id="pack-doc-tenant-b",
                tenant_id="tenant-b",
                inbound_order_id="inbound-b",
                source_file_name="b.csv",
                source_checksum="b" * 64,
            ),
        ]
    )
    await db.flush()

    set_current_tenant_id("tenant-a")
    set_is_platform_admin(False)
    rows = list((await db.execute(select(PackListDocument))).scalars())

    assert [row.id for row in rows] == ["pack-doc-tenant-a"]


@pytest.mark.asyncio
async def test_sqlite_rejects_cross_tenant_pack_list_write(db: AsyncSession) -> None:
    set_current_tenant_id("tenant-a")
    set_is_platform_admin(False)
    db.add(
        PackListDocument(
            id="pack-doc-cross-tenant",
            tenant_id="tenant-b",
            inbound_order_id="inbound-b",
            source_file_name="b.csv",
            source_checksum="c" * 64,
        )
    )

    with pytest.raises(ValueError, match="Cross-tenant write"):
        await db.flush()

    await db.rollback()
