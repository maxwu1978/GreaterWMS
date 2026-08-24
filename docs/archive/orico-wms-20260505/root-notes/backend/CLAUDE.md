# Backend - Claude Code Instructions

## Running

```bash
uv run uvicorn app.main:app --reload     # dev server
uv run pytest                             # tests
uv run ruff check .                       # lint
uv run mypy app/                          # type check
```

## Architecture Rules

### Service Layer Pattern
- **Endpoints** are thin: validate input, call service, return response
- **Services** contain all business logic, receive `AsyncSession` as first arg
- Never put business logic directly in endpoint functions
- Services may call other services (compose, don't duplicate)

### Database Access
- Always use `async` session from `get_db_session()` dependency
- Use `select()` + `await session.execute()` (SQLAlchemy 2.0 style)
- For writes that need the ID immediately: `session.flush()` (not commit)
- For concurrent inventory updates: `with_for_update()` to lock rows
- Never use legacy `session.query()` API

### Multi-Tenancy
- Every tenant-scoped model inherits `TenantMixin` (adds `tenant_id` column)
- RLS context is set automatically via `get_db_session()` dependency
- In tests, RLS is simulated via SQLAlchemy `after_bulk_insert` / `before_exec` events
- When querying: RLS handles filtering, no need to manually add `where(tenant_id==...)`
- Exception: platform admin endpoints bypass RLS via `_is_platform_admin` context var

### Request/Response Schemas
- Define Pydantic models inline in endpoint files (not separate schema files)
- Use `class Config: from_attributes = True` for ORM model serialization
- Response models go in the endpoint's return type annotation

### Error Handling
- Raise `HTTPException` in endpoints for client errors (400, 404, 409)
- Services raise domain exceptions; endpoints catch and translate to HTTP
- Use `status_code=422` for validation failures beyond Pydantic

## Model Conventions

All models in `app/models/`:
- UUID primary keys via `generate_uuid()` default
- `TimestampMixin` for created_at/updated_at
- `TenantMixin` for tenant-scoped tables
- Import via `from app.models import ModelName`

Key relationships:
```
Tenant -> User, Warehouse, Client, SKU, InboundOrder, OutboundOrder
Warehouse -> Zone -> Location
InboundOrder -> InboundOrderLine -> ReceivingLabel
Task (unified) -> linked via order_id, location_id, assigned_to
Inventory -> keyed by (tenant_id, sku_id, location_id)
```

## Adding a New Feature

1. **Model**: Add to `app/models/`, update `__init__.py` re-exports
2. **Service**: Create `app/services/<feature>_service.py`
3. **Endpoint**: Create `app/api/v1/endpoints/<feature>.py`
4. **Router**: Register in `app/api/v1/router.py` (or wherever routes are aggregated)
5. **Migration**: `uv run alembic revision --autogenerate -m "add <feature>"`
6. **Test**: Add to `tests/test_<feature>.py`

## Test Fixtures (conftest.py)

Available fixtures:
- `db_session` - async SQLite session (auto-rolled-back)
- `tenant_id` - pre-created tenant UUID
- `client_id` - pre-created client UUID
- `warehouse_id` - pre-created warehouse UUID
- `user_id` - pre-created operator user UUID
- `operator_token` - JWT for OPERATOR role
- `admin_token` - JWT for TENANT_ADMIN role

## Common Gotchas

- **Don't forget `await`** on all DB operations (async SQLAlchemy)
- **Model imports**: Always import from `app.models`, not from individual files
- **Circular imports**: Services should not import from endpoints
- **Test isolation**: Each test gets a fresh session; don't share state between tests
- **Enum values**: Use `.value` when comparing with DB-stored enum strings
