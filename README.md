# WMS QuickStart

Multi-tenant warehouse management system for 3PL operations. The product name in
this checkout is WMS QuickStart. Older documents and conversations may refer to
it as GreaterWMS or MaxSmart WMS; those names are historical aliases, not a
different source tree.

## Repository Identity

- Active Git remote after migration: https://github.com/maxwu1978/GreaterWMS.git
- Migration source: https://github.com/maxwu1978/wms-quickstart.git
- Deployment branch: main
- Source layout: backend/ (FastAPI), frontend/ (React/Vite), wms-agent/
  (local governed agent), mcp-server/ (MCP adapter), agv-simulator/
  (AGV/WCS sandbox)
- Pre-migration snapshot: 55e4a70c7b0fd68d472483048a317fe02c665ad6
- Migration target: maxwu1978/GreaterWMS, branch main
- This checkout is shallow. Before history-sensitive work, run:
  git fetch --unshallow origin

The formal handoff record is docs/41-project-handoff.md. It distinguishes
the migrated GreaterWMS repository from historical deployment evidence.

## Product Surface

The system covers:

- tenant, user, client, warehouse, SKU, location, and inventory management;
- inbound ASN/import, receiving, staging, putaway, and receiving evidence;
- outbound orders, allocation, picking, packing, shipping, and returns;
- task assignment, operations board, reporting, billing, portal, and integrations;
- governed Agent Console APIs, local WMS Agent, MCP access, and AGV/WCS sandbox.

The lifecycle rules are documented in docs/14-stage-status-workflow.md:
receiving owns dock receipt into staging, Putaway owns movement from staging to
storage, Picking owns outbound execution, and Shipping owns final dispatch.

## Local Development

Prerequisites: Docker, Python 3.12+, Node.js 20+, and either uv or pip.

Start PostgreSQL, Redis, and the backend:

    docker compose up --build

The local API is http://localhost:8000. The local frontend runs separately:

    cd frontend
    npm ci
    npm run dev

The Vite development server is normally http://localhost:5173 and proxies /api
to the local backend.

Backend checks:

    cd backend
    uv sync --extra dev
    uv run ruff check app/ tests/
    uv run mypy app/ --ignore-missing-imports
    uv run pytest tests/ -q

If uv is unavailable, install the backend with:
    python -m pip install -e ".[dev]"

Frontend checks:

    cd frontend
    npm run build
    npm run lint
    npm run check:ui-language

## Agent And CLI Entry Points

There is no checked-in tools/wms.mjs or tools/greaterwms.mjs in this
repository. Do not use those paths from older runbooks.

The current local agent launcher is:

    node tools/local-agent.mjs start
    node tools/local-agent.mjs smoke

It starts the local governed agent at http://127.0.0.1:8787 and runs the
local-agent test suite. Install its standalone dependencies first:

    cd wms-agent
    uv sync --extra dev

Then build distributable installers with:

    node wms-agent/scripts/build-installers.mjs

The platform Agent API is part of the FastAPI backend under /api/v1/agent.
The MCP adapter is a separate integration:

    cd mcp-server
    uv sync

Configure MCP with WMS_API_BASE_URL, WMS_EMAIL, and WMS_PASSWORD as described
in mcp-server/README.md. Agent writes must use the server-side
preview/confirmation and idempotency gates; never treat plain chat text as a
production authorization.

The narrow migration helpers under tools/ are not a general WMS CLI. Review
their source and the target environment before using them.

## Deployment

The deployment declaration is render.yaml: the backend is a Render Docker web
service rooted at backend, and the AGV sandbox is a separate service rooted at
agv-simulator. The frontend is configured for Vercel in frontend/vercel.json.

Operational release procedures are in:

- docs/10-render-deploy-operations.md
- docs/17-release-gate-and-access-audit.md
- docs/16-uat-runbook.md

The documented production URLs are https://app.maxsmartwms.online,
https://api.maxsmartwms.online/api/v1, and
https://api.maxsmartwms.online/health. Verify the deployed SHA and health
response before describing a release as live; the handoff document does not
replace that verification.

## Handoff Rules

1. Treat main and render.yaml as the deployment source of truth.
2. Do not use archived docs or old GreaterWMS CLI examples as current commands.
3. Use a least-privilege tenant account for Agent/MCP work; do not place secrets
   in source, audit logs, or committed examples.
4. Run read-only checks first. For writes, use preview, explicit confirmation,
   idempotency, and cleanup safeguards.
5. Do not access or modify the production database directly without the release
   gate and a tested rollback/backup plan.
