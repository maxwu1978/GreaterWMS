# WMS QuickStart

Multi-tenant Cloud Warehouse Management System for 3PL warehouses. Supports full warehouse lifecycle from receiving to shipping, with AGV integration and AI-assisted operations.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, SQLAlchemy 2.0 (async), PostgreSQL, Redis |
| Frontend | React 18, TypeScript, Vite, TailwindCSS, Zustand |
| Auth | JWT + RBAC + PostgreSQL RLS (multi-tenant isolation) |
| Deployment | Render.com (backend), Vercel (frontend) |
| CI/CD | GitHub Actions (lint, type-check, test, build) |

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- Docker & Docker Compose (for PostgreSQL + Redis)

### 1. Start Infrastructure

```bash
docker-compose up -d   # PostgreSQL 16 + Redis 7
```

### 2. Backend

```bash
cd backend
cp .env.example .env   # configure environment variables
uv sync                # install dependencies
uv run alembic upgrade head   # run migrations
uv run python seed.py         # seed demo data
uv run uvicorn app.main:app --reload  # http://localhost:8000
```

API docs available at `http://localhost:8000/docs` (Swagger UI).

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # set VITE_API_BASE_URL=http://localhost:8000/api/v1
npm run dev                   # http://localhost:5173
```

## Core Modules

| Module | Description |
|--------|-------------|
| Receiving | Inbound order processing, label generation, goods receipt |
| Putaway | Location suggestion, split-destination planning, operator UX |
| Picking | Wave allocation, FIFO selection, pick task management |
| Shipping | Packing verification, label printing, manifest generation |
| Inventory | Stock levels, cycle counts, adjustments, transactions |
| AGV | Robot task dispatch, WebSocket coordination, location mapping |
| Billing | Usage-based invoicing, subscription tiers, Stripe integration |
| Client Portal | Customer-facing view of orders, inventory, invoices |
| Agent Console | AI-assisted warehouse operations (multi-model) |

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌────────────┐
│   Frontend  │────▶│  FastAPI     │────▶│ PostgreSQL │
│  React SPA  │     │  Backend     │     │  (RLS)     │
└─────────────┘     └──────┬───────┘     └────────────┘
                           │
                    ┌──────┴───────┐
                    │    Redis     │
                    │ (cache/queue)│
                    └──────────────┘
```

**Multi-Tenancy**: Row-Level Security (RLS) ensures complete data isolation between tenants at the database level.

**Task System**: Unified task model drives both human and AGV workflows through a shared state machine (OPEN → ASSIGNED → IN_PROGRESS → COMPLETED).

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/    # 35 REST endpoint modules
│   │   ├── models/              # 13 SQLAlchemy model files
│   │   ├── services/            # 23 business logic services
│   │   ├── core/                # config, DB, auth, middleware
│   │   └── websocket/           # real-time AGV + scanner
│   ├── tests/                   # pytest suites
│   └── alembic/                 # DB migrations
├── frontend/
│   └── src/
│       ├── modules/             # 14 feature modules
│       ├── shared/              # reusable components & hooks
│       └── scanner/             # barcode camera integration
├── docs/                        # project documentation
├── infra/                       # Terraform, init scripts
├── docker-compose.yml           # local dev services
└── render.yaml                  # production deployment
```

## Testing

```bash
# Backend
cd backend
uv run pytest                              # all tests
uv run pytest tests/test_end_to_end_flow.py -v  # e2e flow
uv run ruff check . && uv run mypy app/    # lint + types

# Frontend
cd frontend
npx tsc --noEmit     # type check
npm run build        # build verification
```

## Documentation

See [`docs/`](docs/) for detailed documentation:

**Architecture & Design:**
- [System Architecture](docs/14-system-architecture.md)
- [Database Schema & ERD](docs/12-database-schema.md)
- [API Conventions](docs/13-api-conventions.md)
- [WebSocket Protocol](docs/11-websocket-protocol.md)

**Operations:**
- [Warehouse Operations Flow](docs/09-warehouse-operations-flow.md)
- [Operations Runbook](docs/10-operations-runbook.md)
- [Deployment Guide](docs/vercel-render-deployment.md)

**Project History:**
- [Project Plan](docs/project-plan.md)
- [GitHub & AWS Setup](docs/01-github-and-aws-setup.md)
- [Shopify Integration](docs/02-shopify-integration-guide.md)
- [Capability Gap Analysis](docs/03-capability-gap-analysis.md)
- [QA Test Report](docs/04-qa-test-report.md)
- [CEO Usability Report](docs/05-ceo-usability-report.md)
- [Agent Console Spec](docs/06-agent-console-spec.md)
- [Putaway Retrospective](docs/07-putaway-retrospective.md)
- [AGV-Ready Receiving Roadmap](docs/08-agv-ready-receiving-roadmap.md)

## License

Proprietary - All rights reserved.
