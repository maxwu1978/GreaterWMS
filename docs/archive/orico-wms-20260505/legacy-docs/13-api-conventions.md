# API Design Conventions

REST API design patterns and standards for WMS QuickStart.

## Base URL & Versioning

- **Base path:** `/api/v1/`
- **Strategy:** URL path versioning (all routes under `/api/v1/`)
- **Full production URL:** `https://api.maxsmartwms.online/api/v1/`

## Route Registration

Routes are defined in `backend/app/api/v1/router.py`:

```python
api_v1_router = APIRouter()
api_v1_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_v1_router.include_router(receiving.router, prefix="/receiving", tags=["Receiving"])
api_v1_router.include_router(inventory.router, prefix="/inventory", tags=["Inventory"])
# ... 33 modules total
```

Mounted in `main.py`:
```python
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)
```

## Naming Conventions

| Pattern | Example |
|---------|---------|
| Collection | `GET /api/v1/orders` |
| Single resource | `GET /api/v1/orders/{id}` |
| Sub-resource | `GET /api/v1/orders/{id}/lines` |
| Action | `POST /api/v1/orders/{id}/allocate` |

- Plural nouns for resources
- Kebab-case for multi-word routes: `/inbound-orders/`
- UUIDs for resource identifiers

---

## Authentication

### Bearer Token (JWT)

All protected endpoints require:
```
Authorization: Bearer <jwt_token>
```

### Token Structure
```json
{
  "sub": "<user_id>",
  "tenant_id": "<tenant_id>",
  "client_id": "<client_id|null>",
  "role": "operator|tenant_admin|platform_admin|client_viewer",
  "permissions": ["receiving.execute", "inbound_orders.manage", ...],
  "exp": 1735689600
}
```

Token lifetime: 480 minutes (8 hours, aligned with warehouse shifts).

### Access Control

```python
# Role-based
@router.get("/users")
async def list_users(
    current_user = Depends(require_role(UserRole.TENANT_ADMIN)),
    db = Depends(get_db_session),
): ...

# Permission-based
@router.post("/receiving/accept")
async def accept_goods(
    current_user = Depends(require_permission(UserPermission.RECEIVING_EXECUTE)),
    db = Depends(get_db_session),
): ...
```

### Roles & Permissions

| Role | Scope | Description |
|------|-------|-------------|
| `platform_admin` | Cross-tenant | System operator, bypasses RLS |
| `tenant_admin` | Tenant | Full access within tenant |
| `operator` | Tenant | Execution tasks (receive, pick, ship) |
| `client_viewer` | Client | Read-only portal access |

Permissions (11 total): `inbound_orders.manage`, `receiving.execute`, `inventory.manage`, `outbound_orders.manage`, `picking.execute`, `shipping.execute`, `users.manage`, `billing.manage`, `reports.view`, `settings.manage`, `*` (wildcard)

---

## Request/Response Patterns

### Pagination

**Query parameters:**
```
GET /api/v1/inventory?offset=0&limit=100
```

| Param | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| offset | int | 0 | ≥ 0 | Skip N records |
| limit | int | 100 | 1-500 | Page size |

**Response format:**
```json
{
  "items": [...],
  "total": 1234,
  "limit": 100,
  "offset": 0,
  "has_more": true
}
```

### Single Resource Response
```json
{
  "id": "uuid",
  "field": "value",
  "created_at": "2026-05-05T07:00:00Z",
  "updated_at": "2026-05-05T07:30:00Z"
}
```

### Create/Update Request
```json
{
  "field": "value",
  "nested": {...}
}
```

Returns: the created/updated resource with `201 Created` or `200 OK`.

---

## Error Responses

### Format
```json
{
  "detail": "Error message string"
}
```

Or structured:
```json
{
  "detail": {
    "error": "error_code",
    "message": "Human-readable message",
    "field": "optional_field_name"
  }
}
```

### HTTP Status Codes

| Code | Usage |
|------|-------|
| `200` | Success (GET, PUT, PATCH) |
| `201` | Created (POST) |
| `204` | No content (DELETE) |
| `400` | Bad request / validation error |
| `401` | Invalid or missing JWT token |
| `402` | Subscription required / expired |
| `403` | Insufficient role or permission |
| `404` | Resource not found |
| `409` | Conflict (duplicate, state violation) |
| `422` | Semantic validation failure |
| `429` | Rate limit exceeded |

### 402 Payment Required (Subscription)
```json
{
  "detail": {
    "error": "trial_expired|expired|cancelled|no_subscription",
    "message": "Your trial has expired. Please subscribe to continue.",
    "plans_url": "/api/v1/subscriptions/plans"
  }
}
```

### 429 Rate Limit
```json
{"detail": "Rate limit exceeded"}
```
Header: `Retry-After: 60`

---

## Middleware Stack

Request processing order (first to last):

1. **CORSMiddleware** — origin validation, preflight handling
2. **RequestLoggingMiddleware** — timing, X-Request-ID header, tenant context logging
3. **RateLimitMiddleware** — 120 req/min per IP (exempts `/health`, `/api/docs`)

### Rate Limiting Rules
- Default: 120 requests/minute per IP address
- In-memory tracking (per-process)
- Exempt paths: `/health`, `/api/docs`, `/api/openapi.json`
- Response: `429` with `Retry-After: 60` header

### Request Logging Output
```
INFO: tenant=<uuid> method=GET path=/api/v1/inventory status=200 duration=45ms request_id=a1b2c3d4
```

---

## Multi-Tenancy

### Automatic RLS Isolation

All queries on tenant-scoped tables are automatically filtered by `tenant_id`:
- **PostgreSQL:** Row-Level Security policies
- **SQLite (test):** ORM event listener injects WHERE clauses

**No manual filtering needed** — the middleware sets context before session executes queries.

### Dependency Order (Critical)

```python
@router.get("/items")
async def get_items(
    current_user = Depends(get_current_user),   # 1. Sets ContextVars
    db = Depends(get_db_session),               # 2. Reads ContextVars, applies RLS
): ...
```

`get_current_user` MUST appear before `get_db_session` in the dependency chain.

---

## Subscription Enforcement

- Checked on every authenticated request (except PLATFORM_ADMIN)
- 5-minute in-memory cache per tenant to avoid DB hits
- Statuses: `TRIAL` (check trial_end_date), `ACTIVE`, `PAST_DUE` (allowed), `CANCELLED` (until period end)

---

## WebSocket Endpoints

| Path | Purpose |
|------|---------|
| `/ws/scanner` | Barcode scanning (auth via first JSON message) |
| `/ws/agv` | AGV fleet dispatch (auth via first JSON message) |

See [WebSocket Protocol](11-websocket-protocol.md) for details.

---

## API Documentation (OpenAPI)

Auto-generated Swagger UI available at:
- **Swagger UI:** `/docs`
- **ReDoc:** `/redoc`
- **OpenAPI JSON:** `/openapi.json`

---

## Endpoint Pattern Template

Standard endpoint structure:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.deps import get_current_user, get_db_session, require_permission
from app.core.security import TokenPayload, UserPermission
from app.core.pagination import PaginationParams, paginate
from app.services.my_service import MyService

router = APIRouter()

class ItemCreate(BaseModel):
    name: str
    quantity: int

class ItemResponse(BaseModel):
    id: str
    name: str
    quantity: int
    class Config:
        from_attributes = True

@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    data: ItemCreate,
    current_user: TokenPayload = Depends(require_permission(UserPermission.INVENTORY_MANAGE)),
    db: AsyncSession = Depends(get_db_session),
):
    result = await MyService.create(db, data, current_user.tenant_id)
    return result

@router.get("/", response_model=dict)
async def list_items(
    page: PaginationParams = Depends(),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    query = select(Item).order_by(Item.created_at.desc())
    return await paginate(db, query, page)
```
