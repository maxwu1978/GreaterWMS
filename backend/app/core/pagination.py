"""
Shared pagination helpers.

Usage in endpoints:
    from app.core.pagination import PaginationParams, paginate

    @router.get("/")
    async def list_items(
        page: PaginationParams = Depends(),
        db: AsyncSession = Depends(get_db_session),
    ):
        query = select(Item)
        return await paginate(db, query, page)

Response format:
    {
        "items": [...],
        "total": 1234,
        "limit": 100,
        "offset": 0,
        "has_more": true
    }
"""

from fastapi import Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select


class PaginationParams:
    def __init__(
        self,
        offset: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(100, ge=1, le=500, description="Max records to return (1-500)"),
    ):
        self.offset = offset
        self.limit = limit


async def paginate(db: AsyncSession, query: Select, page: PaginationParams) -> dict:
    """Execute a query with pagination and return items + total count."""
    # Count total matching rows (without limit/offset)
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Fetch the page
    result = await db.execute(query.offset(page.offset).limit(page.limit))
    rows = result.scalars().all()

    return {
        "items": rows,
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
        "has_more": (page.offset + page.limit) < total,
    }


async def paginate_window(db: AsyncSession, query: Select, page: PaginationParams) -> dict:
    """Execute a limit+1 page without running an exact total count.

    Use this for high-growth operational lists where the active workflow only
    needs the current page and whether another page exists.
    """
    result = await db.execute(query.offset(page.offset).limit(page.limit + 1))
    rows = result.scalars().all()
    has_more = len(rows) > page.limit
    visible_rows = rows[: page.limit]
    lower_bound_total = page.offset + len(visible_rows) + (1 if has_more else 0)

    return {
        "items": visible_rows,
        "total": lower_bound_total,
        "total_is_estimate": has_more,
        "limit": page.limit,
        "offset": page.offset,
        "has_more": has_more,
    }
