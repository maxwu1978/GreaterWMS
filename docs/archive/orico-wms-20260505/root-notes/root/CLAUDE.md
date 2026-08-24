# WMS QuickStart - Claude Code Project Instructions

## Project Overview

Multi-tenant Cloud Warehouse Management System (WMS) for 3PL warehouses.
- **Backend**: FastAPI (Python 3.12+), SQLAlchemy 2.0 async, PostgreSQL + Redis
- **Frontend**: React 18, TypeScript, Vite 6, TailwindCSS 3.4, Zustand, React Query
- **Deployment**: Render.com (primary), Vercel (frontend)
- **Testing**: pytest + pytest-asyncio (SQLite in-memory), Vitest (frontend)

## Repository Structure

```
backend/           FastAPI application
  app/
    api/v1/endpoints/   35 endpoint files
    models/             13 model files (SQLAlchemy)
    services/           23 service files (business logic)
    core/               config, database, security, deps, middleware
    websocket/          agv_dispatch.py, scanner.py
  tests/                pytest test suites
  alembic/              database migrations
frontend/          React SPA
  src/
    modules/            14 feature modules (receiving, picking, putaway, shipping...)
    shared/             components, hooks, API client, i18n
    scanner/            BarcodeScanner.tsx (camera-based)
docs/              Project documentation
infra/             Terraform, init scripts
```

## Key Architecture Decisions

### Multi-Tenancy
- PostgreSQL RLS (Row-Level Security) in production
- SQLAlchemy ORM event listener for SQLite in testing
- All tenant-scoped models inherit `TenantMixin`
- Context variables: `_current_tenant_id`, `_is_platform_admin`

### Authentication & Authorization
- JWT tokens (python-jose) with user_id, tenant_id, role, permissions
- Roles: TENANT_ADMIN, OPERATOR, VIEWER, CUSTOMER, PLATFORM_ADMIN
- Fine-grained permissions: RECEIVING_EXECUTE, USERS_MANAGE, etc.
- FastAPI deps: `require_role()`, `require_permission()`

### Database Patterns
- Async sessions via `get_db_session()` dependency
- `for_update()` row-level locks for inventory concurrency
- Composite indexes on task queue (status, assigned_to)
- All models use UUID primary keys via `generate_uuid()`

### Task System
- Unified `Task` model for human + AGV workflows
- TaskType: RECEIVING, PUTAWAY, PICKING, PACKING, SHIPPING, CYCLE_COUNT
- TaskStatus: OPEN -> ASSIGNED -> IN_PROGRESS -> COMPLETED / FAILED
- AssignedType: USER, AGV, WAVE

## Commands

### Backend
```bash
cd backend
uv run uvicorn app.main:app --reload          # dev server (port 8000)
uv run pytest                                  # run all tests
uv run pytest tests/test_end_to_end_flow.py   # specific test file
uv run ruff check .                            # lint
uv run mypy app/                               # type check
uv run alembic upgrade head                    # run migrations
uv run alembic revision --autogenerate -m "description"  # create migration
```

### Frontend
```bash
cd frontend
npm install                  # install deps
npm run dev                  # dev server (port 5173)
npm run build                # production build
npm run lint                 # ESLint
npx tsc --noEmit             # type check
```

### Docker
```bash
docker-compose up -d         # PostgreSQL + Redis + API
```

## Code Style & Conventions

### Backend
- Service layer pattern: all business logic in `app/services/`, endpoints are thin
- Async/await throughout - never use sync DB calls
- Pydantic models for request/response schemas (inline in endpoints)
- Use `flush()` during service operations, session auto-commits via dependency
- Import models via `app.models` package (re-exports from `__init__.py`)

### Frontend
- Feature modules in `src/modules/<feature>/` with page components
- Shared components in `src/shared/components/`
- State: Zustand for auth, React Query for server state
- API calls via `src/shared/api/client.ts` (Axios with auth interceptor)
- Styling: TailwindCSS utility classes, no CSS modules

### Naming
- Backend: snake_case (Python standard)
- Frontend: camelCase for variables/functions, PascalCase for components
- API routes: `/api/v1/<resource>` (plural nouns)
- Database tables: snake_case, plural

## Important Files

- `backend/app/core/database.py` - DB session factory, RLS context
- `backend/app/core/deps.py` - All FastAPI dependency injection
- `backend/app/core/security.py` - JWT, password hashing, roles/permissions
- `backend/app/models/base.py` - TimestampMixin, TenantMixin, base classes
- `frontend/src/shared/hooks/useAuth.ts` - Auth state (Zustand store)
- `frontend/src/shared/api/client.ts` - HTTP client configuration
- `docker-compose.yml` - Local dev infrastructure
- `render.yaml` - Production deployment blueprint

## Testing Notes

- Tests use in-memory SQLite with async driver
- `conftest.py` provides fixtures: tenant_id, warehouse_id, operator_token, admin_token
- RLS isolation simulated via ORM event listener in test mode
- Run specific test: `uv run pytest tests/test_end_to_end_flow.py::test_full_warehouse_flow -v`

## Environment Variables

### Backend (key ones)
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `JWT_SECRET_KEY` - Token signing secret
- `DEBUG` - Enable debug mode
- `CORS_ORIGINS` - Allowed frontend origins

### Frontend
- `VITE_API_BASE_URL` - Backend API base URL

## Current Work Context

- Active branch pattern: `codex/<feature>` for Codex-driven work
- Receiving flow recently enhanced: system labels, traceability, recovery actions
- AGV integration in progress (WebSocket dispatch, location mapping)
- Putaway page is the largest frontend component (~3.5K lines)
