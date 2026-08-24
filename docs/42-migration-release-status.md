# Migration And Release Status

Snapshot: 2026-08-24

## Repository

- Active repository: `https://github.com/maxwu1978/GreaterWMS.git`
- Active branch: `main`
- Current migration commit: `99b2dbe7c559a3be1d6e241c8d4a940c18ad3022`
- Source snapshot: `https://github.com/maxwu1978/wms-quickstart.git`
- Local source remote: `quickstart-source`
- Local active remote: `origin` (`GreaterWMS`)
- Original GreaterWMS baseline: `legacy/greaterwms-original-20260824`
- Production Django rollback line: `legacy/django-production-20260824`
- Production Django source commit: `7592afe87ec94309276d9181103a504f3d91fc32`

The migrated tree is the source of truth for new development. The old
repository and both legacy branches are retained as rollback references; the
production Django line is the one that preserves the deployed business fixes.

## Deployment State

### Migrated staging service

- Render service: `wms-quickstart-staging`
- Service ID: `srv-d7qgk4rbc2fs73fsjbo0`
- Repository: `maxwu1978/GreaterWMS`
- Branch: `main`
- Root: `backend`
- Live deploy: `dep-da67rvvqj5pc73er0jkg`
- Live commit: `99b2dbe7c559a3be1d6e241c8d4a940c18ad3022`
- Health: `https://wms-quickstart-staging.onrender.com/health`

The health response was verified after deployment and returned `status=ok`,
`version=0.2.0`, `branch=main`, and the live migration commit. The OpenAPI
document at `/api/openapi.json` also returned successfully.

### Current production path

The production DNS is still:

- Frontend: `https://app.maxsmartwms.online` (existing Vercel deployment)
- API: `https://api.maxsmartwms.online`

The API DNS currently resolves to `greaterwms-production.onrender.com`, which
is still the legacy Django service on branch `codex/cli-install-info`. The
frontend and API therefore remain a matched legacy pair. They must not be
replaced independently with the migrated FastAPI/React pair.

Production cutover is intentionally pending a combined plan for:

1. database schema/data migration and backup;
2. new Render production service configuration and secrets;
3. new Vercel frontend deployment with the matching API base URL;
4. browser and API smoke tests; and
5. DNS/custom-domain cutover and rollback verification.

This is a deliberate hold, not an unpushed code change. The migrated code is
already pushed and running in staging.

## Verification

- GitHub CI for `99b2dbe`: passed.
- GitHub dependency graph: passed.
- Frontend `npm run build`: passed locally.
- Local Agent smoke: 39 passed, one upstream deprecation warning.
- Staging `/health`: passed on the migrated commit.
- Staging `/api/openapi.json`: passed.
- Production frontend/API cutover: not performed because the contracts and
  database models are different.

## Next Release Gate

Before production cutover, do not deploy from `quickstart-source`, either
legacy branch, or `codex/cli-install-info`. Use only `origin/main`, record the
target database, and deploy backend and frontend as one release. If rollback is
required before cutover, use `legacy/django-production-20260824`, not the old
baseline branch.
