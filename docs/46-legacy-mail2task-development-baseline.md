# Legacy GreaterWMS Mail2Task Development Baseline

Effective date: 2026-08-25

## Source of truth

Mail2Task development is based on the original GreaterWMS production line,
not on the QuickStart React/Vite snapshot. The baseline is the production
commit `7592afe8` on `codex/cli-install-info`:

- backend: the existing Django applications, especially `asnserial/`;
- frontend: the existing Vue 2 + Quasar application under `templates/`;
- shell and operational behavior: `templates/src/layouts/MainLayout.vue` and
  the existing dashboard pages;
- source evidence behavior: `asnserial/models.py`, `asnserial/intake.py`, and
  `asnserial/views.py`.

The FastAPI/React tree is retained as a separate migration experiment. It is
not allowed to replace or silently reduce the legacy GreaterWMS feature set.

## First vertical slice

The existing Source Intake capability is the initial Mail2Task foundation. It
already stores and exposes email provenance, original message identifiers,
attachments, extracted fields, content hashes, processing events, status,
next action, owner role, and matched WMS entity references.

The first slice therefore:

1. makes `mail2task` the canonical frontend route and label;
2. keeps `source-intake` as a compatibility redirect;
3. leaves the existing Dashboard and WMS business routes unchanged;
4. shows owner and WMS handoff state in the task list;
5. permits internal warehouse roles to view the board while excluding
   supplier and customer roles.

No mailbox credentials are stored in the web application, and no production
deployment is implied by this development baseline.

## Required verification

From `templates/`:

```bash
yarn lint
yarn build
```

From the repository root, the Django source tests covering source evidence,
deduplication, provenance, state transitions, and role access must also pass.

Future work must add a feature-parity matrix before porting any additional
legacy module into the FastAPI/React tree.
