# Render Deploy Operations

## Current Repository Note

The active source repository after migration is
`https://github.com/maxwu1978/GreaterWMS.git` on `main`. The migration source
was `https://github.com/maxwu1978/wms-quickstart.git`. `render.yaml` is the
deployment declaration. Service IDs, database
IDs, deployment SHAs, and verification dates later in this document are
historical evidence and must be checked in Render before a new release. The
current source snapshot and ownership transfer procedure are documented in
[`41-project-handoff.md`](41-project-handoff.md).

## Current Production Path

The current customer-facing service is the legacy Django pair:

- Render service: `greaterwms-production` / `srv-d9v6ahvqj5pc73d4spp0`
- Branch: `codex/cli-install-info`
- Verified commit: `7592afe87ec94309276d9181103a504f3d91fc32`
- Immutable rollback tag: `prod-legacy-2026-08-24`
- Frontend/API: `app.maxsmartwms.online` and `api.maxsmartwms.online`
- Auto deploy: disabled; production releases require an explicit commit.

The migrated FastAPI/React service is `wms-quickstart-staging` on `main` and
is not customer production. Do not use the migrated staging health workflow as
proof that the legacy production service has been upgraded. The authoritative
mapping is [`docs/43-environment-release-manifest.md`](43-environment-release-manifest.md).

The legacy AWS ECS workflow is intentionally guarded and renamed
`Legacy AWS ECS Deploy`. Do not use it for normal production releases while the
live backend is served from Render.

## Production Schema Contract Gate

Use a read-only schema contract check before treating a backend deployment as
ready for WCS/Agent work:

```bash
cd backend
DATABASE_URL="postgresql+asyncpg://<production-target>" \
  uv run python scripts/check_schema_contract.py
```

For a hard release gate, add `--strict-alembic`. Without that flag, the checker
fails missing tables, columns, indexes, and PostgreSQL RLS gaps, but reports
`alembic_version` drift as a warning. This matters on the current Render path
because startup can create or heal tables while the recorded Alembic revision
may lag behind the actual schema.

If the Render shell/database URL is unavailable, run equivalent read-only
checks through `render psql`:

```sql
SELECT version_num FROM alembic_version ORDER BY version_num;

SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
    'agent_evidence',
    'idempotency_records',
    'locations',
    'tasks',
    'wcs_task_bindings',
    'zones'
  )
ORDER BY table_name, column_name;

SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class
WHERE relname IN (
  'agent_evidence',
  'idempotency_records',
  'locations',
  'tasks',
  'wcs_task_bindings',
  'zones'
)
ORDER BY relname;
```

Historical note from May 8, 2026: the live database had the required
WCS/layout columns, indexes, and RLS policies for the checked contract, but
`alembic_version` still reported `003`. That drift has since been resolved by
targeted production DDL and the guarded Alembic stamp to revision `015`.

Current production note from May 9, 2026:

- Render CLI confirms the production backend service is
  `srv-d7ako4ggjchc73eh8g70` (`wms-quickstart`), branch `main`, root
  directory `backend`, Docker runtime, region `oregon`, free web service plan,
  and auto deploy enabled.
- Render CLI confirms the public AGV sandbox service is
  `srv-d7v5s1pj2pic73e5e0v0` (`wms-agv-sandbox`), root directory
  `agv-simulator`, Docker runtime, region `oregon`, free web service plan,
  health check `/api/health`, and auto deploy enabled.
- Render CLI confirms the production database is Render Postgres
  `dpg-d7akc4fkijhs73dp4ukg-a` (`WMS-VM`), database name `appdb_0zfl`,
  version `18`, plan `basic_256mb`, region `oregon`, disk `15GB`,
  high availability disabled, disk autoscaling disabled, role `primary`, and
  status `available`.
- A read-only `render psql` contract check found no missing required WCS,
  layout, task, agent evidence, or idempotency columns in the checked tables.
  The final production schema gate reports `missing_indexes=<none>`,
  `rls_failures=<none>`, and `alembic_version=015`.
- Render's Postgres backup documentation says paid Render Postgres databases
  have point-in-time recovery, with the recovery window depending on workspace
  plan, and logical backups are retained for seven days after creation:
  <https://render.com/docs/postgresql-backups>. Render API confirmed
  `recoveryStatus=AVAILABLE` for `WMS-VM`, with `startsAt=2026-05-05T09:00:08Z`.
  Current logical export count is `0`.

Historical expanded migration contract note from May 9, 2026:

- A read-only audit covering the missing 004-015 migration surface found:
  - no missing checked columns;
  - originally reported missing index:
    `ix_outbound_orders_tenant_warehouse_shipping_readiness_created_desc`;
  - `pick_allocations` RLS and forced RLS are not enabled;
  - `alembic_version` still reports `003`.
- A follow-up Render `psql` read-only snapshot after the latest backend deploy
  showed the outbound shipping readiness index now exists; `pick_allocations`
  RLS remains `false/false`.
- This item is now resolved. The reviewed RLS patch was applied, the schema
  contract gate passed, and the guarded Alembic stamp set production to `015`.
- Targeted DDL is prepared in
  [`backend/scripts/prod_schema_gap_patch_20260509.sql`](/Volumes/MaxRelocated/WMS/backend/scripts/prod_schema_gap_patch_20260509.sql).
  It is retained for audit history and must not be rerun unless a future gate
  explicitly calls for it.

```bash
render psql dpg-d7akc4fkijhs73dp4ukg-a -c "
BEGIN;
ALTER TABLE pick_allocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE pick_allocations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON pick_allocations;
DROP POLICY IF EXISTS admin_bypass ON pick_allocations;
CREATE POLICY tenant_isolation ON pick_allocations
    USING (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));
CREATE POLICY admin_bypass ON pick_allocations
    USING (current_setting('app.is_platform_admin', true) = 'true');
COMMIT;
" -o text
```

- The script applies the `pick_allocations` RLS policy block in a transaction
  and ends with a verification snapshot, including the already-present outbound
  shipping readiness index. Do not add it to app startup, CI, or an automatic
  deploy hook.
- The equivalent targeted DDL is:

```sql
ALTER TABLE pick_allocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE pick_allocations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON pick_allocations;
DROP POLICY IF EXISTS admin_bypass ON pick_allocations;
CREATE POLICY tenant_isolation ON pick_allocations
    USING (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));
CREATE POLICY admin_bypass ON pick_allocations
    USING (current_setting('app.is_platform_admin', true) = 'true');
```

Execution evidence from May 9, 2026:

- The RLS patch was executed through `render psql ... -c` after operator
  approval.
- Post-patch read-only verification:
  - `pick_allocations` RLS/forced RLS: `true/true`;
  - policies present: `tenant_isolation`, `admin_bypass`;
  - schema gate RLS failures: `<none>`;
  - production `alembic_version`: `003`.
- Production health and agent production smoke passed on backend build
  `5091de5a00d0108c8a78fa115acdfbaadf9dab7a`.
- PostgreSQL reports the long outbound readiness index name as the 63-character
  truncated identifier
  `ix_outbound_orders_tenant_warehouse_shipping_readiness_created_`; the schema
  contract checker accepts this as the alias for the Alembic index name.

## Production Alembic Stamp Gate

Use this only after the schema/index/RLS gate reports no missing gaps and the
operator explicitly approves a production Alembic provenance write. This is a
stamp, not an upgrade: do not replay `alembic upgrade head` from the current
production state.

The guarded source SQL is
[`backend/scripts/prod_alembic_stamp_015_20260509.sql`](/Volumes/MaxRelocated/WMS/backend/scripts/prod_alembic_stamp_015_20260509.sql).
It refuses to update `alembic_version` unless:

- current production `alembic_version` is exactly `003`, or already `015` for a
  no-op;
- required indexes are present, including PostgreSQL's truncated alias for the
  long outbound readiness index;
- required tenant-scoped tables have RLS enabled and forced.

Render CLI requires `--command` in non-interactive mode. After explicit
approval, run:

```bash
STAMP_SQL="$(perl -ne 'print unless /^\\/' backend/scripts/prod_alembic_stamp_015_20260509.sql)"
render psql dpg-d7akc4fkijhs73dp4ukg-a -c "$STAMP_SQL" -o text
```

Post-stamp verification:

```bash
render psql dpg-d7akc4fkijhs73dp4ukg-a \
  -c "SELECT version_num FROM alembic_version ORDER BY version_num;" \
  -o text

curl --max-time 20 -fsS https://api.maxsmartwms.online/health
npm --prefix frontend run smoke:agent-production
```

Stamp execution evidence from May 9, 2026:

- Operator approved `Alembic stamp 015`.
- The guarded stamp SQL completed through `render psql ... -c`.
- Post-stamp verification:
  - `alembic_version`: `015`;
  - `missing_indexes`: `<none>`;
  - `rls_failures`: `<none>`;
  - production health: `ok` on backend build
    `84ee9610a4600dd8b2ca89b7d817acb2c514baff`;
  - `npm run smoke:agent-production`: passed.

## WCS Sandbox Certification Gate

Use this gate before enabling live AGV/WCS dispatch for a warehouse. Keep the
first pass sandbox-only: preview payloads and local simulator callbacks are
allowed; live WCS dispatch and live production callback writes require explicit
operator approval.

```bash
cd backend
DATABASE_URL="postgresql+asyncpg://<production-target>" \
  uv run python scripts/check_schema_contract.py

WMS_TOKEN=... node tools/wms.mjs wcs config --warehouse-id WH-ID
WMS_TOKEN=... node tools/wms.mjs wcs point-mappings list --warehouse-id WH-ID --include-unmapped
WMS_TOKEN=... node tools/wms.mjs wcs point-mappings export --warehouse-id WH-ID --format csv --file mappings.csv
WMS_TOKEN=... node tools/wms.mjs wcs point-mappings validate --warehouse-id WH-ID --file mappings.csv
WMS_TOKEN=... node tools/wms.mjs wcs gate-check --dry-run --task-id TASK-ID
WMS_TOKEN=... node tools/wms.mjs wcs dispatch --dry-run --task-id TASK-ID
WMS_TOKEN=... node tools/wms.mjs wcs ready-config --dry-run --warehouse-id WH-ID --ready-sign SIGN --api-sign 1 --api-num 3
WMS_TOKEN=... node tools/wms.mjs wcs quality-complete --dry-run --warehouse-id WH-ID --wtaskinfo-psn PSN
npm --prefix agv-simulator run smoke:dallas
WMS_TOKEN=... node tools/wms.mjs wcs callback replay --dry-run --tenant-id TENANT-ID --payload '{"taskTid":4093,"taskPsn":"PALLET-1","stepStatus":30}'
```

Evidence to retain in the release note:

- schema contract result, including any `alembic_version` warning;
- redacted WCS config with callback URL present;
- mapping counts: mapped locations, unmapped AGV-accessible locations, external
  points, issues, and warnings;
- dispatch preview gate result and source/destination point codes;
- ready-config and quality-complete preview payloads when outbound/QC flows are in scope;
- simulator route, callback statuses for `20` running / `25` paused / `30`
  completed / `40` exception, and saved exchange replay result;
- callback replay prediction, especially binding match and inventory movement.

Do not use simulator callbacks against the production webhook unless a live WCS
binding exists and the operator has approved the write-path test.

## 2026-05-06 Production Infrastructure Gate

Known from the repository and current runbooks:

- `render.yaml` defines the production backend as Render service
  `wms-quickstart` on branch `main`, root directory `backend`, Docker runtime,
  region `oregon`, `autoDeployTrigger: commit`, and `plan: free`.
- `render.yaml` keeps `DATABASE_URL`, `REDIS_URL`, JWT, and provider secrets as
  unsynced Render environment variables. The actual values, database provider,
  and database plan are not stored in the repository.
- `render.yaml` does not define a managed Postgres resource or backup policy.
  Legacy AWS RDS Terraform mentions seven-day backups, but that is not the
  active Render production path.
- `render.yaml` still has no `preDeployCommand`. Production schema changes
  therefore remain an explicit operator step from the Render shell or another
  trusted shell with the intended production `DATABASE_URL`.
- The local Alembic migration head is revision `015`; the production database
  revision must be checked directly on the production Postgres target.

Production infrastructure gate status: passed on 2026-05-09.

The gate uses Render CLI/API evidence plus operator acceptance from the current
thread. Do not record database connection strings or API tokens in this file.

Read-only Render CLI evidence captured on 2026-05-09:

- production backend service: `wms-quickstart`,
  `srv-d7ako4ggjchc73eh8g70`, repo
  `https://github.com/maxwu1978/wms-quickstart`, branch `main`, root
  `backend`, runtime `docker`, region `oregon`, one instance, plan `free`,
  auto-deploy `commit`;
- AGV sandbox service: `wms-agv-sandbox`,
  `srv-d7v5s1pj2pic73e5e0v0`, root `agv-simulator`, runtime `docker`, region
  `oregon`, one instance, plan `free`, health check `/api/health`;
- production database: Render Postgres `WMS-VM`,
  `dpg-d7akc4fkijhs73dp4ukg-a`, database `appdb_0zfl`, plan `basic_256mb`,
  15 GB disk, Postgres `18`, region `oregon`, status `available`;
- production `alembic_version`: `015`, checked through
  `render psql WMS-VM --command "select version_num from alembic_version;"`;
- production health: `https://api.maxsmartwms.online/health` returned
  `status=ok` on build `84ee9610a4600dd8b2ca89b7d817acb2c514baff`.
- Render API recovery status: `AVAILABLE`, starts at
  `2026-05-05T09:00:08Z`;
- Render API logical exports: latest export created at
  `2026-05-09T15:10:00Z`, id
  `dpg-d7akc4fkijhs73dp4ukg-a/2026-05-09T15:10Z`;
- restore owner: current Render account `Max Wu <wuqxmark@gmail.com>`;
- release-window plan acceptance: operator accepted the current backend
  `free` one-instance service plan with Render Postgres `basic_256mb` for the
  current release/test stage.

Operational follow-up, not a release blocker:

- download and retain the on-demand logical export if a local/off-platform
  archive is required in addition to Render PITR;
- revisit the backend service plan before sustained production traffic or any
  SLA commitment, because the accepted `free` one-instance plan is a release
  stage decision rather than a long-term capacity recommendation.

Suggested gate commands:

```bash
git rev-parse HEAD
curl --fail --silent --show-error https://api.maxsmartwms.online/health

cd backend
alembic heads
DATABASE_URL="postgresql+asyncpg://<production-target>" alembic current
```

Do not run `alembic upgrade head` against this production database unless a
future migration plan explicitly says to do so. The current production schema
surface is verified and the provenance stamp is already at `015`.

## Staging Backend Path

- Render service: `srv-d7qgk4rbc2fs73fsjbo0`
- Name: `wms-quickstart-staging`
- URL: `https://wms-quickstart-staging.onrender.com`
- Branch: `main`
- Root directory: `backend`
- Runtime: Docker, using `backend/Dockerfile`
- Plan: free
- Region: `oregon`
- Auto deploy: disabled
- Database: Neon staging project `maxsmartwms-staging`

This service is for backend smoke tests, migration rehearsal, and performance
regression checks. It must not be treated as production and should not receive
customer traffic or custom production domains.

The staging service stores its Neon `DATABASE_URL` and `JWT_SECRET_KEY` as
Render environment variables. Do not commit either value to the repository. The
connection string should use the SQLAlchemy asyncpg form:

```text
postgresql+asyncpg://<user>:<password>@<host>/<database>?ssl=require
```

Because auto deploy is disabled, trigger staging explicitly when a new backend
commit needs validation:

```bash
render deploys create srv-d7qgk4rbc2fs73fsjbo0 --commit <git-sha> --wait --confirm --output text
```

Then confirm:

```bash
curl --fail --silent --show-error https://wms-quickstart-staging.onrender.com/health
```

For database plan checks, continue using the trusted-shell runbook in
`docs/15-performance-and-database-plan.md`; do not print or paste the raw Neon
connection string into issue comments, commits, or screenshots.

Current validation status:

- 2026-05-01: staging deploy `dep-d7qgk53bc2fs73fsjc20` is live at build SHA
  `e683dadfcb10ef96d3a7d3af352a0081835fb8df`.
- 2026-05-01: `/health` passed and returned service ID
  `srv-d7qgk4rbc2fs73fsjbo0`.
- 2026-05-01: API smoke passed through the deployed staging backend by
  registering a temporary tenant and reading the core operational endpoints.
- 2026-05-01: Neon staging was promoted to Alembic revision `009` after the
  larger performance fixture exposed dashboard inventory aggregation as the
  main remaining measurable cost. The `ix_inventory_tenant_warehouse_live_metrics`
  index is present on staging.
- 2026-05-01: Neon staging was promoted to Alembic revision `010` after the
  production-like multi-warehouse fixture. The tenant-wide
  `ix_inventory_tenant_live_metrics` index is present on staging.
- 2026-05-01: staging API lifecycle QA passed against
  `https://wms-quickstart-staging.onrender.com/api/v1`, covering receiving,
  putaway, inventory movement, picking, packing, shipping, and tracking
  persistence.

## Production Email

Transactional email should use an HTTP/API provider on Render. SMTP settings are
still supported as a fallback, but they should not be the primary production
path on Render.

If Resend is unavailable, use one of these provider modes:

```text
EMAIL_VERIFICATION_REQUIRED=true
EMAIL_PROVIDER=brevo
BREVO_API_KEY=<brevo-api-key>
BREVO_FROM_EMAIL=WMS QuickStart <no-reply@your-domain.com>
```

or:

```text
EMAIL_VERIFICATION_REQUIRED=true
EMAIL_PROVIDER=smtp2go
SMTP2GO_API_KEY=<smtp2go-api-key>
SMTP2GO_FROM_EMAIL=WMS QuickStart <no-reply@your-domain.com>
```

or:

```text
EMAIL_VERIFICATION_REQUIRED=true
EMAIL_PROVIDER=mailersend
MAILERSEND_API_KEY=<mailersend-api-key>
MAILERSEND_FROM_EMAIL=WMS QuickStart <no-reply@your-domain.com>
```

The code also supports `EMAIL_PROVIDER=postmark`, `sendgrid`, `mailgun`,
`resend`, and `smtp`. Prefer `brevo`, `smtp2go`, or `mailersend` for a quick
replacement, then move to Postmark, Mailgun, or SendGrid if the account/domain
review process fits the production mail volume better.

Current production note:

- 2026-05-01: production self-registration still fails when verification email
  cannot be sent. Automated production page QA needs either a healthy email
  provider or a platform-admin bootstrap credential so the test tenant can be
  created without waiting for mailbox verification.
- 2026-05-01 follow-up: production logs show MailerSend returning
  `403 Forbidden` for verification email sends. After failover was deployed,
  SMTP was also attempted but failed from Render with network unreachable. The
  backend now attempts configured fallback providers after the selected provider
  fails, but public self-service registration still needs a healthy HTTP email
  provider such as Brevo, SMTP2GO, Postmark, SendGrid, Mailgun, or a repaired
  MailerSend account/domain.
- 2026-05-01 follow-up 2: the production mail-provider smoke confirms only
  `mailersend` and `smtp` are ready. MailerSend rejects Gmail recipients with
  `#MS42212` because the account can currently send only to verified recipient
  domains; SMTP still fails from Render with network unreachable. Public
  self-service registration should remain considered blocked until the
  MailerSend account is approved for external recipients or Render is configured
  with another HTTP/API provider.
- 2026-05-02 follow-up: MailerSend now accepts diagnostic sends from production
  (`POST /maintenance/email-provider/test` returns `deliveredBy=mailersend`).
  Public self-service registration is still blocked for brand-new recipients:
  MailerSend returns `#MS42225` (`trial account unique recipients limit`) before
  a verification email can be sent. Keep platform-admin bootstrap as the QA
  path until the MailerSend account limit is removed or a second HTTP/API
  provider is configured in Render.
- 2026-05-02 verification: `npm run smoke:mail-provider` passed against
  production, `npm run smoke:registration-email` reproduced the public
  registration block, and `npm run smoke:production-bootstrap` created a
  verified tenant admin through the protected platform path. The production page
  audit checked 70 desktop/mobile routes with 0 failures and 0 console errors.
- 2026-05-02 recovery: after the MailerSend Free subscription was completed,
  both `npm run smoke:mail-provider` and `npm run smoke:registration-email`
  passed in production. MailerSend returned `202 Accepted`, the registration
  endpoint returned `verificationRequired=true`, and the protected platform
  bootstrap still passed.
- 2026-05-02 recovery verification: a fresh public registration email was read
  from Gmail, its verification link returned the `Email verified` page, and the
  new tenant admin then signed in successfully. Core production regression also
  passed: warehouse lifecycle, receiving/putaway action surface, pack
  completeness, and shipping flow.
- Production smoke/regression scripts should use the protected platform
  bootstrap path first. Create a local ignored `.env.audit.local` from
  `/.env.audit.local.example`, then run:

  ```bash
  cd frontend
  npm run smoke:production-bootstrap
  ```

- Platform admins can test the live mail provider chain without exposing API
  keys. The endpoint reports configured providers, redacted provider errors,
  and which fallback actually delivered the diagnostic message:

  ```bash
  cd frontend
  npm run smoke:mail-provider
  ```

  The provider status response is production-safe: it reports provider names,
  HTTP/API vs SMTP transport, readiness, selected fallback order, and missing
  setting names only. It also flags whether the requested `EMAIL_PROVIDER` is
  supported and ready, so a Render typo or incomplete provider setup can be
  diagnosed without exposing API keys, passwords, sender addresses, or recipient
  addresses. Password reset and public email verification use the same provider
  chain and fallback behavior as this diagnostic.

  To test the public registration email path with a new recipient alias, run:

  ```bash
  cd frontend
  npm run smoke:registration-email
  ```

  To run the full operational lifecycle check against production:

  ```bash
  cd frontend
  npm run smoke:warehouse-lifecycle
  ```

  Optional: set `WMS_AUDIT_MAIL_TO` in `.env.audit.local` to choose the
  diagnostic/registration recipient. If `smoke:mail-provider` succeeds but
  `smoke:registration-email` returns `#MS42225`, the code and Render provider
  setup are healthy, but the MailerSend account still cannot send verification
  mail to additional unique recipients. Configure a second HTTP/API provider
  (`smtp2go`, `brevo`, `postmark`, `sendgrid`, or `mailgun`) or remove the
  MailerSend limit before reopening public self-registration.

The live service is currently on Render's free web plan. Render Blueprint
validation rejects `preDeployCommand` for that tier, so `render.yaml` does not
declare automatic Alembic migrations. Run migrations manually before or
immediately after a deploy that introduces schema changes, or move the service
to a plan that supports pre-deploy commands before adding
`preDeployCommand: alembic upgrade head`. After adding a pre-deploy command,
apply it in the Render dashboard or sync the Render Blueprint so the live
service actually uses the repository setting.

## Manual Migration

Run this from the Render shell, or from another trusted shell where you
explicitly export the async SQLAlchemy production database URL. Do not run a
plain `alembic upgrade head` from a local checkout, because it can pick up
`backend/.env` and migrate the wrong database.

```bash
DATABASE_URL="postgresql+asyncpg://<user>:<password>@<host>:5432/<database>" alembic upgrade head
```

After migration, confirm the service and build SHA:

```bash
curl --fail --silent --show-error https://api.maxsmartwms.online/health
```

Compare the returned full `build_sha` with the intended 40-character Git commit.

## When To Add A Deploy Hook

Add a Render deploy hook only if one of these becomes true:

- Render auto deploy is disabled and GitHub Actions becomes the deployment
  trigger.
- Production deploys need an explicit approval gate before Render starts.
- A staging-to-production promotion flow needs GitHub Actions to decide which
  commit Render should deploy.

If that happens, store the hook as `RENDER_DEPLOY_HOOK_URL` in GitHub Actions
secrets and change the Render workflow from SHA verification back to an
explicit hook trigger plus the same post-deploy health check.

## Manual Fallback

For a one-off production deploy, use the Render CLI with the intended commit:

```bash
render deploys create srv-d7ako4ggjchc73eh8g70 --commit <git-sha> --wait --confirm --output text
```

After it succeeds, confirm:

```bash
curl --fail --silent --show-error https://api.maxsmartwms.online/health
```
