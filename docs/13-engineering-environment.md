# Engineering Environment Notes

_Last updated: 2026-05-06; repository reconciliation added 2026-08-24_

## Repository Reconciliation Note

The migrated checkout is the `GreaterWMS` repository at
`https://github.com/maxwu1978/GreaterWMS.git`, branch `main`. It was migrated
from `https://github.com/maxwu1978/wms-quickstart.git`; the pre-migration source
snapshot was `55e4a70c7b0fd68d472483048a317fe02c665ad6`. The migration checkout
is shallow; run `git fetch --unshallow origin` before history-sensitive work.

The `/Volumes/MaxRelocated/WMS` path and deployment IDs below are historical
operational records from the dates stated in this document. Verify them against
GitHub, Render, and Vercel before a new release. See
[`docs/41-project-handoff.md`](41-project-handoff.md) for the current handoff
record and supported Agent/CLI entry points.

## Canonical Workspace

Use this directory as the only active WMS engineering workspace:

```text
/Volumes/MaxRelocated/WMS
```

This path is the Git working tree used for code changes, production deploys,
UAT scripts, documents, and release evidence. Do not use similarly named
folders on other mounted drives as active workspaces.

The previous duplicate workspace at `/Volumes/ORICO/WMS` was consolidated on
2026-05-05. Its useful artifacts were preserved under:

- [`docs/archive/orico-wms-20260505/`](/Volumes/MaxRelocated/WMS/docs/archive/orico-wms-20260505/)
- [`docs/assets/warehouse-layouts/carquest/`](/Volumes/MaxRelocated/WMS/docs/assets/warehouse-layouts/carquest/)

The full old ORICO working copy was renamed outside the active repo to:

```text
/Volumes/ORICO/_archived_20260505/orico-old-workcopy
```

That archive is for recovery only. New work should never start there.

## Current Production Baseline

- Frontend production domain: `https://app.maxsmartwms.online`
- Backend production API: `https://api.maxsmartwms.online/api/v1`
- Backend health check: `https://api.maxsmartwms.online/health`
- Frontend hosting: Vercel project `wms-quickstart-frontend`
- Backend hosting: Render service `srv-d7ako4ggjchc73eh8g70`
- Latest release closure commit:
  `f60ed6c Record release closure`
- Latest automated UAT evidence commit:
  `f9cd86f Record automated UAT completion`
- Latest verified CI run:
  `25428249062`
- Backend production build verified on 2026-05-06:
  `0616d3240c3dd7e5bb37f0f9f22fd358bca40ef0`
- Backend production deploy after email-token repair:
  `dep-d7tglvd0lvsc7397n9o0`
- Frontend production deployment verified on 2026-05-06:
  `dpl_2zU2mWFifUC44hzQFRJAKYAsjArm`
- Release UAT evidence:
  [`docs/23-uat-execution-log.md`](/Volumes/MaxRelocated/WMS/docs/23-uat-execution-log.md)
- iOS/iPadOS build runbook:
  [`docs/18-ios-ipad-build-runbook.md`](/Volumes/MaxRelocated/WMS/docs/18-ios-ipad-build-runbook.md)

Legacy deployment notes that reference AWS Activate or early Vercel/Render
setup have been moved to:

- [`docs/archive/legacy-deployment/`](/Volumes/MaxRelocated/WMS/docs/archive/legacy-deployment/)

Use [`docs/10-render-deploy-operations.md`](/Volumes/MaxRelocated/WMS/docs/10-render-deploy-operations.md)
and this file as the current operational source of truth.

## Local Workspace Hygiene

The repository should stay clean after normal build, lint, test, and deployment
work. These generated paths are expected to remain ignored:

- `frontend/node_modules/`
- `frontend/dist/`
- `frontend/tsconfig.tsbuildinfo`
- `frontend/.vercel/`
- `frontend/ios/App/App/public/`
- `frontend/ios/App/Pods/`
- `frontend/ios/App/build/`
- `backend/.venv/`
- `backend/.pytest_cache/`
- `backend/.ruff_cache/`
- `backend/.mypy_cache/`
- `**/__pycache__/`
- local databases such as `backend/wms_dev.db`
- local environment files such as `backend/.env`

Safe example templates should remain trackable even when they look like env
files. The canonical Render template is:

- [`backend/.env.render.example`](/Volumes/MaxRelocated/WMS/backend/.env.render.example)

## Recommended Checks Before Shipping

Run these before a frontend-only production push:

```bash
cd frontend
npm run build
npm run smoke:receiving-package-fallback
npm run lint
```

Current lint status: the command exits successfully in CI. Treat new lint
errors as blockers.

For backend-impacting changes, run:

```bash
cd backend
uv run pytest
```

If a backend deploy changes schema, run Alembic against the intended production
database from a trusted shell as described in
[`docs/10-render-deploy-operations.md`](/Volumes/MaxRelocated/WMS/docs/10-render-deploy-operations.md).

## Production Regression Pattern

### Verified Test Tenant Bootstrap

Production regression scripts should not use public self-service registration as
their primary path. Production keeps email verification enabled, so any mail
provider outage can block unrelated WMS flow tests.

Use platform-admin credentials for smoke/regression runs:

```bash
cd frontend
WMS_AUDIT_PLATFORM_EMAIL=... WMS_AUDIT_PLATFORM_PASSWORD=... npm run smoke:pack-completeness
WMS_AUDIT_PLATFORM_EMAIL=... WMS_AUDIT_PLATFORM_PASSWORD=... npm run smoke:receiving-putaway
WMS_AUDIT_PLATFORM_EMAIL=... WMS_AUDIT_PLATFORM_PASSWORD=... node ./scripts/verify-shipping-flow.mjs
WMS_AUDIT_PLATFORM_EMAIL=... WMS_AUDIT_PLATFORM_PASSWORD=... npm run audit:production-pages
```

For local Codex/operator runs, you can also create an ignored
`.env.audit.local` file from
[`/.env.audit.local.example`](/Volumes/MaxRelocated/WMS/.env.audit.local.example).
The audit scripts load this file automatically before reading
`WMS_AUDIT_*` variables. Never commit the real file.

Quick bootstrap-only check:

```bash
cd frontend
npm run smoke:production-bootstrap
```

The shared helper
[`frontend/scripts/audit-tenant-bootstrap.mjs`](/Volumes/MaxRelocated/WMS/frontend/scripts/audit-tenant-bootstrap.mjs)
calls the platform-only API
`POST /api/v1/maintenance/test-tenant/bootstrap`. The endpoint creates a fresh
tenant admin with `is_email_verified=true` and an active subscription, then
returns a tenant-admin JWT for the script. Local runs without platform
credentials can still fall back to `/subscriptions/register`.

For receiving and putaway regressions, use a two-layer check:

1. API closed-loop verification:
   - create QA-prefixed inbound orders under the production tenant
   - receive into staging
   - confirm normal putaway to empty slots
   - confirm same-SKU merge behavior
   - confirm split putaway behavior
   - confirm different-lot warning behavior
   - confirm different-SKU blocking behavior
   - confirm invalid receiving and scan attempts do not advance order state
2. Browser verification on `app.maxsmartwms.online`:
   - inspect receiving detail blocker text
   - test manual scan failure messaging
   - inspect putaway destination policy warning
   - confirm disabled actions do not mutate tasks or inventory
   - check browser console errors

The 2026-04-29 run used `qa0429064310` and confirmed:

- `SCAN-OPEN` stayed in `receiving` with `Expected 1 / Received 0`
- `DIFF-SKU-BLOCK` stayed in `putaway` with its putaway task `pending`
- selecting a mixed-SKU destination disabled `Confirm putaway`
- manual unknown barcode input displayed the rejected code and API error
- browser console errors: `0`

## Safe Cleanup Candidates

These are local generated files only. Delete them only when you do not need the
current local caches or build output:

```bash
rm -rf frontend/dist frontend/tsconfig.tsbuildinfo
rm -rf backend/.pytest_cache backend/.ruff_cache backend/.mypy_cache
find backend tools -type d -name '__pycache__' -prune -exec rm -rf {} +
```

Do not delete:

- `frontend/node_modules/` unless you are prepared to reinstall dependencies
- `backend/.venv/` unless you are prepared to recreate the virtual environment
- `.vercel/project.json` unless the project will be relinked
- any local `.env` file unless its values have been copied into the proper
  secret manager

## Current Follow-Up Backlog

- Clean existing frontend lint warnings in a separate refactor pass.
- Turn the production closed-loop API verification into a reusable script under
  `tools/`, avoiding temporary files under `/tmp`.
- Add a dedicated production smoke for putaway destination policy warnings.
- Decide whether old QA-prefixed production test records should be archived by
  an explicit maintenance script.
