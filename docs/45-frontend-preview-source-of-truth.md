# Frontend Preview Source of Truth

Snapshot: 2026-08-25

## Problem fixed

The repository had two different frontend preview paths:

- the legacy Vue build served from a temporary `/tmp/.../templates/dist/spa`
  directory on port `8123`; and
- the migrated React/Vite build in `frontend/`, used for the Vercel staging
  preview.

They were not the same application shell. A reviewer could therefore inspect a
standalone or legacy page while the deploy candidate was the migrated React
page, producing a false visual review result.

## New rule

The migrated release has one preview source: `/frontend` in this repository.
The production GreaterWMS page remains the visual reference until cutover, but
the preview artifact must always be built from the same `/frontend` tree that
will be deployed with the migrated FastAPI service.

Do not use a temporary `templates/dist/spa` server as the migrated preview. It
is a legacy reference artifact only and must not be presented as the release
candidate.

## Reproducible preview

```bash
cd frontend
npm run check:greaterwms-shell
npm run build
npm run preview:greaterwms
```

The canonical local URL is `http://127.0.0.1:8130/`. The API base URL is set at
build time with `VITE_API_BASE_URL`; for staging, use the staging API URL from
`release/environment-manifest.json`.

The Vercel Preview build sets `VITE_PREVIEW_MODE=1`. In that mode the root URL
opens directly on the read-only GreaterWMS `Warehouse Operations` board with
fixed review data, so visual review does not depend on browser login state,
cached local storage, service workers, or a live staging response. The preview
data is clearly synthetic and must never be treated as operational data. A
normal production build does not set this flag and keeps the normal landing and
login flow.

## UI contract

- `Dashboard` renders only the legacy-style `Warehouse Operations` execution
  board.
- `Mail2Task` is the only email-to-task workbench and owns task status,
  owners, email evidence, attachments, and WMS handoff.
- The migrated shell keeps the production GreaterWMS geometry: 56px top bar,
  200px drawer, compact grey work surface, and horizontally scrollable legacy
  tables.
- `Warehouse Operations` keeps its existing GreaterWMS table implementation;
  this page is the canonical visual reference and should not be refactored to
  accommodate a new component.
- Operational tables use
  `frontend/src/shared/components/GreaterWmsTable.tsx`. Its
  `GREATER_WMS_TABLE_SPEC` records the production table contract: dark navy
  header, 38px header rhythm, 48px minimum rows, zebra/hover states, and
  horizontal overflow. New feature pages supply business columns and content
  through this component; they must not copy the table chrome into separate
  Tailwind class sets.
- `DataTable.tsx` remains available for non-operational admin and portal data
  grids; Mail2Task uses `GreaterWmsTable`, while the execution board retains
  its original canonical implementation.
- `npm run check:greaterwms-shell` fails if Dashboard and Mail2Task are merged
  again, the shell markers are removed, or either operational table stops using
  the canonical/shared contract appropriate to its role.

## Release boundary

The current production alias `https://app.maxsmartwms.online` remains on the
legacy frontend/API pair. This change does not promote or deploy production.
Any future cutover must promote the tested `/frontend` artifact together with
the migrated API and database release, never one side independently.
