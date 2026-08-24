# System Architecture

High-level architecture documentation for WMS QuickStart.

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENTS                                         │
├───────────┬──────────────┬────────────────┬────────────────────────────────┤
│  Browser  │  Mobile App  │  AGV Units     │  External Systems              │
│  (React)  │  (Capacitor) │  (WebSocket)   │  (Shopify, Stripe)            │
└─────┬─────┴──────┬───────┴───────┬────────┴───────────┬───────────────────┘
      │            │               │                     │
      │  HTTPS     │  HTTPS        │  WSS                │  Webhooks
      ▼            ▼               ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          RENDER.COM (Backend)                                │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         FastAPI Application                            │  │
│  │                                                                       │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────┐    │  │
│  │  │  Middleware  │  │   REST API   │  │     WebSocket Layer      │    │  │
│  │  │  - CORS     │  │  35 endpoint │  │  - /ws/scanner           │    │  │
│  │  │  - Logging  │  │   modules    │  │  - /ws/agv               │    │  │
│  │  │  - RateLimit│  │  /api/v1/*   │  │                          │    │  │
│  │  └─────────────┘  └──────┬───────┘  └──────────┬───────────────┘    │  │
│  │                           │                     │                     │  │
│  │                    ┌──────▼─────────────────────▼──────────────┐      │  │
│  │                    │          SERVICE LAYER                     │      │  │
│  │                    │  23 services (business logic)              │      │  │
│  │                    │  - ReceivingService                        │      │  │
│  │                    │  - PutawayService                          │      │  │
│  │                    │  - PickingService                          │      │  │
│  │                    │  - AGVService                              │      │  │
│  │                    │  - BillingService                          │      │  │
│  │                    │  - ...                                     │      │  │
│  │                    └──────────────────┬────────────────────────┘      │  │
│  │                                       │                               │  │
│  │                    ┌──────────────────▼────────────────────────┐      │  │
│  │                    │       SQLAlchemy ORM (async)               │      │  │
│  │                    │  13 models + RLS context management        │      │  │
│  │                    └──────────────────┬────────────────────────┘      │  │
│  └───────────────────────────────────────┼───────────────────────────────┘  │
│                                          │                                   │
│  ┌───────────────────┐    ┌─────────────▼───────────────┐                   │
│  │      Redis 7      │    │      PostgreSQL 16           │                   │
│  │  - Rate limiting  │    │  - RLS policies              │                   │
│  │  - Session cache  │    │  - Multi-tenant isolation    │                   │
│  │  - WS state       │    │  - UUID primary keys         │                   │
│  └───────────────────┘    └─────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          VERCEL (Frontend)                                    │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  React SPA (Static Build)                                             │  │
│  │  - 14 feature modules                                                 │  │
│  │  - Zustand auth state                                                 │  │
│  │  - React Query server state                                           │  │
│  │  - TailwindCSS styling                                                │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Layered Architecture

### Request Flow

```
HTTP Request
    │
    ▼
┌─────────────────┐
│   Middleware     │  CORS → Logging → Rate Limit
└────────┬────────┘
         ▼
┌─────────────────┐
│   Endpoint      │  Input validation (Pydantic), auth (JWT)
└────────┬────────┘
         ▼
┌─────────────────┐
│   Dependency     │  get_current_user → set ContextVars → get_db_session
│   Injection      │  (RLS tenant context applied here)
└────────┬────────┘
         ▼
┌─────────────────┐
│   Service Layer  │  Business logic, orchestration, domain rules
└────────┬────────┘
         ▼
┌─────────────────┐
│   ORM / DB      │  SQLAlchemy async queries (RLS-filtered)
└─────────────────┘
```

### Layer Responsibilities

| Layer | Responsibility | Rules |
|-------|---------------|-------|
| Endpoint | HTTP concerns, request/response shape | Thin; no business logic |
| Service | Business rules, orchestration | May compose other services |
| Model | Data structure, relationships | No behavior beyond computed props |
| Core | Cross-cutting concerns | Config, auth, DB setup, middleware |

---

## Multi-Tenancy Architecture

### Row-Level Security (RLS)

```
┌────────────────────────────────────────────────────────┐
│                    REQUEST PROCESSING                    │
│                                                         │
│  1. JWT decoded → extract tenant_id                     │
│  2. ContextVar _current_tenant_id = tenant_id           │
│  3. DB session created                                  │
│  4. PostgreSQL: SET app.current_tenant_id = '...'       │
│  5. All subsequent queries auto-filtered by RLS         │
│                                                         │
│  Result: Impossible to access other tenant's data       │
└────────────────────────────────────────────────────────┘
```

### Dual-Mode Isolation

| Environment | Mechanism | Enforcement Level |
|-------------|-----------|-------------------|
| Production (PostgreSQL) | RLS policies | Database engine |
| Testing (SQLite) | ORM event listener | Application layer |

**Platform Admin Bypass:** When `_is_platform_admin = True`, RLS policies are bypassed via a separate policy that checks `current_setting('app.is_platform_admin')`.

---

## Authentication & Authorization

```
┌──────────────────────────────────────────────────────────────┐
│                     AUTH FLOW                                  │
│                                                              │
│  Login: POST /api/v1/auth/login                              │
│    → Verify credentials                                      │
│    → Generate JWT (user_id, tenant_id, role, permissions)    │
│    → Return token (8-hour expiry)                            │
│                                                              │
│  Protected Request:                                          │
│    → Bearer token in Authorization header                    │
│    → Decode & verify JWT                                     │
│    → Check subscription status (cached 5 min)                │
│    → Set tenant context (ContextVars)                        │
│    → Check role/permission if endpoint requires              │
│    → Proceed to endpoint handler                             │
└──────────────────────────────────────────────────────────────┘
```

### Permission Model

```
PLATFORM_ADMIN ─── bypasses all checks, cross-tenant
       │
TENANT_ADMIN ──── full access within tenant
       │
OPERATOR ──────── specific permissions (receiving.execute, picking.execute, ...)
       │
CLIENT_VIEWER ──── read-only, scoped to assigned client_id
```

---

## Data Flow: Warehouse Operations

### Receiving → Putaway → Storage

```
InboundOrder (ASN)
    │
    ▼ [receiving_service.py]
ReceivingLabel generated
    │
    ▼ [operator scans label]
InventoryTransaction (type: RECEIVE)
    │
    ▼ [putaway_service.py]
Task (type: PUTAWAY) created
    │
    ▼ [suggest location → operator confirms]
Inventory record created/updated at destination
InventoryTransaction (type: PUTAWAY)
```

### Order → Pick → Ship

```
OutboundOrder
    │
    ▼ [picking_service.py]
Allocation (FIFO inventory selection)
    │
    ▼
Task(s) (type: PICKING) created
    │
    ▼ [operator/AGV executes]
Inventory.quantity_allocated → quantity_on_hand decremented
InventoryTransaction (type: PICK)
    │
    ▼ [shipping_service.py]
Packing → Label → Ship
InventoryTransaction (type: SHIP)
```

---

## WebSocket Architecture

```
┌──────────────┐          ┌─────────────────────────────────┐
│  Mobile App  │──WSS────▶│  /ws/scanner                     │
│  (scanner)   │          │  - Auth via first JSON message   │
└──────────────┘          │  - Barcode lookup (location/SKU) │
                          │  - Per-user connection           │
                          └─────────────────────────────────┘

┌──────────────┐          ┌─────────────────────────────────┐
│  AGV Unit    │──WSS────▶│  /ws/agv                         │
│  (robot)     │          │  - Auth + unit_id registration   │
└──────────────┘          ��  - Position/status reporting     │
                          │  - Fleet broadcast (per-tenant)  │
┌──────────────┐          │  - Task dispatch (server→AGV)    │
│  AGV Unit 2  │──WSS────▶│                                  │
└──────────────┘          └──────────┬──────────────────────┘
                                     │
                          ┌──────────▼──────────────────────┐
                          │  AGVFleetManager (in-memory)      │
                          │  {tenant_id: {unit_id: state}}   │
                          └─────────────────────────────────┘
```

---

## External Integrations

```
┌────────────────────────────────────────────────────────────┐
│                    INTEGRATIONS                              │
│                                                            │
│  ┌──────────┐   Webhooks    ┌─────────��────────────┐      │
│  │ Shopify  │──────────────▶│ /api/v1/integrations │      │
│  │          │◀──────────────│ (order sync)         │      │
│  └─────���────┘   API calls   └──────────────────────┘      │
│                                                            │
│  ┌──────────┐   Webhooks    ┌──────────────────────┐      │
│  │ Stripe   │──────────────▶│ /api/v1/billing      │      │
│  │          │◀──────────────│ (payment processing) │      │
│  └──────────┘   API calls   └──────────────────────┘      │
│                                                            │
│  ┌─────────��┐   API calls   ┌──────────────────────┐      │
│  │ AI APIs  │◀──────────────│ Agent Console        │      │
│  │ DeepSeek │               │ (multi-model)        │      │
│  │ Qwen     │               └──────────────────────┘      │
│  │ Kimi     │                                              │
│  │ MiniMax  │                                              │
│  └──────────┘                                              │
└────────────────────────────────────────────────────────────┘
```

---

## Frontend Architecture

```
┌───────────────────────────────────────────────────────────┐
│                   REACT APPLICATION                         │
│                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐   │
│  │   Router    │  │  Auth Store  │  │  React Query  │   │
│  │ (React      │  │  (Zustand)   │  │  (Server      │   │
│  │  Router v6) │  │  - token     │  │   State)      │   │
│  │             │  │  - user      │  │  - caching    │   │
│  │             │  │  - role      │  │  - refetch    │   │
│  └──────┬──────┘  └──────────────┘  └───────────────┘   │
│         │                                                 │
│  ┌──────▼───────────────────────────────────────────────┐ │
│  │              FEATURE MODULES (14)                     │ │
│  │                                                      │ │
│  │  receiving/  picking/  putaway/  shipping/           │ │
│  │  inventory/  dashboard/  billing/  agv/             │ │
│  │  admin/  auth/  clients/  client-portal/            │ │
│  │  marketing/                                          │ │
│  └──────────────────────────────────────────────────────┘ │
│         │                                                 │
│  ┌──────▼───────────────────────────────────────────────┐ │
│  │              SHARED LAYER                             │ │
│  │  - API client (Axios + auth interceptor)             │ │
│  │  - DataTable, Layout, StatusBadge                    │ │
│  │  - useAuth hook, useWebSocket hook                   │ │
│  │  - i18n (en/zh)                                      │ │
│  └──────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

---

## Deployment Topology

### Production

| Component | Platform | URL |
|-----------|----------|-----|
| Backend API | Render.com | api.maxsmartwms.online |
| Frontend SPA | Vercel | app.maxsmartwms.online |
| PostgreSQL | Render.com | Internal connection |
| Redis | Render.com | Internal connection |

### Local Development

```bash
docker-compose up -d     # PostgreSQL 16 + Redis 7
cd backend && uv run uvicorn app.main:app --reload   # :8000
cd frontend && npm run dev                            # :5173
```

---

## Security Architecture

### Defense in Depth

```
Layer 1: CORS (origin whitelist)
Layer 2: Rate Limiting (120 req/min per IP)
Layer 3: JWT Authentication (token verification)
Layer 4: Subscription Check (payment enforcement)
Layer 5: Role/Permission Check (authorization)
Layer 6: RLS (database-level tenant isolation)
Layer 7: Input Validation (Pydantic schemas)
Layer 8: Row-level Locking (concurrency safety)
```

### Sensitive Data Handling
- Passwords: bcrypt hashed via passlib
- JWT secrets: auto-generated in dev, required env var in production
- API keys (Stripe, AI): env vars only, never in code
- Tenant data: physically isolated via RLS at DB level

---

## Scalability Considerations

### Current State (Single Instance)
- Stateless API (can horizontally scale)
- Stateful WebSocket connections (AGVFleetManager is in-memory)
- Single PostgreSQL instance with connection pooling

### Scaling Path
1. **Horizontal API scaling:** Add Render instances (stateless, share DB)
2. **WebSocket scaling:** Extract AGVFleetManager to Redis pub/sub
3. **Database scaling:** Read replicas for queries, write primary for mutations
4. **Background jobs:** Celery workers (already in dependencies) with Redis broker
5. **CDN:** Vercel already provides edge caching for frontend
