# Current WMS Handoff

Snapshot: 2026-08-25

This is the current handoff entry point for the next development conversation.
Read this file together with `docs/43-environment-release-manifest.md` before
changing code or deploying anything.

## Repository

- Repository: `https://github.com/maxwu1978/GreaterWMS.git`
- Local checkout: `/Users/wuqingxin/Desktop/test/Program/3-仓库管理系统/tmp/greatewms-source`
- Active migrated release branch: `codex/mail2task-business-groups-20260825`
- Current migrated release commit: `88b3bf6729dff96b117759328c8c182a19d16f05`
- Migration source remote: `https://github.com/maxwu1978/wms-quickstart.git`
- Production rollback tag: `prod-legacy-2026-08-24`
- Working tree at handoff: clean

The GitHub `main` ref currently points to the legacy Django line at
`5371d0af`; the migrated staging release above was deployed by explicit commit
from the dedicated release branch. Do not force-update `main` while the two
code lines are being kept separate.

The active `main` tree is the migrated FastAPI/React system. The legacy Django
production code is retained in the `codex/cli-install-info` line and the
immutable production tag. Do not assume that `main` is the live customer
version.

## Runtime Environments

| Environment | Service | Code | Current status |
| --- | --- | --- | --- |
| Customer production | `greaterwms-production` / `srv-d9v6ahvqj5pc73d4spp0` | `codex/cli-install-info` at `7592afe8` | Healthy; auto-deploy disabled |
| Migrated staging | `wms-quickstart-staging` / `srv-d7qgk4rbc2fs73fsjbo0` | explicit `88b3bf67`; runtime `88b3bf67` | Healthy; explicit deploy only |
| AGV sandbox | `wms-agv-sandbox` | `main` / `agv-simulator` | Separate non-customer service |

Production URLs:

- Frontend: `https://app.maxsmartwms.online`
- API: `https://api.maxsmartwms.online`

Migrated staging health:

- `https://wms-quickstart-staging.onrender.com/health`
- Expected runtime SHA: `88b3bf6729dff96b117759328c8c182a19d16f05`

Migrated frontend preview (single source: `frontend/`):

- Vercel deployment: `dpl_6GfWg57Zu61ta2ujNtPiLMWdqXZD`
- URL: `https://wms-quickstart-frontend-i8s1te990-maxw-2608s-projects.vercel.app`
- Target: `preview`; production alias was not promoted
- Preview contract: `docs/45-frontend-preview-source-of-truth.md`

The production health endpoint returns `{"status":"ok"}` from the legacy
service and does not expose a build SHA. Render deployment history is the
source for the verified production commit.

## Data Migration

Production was treated as a read-only source. The new target database is
`WMS-VM`; migration was performed with:

- `1` Peak Smart Logistics tenant
- `1` warehouse
- `2` clients: Delta `56315` and PYTES `50895`
- `271` SKUs
- `40` locations across two staging zones
- `1` pre-arrival ASN: `ASN202608191`
- `0` inventory rows, matching the source production data

Source dimensions and weights were converted from inches/pounds to
centimeters/kilograms while preserving the original values in SKU attributes.
The production export is outside Git at
`/private/tmp/greaterwms-production-export-20260825.json` with restricted file
permissions. Do not commit it or paste its contents into issues.

Important data boundaries:

- Target users were not migrated; target admin bootstrap is still a separate
  task.
- Existing inactive/test tenants in the target database were not deleted.
- The new schema does not yet expose a first-class legacy source-evidence table;
  source metadata is preserved in migration metadata and SKU/ASN attributes.
- No writes were made to the legacy production database during migration.

## Code Areas

- `backend/`: FastAPI API, SQLAlchemy models, Alembic migrations, tests.
- `frontend/`: React/Vite web application and Capacitor shell.
- `wms-agent/`: local governed agent and installer build.
- `mcp-server/`: MCP adapter.
- `agv-simulator/`: AGV/WCS sandbox.
- `tools/migrate_legacy_django_export.py`: one-time legacy read/export mapper.
- `tools/verify_release_manifest.py`: offline environment consistency check.
- `release/environment-manifest.json`: current environment/version mapping.

## Required Checks Before Development

```bash
cd /Users/wuqingxin/Desktop/test/Program/3-仓库管理系统/tmp/greatewms-source
git status --short --branch
python3 tools/verify_release_manifest.py
git fetch --unshallow origin  # only if history-sensitive work is needed
```

Backend:

```bash
cd backend
uv run ruff check app/ tests/
uv run mypy app/ --ignore-missing-imports
uv run pytest tests/ -q
```

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm run check:ui-language
npm run build
```

## Release Rules

1. New feature work goes to `main` and is validated in migrated staging.
2. Do not deploy `main` to customer production.
3. Production auto-deploy is disabled. A production release requires an
   approved full commit SHA or immutable production tag.
4. Backend, frontend, API domain, database, secrets, and rollback evidence must
   be released together during the future cutover.
5. Never run cleanup, migration, import, or reset commands against production
   merely to test an interface. Use an isolated tenant or staging database.

Explicit production deployment, only after approval:

```bash
render deploys create srv-d9v6ahvqj5pc73d4spp0 \
  --commit <approved-production-commit> --wait --confirm --output text
```

Explicit staging deployment:

```bash
render deploys create srv-d7qgk4rbc2fs73fsjbo0 \
  --commit <approved-staging-commit> --wait --confirm --output text
```

After either deployment, verify the correct health URL and record the deploy
ID and returned commit. Do not store Render tokens, database URLs, passwords,
or customer email contents in Git.

## Recommended First Step In The Next Conversation

Start by saying: “Read `docs/44-current-handoff-2026-08-25.md`, inspect the
current `main` tree, and do not touch customer production. I want to develop
the following feature: ...”

The next agent should first identify whether the requested feature belongs to
the migrated FastAPI/React system or the legacy Django production system. New
development should target `main`; legacy production changes require a separate
security review and an explicit release decision.
