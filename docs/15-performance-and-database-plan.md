# Performance And Database Plan

Updated: 2026-05-03

## Decision

Keep production on Render Postgres for now. Optimize the application hot paths first, then introduce Neon as a staging and regression-test database before considering any production database migration.

2026-05-03 status: plan item 5 is complete for documentation ownership. The monitoring/performance release gate now combines the Neon staging query-plan evidence, production health/deploy evidence, CI status, and production page-audit checks that must stay green for release readiness.

## Why

The main performance risks are currently application-level:

- task list reads were also repairing historical putaway data
- putaway and inventory pages fetched broad pending task lists and filtered them in the browser
- large workbench pages still do client-side aggregation over broad lists
- several list APIs need more targeted indexes and summary endpoints

Changing database vendors before fixing these access patterns would make the system harder to reason about without proving the root cause is solved.

## Implemented Phase 1

- `GET /tasks` is now a read-only task queue query.
- Application startup no longer repairs putaway tasks automatically. Historical repair is an explicit operations action so deploys and restarts do not create warehouse work.
- Historical putaway task repair moved to an explicit endpoint:
  - `POST /api/v1/tasks/repairs/putaway`
  - tenant-scoped for normal users
  - platform admins may pass `tenant_id`
  - supports `warehouse_id`, `inbound_order_id`, `dry_run`, and `limit`
- Startup repair now reuses the same explicit repair service instead of carrying duplicate logic.
- Putaway and inventory screens now request only pending putaway tasks:
  - `GET /tasks/?status=pending&task_type=putaway&limit=500`
- Added targeted indexes:
  - `ix_tasks_tenant_queue`
  - `ix_inventory_tenant_warehouse_location_sku`
- The indexes are included in Alembic migrations `006` and `007` and in the existing startup schema ensure path so Render deployments apply them even when migrations are not run manually.

## Validation Added

- `GET /tasks` no longer creates missing putaway tasks by default.
- Explicit putaway repair creates the missing task.
- Re-running the repair is idempotent.
- Existing task list response still exposes handling-unit identity and execution guidance.

## Implemented Phase 2A

- Added backend summary endpoints that let large workbench pages fetch aggregate counts without loading full operational lists first:
  - `GET /api/v1/workbench-summaries/receiving`
  - `GET /api/v1/workbench-summaries/putaway`
  - `GET /api/v1/workbench-summaries/picking`
  - `GET /api/v1/workbench-summaries/inventory`
- Each endpoint accepts the relevant `warehouse_id` filter, and the workbenches with client-owned records accept `client_id` while still respecting client-viewer scope.
- Added regression coverage that seeds inbound, outbound, task, package, label, and inventory records and verifies the returned aggregate counts.

## Implemented Phase 2B

- Added a shared frontend summary API client for the new workbench summary endpoints.
- Inventory now uses `/workbench-summaries/inventory` for top-level on-hand, allocated, and available totals instead of the older report aggregation path.
- Receiving now uses `/workbench-summaries/receiving` for package-not-completed, putaway-handoff, and label-print queue totals.
- Putaway now uses `/workbench-summaries/putaway` for total open task and waiting-unit counts, while keeping the task list query scoped to actionable pending tasks.
- Picking now uses `/workbench-summaries/picking` for outbound queue and released task counts, while keeping the order and task lists responsible for row-level interaction.
- Receiving, putaway, picking, and inventory workflows now invalidate the relevant summary queries after mutations so dashboard numbers refresh with the operational changes.

## Implemented Phase 2C

- Added backward-compatible `offset` and `limit` query parameters to the high-growth order list endpoints:
  - `GET /api/v1/orders/inbound`
  - `GET /api/v1/orders/outbound`
- Both endpoints now use a `limit + 1` read to determine whether another page exists without running a broad exact count.
- Existing response bodies remain arrays so current frontend callers continue to work.
- Pagination metadata is returned through response headers:
  - `X-Offset`
  - `X-Limit`
  - `X-Returned-Count`
  - `X-Has-More`
- Added regression coverage for the pagination headers on inbound and outbound order lists.
- Exposed these pagination headers through CORS so the production frontend can read them in browser-based API calls.
- Receiving, picking, and shipping now consume the order list endpoints in server-sized batches. The initial batch keeps the existing local filter/sort experience, and the page shows a deliberate load-more control when the backend reports more rows.
- Outbound order lists now accept comma-separated `statuses`, `sort_by`, and `sort_direction` query parameters. Picking, picking work, and shipping use status-scoped outbound reads instead of pulling the full outbound order set before filtering in the browser.
- Inbound order lists now accept comma-separated `statuses`, `lifecycle`, `operation`, `sort_by`, `sort_direction`, and `recent_hours` query parameters. Receiving uses these server-side filters for lifecycle tabs and package-work queues before applying the remaining local presentation filters.
- Outbound order lists now support backend sort keys for computed operational readiness:
  - `pick_readiness`
  - `shipping_readiness`
- Inventory list pagination now uses a shared `limit + 1` window helper instead of a broad exact `count(*)`. The API still returns pagination metadata, but `total_is_estimate` marks pages where the total is a lower bound because another page exists.
- Added indexes for the next hot paths:
  - outbound order list filters and readiness joins
  - outbound line aggregation by order and SKU
  - inventory availability by warehouse/SKU
  - invoice follow-up by tenant/status/client
- Added `backend/scripts/check_query_plans.py` so Render, Neon, or local Postgres can print the same representative `EXPLAIN` checks for task queues, inbound/outbound lists, inventory, and billing follow-up.

## Implemented Phase 2D

- Added multi-model review coverage, including DeepSeek, for backend hot paths, frontend list consistency, and WMS workflow risk.
- Inventory search, warehouse/client/location filters, issue filters, and focus chips now flow to `GET /api/v1/inventory/` instead of filtering only the currently loaded browser page.
- The inventory staging focus now follows open putaway source locations, matching the work queue meaning of “awaiting putaway.”
- Inventory list ordering is deterministic for paginated reads.
- Added more targeted indexes for:
  - default outbound created-date listing
  - warehouse-scoped outbound listing
  - pending task queue priority order
  - live inventory stable ordering
  - invoice follow-up created-date listing
- Expanded `backend/scripts/check_query_plans.py` so it checks valid inbound statuses, default outbound sorting, pick/shipping readiness sorting, inventory window reads, inventory stable order, and billing follow-up.
- Added regression coverage for inventory tenant isolation, server-side search before pagination, and staging focus behavior.

## Implemented Phase 2E

- Added persisted readiness rank projections on outbound orders:
  - `pick_readiness_rank`
  - `shipping_readiness_rank`
- Picking, wave, shipping, Shopify import, outbound creation, and outbound list reads now keep these projections aligned with the current workflow state.
- Outbound order list sorting now uses indexed rank columns instead of per-request readiness `CASE` / aggregation sorting.
- Added readiness-rank indexes for tenant and warehouse-scoped outbound lists.
- Updated the query-plan script so pick/shipping readiness checks validate the indexed rank path.
- Existing production rows are initialized with status-based rank defaults during migration/startup. API reads also refresh the returned page with more precise stock-shortage readiness.
- Added an explicit operational refresh endpoint for edge cases where inventory changes outside the outbound workflow:
  - `POST /api/v1/orders/outbound/readiness/refresh`
  - defaults to dry-run
  - supports tenant, warehouse, order, status, and limit scoping
- Inventory changes that affect pending outbound readiness now trigger a scoped automatic refresh:
  - CSV inventory imports group touched SKU/warehouse pairs and refresh only matching pending outbound orders
  - single-row inventory imports refresh the matching SKU/warehouse
  - manual inventory adjustments and cycle-count variances refresh the affected SKU/warehouse
  - the manual endpoint remains available for historical repair, audit dry-runs, and operator-triggered rebuilds
- Render production query-plan check was attempted after deployment through the Render PostgreSQL session path. The operational tables were empty at the time of the check (`inventory`, `tasks`, `inbound_orders`, `outbound_orders`, `outbound_order_lines`, and `invoices` all had 0 rows), so production plans were not representative for load behavior. Keep this check open for Neon staging or a seeded regression database.

## Implemented Phase 2F

- Master-data list endpoints now use `limit + 1` window pagination instead of an exact `count(*)`:
  - `GET /api/v1/clients/`
  - `GET /api/v1/skus/`
  - `GET /api/v1/warehouses/`
  - `GET /api/v1/users/`
- Responses remain backward-compatible with `items`, `total`, `limit`, `offset`, and `has_more`.
- When another page exists, `total` is a lower-bound estimate and `total_is_estimate` is true.
- Added regression coverage to verify client listing avoids a separate exact count query.

## Implemented Phase 2G

- Dashboard and reporting reads now use explicit tenant filters on every operational aggregate.
- Warehouse-scoped dashboard KPI reads also apply the warehouse filter to outbound, inbound, inventory, task, and pick-transaction counts.
- The dashboard now returns `inbound.received_today`, matching the frontend contract that already expected the field.
- Order reports, inventory summaries, activity logs, return analytics, and client portal dashboard/list reads now include defensive tenant filters in addition to client filters.
- Added regression coverage for:
  - dashboard/report/activity aggregates excluding another tenant's records
  - return analytics excluding another tenant's RMA lines, reasons, SKU totals, and disposition totals

## Implemented Phase 2H

- Dashboard KPI reads now combine related aggregates into conditional aggregate queries:
  - outbound pending, shipped today, and shipped in 7 days
  - inventory SKU, unit, and location totals
  - pending and completed task totals
  - pending and received inbound totals
- This keeps the existing exact dashboard numbers but reduces database round trips for `/api/v1/reports/dashboard`.
- Added regression coverage that caps the dashboard KPI query count so the endpoint does not drift back to many serial aggregate reads.
- Expanded `backend/scripts/check_query_plans.py` with the dashboard order, inventory, task, and inbound aggregate queries so Neon staging can validate these plans with the rest of the hot paths.

## Next Lane: Inventory And Dashboard Operator Focus

The next non-blocking product lane should stay scoped to Inventory and
Dashboard rather than widening the release after the mobile recovery pass.

2026-05-05 completion update: this lane is released. Inventory lookup,
Inventory adjustment safety, Dashboard next-work, verification, and the
production release gate are recorded in
[docs/project-plan.md](/Volumes/MaxRelocated/WMS/docs/project-plan.md). The
final production evidence is:

- commit `aff3a76` released the Inventory/Dashboard operator-focus changes.
- GitHub CI `25401391702` and Render Backend Deploy `25401391744` passed.
- Vercel deployment `dpl_5VKuRmRTha3zLCKFf6NxwRRxo85y` was promoted to
  `https://app.maxsmartwms.online`.
- production alias returned `HTTP/2 200` on 2026-05-05 21:52 UTC.
- production `npm run uat:mobile-orchestrator` passed across Admin, Agent,
  Dashboard, Inventory, Master Data, Migration, Picking, Putaway, Receiving,
  and Shipping.
- production cleanup deleted `7` test tenants and `76` test rows while
  preserving `GREENECOPO` and `PLATFORM`.

Recommended order:

1. Inventory mobile lookup:
   - complete in commit `aff3a76`
   - make the phone surface a SKU/location/client lookup and count-adjust
     workflow, not a dense table-first view
   - keep filters compact, with row detail and movement history behind explicit
     drill-in
   - preserve server-side search, deterministic paging, and tenant-scoped reads
2. Inventory adjustment safety:
   - complete in commit `aff3a76`
   - confirm manual count adjustments require an explicit reason and leave an
     auditable inventory transaction
   - validate available/on-hand/allocated math after receiving, putaway,
     picking, and manual adjustment
   - check that readiness refreshes still run for affected pending outbound
     orders after inventory changes
3. Dashboard next-work surface:
   - complete in commit `aff3a76`
   - reduce phone dashboard priority to the next recommended warehouse action
     plus compact navigation
   - keep analytics and supervisor KPI panels secondary on phone
   - keep desktop dashboard aggregate accuracy and query-count regression
     coverage intact
4. Verification:
   - complete through local checks, production deployment, production
     `uat:mobile-orchestrator`, and CI `25404435075`
   - add or extend targeted smoke coverage for mobile Inventory lookup/count
     adjustment and mobile Dashboard next-work navigation
   - no query-plan rerun was required in this slice because the released
     changes did not alter dashboard aggregate SQL or indexes
   - include manual UAT rows for Inventory adjustment and Dashboard next-work
     clarity before release
5. Release gate:
   - complete through Vercel production deployment, production HTTP check,
     production mobile UAT orchestration, cleanup, evidence commit `9f1560d`,
     and CI `25404435075`

Parallel work packages:

- A, Inventory mobile lookup:
  - owner scope: `frontend/src/modules/inventory/` and inventory smoke coverage
  - deliverable: phone-first SKU/location/client lookup with compact filters and
    row drill-in
- B, Inventory adjustment safety:
  - owner scope: inventory adjustment API/service tests and audit evidence
  - deliverable: explicit adjustment reason, inventory transaction evidence, and
    outbound readiness refresh proof
- C, Dashboard next-work:
  - owner scope: `DashboardPage`, dashboard summary contracts, and mobile
    navigation
  - deliverable: phone dashboard focused on next recommended warehouse work,
    while desktop KPI accuracy remains unchanged
- D, Verification:
  - owner scope: smoke scripts, query-plan checks, and manual UAT rows
  - deliverable: one command or checklist bundle that proves Inventory and
    Dashboard behavior before release

## Implemented Phase 2I

- Created a dedicated Neon staging project for WMS performance and regression work:
  - Project: `maxsmartwms-staging`
  - Project ID: `billowing-paper-54822031`
  - Region: `aws-us-west-2`
  - Database: `maxsmartwms`
  - Role: `maxsmartwms_owner`
  - Default branch: `main`
  - Endpoint host: `ep-crimson-credit-akxi5btb.c-3.us-west-2.aws.neon.tech`
- The Neon connection string is not committed. The local one-off setup files used during creation were kept under `/tmp/`.
- Initialized schema on the Neon database with the current application schema, then stamped Alembic to revision `008` after confirming that the startup schema path had already created the latest table set.
- Enabled and verified PostgreSQL RLS on all 28 tenant-scoped tables. Each tenant table has the standard `tenant_isolation` and `admin_bypass` policies.
- Verified the key performance indexes on Neon, including task queue, live inventory ordering, pick allocations, and outbound readiness indexes.
- Seeded the Neon staging database with synthetic operational data:
  - 8 clients
  - 240 SKUs
  - 805 locations
  - 5,000 inventory rows
  - 1,200 inbound orders
  - 2,400 outbound orders
  - 1,600 tasks
  - 300 invoices
- Fixed `backend/scripts/seed_performance_fixture.py` so fixture records are flushed by dependency group before child tables are inserted. This prevents foreign-key failures when a batch boundary lands between parent and child records.
- Ran `backend/scripts/check_query_plans.py --tenant-id perf-tenant-001` and `--analyze` against Neon staging. The hot list paths use tenant-scoped indexes, including task queues, inbound/outbound lists, outbound readiness sorting, inventory stable ordering, and invoice follow-up.
- The seeded `EXPLAIN ANALYZE` pass showed representative hot-path timings in the low millisecond range:
  - task queue: about 0.14 ms
  - inbound order list: about 0.10 ms
  - outbound default list: about 0.14 ms
  - outbound pick readiness sort: about 0.23 ms
  - outbound shipping readiness sort: about 0.16 ms
  - inventory stable order: about 0.06 ms
  - billing follow-up: about 1.16 ms
  - dashboard aggregate checks: about 0.39-4.05 ms on the synthetic fixture
- Dashboard aggregate plans are acceptable at the current fixture size, but still worth watching with production-like restored data because PostgreSQL may prefer sequential scans for low-cardinality tenant-wide aggregates.

## Implemented Phase 2J

- Expanded the Neon staging performance fixture to a larger production-like synthetic workload:
  - 20 clients
  - 1,000 SKUs
  - 3,005 locations
  - 60,000 inventory rows
  - 12,000 inbound orders
  - 24,000 outbound orders
  - 16,000 tasks
  - 3,000 invoices
- Updated `backend/scripts/seed_performance_fixture.py` to run `ANALYZE` after rebuilding the fixture. This keeps PostgreSQL planner statistics fresh after large synthetic loads and avoids false slow-query findings caused by stale row estimates.
- Added Alembic revision `009` with `ix_inventory_tenant_warehouse_live_metrics`, a portable partial covering index for dashboard inventory metrics:

  ```sql
  CREATE INDEX IF NOT EXISTS ix_inventory_tenant_warehouse_live_metrics
  ON inventory (tenant_id, warehouse_id, sku_id, location_id, quantity_on_hand)
  WHERE quantity_on_hand > 0
  ```

- Added the same index to the startup schema reconciliation path so fresh cloud databases get the index even when bootstrapped by application startup before Alembic catches up.
- Promoted Neon staging to Alembic revision `009` and confirmed the index exists.
- Re-ran `scripts/check_query_plans.py --tenant-id perf-tenant-001 --analyze` on the larger fixture. Key results:
  - task queue: about 0.16 ms
  - inbound list: about 0.10 ms
  - outbound default list: about 0.14 ms
  - outbound pick readiness sort: about 0.20 ms
  - outbound shipping readiness sort: about 0.12 ms
  - inventory stable order: about 0.06 ms
  - billing follow-up: about 0.26 ms
  - dashboard outbound metrics: about 10.9 ms
  - dashboard inventory metrics: about 25.3 ms, using index-only scan with 0 heap fetches
  - dashboard task metrics: about 5.0 ms
  - dashboard inbound metrics: about 3.5 ms
- The dashboard inventory aggregate still scans all live inventory rows for exact totals. That is acceptable for the current staging workload after the covering index, but a future production workload above several hundred thousand live inventory rows should move these homepage metrics to a maintained summary table or cached rollup.

## Implemented Phase 2K

- Expanded `backend/scripts/seed_performance_fixture.py` with a `--profile production-like` mode and multi-warehouse fixture support. The production-like profile uses deterministic skew so a smaller number of clients, SKUs, and warehouses carry more volume, which better matches real 3PL load patterns than uniform data.
- Added input validation to the fixture script so invalid client, SKU, warehouse, and location cardinalities fail before records are generated.
- Loaded a larger Neon staging fixture:
  - 40 clients
  - 3,000 SKUs
  - 3 warehouses
  - 8,015 locations
  - 150,000 inventory rows
  - 30,000 inbound orders
  - 60,000 outbound orders
  - 40,000 tasks
  - 8,000 invoices
- Added tenant-wide dashboard aggregate checks to `backend/scripts/check_query_plans.py` so tenant-level and warehouse-scoped dashboard paths are both visible in the same EXPLAIN run.
- Added Alembic revision `010` with `ix_inventory_tenant_live_metrics`, a tenant-wide partial covering index for exact dashboard inventory metrics:

  ```sql
  CREATE INDEX IF NOT EXISTS ix_inventory_tenant_live_metrics
  ON inventory (tenant_id, sku_id, location_id, warehouse_id, quantity_on_hand)
  WHERE quantity_on_hand > 0
  ```

- Added the same tenant-wide index to the startup schema reconciliation path so fresh cloud databases get the index even before Alembic is run manually.
- Promoted Neon staging to Alembic revision `010` and confirmed both dashboard inventory metric indexes exist.
- Re-ran `scripts/check_query_plans.py --tenant-id perf-tenant-001 --analyze` on the production-like fixture. Warm-run highlights:
  - task/inbound/outbound list paths: about 0.10-0.47 ms
  - inventory window read: about 0.10 ms
  - inventory stable order: about 0.10 ms
  - billing follow-up: about 0.68 ms
  - dashboard outbound tenant metrics: about 107 ms
  - dashboard inventory tenant metrics: about 79 ms, using `ix_inventory_tenant_live_metrics`
  - dashboard inventory warehouse metrics: about 49 ms, using `ix_inventory_tenant_warehouse_live_metrics`
  - dashboard task tenant metrics: about 12 ms
  - dashboard inbound tenant metrics: about 9 ms
- A cold EXPLAIN ANALYZE run showed exact inventory dashboard aggregates can spike higher because PostgreSQL still scans all live inventory entries needed for exact `COUNT(DISTINCT ...)` and `SUM(...)` values. This confirms the next scale step is a maintained dashboard summary table if real tenant data pushes dashboard p95 beyond the budget.
- Decision: keep the exact real-time dashboard queries for now because warm staging timings are acceptable and all list endpoints are already fast. Add a maintained dashboard summary table when either condition is true:
  - tenant live inventory grows beyond roughly 200k-300k rows and dashboard p95 exceeds 250 ms, or
  - the homepage becomes a high-frequency operational display where cold-start latency is user-visible.
- Split pure Putaway workbench helper logic from `frontend/src/modules/putaway/PutawayPage.tsx` into `frontend/src/modules/putaway/putawayWorkUtils.ts`. This is the first frontend module-size reduction step and keeps behavior unchanged while making future page decomposition safer.
- Staging API full-flow QA passed against `https://wms-quickstart-staging.onrender.com/api/v1`:
  - inbound import -> receiving -> completed receiving -> putaway -> completed inbound
  - dock inventory moved from 5 to 0
  - storage inventory moved to 5
  - outbound import -> allocation -> pick task -> picked -> packed -> shipped
  - storage inventory reduced from 5 to 3 after picking
  - shipment carrier and tracking number persisted
- 2026-05-06 update: the transactional email path has provider-chain
  diagnostics and password-reset fallback regression coverage. Production
  page-level automated QA is no longer treated as an email-code blocker, but it
  still requires the documented readiness gates: platform bootstrap credential,
  monitored email recipient, cleanup preserve-list review, and mobile
  orchestrator owner approval before running production-writing commands.

## Next Performance Phases

1. Add a maintained dashboard summary table if production-like or real restored data pushes tenant-level dashboard p95 above the release budget.
2. Continue splitting oversized frontend modules after API contracts are stable, next targeting Putaway hooks/components, Warehouse Planner helpers, and Receiving flow helpers.
3. Re-run production page-level automated QA after the 2026-05-06 readiness
   gates are explicitly approved: platform bootstrap credential, monitored
   email recipient, cleanup preserve-list review, and mobile orchestrator owner.

## Render Production Position

Render remains the production runtime for backend and database in the short term.

Required checks before serious production usage:

- confirm the Render Postgres plan has backups and recovery appropriate for business data
- confirm backend instance sizing is not still on a free/runtime-limited plan
- prefer the production Docker configuration or explicit multi-worker Uvicorn setup once traffic grows
- keep migrations run from a trusted shell with the intended production `DATABASE_URL`

## Neon Position

Neon should be added first as a staging and regression-test database, not as an immediate production replacement.

Use Neon for:

- clean full-flow test databases
- branch databases before large QA runs
- representative messy-data regression sets
- migration dry runs
- restore drills

Before any production migration to Neon, validate:

- PostgreSQL RLS tenant isolation
- `set_config` tenant context behavior
- direct connection versus pooled connection behavior
- latency between Render backend and the Neon region
- backup, restore, connection count, and cost under realistic load

## Neon Staging Runbook

Use the dedicated Neon staging project above for performance/regression checks. Run this sequence from `backend/`.

1. On an empty Neon database, create or reconcile schema:

   ```bash
   DATABASE_URL="postgresql+asyncpg://<neon-staging-connection>" \
     python - <<'PY'
   import asyncio
   from app.main import ensure_schema_and_seed_defaults
   from app.core.database import engine

   async def main():
       await ensure_schema_and_seed_defaults()
       await engine.dispose()

   asyncio.run(main())
   PY
   ```

2. Apply migrations, or stamp to head only after verifying the current startup schema has already created the equivalent objects:

   ```bash
   DATABASE_URL="postgresql+asyncpg://<neon-staging-connection>" alembic upgrade head
   # If startup schema already created latest objects and Alembic hits duplicate-table DDL:
   DATABASE_URL="postgresql+asyncpg://<neon-staging-connection>" alembic stamp head
   ```

3. Seed representative operational data:

   ```bash
   DATABASE_URL="postgresql+asyncpg://<neon-staging-connection>" \
     python scripts/seed_performance_fixture.py --confirm-seed --replace
   ```

   For larger skewed staging checks:

   ```bash
   DATABASE_URL="postgresql+asyncpg://<neon-staging-connection>" \
     python scripts/seed_performance_fixture.py --confirm-seed --replace \
       --profile production-like \
       --warehouses 3 \
       --clients 40 \
       --skus 3000 \
       --locations 8000 \
       --inventory 150000 \
       --inbound-orders 30000 \
       --outbound-orders 60000 \
       --tasks 40000 \
       --invoices 8000
   ```

   The fixture creates tenant `PERFSEED` with clients, SKUs, locations, inventory, inbound orders, outbound orders, tasks, and invoices. The script refuses non-Neon targets unless `--allow-non-neon` is explicitly passed.

4. Capture read-only query plans:

   ```bash
   DATABASE_URL="postgresql+asyncpg://<neon-staging-connection>" \
     python scripts/check_query_plans.py --tenant-id perf-tenant-001
   ```

5. For timing and buffer checks, run only on staging or during a safe maintenance window:

   ```bash
   DATABASE_URL="postgresql+asyncpg://<neon-staging-connection>" \
     python scripts/check_query_plans.py --tenant-id perf-tenant-001 --analyze
   ```

The performance fixture is intentionally synthetic. Use it to validate index paths and query shape before loading restored production-like data.

For the current project, a Render staging backend service is configured to use this Neon database:

- Service: `wms-quickstart-staging`
- Service ID: `srv-d7qgk4rbc2fs73fsjbo0`
- URL: `https://wms-quickstart-staging.onrender.com`
- Auto deploy: disabled
- Purpose: staging API smoke, database migration rehearsal, and performance regression checks only

### Deployed Staging Validation

Validated on 2026-05-01 against Render service `srv-d7qgk4rbc2fs73fsjbo0` and Neon project `billowing-paper-54822031`:

- `/health` returned status `ok` with build SHA `e683dadfcb10ef96d3a7d3af352a0081835fb8df`.
- Database structure check confirmed Alembic revision `008`, 28 tenant-scoped tables with RLS enabled, and 56 tenant isolation policies.
- The seeded performance tenant still contains the synthetic operational fixture: 8 clients, 240 SKUs, 805 locations, 5,000 inventory rows, 1,200 inbound orders, 2,400 outbound orders, 1,600 tasks, and 300 invoices.
- `scripts/check_query_plans.py --tenant-id perf-tenant-001 --analyze` completed on Neon staging. The primary list paths used the intended tenant-scoped indexes. Dashboard aggregate scans remain acceptable on the current synthetic fixture, but should be rechecked with production-like restored data.
- API smoke through the deployed staging backend succeeded by registering a temporary tenant and calling plans, registration, warehouses, clients, inventory, inbound orders, outbound orders, tasks, receiving summary, putaway summary, picking summary, inventory summary, and dashboard endpoints.
- 2026-05-01 follow-up: larger synthetic fixture was loaded, Alembic was upgraded to `009`, and the dashboard inventory metrics query was moved to an index-only plan through `ix_inventory_tenant_warehouse_live_metrics`.
- 2026-05-01 second follow-up: production-like multi-warehouse fixture was loaded, Alembic was upgraded to `010`, tenant-wide dashboard inventory metrics gained `ix_inventory_tenant_live_metrics`, and staging API lifecycle QA passed from receiving through shipping.

## Release Gate

Do not consider the performance phase complete until these checks pass:

- task list result parity before and after the repair decoupling
- historical putaway repair is run only by an intentional dry-run/review/apply procedure
- no cross-tenant task visibility in repair or list flows
- putaway/inventory task counts match created receiving work
- full backend regression suite passes
- frontend production build passes
- production health endpoint reports the deployed commit after push

## Monitoring And Performance Release Gate

Use this gate for release readiness and for future performance regressions:

- Production health must return `status=ok`, `branch=main`, the expected Render service ID, and the expected `build_sha`.
- Frontend production must be verified separately from backend health: inspect the latest Vercel production deployment, confirm `https://app.maxsmartwms.online` aliases to that deployment, and capture the current HTML bundle asset hash after deploy.
- GitHub CI for the deployed commit must pass before the release is treated as the current baseline.
- Production page audit must pass across desktop and mobile viewports with `failures=0` and `consoleErrorCount=0`.
- Formal UAT automation must pass before manual sign-off starts, then cleanup must confirm test tenant candidates `0`, test rows `0`, and preserved-tenant operational rows `0`.
- Neon staging must remain available as the performance regression target, with RLS enabled on all tenant-scoped tables and Alembic at the current head before query-plan evidence is trusted.
- `backend/scripts/check_query_plans.py --tenant-id perf-tenant-001 --analyze` should be run on Neon staging after schema/index changes or before any database migration decision.
- Hot list paths should continue using tenant-scoped indexes for task queues, inbound lists, outbound lists, readiness sorting, inventory windows, and billing follow-up.
- Dashboard exact aggregates are acceptable on the current production-like fixture, but they are the watched surface. If tenant live inventory reaches roughly 200k-300k rows and dashboard p95 exceeds 250 ms, add a maintained dashboard summary table or cached rollup before scaling usage.
- Non-blocking responsive overflow observations can be tracked as polish only when the page audit does not count them as failures and primary mobile actions remain reachable.

The 2026-05-03 release evidence chain is:

- Full automated release gate target: `6329c321690641901000ff8732046be1350543cd`.
- Final deployed production baseline after evidence recording and UAT batch-date fix: `f264d1ccda99e0e3009d406cdad375854463afd4`.
- Production backend service: `wms-quickstart`, service ID `srv-d7ako4ggjchc73eh8g70`.
- Health endpoint: `https://api.maxsmartwms.online/health`.
- GitHub CI run for the final deployed baseline: `25270291831`, passed.
