# Project Handoff

Handoff snapshot: 2026-08-24
Scope: repository, local development, deployment, WMS workflows, Agent/MCP
integrations, and release operations.

## 1. Executive Summary

This repository is the migrated GreaterWMS codebase, a multi-tenant FastAPI +
React warehouse management system originally developed in WMS QuickStart. The
active Git remote after migration is:

    https://github.com/maxwu1978/GreaterWMS.git

The migration source was:

    https://github.com/maxwu1978/wms-quickstart.git

The pre-migration checkout was on main at:

    55e4a70c7b0fd68d472483048a317fe02c665ad6

The checkout is shallow and contains only the current snapshot. A new owner
must fetch full history before doing ancestry, release, or regression analysis:

    git fetch --unshallow origin
    git log --oneline --decorate --graph --all

The source tree is the authoritative implementation. The outer desktop folder,
its outputs/, tmp/, and generated artifacts are not part of the Git source of
truth.

## 2. Repository Map

| Path | Responsibility |
| --- | --- |
| backend/ | FastAPI application, SQLAlchemy models, Alembic migrations, tests |
| frontend/ | React 18/Vite/TypeScript web application and Capacitor iOS shell |
| wms-agent/ | Separately packaged local governed agent and installers |
| mcp-server/ | MCP adapter for Claude Desktop/Code and other MCP clients |
| agv-simulator/ | AGV/WCS sandbox service |
| tools/ | Local launcher, migration helpers, backups, and verification scripts |
| docs/ | Operational, workflow, release, and historical project documentation |
| render.yaml | Render service declarations |
| frontend/vercel.json | Frontend redirects and SPA hosting rules |
| .github/workflows/ci.yml | Backend and frontend CI gates |

At this snapshot there is no tools/wms.mjs and no tools/greaterwms.mjs.
References to those files in older documents are historical and must not be
copied into a new runbook.

## 3. Architecture

### Backend

- Python 3.12+.
- FastAPI with async SQLAlchemy and asyncpg.
- Alembic migrations.
- PostgreSQL and Redis in the normal deployment topology.
- Optional Celery, S3-compatible storage, email providers, and model-provider
  integrations are configured through environment variables.
- API base path: /api/v1.

Important backend areas include authentication, tenants, users, clients,
warehouses, SKUs, inventory, inbound/receiving, putaway, outbound/picking,
shipping, task assignment, operations board, billing, portal, Agent, AGV, and
WCS integrations.

### Frontend

- React 18, TypeScript, Vite, React Router, React Query, Zustand.
- Main execution routes include /dashboard, /receiving, /putaway, /inventory,
/picking, /shipping, /warehouses, /clients, /skus, /agent-console,
/agent-settings, /users, and /agv.
- Vercel serves the SPA. frontend/vercel.json redirects the apex and www
  domains to app.maxsmartwms.online and rewrites application routes to
  index.html.

### Local Agent And MCP

The local agent is a separate consumer of the platform API. It owns local
login/session UX, skill loading, provider planning, policy adjudication, local
audit/redaction, and confirmation cards. It does not own platform models,
migrations, or Agent API capability definitions.

The MCP server is another governed client. Both integrations must use the
server-side tool allow-list, preview/confirmation tokens, evidence/audit flow,
and idempotency controls.

## 4. Local Startup And Verification

From the repository root:

    docker compose up --build

This starts PostgreSQL, Redis, and the backend on port 8000. In a second
terminal:

    cd frontend
    npm ci
    npm run dev

The frontend normally runs on port 5173.

Run backend checks:

    cd backend
    uv sync --extra dev
    uv run ruff check app/ tests/
    uv run mypy app/ --ignore-missing-imports
    uv run pytest tests/ -q

Run frontend checks:

    cd frontend
    npm run build
    npm run lint
    npm run check:ui-language

Run the local agent:

    cd wms-agent
    uv sync --extra dev
    cd ..
    node tools/local-agent.mjs start
    node tools/local-agent.mjs smoke

Build local-agent installers:

    node wms-agent/scripts/build-installers.mjs

Do not put production credentials in .env files committed to the repository.
Use local-only environment files and least-privilege test accounts.

## 5. Business Workflow

The active inbound path is:

    draft -> expected -> arrived -> receiving -> putaway -> completed

An inbound order/ASN is imported or created, freight is opened at the dock,
receiving records package/SKU quantities into staging, and Putaway moves stock
from staging to storage. Exceptions must remain visible and must not be hidden
by a downstream completion state.

The active outbound path is:

    draft -> pending -> allocated -> picking -> picked -> packing -> packed -> shipped

Picking owns inventory allocation and pick tasks. Shipping owns pack verification
and final dispatch. Cancelled records are reference records, not active work.
The complete status/action matrix is in docs/14-stage-status-workflow.md.

## 6. Roles And Access Boundary

The security model defines these role families:

- platform_admin: platform-level administration;
- tenant_admin: tenant setup and tenant administration;
- operator: warehouse execution according to assigned permissions;
- client_viewer: restricted client/portal visibility.

Permissions cover inbound management/import, receiving execution, outbound
management, picking, shipping, master data, users, billing, planner, and portal
access. Do not infer access from a UI route. Verify the backend permission and
tenant scope for every write path.

## 7. Current Agent/CLI Integration

### Local launcher

The supported launcher is tools/local-agent.mjs:

    node tools/local-agent.mjs start
    node tools/local-agent.mjs smoke

The service defaults to 127.0.0.1:8787. WMS_LOCAL_AGENT_HOST and
WMS_LOCAL_AGENT_PORT may override the bind address and port.

### MCP adapter

Install from mcp-server/ with uv sync. Configure the client with:

    WMS_API_BASE_URL=https://api.maxsmartwms.online/api/v1
    WMS_EMAIL=<least-privilege account>
    WMS_PASSWORD=<secret supplied outside source control>

For local development, use http://localhost:8000/api/v1.

### Write safety

Agent and MCP writes must be previewed, tied to the exact payload/evidence, and
confirmed through the governed server flow. Use idempotency keys for retries.
Do not revive the old pattern of copying long confirmation tokens between
windows, and do not accept a plain text yes as a production authorization.

## 8. Deployment Topology

The migrated `render.yaml` declares two Render Docker services:

1. `wms-quickstart-staging`, rooted at backend, branch `main`, migration target.
2. `wms-agv-sandbox`, rooted at agv-simulator, branch `main`, public AGV/WCS
   sandbox.

The current customer-facing service is separate from this blueprint:
`greaterwms-production` (`srv-d9v6ahvqj5pc73d4spp0`) runs the legacy Django
pair on `codex/cli-install-info` at the immutable release tag
`prod-legacy-2026-08-24`. See `docs/43-environment-release-manifest.md`; do
not infer production from `main`.

The documented production endpoints are:

- Frontend: https://app.maxsmartwms.online
- API: https://api.maxsmartwms.online/api/v1
- Health: https://api.maxsmartwms.online/health

The documented Render service and database identifiers are recorded in
docs/10-render-deploy-operations.md. They are deployment evidence from the
dates stated in that document, not proof of the current live revision. Before a
release, query Render and verify the deployed commit, service status, environment
variables, migration state, and health response.

The Vercel project configuration is in frontend/vercel.json; confirm the
actual Vercel project and deployment SHA in the Vercel dashboard before a
frontend release.

The legacy AWS workflow is manual and explicitly guarded. It is not the normal
production path while Render is serving the backend.

## 9. Release And UAT Gates

Before merging or deploying:

1. Confirm the branch, remote, and working tree.
2. Run backend lint, type check, tests, and migration checks for backend changes.
3. Run frontend type check, lint, UI-language guard, build, and relevant browser
   verification for frontend changes.
4. Review docs/17-release-gate-and-access-audit.md.
5. For production writes, use the controlled UAT runbook and an isolated test
   tenant where possible.
6. Verify /health and the deployed SHA after deployment.
7. Record the release commit, deployment IDs, test evidence, and any known
   exceptions in the release log.

Never run cleanup, migration, import, or production-writing scripts merely to
test that a command exists. Read their source and confirm the target tenant
first.

## 10. Known Handoff Risks

- Naming drift: WMS QuickStart, GreaterWMS, and MaxSmart WMS are used in
  different historical materials. Use WMS QuickStart for new code and documents.
- Shallow checkout: this clone does not provide complete history. Unshallow
  before comparing release ancestry or auditing prior fixes.
- Historical production claims: documents dated in May 2026 contain service,
  deployment, and UAT identifiers that require live verification.
- Stale command examples: many older documents describe a removed tools/wms.mjs;
  current integration entry points are listed above.
- Legacy frontend Agent contract scripts and some repo-local historical skills
  still reference the removed CLI. They are not wired into the current
  frontend package scripts; reconcile them before re-enabling those checks.
- Separate agent boundary: wms-agent/ consumes platform APIs; it must not
  silently implement backend behavior or database changes.
- Production not verified by this handoff: this document records the repository
  state and procedures. It does not claim a fresh production health, browser,
  database, or deployment verification.

## 11. Takeover Procedure

The next engineer should complete this sequence:

    git status --short --branch
    git remote -v
    git fetch --unshallow origin
    git log --oneline --decorate --graph --all

Then:

1. Read this document, README.md, docs/10-render-deploy-operations.md,
   docs/14-stage-status-workflow.md, docs/16-uat-runbook.md, and
   docs/17-release-gate-and-access-audit.md.
2. Start the local stack and run the backend/frontend checks.
3. Verify the current Render/Vercel deployment against the documented URLs and
   commit, without writing production data.
4. Confirm the Agent/MCP account and allowed tools with a read-only call.
5. Only after those checks, create a scoped implementation plan and a release
   record for any change.

## 12. Handoff Definition Of Done

This project is handoff-ready when the receiving engineer can identify the
source repository, start the local stack, run the tests, locate the deployment
configuration, understand inbound/outbound ownership, use the supported Agent
entry points, and distinguish historical evidence from current production
truth without asking the previous engineer for undocumented credentials or
paths.
