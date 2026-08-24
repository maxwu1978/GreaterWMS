# ORICO WMS Workspace Archive

This archive preserves useful material from the old duplicate workspace:

```text
/Volumes/ORICO/WMS
```

The active WMS workspace is:

```text
/Volumes/MaxRelocated/WMS
```

## What Was Preserved

- `orico-uncommitted.patch.gz`: compressed uncommitted code diff from the old
  ORICO Git working copy.
- `orico-status.txt`: short Git status from the old copy before it was
  archived.
- `orico-recent-log.txt`: recent Git history from the old copy.
- `legacy-docs/`: older documentation files from the ORICO copy.
- `root-notes/`: old `README.md`, `CLAUDE.md`, and environment example notes,
  grouped by their original root/backend/frontend location.

Warehouse layout drawing assets were moved into the active docs asset area:

```text
docs/assets/warehouse-layouts/carquest/
```

## Decision

Do not use this archive as an active source of truth. Treat it as recovery
evidence only. If a future task needs material from here, inspect and migrate
the specific file into the active document or code structure instead of editing
inside this archive.

## 2026-05-05 Codex Intake Review

This archive was reviewed after consolidation into the active workspace.

Useful as reference:

- `legacy-docs/06-agent-console-spec.md`: still useful product direction for
  tenant-scoped BYO model configuration, tool boundaries, confirmation policy,
  and audit logging.
- `legacy-docs/08-agv-ready-receiving-roadmap.md`: useful background for future
  AGV receiving work, especially the principle that customer-facing labels
  should stay separate from internal execution labels.
- `legacy-docs/11-websocket-protocol.md`, `12-database-schema.md`,
  `13-api-conventions.md`, and `14-system-architecture.md`: useful orientation
  material, but verify every endpoint, model, and status against current code
  before reusing.
- `legacy-docs/project-plan.md`: contains durable working lessons around i18n,
  task-type filtering, closed-loop operator flows, and production walkthroughs.

Already absorbed or superseded:

- `orico-uncommitted.patch.gz` is an old code diff for split putaway
  allocations and Putaway UI work. It no longer applies cleanly to the active
  tree, and the current code already contains a more mature split allocation
  implementation and regression coverage. Keep it only as historical evidence.
- `root-notes/*/CLAUDE.md` and `root-notes/root/README.md` are old agent
  orientation notes. They are useful for context, but several details are stale
  and should not be copied wholesale.
- Legacy deployment notes have been superseded by the current deployment and
  environment runbooks in the active `docs/` directory.

Not project documentation:

- The ignored local `.claude/` directory in the workspace contains personal
  Claude settings and command permissions. It should remain untracked and should
  not be treated as reusable project documentation.
- `tmp/` screenshots are local visual evidence only. Move specific images into
  an active doc only when a future task needs them.
