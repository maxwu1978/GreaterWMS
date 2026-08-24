"""Read-only operations board API."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import client_scope_filter, get_current_user, require_role
from app.core.security import TokenPayload, UserRole
from app.services.operations_board_service import OperationsBoardService

router = APIRouter()


class OperationsBoardItem(BaseModel):
    id: str
    category: str
    operation: str
    lane: str
    source_status: str
    reference_type: str
    reference_id: str
    reference_number: str
    client_id: str | None = None
    client_name: str | None = None
    priority: int
    due_at: str | None = None
    created_at: str | None = None
    quantity: int = 0
    quantity_progress: int | None = None
    location_label: str | None = None
    assigned_type: str | None = None
    assigned_to: str | None = None
    action_key: str
    action_route: str
    blocker_code: str | None = None


class OperationsBoardResponse(BaseModel):
    generated_at: str
    warehouse_id: str | None = None
    items: list[OperationsBoardItem]
    counts: dict[str, Any]


@router.get(
    "/board",
    response_model=OperationsBoardResponse,
    dependencies=[
        Depends(
            require_role(
                UserRole.TENANT_ADMIN,
                UserRole.OPERATOR,
                UserRole.CLIENT_VIEWER,
            )
        )
    ],
)
async def operations_board(
    warehouse_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> OperationsBoardResponse:
    client_id = client_scope_filter(current_user)
    result = await OperationsBoardService(db, current_user.tenant_id).build(
        warehouse_id=warehouse_id,
        client_id=client_id,
        limit=limit,
        include_tasks=current_user.role != UserRole.CLIENT_VIEWER,
    )
    return OperationsBoardResponse(**result)
