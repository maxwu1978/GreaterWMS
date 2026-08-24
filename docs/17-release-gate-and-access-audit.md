# Release Gate And Access Audit

This document defines the non-manual checks to run before a production release
or before starting a formal manual UAT cycle.

## Required Environment

Run commands from `frontend` with `.env.audit.local` available.

Required variables:

- `WMS_AUDIT_API_URL`
- `WMS_AUDIT_APP_URL`
- `WMS_AUDIT_PLATFORM_EMAIL`
- `WMS_AUDIT_PLATFORM_PASSWORD`
- `WMS_AUDIT_PASSWORD`

Do not paste provider keys, passwords, or API tokens into tickets or run logs.

## Fixed Commands

For the current idempotency, recovery, and mobile workflow release, run the
gate in this order:

1. Confirm the target commit and backend migration state.
2. Run the database/RLS checks below against the target database.
3. Run local or preview workflow smokes for recovery, receiving, shipping, and
   pack completeness.
4. Deploy the intended commit.
5. Confirm backend health reports the intended `build_sha`.
6. Run the production acceptance commands.
7. Review evidence, then run cleanup and confirm no preserved operational rows
   were deleted.

```bash
npm run smoke:mail-provider
npm run smoke:registration-email
npm run smoke:production-bootstrap
npm run smoke:recovery-matrix
npm run audit:access-control
npm run uat:production
npm run uat:mobile-orchestrator
npm run audit:production-pages
npm run smoke:receiving-package-fallback
npm run smoke:pack-completeness
node ./scripts/verify-shipping-flow.mjs
npm run smoke:recovery-actions
npm run lint -- --quiet
```

After any command that creates production test data, clean it:

```bash
npm run uat:production:cleanup
```

`npm run uat:production` intentionally keeps its Acceptance UAT tenant until the
tester or release owner has reviewed the evidence. `npm run
uat:production:cleanup` does the controlled cleanup path: dry-run, execute, and
final dry-run. It preserves `PLATFORM` and `GREENECOPO` and does not clear
operational rows in preserved tenants.

## Decision Table

| Gate | Pass | Fail Action |
| --- | --- | --- |
| CI | GitHub CI is green for the intended commit. | Stop release and fix CI. |
| Backend health | `/health` returns `ok` and expected `build_sha`. | Wait for deploy or redeploy the intended commit. |
| Database migration | Alembic is at revision `012` or later on the target database. | Stop release and run the migration/bootstrap path before user traffic. |
| RLS and policies | `pick_allocations` and `idempotency_records` have forced RLS plus tenant and platform-admin policies. | Stop release; tenant isolation is not proven. |
| Mail provider | Diagnostic and registration email smoke pass. | Fix provider settings before user testing. |
| Access control | `audit:access-control` passes and cleanup reports preserved operational rows deleted as `0`. | Treat as high severity; do not start manual UAT. |
| Recovery matrix | `smoke:recovery-matrix` passes and every operator workflow has automated coverage. | Stop release; recovery code, docs, source, or script coverage has drifted. |
| Mobile orchestrator | `uat:mobile-orchestrator` passes on production, covering Receiving, Putaway, Picking, and Shipping. | Stop release; mobile execution is not safe for operator UAT. |
| UAT script | `uat:production` passes API and page checks with console errors `0`. | Investigate failed module before manual UAT. |
| Page audit | Production page audit reports `failures=0` and `consoleErrorCount=0`. | Fix visible layout or runtime errors. |
| Cleanup | Final dry-run reports test tenants `0`, test rows `0`, preserved operational rows `0`. | Re-run cleanup or inspect candidates manually. |

## 2026-05-06 Production Infrastructure Gate

Run this gate before the production acceptance commands whenever the backend,
database, Render plan, backup posture, or migration state could affect the
release.

Repository-confirmed facts:

- Render backend deployment is documented as service
  `srv-d7ako4ggjchc73eh8g70` / `wms-quickstart`, branch `main`, backend Docker
  root, auto-deploy on commit.
- The checked-in Blueprint says `plan: free`, stores `DATABASE_URL` as an
  unsynced environment variable, and does not declare managed Postgres backups.
- Alembic migrations are manual because no `preDeployCommand` is checked in.
- Local migration files reach revision `015`, and production
  `alembic_version` is stamped to `015`.

Confirmed on 2026-05-09:

- Render Dashboard live service plan, instance size/count, runtime region, and
  auto-deploy state were checked through Render CLI/API.
- Production Postgres provider and plan: Render Postgres `WMS-VM`,
  `basic_256mb`, Postgres 18, status `available`.
- Restore/PITR ability: Render API reports `recoveryStatus=AVAILABLE` with
  `startsAt=2026-05-05T09:00:08Z`.
- Logical export: created on-demand export
  `dpg-d7akc4fkijhs73dp4ukg-a/2026-05-09T15:10Z` at
  `2026-05-09T15:10:00Z`. Download and retain it if an off-platform archive
  is required.
- Restore owner: current Render account `Max Wu <wuqxmark@gmail.com>`.
- Operator accepted the backend `free` one-instance plan and Render Postgres
  `basic_256mb` for the current release/test stage.

Suggested infrastructure gate commands:

```bash
git rev-parse HEAD
curl --fail --silent --show-error https://api.maxsmartwms.online/health

cd backend
alembic heads
DATABASE_URL="postgresql+asyncpg://<production-target>" alembic current
```

If `alembic current` is not at revision `012` or later, run the migration from
the Render shell or trusted production shell, then re-check:

```bash
DATABASE_URL="postgresql+asyncpg://<production-target>" alembic upgrade head
DATABASE_URL="postgresql+asyncpg://<production-target>" alembic current
```

Do not pass this gate from repository evidence alone. Any item not visible from
the local checkout must be recorded as `external confirmation required`.

## Database And RLS Gate

Run this before production acceptance whenever Alembic, RLS, idempotency,
putaway allocation, or tenant filtering changes.

Required checks:

- `alembic_version` is at revision `012` or later for this release.
- `idempotency_records` exists with:
  - unique constraint `uq_idempotency_tenant_key` on
    `(tenant_id, idempotency_key)`
  - lookup index `ix_idempotency_tenant_operation`
  - forced row-level security
  - `tenant_isolation` policy using
    `current_setting('app.current_tenant_id', true)`
  - `admin_bypass` policy using
    `current_setting('app.is_platform_admin', true) = 'true'`
- `pick_allocations` exists with forced row-level security and both standard
  tenant isolation and platform-admin bypass policies.
- `putaway_allocations`, `tasks`, and the other tenant-scoped workflow tables
  still have RLS enabled after the migration.
- SQLite tenant filtering for local/dev paths includes both `pick_allocations`
  and `putaway_allocations`.

Suggested SQL inspection on Postgres:

```sql
select version_num from alembic_version;

select
  relname,
  relrowsecurity,
  relforcerowsecurity
from pg_class
where relname in (
  'idempotency_records',
  'pick_allocations',
  'putaway_allocations',
  'tasks'
);

select
  tablename,
  policyname,
  permissive,
  roles,
  cmd,
  qual
from pg_policies
where tablename in ('idempotency_records', 'pick_allocations')
order by tablename, policyname;

select indexname, indexdef
from pg_indexes
where tablename in ('idempotency_records', 'pick_allocations')
order by tablename, indexname;
```

Release evidence should record:

- target Git SHA
- target backend `build_sha`
- database environment name, not a connection string
- Alembic revision
- RLS and policy inspection result
- command name, exit status, and elapsed time
- UAT batch ID
- cleanup deleted tenant count, deleted row count, and preserved operational
  row deletion count
- reviewer or release owner

## Access-Control Audit Scope

`npm run audit:access-control` creates an isolated `Access Audit ...` tenant,
checks role boundaries, and then cleans the audit tenant.

The script verifies:

- Platform admin can see users across tenant workspaces.
- Tenant admin user list is scoped to its tenant.
- Tenant admin cannot create `tenant_admin` or `platform_admin` users.
- Tenant admin can create child `operator` and `client_viewer` users.
- Operator permissions are clamped to operational execution permissions and
  cannot keep `users.manage` or `billing.manage` from a direct API payload.
- Client viewer permissions are clamped to `portal.view` and remain attached to
  one client.
- Operator cannot access user management or tenant-admin billing settings.
- Operator can read operational inventory and inspect a portal dashboard when a
  valid `client_id` is supplied.
- Client viewer cannot access user management or tenant-admin billing settings.
- Client viewer can read filtered inventory and its portal dashboard.
- Cleanup deletes only the generated test tenant data and preserves operational
  rows in `PLATFORM` and `GREENECOPO`.

## 2026-05-02 Production Result

The production access-control audit passed after creating and deleting one
temporary `Access Audit ...` tenant.

Confirmed results:

- Tenant admin user listing stayed scoped to its own tenant.
- Tenant admin was blocked from creating `tenant_admin` and `platform_admin`
  users.
- Operator permissions were clamped to `receiving.execute`.
- Client viewer permissions were clamped to `portal.view` and one assigned
  client.
- Operator and client viewer were blocked from user management and
  tenant-admin billing settings.
- Operator could read inventory.
- Client viewer could read filtered inventory and open its portal dashboard.
- Platform admin could inspect the audit tenant users before cleanup.
- Cleanup deleted `1` temporary audit tenant and `5` tenant-scoped rows.
- Preserved operational rows deleted: `0`.
- Final cleanup dry-run reported test tenants `0`, test rows `0`, and
  preserved operational rows `0`.

## 2026-05-03 Final Deployment Snapshot

Production was redeployed after the release gate evidence was recorded.

- Final backend build SHA:
  `f264d1ccda99e0e3009d406cdad375854463afd4`
- Branch: `main`
- Render service: `wms-quickstart`
- Render service ID: `srv-d7ako4ggjchc73eh8g70`
- Health endpoint: `https://api.maxsmartwms.online/health`
- Health status: `ok`
- GitHub CI run: `25270291831`, passed
- GitHub CI URL:
  `https://github.com/maxwu1978/wms-quickstart/actions/runs/25270291831`

The full automated release gate ran against
`6329c321690641901000ff8732046be1350543cd`; the final deployment adds the
recorded evidence and the UAT default batch-date fix.

## Release Owner Checklist

- Confirm the target Git SHA.
- Confirm Render production health reports that SHA after deploy.
- Run the fixed commands above.
- Clean test data after evidence review.
- Record the batch ID, command outputs, and cleanup totals in
  `docs/16-uat-runbook.md` or the release note.
- Only then start manual UAT or approve the production release.
