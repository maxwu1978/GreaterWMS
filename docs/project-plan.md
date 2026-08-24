# Project Plan

## Handoff Reconciliation (2026-08-24)

This file is a chronological project log, not the current command reference.
The active repository after migration is `GreaterWMS` and the current supported
local Agent launcher is `node tools/local-agent.mjs`; this checkout does not contain
`tools/wms.mjs` or `tools/greaterwms.mjs`. Older entries below intentionally
preserve historical decisions and command examples. For current startup,
deployment, workflow, and Agent/MCP instructions, use
[`README.md`](../README.md), [`41-project-handoff.md`](41-project-handoff.md),
and [`25-greaterwms-cli-reference.md`](25-greaterwms-cli-reference.md).

## 2026-05-07 WMS Agent Standalone Installer Packaging

The local agent reference implementation has been moved into a standalone
`wms-agent/` folder so it can be distributed without the full WMS repository.

- Packaging:
  - `wms-agent/` now contains the Python package, bundled static UI, bundled WMS
    skills, install scripts, tests, and build script.
  - macOS installer: `wms-agent/install/macos/install.command`.
  - Windows installer: `wms-agent/install/windows/Install WMS Agent.cmd`, which
    invokes the PowerShell installer.
  - `node wms-agent/scripts/build-installers.mjs` creates macOS, Windows, and
    source archives in `dist/wms-agent/`.
- Runtime:
  - Installed WMS Agent defaults to packaged `bundled_skills` instead of
    repository `.codex/skills`.
  - Static UI is packaged under `local_agent/static`.
  - Audit logs default to the user's application data directory.
  - Host and port are read from `WMS_LOCAL_AGENT_*` settings by the installed
    `wms-local-agent` entrypoint.
- Verification:
  - `node tools/local-agent.mjs smoke`: 36 passed.
  - `backend/.venv/bin/python -m ruff check wms-agent/local_agent wms-agent/tests`:
    passed.
  - `node wms-agent/scripts/build-installers.mjs`: created macOS, Windows, and
    source archives.
  - Installed-from-archive venv check: static UI exists, bundled skill count is
    8, and port config is honored.

## 2026-05-07 Local-Agent Lane Boundary And Feature Batch

This thread is scoped to the local-agent lane only. It consumes existing WMS
platform APIs and must not implement platform endpoints, capability metadata,
database changes, migrations, or the WMS web Agent Console.

- Boundary and safety:
  - `wms-agent/README.md` now defines local ownership versus platform
    dependencies.
  - [30-local-agent-platform-contract-handoff.md](30-local-agent-platform-contract-handoff.md)
    now states that this local-agent process consumes the platform contract and
    records missing APIs as dependencies instead of implementing them.
  - local tests now cover `/api/plans/compare` authentication, direct-write
    model suggestion rejection, skill reason redaction, model secret redaction,
    strong confirmation, evidence session gates, and audit redaction.
- Local UI:
  - Evidence failed list has a local filter and copy-id actions.
  - Replay preview renders a compact summary before raw JSON.
  - Confirmation cards show impact, before/after, recovery, and strong
    confirmation state.
  - Settings preview form controls now cover client profile, SKU, and warehouse
    location in addition to receiving codes and labels.
- Local multi-model planning:
  - added `/api/plans/compare` for DeepSeek/Qwen/Kimi/MiniMax-compatible local
    planner comparison without executing WMS tools.
  - local policy adjudication chooses only safe allowed tool suggestions and
    rejects direct write tools.
- Local skills:
  - skill selection now returns public reasons and scores without exposing skill
    body text in UI/audit selection summaries.
- Local demo:
  - [29-local-agent-customer-demo-script.md](29-local-agent-customer-demo-script.md)
    now includes the local/platform boundary and planner comparison flow.
- Verification:
  - `node tools/local-agent.mjs smoke`: 35 passed.
  - `PYTHONPATH=wms-agent backend/.venv/bin/python wms-agent/scripts/verify_live_dry_run.py`:
    passed with missing-credentials skip.
  - `backend/.venv/bin/python -m ruff check wms-agent/local_agent wms-agent/tests`:
    passed.
  - `PYTHONPATH=wms-agent backend/.venv/bin/python -m pytest -q wms-agent/tests`:
    35 passed.
  - `git diff --check`: passed.

## 2026-05-07 Agent Responsibility Split

The agent work is now split into two lanes to avoid duplicating the separate
local-agent process.

- Codex-owned platform lane:
  - backend governed agent APIs: preview, evidence, confirmation token,
    idempotency, permission checks, rollback, and audit state.
  - CLI contract in `tools/wms.mjs`, including dry-run, live preview,
    confirm-only writes, capabilities, and production smoke commands.
  - Skills, SOPs, runbooks, project plan, and release gates that tell other
    models how to operate WMS safely.
  - CI/deploy/production health monitoring and closure evidence.
- Separate local-agent process lane:
  - local runtime service, model orchestration, local session handling, local
    UI, chat UX, local audit UX, provider routing, and customer demo flow.
  - Local Agent can consume Codex-owned platform APIs and CLI contracts, but
    should own its product behavior and UI decisions.
- Boundary rule:
  - Codex should not add new product features to `local-agent/` unless a
    platform API change breaks compatibility or a contract test needs a narrow
    fixture update.
  - Existing `local-agent/` code remains as a tested reference implementation
    until the separate process replaces it or it is deliberately archived.
- Next plan:
  1. Keep platform gates green: CI, Render deploy, `/health`, agent readiness,
     and production smoke.
  2. Freeze new `local-agent/` feature work on this lane and document any
     compatibility-only changes explicitly.
  3. Hand the separate local-agent process the current contract references in
     [30-local-agent-platform-contract-handoff.md](30-local-agent-platform-contract-handoff.md).
  4. Add or update contract tests only when the local agent needs a stable API
     guarantee from the platform.
  5. Continue platform roadmap after the split: high-risk Settings designs,
     authenticated import smoke in a disposable test tenant, and remaining
     agent command coverage.

### 2026-05-07 Handoff Execution

- Added [30-local-agent-platform-contract-handoff.md](30-local-agent-platform-contract-handoff.md)
  as the explicit handoff packet for the separate local-agent process.
- Updated [README.md](README.md) so the handoff is discoverable from the active
  documentation index.
- No new `local-agent/` product feature work was added in this lane.

### 2026-05-07 Local Agent Checklist And High-Risk Settings Design

- Completed next-plan item 2 by adding
  [31-local-agent-process-checklist.md](31-local-agent-process-checklist.md).
  It gives the separate local-agent process startup, read, preview, confirm,
  import, high-risk Settings, gate, and escalation checklists.
- Completed next-plan item 3 by adding
  [32-high-risk-settings-write-design.md](32-high-risk-settings-write-design.md).
  The decision remains no high-risk Settings writes yet; future gates must be
  preview-first, evidence-backed, idempotent, redacted, and separately tested.
- Updated [README.md](README.md) so both documents are discoverable.
- No `local-agent/` product-shell code was changed by this platform lane.
- Verification:
  - `cd frontend && npm run check:agent-contract`: passed.
  - `cd frontend && npm run check:agent-readiness`: passed.
  - `cd frontend && npm run smoke:agent-production`: passed against
    production build `c0418b7c624c06d22290ac077a88656d99825c4c`.
  - `cd frontend && npm run smoke:agent-import-production`: passed in
    preview-only/no-token mode.
  - `git diff --check`: passed.

### 2026-05-07 CLI And Skill Coverage Roadmap

- Started the post-split platform roadmap by adding
  [33-agent-cli-skill-coverage-roadmap.md](33-agent-cli-skill-coverage-roadmap.md).
- Current capability metadata reports 59 commands, 45 authenticated commands,
  and 17 planned write commands with governed write-gate metadata.
- Authenticated import smoke remains blocked in this runtime because no
  `WMS_TOKEN` or disposable import smoke tenant/session is configured.
- Next platform candidates are preview-only billing smoke, narrower Settings
  governance reads, recovery CLI convenience aliases, and desktop-first admin
  reads. High-risk writes remain blocked.

### 2026-05-07 Authenticated Import And Billing Preview Smoke

- Confirmed authenticated import smoke cannot run in this environment yet:
  `WMS_TOKEN` is not set and no disposable import smoke tenant/session is
  configured. Preview-only import smoke remains available and safe.
- Added `npm run smoke:agent-billing-production`.
  - no token: checks production health and billing capability metadata.
  - with token: reads billing settings, lists rate cards, and runs billing
    rate-card preview-only smoke.
  - it does not enable or execute billing writes.
- Verification:
  - `node --check frontend/scripts/verify-agent-billing-production-smoke.mjs`:
    passed.
  - `cd frontend && npm run smoke:agent-billing-production`: passed in
    no-token capability mode.
  - `cd frontend && npm run check:agent-contract`: passed.
  - `cd frontend && npm run check:agent-readiness`: passed.
  - `cd frontend && npm run smoke:agent-production`: passed.
  - `cd frontend && npm run smoke:agent-import-production`: passed in
    preview-only/no-token mode.
  - `git diff --check`: passed.

### 2026-05-07 Settings Governance CLI Split

- Started B1 from the post-handoff platform plan.
- Added narrow CLI views that consume the existing `/api/v1/agent/settings`
  endpoint without adding backend surface area:
  - `node tools/wms.mjs agent provider-health`
  - `node tools/wms.mjs agent allowed-tools`
  - `node tools/wms.mjs agent confirmation-policy`
  - `node tools/wms.mjs agent model-roster`
- These commands let the local-agent process inspect provider health, enabled
  tools, confirmation policy, and model validation state without parsing the
  full `agent settings` payload.
- Capability metadata now reports 63 commands, 49 authenticated commands, and
  17 planned write commands with governed write-gate metadata.
- Cancelled stale CI run `25465059672`; its backend job had passed, and its
  frontend job was stuck at `Install Playwright Chromium`.
- Verification:
  - `node --check tools/wms.mjs`: passed.
  - `cd frontend && npm run check:agent-contract`: passed.
  - `cd frontend && npm run check:agent-readiness`: passed.
  - `cd frontend && npm run smoke:agent-production`: passed.
  - `cd frontend && npm run smoke:agent-import-production`: passed in
    preview-only/no-token mode.
  - `cd frontend && npm run smoke:agent-billing-production`: passed in
    no-token capability mode.
  - `node tools/local-agent.mjs smoke`: 35 passed.

### 2026-05-07 Recovery Matrix CLI Convenience

- Started B2 from the post-handoff platform plan.
- Added static, preview-only recovery guidance aliases for the remaining
  operator/admin flows:
  - `node tools/wms.mjs putaway recover --dry-run --error-code ERROR`
  - `node tools/wms.mjs picking recover --dry-run --error-code ERROR`
  - `node tools/wms.mjs shipping recover --dry-run --error-code ERROR`
  - `node tools/wms.mjs inventory recover --dry-run --error-code ERROR`
- The aliases follow the Receiving recovery shape and return
  `what_happened`, `why_blocked`, `recommended_action`, `safe_commands`, and
  `next_action` without calling backend write endpoints.
- Capability metadata now reports 67 commands, 49 authenticated commands, and
  17 planned write commands with governed write-gate metadata.
- Verification:
  - `node --check tools/wms.mjs`: passed.
  - sample `putaway recover`, `picking recover`, `shipping recover`, and
    `inventory recover` dry-runs: passed.
  - `cd frontend && npm run check:agent-contract`: passed.
  - `cd frontend && npm run check:agent-readiness`: passed.
  - `cd frontend && npm run smoke:agent-production`: passed against
    production build `c0418b7c624c06d22290ac077a88656d99825c4c`.

### 2026-05-07 Desktop Admin Reads And Agent SOP Refresh

- Completed P3 from the post-handoff platform roadmap.
- Added authenticated, read-only desktop-first admin CLI views:
  - `node tools/wms.mjs admin subscription-status`
  - `node tools/wms.mjs admin warehouse-setup`
  - `node tools/wms.mjs admin billing-readiness`
  - `node tools/wms.mjs admin integration-status --client-id CLIENT`
  - `node tools/wms.mjs admin audit-summary`
- These views reuse existing subscription, setup, billing, integration, and
  evidence read surfaces. They add no backend endpoint and no write gate.
- Capability metadata now reports 72 commands, 54 authenticated commands, and
  18 planned write commands with governed write-gate metadata.
- Refreshed the agent SOP and skills so other models know to use the new
  workflow recovery helpers and desktop admin reads instead of opening the app
  UI or guessing hidden endpoints.
- Authenticated import smoke status remains unchanged:
  - preview-only production smoke passed.
  - authenticated preview/confirm remains blocked until `WMS_TOKEN` and a
    disposable test tenant/session are explicitly selected.
- High-risk Settings status remains unchanged:
  - billing rate-card apply, users/permissions, provider secrets, model roster
    writes, and allowed-tool governance stay blocked.
  - billing preview-only smoke passed, and capability metadata exposes no
    high-risk Settings write gate.
- Verification:
  - `node --check tools/wms.mjs`: passed.
  - `node tools/wms.mjs capabilities --json`: 72 commands, 54 authenticated,
    all `admin ...` commands have `agent_write_gate.enabled=false`.
  - `cd frontend && npm run check:agent-contract`: passed.
  - `cd frontend && npm run check:agent-readiness`: passed.
  - `cd frontend && npm run smoke:agent-import-production`: passed in
    preview-only/no-token mode.
  - `cd frontend && npm run smoke:agent-billing-production`: passed in
    no-token capability mode.

### 2026-05-07 Authenticated Local-Agent Online Checks

- Confirmed the local-agent live test account can authenticate against
  production without writing business state.
- Fixed the capability contract drift:
  - `planned_write_commands` now includes `receiving confirm`.
  - capability metadata reports 72 commands, 54 authenticated commands, and
    18 enabled write-gate commands.
  - `smoke:agent-production` now asserts `planned_write_commands` matches the
    enabled write-gate command count.
- Hardened release smoke coverage:
  - `smoke:agent-production` checks all five `admin ...` commands exist,
    require auth, and expose `agent_write_gate.enabled=false`.
  - it also asserts high-risk Settings/admin governance commands remain without
    an agent write gate.
- Authenticated import preview:
  - ran `smoke:agent-import-production` with the local-agent online test
    account.
  - result was safe preview-only evidence: `dry_run=true`, `writes=false`,
    one row error for the intentionally non-matching smoke CSV, and no confirm.
- Authenticated admin read smoke:
  - `admin subscription-status`: passed, subscription status `active`.
  - `admin warehouse-setup`: passed.
  - `admin billing-readiness`: passed, readiness summary `ready=true`.
  - `admin audit-summary --limit 5`: passed, failed evidence count `0`.
  - `admin integration-status --client-id 84fc7c71-3c6a-44fb-bee7-3a586bf8e06d`:
    passed.
- No production confirm/write was executed.

### 2026-05-07 Local Agent UI And Admin Smoke Automation

- Completed the first online local-agent interaction pass through the local
  service endpoints behind the UI:
  - `/api/health`: passed.
  - `/api/config`: returned configured MiniMax, Qwen, Kimi, and DeepSeek
    roster without exposing API keys.
  - `/api/session/login`: passed with the online test account.
  - `/api/tools/run`: inventory, inbound, outbound, and billing read tools
    passed.
  - `/api/chat`: passed for an inventory read prompt.
  - `/api/plans/compare`: passed across four configured model providers and
    selected `inventory.search`.
  - direct write tool `migration.inventory.import` was blocked with a 403 and
    a preview-first recovery message.
  - `/api/audit`: returned recent events without leaking the password.
- Added timeout protection to local-agent multi-model planning so one slow
  provider returns a structured timeout result instead of hanging the local UI.
- Added `npm run smoke:agent-admin-production`.
  - without `WMS_TOKEN`, it checks production health and admin command
    capability metadata.
  - with `WMS_TOKEN`, it reads subscription status, warehouse setup, billing
    readiness, audit summary, client lookup, and one integration status.
- Verification:
  - no-token `npm run smoke:agent-admin-production`: passed.
  - authenticated `npm run smoke:agent-admin-production`: passed with the
    online test account.
  - targeted local-agent timeout unit tests: passed.
  - no production confirm/write was executed.

### 2026-05-07 Agent Acceptance Gate And Closure Backlog

- Completed the requested follow-up gate pass after the Local Agent online
  checks.
- Authenticated import preview smoke:
  - ran `smoke:agent-import-production` with the online test account.
  - result was `ok=true`, `dry_run=true`, `writes=false`.
  - the intentionally non-matching inline CSV returned one row-level error and
    no confirmation card; confirm remained skipped.
- Acceptance gate results:
  - `node --check tools/wms.mjs`: passed.
  - `cd frontend && npm run check:agent-contract`: passed.
  - `cd frontend && npm run check:agent-readiness`: passed.
  - `cd frontend && npm run smoke:agent-production`: passed against production
    health build `c0418b7c624c06d22290ac077a88656d99825c4c`.
  - authenticated `cd frontend && npm run smoke:agent-import-production`:
    passed in preview-only mode.
  - authenticated `cd frontend && npm run smoke:agent-admin-production`:
    passed in read-only mode.
  - no-token `cd frontend && npm run smoke:agent-billing-production`: passed
    as a capability metadata gate.
  - `git diff --check`: passed.
  - GitHub CI run `25467919634` for
    `0b82c34bec8d3d858cfb5a8ec131fb58def06865`: passed.
  - production `GET /health`: `status=ok`, branch `main`, service
    `srv-d7ako4ggjchc73eh8g70`.
- Billing preview boundary found during the authenticated smoke:
  - billing read and rate-card list passed for the online test account.
  - `settings.billing_rate_card.preview` returned `403` because that tenant
    has not enabled the tool in allowed-tools.
  - this was not treated as a production write failure; no allowed-tools or
    governance settings were changed during the smoke.
- High-risk write boundary remains unchanged:
  - billing apply, users and permissions, provider secrets, model roster
    updates, allowed-tool governance, destructive deletes, carrier voids, label
    completion exceptions, and inventory bulk mutation still have no agent
    write gate.
  - future work must add a dedicated design, preview, evidence,
    confirmation-token, idempotency, permission, and audit contract before any
    one of those writes is enabled.
- Closure backlog:
  1. Decide whether the test tenant should enable
     `settings.billing_rate_card.preview` for authenticated preview-only smoke.
  2. If approved, rerun authenticated `smoke:agent-billing-production` and
     document the result.
  3. Keep production confirm smoke disabled until a disposable test tenant,
     controlled CSV, idempotency key, and explicit write approval are selected.
  4. Treat the current platform agent lane as ready for read, dry-run,
     preview-only, and governed medium-risk writes, with high-risk settings
     still blocked by design.

### 2026-05-07 Full Production Test Pass With Controlled Writes

- The owner confirmed the current system has no commercial production data, so
  the release validation scope was expanded from read/preview-only to
  controlled production writes.
- Production UAT:
  - `cd frontend && npm run uat:production`: passed for batch
    `UAT-20260507-01`.
  - covered warehouse/client/rate-card setup, receiving 2 packages, creating 2
    putaway tasks, putaway completion, inventory movement, rejected over-pick,
    picking, shipping, billing invoice sent, and billing invoice paid.
  - final UAT health build:
    `c0418b7c624c06d22290ac077a88656d99825c4c`.
  - final outbound status was `shipped`; tracking persisted; console errors
    were `0`.
- Mobile and admin UAT:
  - `cd frontend && npm run uat:mobile-orchestrator`: passed.
  - covered Admin, Agent, Dashboard, Inventory, Master Data, Migration,
    Picking, Putaway, Receiving, and Shipping.
  - cleanup inside the orchestrator deleted 4 test tenants and 84 tenant-scoped
    rows.
  - preserved tenants were `GREENECOPO` and `PLATFORM`; preserved operational
    rows deleted was `0`.
- Current test tenant reset:
  - reset `GREENECOPO` through
    `POST /api/v1/maintenance/current-tenant/demo-data/reset` using
    `RESET_CURRENT_TENANT_DEMO_DATA`.
  - preserved the tenant, current user, and subscriptions.
  - seeded demo client `MAXSMART`, warehouse `DEMO-FC`, locations
    `RCV-DOCK-01`, `RCV-STAGE-01`, `FP-01-01-01-01`,
    `RS-02-01-01-01`, demo SKUs, demo users, and demo rate card.
- Agent production writes:
  - authenticated `cd frontend && npm run smoke:agent-import-production` passed
    with `WMS_IMPORT_SMOKE_CONFIRM=true`.
  - the controlled CSV imported `DEMO-TOTE-BLUE` into
    `FP-01-01-01-01`.
  - preview result: `create=1`, `error=0`, `total_quantity_delta=7`,
    evidence `d474f451-8c18-4a25-aad0-efff318d85a3`.
  - confirm result: `ok=true`, imported `1`, idempotency key
    `agent-import-confirm-smoke-20260507-01`.
- Billing preview:
  - the test tenant allowed-tools list was expanded from 26 to 27 by adding
    only `settings.billing_rate_card.preview`.
  - authenticated `cd frontend && npm run smoke:agent-billing-production`:
    passed after the demo reset.
  - billing rate-card preview returned `writes=false` and
    `confirmation_required_for_write=false`.
- Follow-up defect found:
  - `settings receiving-codes preview --confirm` currently fails with
    `confirmation_mismatch` when the preview token comes from the CLI
    `/agent/tools/run` path.
  - the failed confirm did not mutate state; receiving code settings remained
    at the demo reset value `RCV`.
  - suspected cause: the preview payload hash includes the wrapper/default
    `/agent/tools/run` args while the confirm endpoint receives the narrower
    `/agent/settings/{key}/agent` body.
  - next platform fix should make settings CLI preview and confirm use the same
    canonical payload, then add production confirm smoke for receiving-codes,
    receiving-labels, client-profile, SKU, and warehouse-location.
- Final gates after write testing:
  - `cd frontend && npm run uat:production:cleanup`: passed; no test tenants
    remained.
  - `cd frontend && npm run smoke:agent-production`: passed.
  - authenticated `cd frontend && npm run smoke:agent-billing-production`:
    passed.
  - production `GET /health`: `status=ok` on build
    `c0418b7c624c06d22290ac077a88656d99825c4c`.

### 2026-05-07 Settings Confirm CLI Contract Fix

- Fixed the Settings CLI preview/confirm mismatch found during the controlled
  production write pass.
- Root cause:
  - confirm endpoints hash the canonical `/api/v1/agent/settings/{key}/preview`
    request body.
  - the CLI preview path for confirmable Settings tools previously used
    `/api/v1/agent/tools/run`, which added wrapper/default fields such as
    `limit`, `query`, and empty ids into the preview payload hash.
  - the later `/agent/settings/{key}/agent` confirm used the narrower
    canonical body, causing `confirmation_mismatch`.
- Fix:
  - `tools/wms.mjs` now routes confirmable Settings preview commands directly
    to the dedicated preview endpoints:
    `receiving-codes`, `receiving-labels`, `client-profile`, `sku`, and
    `warehouse-location`.
  - billing rate-card preview remains on the governed tool path because it is
    preview-only and has no confirmable billing write gate.
- Added `npm run smoke:agent-settings-confirm-production`.
  - no token: health and capability metadata only.
  - token without `WMS_SETTINGS_CONFIRM_SMOKE=true`: one receiving-codes
    preview, no write.
  - token with `WMS_SETTINGS_CONFIRM_SMOKE=true`: confirms receiving-codes,
    receiving-labels, client-profile, SKU, and warehouse-location, then replays
    each idempotency key.
- Production verification:
  - `node --check tools/wms.mjs`: passed.
  - `node --check frontend/scripts/verify-agent-settings-confirm-production-smoke.mjs`:
    passed.
  - no-token `cd frontend && npm run smoke:agent-settings-confirm-production`:
    passed.
  - the test tenant allowed-tools list was expanded to include
    `settings.client_profile.preview`, `settings.sku.preview`, and
    `settings.warehouse_location.preview`; `requires_human_confirmation_for_writes`
    stayed `true`.
  - authenticated `WMS_SETTINGS_CONFIRM_SMOKE=true npm run
    smoke:agent-settings-confirm-production`: passed.
  - evidence ids:
    `79348302-f041-494b-80d7-882c0bdbd572`,
    `bb996781-8e02-4483-89e2-645f220fb608`,
    `bd57b707-2907-4947-8307-cdaf6f369c4d`,
    `86005e7f-7433-42db-b531-f8b246645171`,
    `e609904d-1bd4-4e5c-9475-da8e759d0fb1`.
  - all five settings confirms returned `ok=true` and idempotency replay
    returned `ok=true` using the same evidence ids.
  - current test tenant was reset again through demo-data reset after the
    write smoke.

### 2026-05-07 Final Closure Evidence

- Current closure commit:
  - `5c03f7b9d11e33eea006d0201df0d17449da5072`
    (`Fix settings confirm CLI preview contract`).
- CI:
  - GitHub Actions CI run `25483152535`: passed.
  - backend job passed: ruff, mypy, and tests.
  - frontend job passed: type check, recovery matrix guard, UI language guard,
    build, Playwright Chromium install, and Admin mobile governance visual
    guard.
- Production health:
  - `GET https://api.maxsmartwms.online/health`: `status=ok`.
  - build SHA: `c0418b7c624c06d22290ac077a88656d99825c4c`.
  - branch: `main`.
  - service id: `srv-d7ako4ggjchc73eh8g70`.
- Production data cleanup:
  - final `cd frontend && npm run uat:production:cleanup`: passed.
  - before and after test tenant candidates: `0`.
  - before and after test tenant row total: `0`.
  - preserved tenants: `GREENECOPO`, `PLATFORM`.
  - preserved operational rows deleted: `0`.
- Final agent smoke:
  - final no-token `cd frontend && npm run
    smoke:agent-settings-confirm-production`: passed.
  - checked five Settings write-gate capabilities:
    receiving-codes, receiving-labels, client-profile, SKU, and
    warehouse-location.
  - mode was capability/preview-only; no write was executed in the final smoke.
- Closure state:
  - automated UAT, controlled write smoke, Settings confirm smoke, cleanup,
    CI, and production health have passed.
  - current platform agent lane is closed for read, dry-run, preview, governed
    medium-risk writes, import confirm, and Settings confirm.
  - remaining high-risk domains are intentionally future iteration work:
    billing apply, users and permissions, provider secrets, model roster,
    allowed-tool governance, destructive deletes, carrier voids, label
    completion exceptions, and inventory bulk mutation.

## 2026-05-07 Import Deployment Confirmation And Atomicity Expansion

This follow-up completes the first two next-plan items: production confirmation
and deeper import atomicity coverage.

- Production confirmation:
  - `main` is synced to `8dfb19cc6d595aba5025c362c78b23e28404fec3`.
  - GitHub CI passed for `8dfb19c`.
  - Render Backend Deploy passed for functional commit
    `0faf2fac995451d8e830998f04832e08e2f6869e`.
  - production health is `status: ok` on build SHA `0faf2fa...`.
  - `npm run smoke:agent-import-production` passed in preview-only mode.
- Import atomicity expansion:
  - added rollback coverage for inbound, outbound, and inventory when an import
    raises after a partial flush.
  - added checks that the idempotency in-progress row is cleared after that
    exception path.
  - added all-family idempotency replay coverage proving same key/same payload
    does not rerun import execution.
  - added all-family same key/different payload checks returning `409`.
- Verification:
  - `backend/.venv/bin/python -m ruff check backend/tests/test_regressions.py`
    passed.
  - targeted import regression tests passed: 9 passed, 153 deselected.

## 2026-05-07 Agent Import Hardening And Closure Plan

This pass closes the current six-line agent-first plan while keeping production
writes opt-in.

- Import write hardening:
  - inbound, outbound, and inventory import confirmations now run inside a
    backend savepoint so returned row errors roll back partial writes.
  - regression coverage now includes confirmation-token mismatch, changed
    payload mismatch, same idempotency key with a different payload, and
    rollback of partial import writes for all three import types.
- Production import smoke:
  - added `npm run smoke:agent-import-production`.
  - default mode is preview-only; confirm mode requires `WMS_TOKEN`,
    `WMS_IMPORT_SMOKE_CONFIRM=true`, a controlled test-tenant CSV, and an
    idempotency key.
- High-risk Settings:
  - added [29-high-risk-settings-agent-runbook.md](29-high-risk-settings-agent-runbook.md).
  - billing apply, users, permissions, provider secrets, model roster settings,
    and allowed-tool governance remain design-only until a later explicit gate.
- Agent-first operations:
  - local-agent skill and SOP now clarify direct reads, preview-first writes,
    import error recovery, and high-risk Settings boundaries.
- Local Agent UI:
  - confirmation cards now show concise recovery copy and mobile one-column
    controls without exposing confirmation tokens in the card.
- Remaining high-risk backlog:
  - production confirm smoke should be run only against a disposable test tenant.
  - high-risk Settings writes need separate designs and gates.
  - CI/deploy/production-health evidence must be updated after this pass is
    committed and pushed.
- Verification completed locally:
  - `node --check tools/wms.mjs`: passed.
  - `node --check frontend/scripts/verify-agent-import-production-smoke.mjs`:
    passed.
  - `cd backend && uv run ruff check app tests/test_regressions.py`: passed.
  - `cd backend && uv run mypy app`: passed.
  - `cd backend && uv run pytest -q`: 183 passed, 1 warning.
  - `cd local-agent && uv run pytest -q`: 30 passed.
  - `cd frontend && npm run check:agent-contract`: passed.
  - `cd frontend && npm run check:agent-readiness`: passed.
  - `cd frontend && npm run check:ui-language`: passed.
  - `cd frontend && npm run lint -- --quiet`: passed.
  - `cd frontend && npm run build`: passed.
  - `cd frontend && npm run smoke:agent-production`: passed against
    production build `703985639c9144f4922bcc4ed5b0b6f39090694c`.
  - `cd frontend && npm run smoke:agent-import-production`: passed in
    preview-only/no-token mode; authenticated preview/confirm was skipped.
  - `git diff --check`: passed.
  - Remote gates for commit `0faf2fac995451d8e830998f04832e08e2f6869e`:
    CI `25463876675` passed; Render deploy `25463876692` passed; production
    health is `status: ok` on the same build SHA.

## 2026-05-06 Settings Controlled Writes

This pass completes the Phase C medium-risk Settings write boundary. Receiving
code rules, Receiving label templates, client profile scalar fields, SKU scalar
fields, and warehouse location operational fields now share the same preview,
evidence, confirmation-token, idempotency, and audit contract.

- Backend write gates:
  - `POST /api/v1/agent/settings/receiving-codes/agent`
  - `POST /api/v1/agent/settings/receiving-labels/agent`
  - `POST /api/v1/agent/settings/client-profile/agent`
  - `POST /api/v1/agent/settings/sku/agent`
  - `POST /api/v1/agent/settings/warehouse-location/agent`
- Guardrails:
  - each write must match a persisted preview evidence row.
  - each write requires a confirmation token and `X-Idempotency-Key`.
  - each write reuses the caller's tenant scope and permission gate.
  - evidence is marked executed only after the setting is applied.
- CLI and Local Agent:
  - Settings preview commands now advertise `agent_write_gate` metadata.
  - CLI confirm commands reuse the existing `--confirm`,
    `--production-confirm`, and `--idempotency-key` pattern.
  - Local Agent confirmation cards work for Settings previews because the
    preview payload now includes `planned_request` and
    `confirmation_payload.confirmation_token`.
  - Direct import write tools are removed from default agent tools and blocked
    by local-agent policy; inbound, outbound, and inventory imports now route
    through preview evidence, confirmation token, idempotency, and
    `/agent/imports/{kind}/agent`.
- Still not enabled:
  - nested client settings and SKU attributes writes.
  - users and permission writes.
  - billing rate-card apply.
  - provider secrets, model settings, and allowed-tool governance writes.

## 2026-05-06 Settings Detail/Preview Closure And Phase C Plan

This pass completed the Settings-first agent read and preview lane, then set
the next controlled-write boundary.

- Completed Settings detail tools:
  - `settings.users.get`
  - `settings.warehouse.get`
  - `settings.rate_card.get`
- Completed Settings preview tools:
  - `settings.receiving_codes.preview`
  - `settings.receiving_labels.preview`
  - `settings.client_profile.preview`
  - `settings.sku.preview`
  - `settings.warehouse_location.preview`
  - `settings.billing_rate_card.preview`
- Production evidence:
  - commit: `3dd49ad`
  - CI: `25459077476`, passed.
  - Render deploy: `25459077561`, passed.
  - production API health build:
    `3dd49adcb5252665b57fc572e851640233aeb476`.
- Phase C checklist:
  1. Add controlled write gates for medium-risk Settings changes only:
     receiving code rules, receiving label template, client profile, SKU, and
     warehouse location.
  2. Each write must require a matching preview, persisted evidence,
     confirmation token, `X-Idempotency-Key`, permission gate, and audit update.
  3. CLI confirm commands must use the preview token and production confirmation
     flag, matching the existing Receiving/Inventory write gate pattern.
  4. Local Agent may show a confirmation card only when the WMS preview returns
     `confirmation_payload.confirmation_token`; chat text alone remains
     insufficient for writes.
  5. High-risk settings writes stay design-only for now: users, permissions,
     billing rate-card apply, provider secrets, and allowed-tool governance.

## 2026-05-06 Release Closure

This pass closes the current WMS release after production deploy, automated UAT,
and cleanup evidence all passed.

- Release artifacts:
  - frontend production deployment: `dpl_2zU2mWFifUC44hzQFRJAKYAsjArm`.
  - frontend production alias: `https://app.maxsmartwms.online`.
  - backend production deploy after email-token repair:
    `dep-d7tglvd0lvsc7397n9o0`.
  - backend health build:
    `0616d3240c3dd7e5bb37f0f9f22fd358bca40ef0`.
  - final evidence commit before closeout: `f9cd86f`.
  - final evidence CI before closeout: `25428034631`, passed.
- Release validation:
  - production frontend alias inspected as ready.
  - production backend `GET /health`: `HTTP/2 200`, status `ok`.
  - MailerSend diagnostic: passed after production token repair.
  - automated production UAT: passed for batch `UAT-20260506-01`.
  - mobile UAT orchestrator: passed across core mobile/admin workflows.
  - production page audit: `70` pages checked, `0` failures, `0` console
    errors.
  - final cleanup: final dry-run found `0` test tenants and `0` test rows;
    preserved operational rows deleted = `0`.
- Closure decision:
  - release is ready for final human evidence review and owner sign-off.
  - no page-by-page manual UAT is required for this release.
  - future product work should start as a new iteration, not as part of this
    release closure.

## 2026-05-06 Automated UAT Completed After MailerSend Token Repair

This pass repaired the production email gate and completed the approved
automated UAT sequence.

- Production email repair:
  - updated Render service `srv-d7ako4ggjchc73eh8g70` `MAILERSEND_API_KEY`
    through the Render API.
  - triggered backend deploy `dep-d7tglvd0lvsc7397n9o0`.
  - production health returned build
    `0616d3240c3dd7e5bb37f0f9f22fd358bca40ef0`.
  - `npm run smoke:mail-provider`: passed, diagnostic email sent by
    `mailersend`.
- Automated production UAT:
  - `npm run smoke:production-bootstrap`: passed with verified tenant admin.
  - `npm run uat:production`: passed for batch `UAT-20260506-01`.
  - `npm run uat:mobile-orchestrator`: passed across Admin, Agent, Dashboard,
    Inventory, Master Data, Migration, Picking, Putaway, Receiving, and
    Shipping.
  - orchestrator cleanup deleted `7` test tenants and `130` tenant-scoped rows,
    with preserved operational rows deleted = `0`.
  - `npm run audit:production-pages`: passed, `70` pages checked, `0` failures,
    `0` console errors.
  - final `npm run uat:production:cleanup`: passed, deleted the final
    layout-audit tenant and `11` tenant-scoped rows; final dry-run found `0`
    test tenants and `0` test rows.
- Release decision:
  - automated UAT evidence is complete.
  - the remaining human work is evidence review and final release sign-off, not
    manual page-by-page UAT.

## 2026-05-06 Automated UAT Paused On Email Provider Gate

This pass attempted to replace manual UAT with the approved automated
production UAT sequence, but stopped at the first gate before creating
production QA tenants.

- Automated UAT prerequisites:
  - platform credential: configured.
  - monitored recipient: configured as the platform Gmail mailbox.
  - cleanup preserve list: explicitly configured as `PLATFORM,GREENECOPO`.
  - release-owner approval: granted in-thread.
- Gate result:
  - `npm run smoke:mail-provider` returned `success=false`.
  - MailerSend returned `401 Unauthorized`.
  - SMTP fallback returned `Network is unreachable` from Render.
  - Render logs confirmed the same provider failures around the diagnostic
    request.
- Execution decision:
  - paused before `smoke:production-bootstrap`, `uat:production`,
    `uat:mobile-orchestrator`, `audit:production-pages`, and cleanup.
  - no automated UAT tenants were created in this attempt.
- Follow-up:
  - repair the production MailerSend API key/account or switch production email
    to another HTTP/API provider, then rerun `npm run smoke:mail-provider`
    before continuing automated UAT.

## 2026-05-06 Manual UAT Execution Log Prepared

This heartbeat confirmed the release gate is complete and moved the project
into manual UAT preparation without running production-writing automation.

- Current release status:
  - latest tracked commit: `35e0a89`.
  - CI run `25421643453`: passed.
  - production app alias `https://app.maxsmartwms.online`: `HTTP/2 200`.
  - production API health: `HTTP/2 200`, status `ok`, backend build
    `9a459f7c0d80dc398da34a8d19d7716602e7e8ef`.
- UAT execution artifact:
  - added `docs/23-uat-execution-log.md` with release-under-test evidence,
    read-only gate status, lane owners, core scenario result rows, issue log,
    and exit decision table.
- Production-writing automation remains gated:
  - do not run registration email, production bootstrap, production page audit,
    mobile orchestrator, or cleanup until platform credential, monitored email,
    cleanup preserve list, and release-owner approval are confirmed.

## 2026-05-06 Frontend Production Deploy For Receiving Split

This pass completed the release gate for the Receiving component split without
running production-writing QA commands.

- Frontend production deployment:
  - deployed `dc59a65` to Vercel production.
  - new deployment: `dpl_2zU2mWFifUC44hzQFRJAKYAsjArm`.
  - production URL:
    `https://wms-quickstart-frontend-lli015jbi-maxw-2608s-projects.vercel.app`.
  - production alias `https://app.maxsmartwms.online` now points to the new
    deployment.
- Read-only production checks completed:
  - `https://app.maxsmartwms.online`: `HTTP/2 200`.
  - `https://api.maxsmartwms.online/health`: `HTTP/2 200`, status `ok`,
    backend build `9a459f7c0d80dc398da34a8d19d7716602e7e8ef`.
- Production-writing QA remains gated by the UAT runbook prerequisites:
  platform bootstrap credential, monitored email delivery, cleanup preserve-list
  safety, and release-owner approval.

## 2026-05-06 Receiving Flow Component Split

This pass continues the Receiving module-size reduction lane by extracting
small presentational pieces from the main workflow file.

- Receiving workflow component split:
  - added `frontend/src/modules/receiving/receivingFlowComponents.tsx` for the
    recovery panel, process signal, and flow progress components.
  - `ReceivingFlow.tsx` now keeps the workflow orchestration while importing
    those presentational pieces from the component module.
  - `ReceivingFlow.tsx` dropped from `5481` lines to `5298`; the new component
    module is `187` lines.
- Verification completed:
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1979` modules transformed
  - frontend `npm run check:ui-language`: passed, checking `3371` operator
    strings and `243` button labels
  - frontend `npm run smoke:receiving-putaway`: passed
  - `git diff --check`: passed

## 2026-05-06 Receiving Flow Helper Split

This pass continues the frontend module-size reduction lane without touching
production data paths.

- Receiving pure logic split:
  - added `frontend/src/modules/receiving/receivingFlowUtils.ts` for receiving
    flow types, initial-step selection, package sorting, package type helpers,
    package origin labels, and quantity splitting.
  - `ReceivingFlow.tsx` now imports those helpers while keeping JSX workflow
    components in place for a smaller, safer first split.
  - `ReceivingFlow.tsx` dropped from `5719` lines to `5481`; the helper module
    is `262` lines.
- Verification completed:
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1978` modules transformed
  - frontend `npm run check:ui-language`: passed
  - frontend `npm run smoke:receiving-putaway`: passed
  - `git diff --check`: passed

## 2026-05-06 Parallel Production Hardening Pass

This pass ran the requested A-E lanes in parallel and reconciled them under
the main release plan.

- A, production infrastructure gate:
  - documented the production infrastructure gate in the Render runbook and
    release-gate audit.
  - repository-confirmed facts now stay separate from external platform facts
    that require Render/Postgres dashboard or trusted-shell confirmation.
  - production API health check through `https://api.maxsmartwms.online/health`
    returned `200 ok` with backend build `9a459f7` after the integrated pass
    deployed.
- B, transactional email:
  - `email_provider_status()` now reports whether the requested provider is
    supported, ready, or missing safe setting names.
  - password reset now has regression coverage for provider-chain fallback,
    matching the verification email path.
  - the runbook records that diagnostics expose provider names and redacted
    attempts, not provider secrets or recipient data.
- C, Putaway/Picking recovery structure:
  - Picking service failures now include `error_code` plus structured
    `detail.error_code/message`.
  - Putaway and Picking recovery classification now prefers backend error codes
    instead of message-string matching on the main paths.
  - recovery click smoke covers detail-only error-code payloads and key
    recovery button clicks.
- D, frontend module-size reduction:
  - Warehouse Planner pure helper logic moved into
    `warehousePlannerUtils.ts`.
  - `WarehousePlannerPage.tsx` keeps behavior but drops several hundred lines
    of unit conversion, grouping, heatmap, template, and label helpers.
- E, production QA readiness:
  - production page-level QA prerequisites are now explicit: platform bootstrap
    credential, monitored email delivery, cleanup preserve-list safety, and
    mobile orchestrator readiness.
  - production-writing commands are documented as requiring release-owner
    approval before execution.
- Integrated verification completed:
  - backend targeted pytest for email, password reset, forgot password, and
    picking guards: passed, `14` tests
  - backend ruff on changed backend files: passed
  - frontend `npm run check:ui-language`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1977` modules transformed
  - frontend `npm run smoke:recovery-actions`: passed against local preview
  - `git diff --check`: passed

## 2026-05-06 Production QA Readiness And Blocker Closure

This pass documents the E-lane production QA preflight without executing
production-writing commands.

- Production page-level automated QA prerequisites clarified:
  - bootstrap requires `WMS_AUDIT_PLATFORM_EMAIL` and
    `WMS_AUDIT_PLATFORM_PASSWORD` for a platform account that can create
    verified QA tenants and run cleanup.
  - email delivery requires a monitored `WMS_AUDIT_MAIL_TO` inbox and ready
    production provider status before registration-email smoke is meaningful.
  - test tenant cleanup requires `WMS_CLEANUP_PRESERVE_TENANTS` to preserve at
    least `PLATFORM,GREENECOPO`, dry-run review, and preserved operational rows
    deleted = `0`.
  - mobile orchestrator readiness requires Playwright/Chromium availability,
    confirmed production app/API targets, and an owner present for the cleanup
    step.
- Production-write command boundary recorded:
  - `smoke:registration-email`, `smoke:production-bootstrap`,
    `audit:production-pages`, `uat:mobile-orchestrator`, and
    `uat:production:cleanup` all create, mutate, email, or delete production QA
    data and should not be run without explicit release-owner approval.
  - `audit:production-pages` creates/seeds a layout-audit tenant before browser
    checks; it is not a pure page read.
  - `uat:mobile-orchestrator` chains production workflow checks and then invokes
    production test-data cleanup.
- Documentation updated:
  - [docs/16-uat-runbook.md](/Volumes/MaxRelocated/WMS/docs/16-uat-runbook.md)
    now carries the 2026-05-06 production QA readiness checklist and command
    classification.
  - [docs/20-manual-uat-checklist.md](/Volumes/MaxRelocated/WMS/docs/20-manual-uat-checklist.md)
    now has a field checklist for bootstrap credential, email delivery, cleanup
    safety, and mobile orchestrator readiness.

## 2026-05-06 Production Infrastructure Gate Documentation

- Added a production infrastructure gate to
  [docs/10-render-deploy-operations.md](/Volumes/MaxRelocated/WMS/docs/10-render-deploy-operations.md)
  and
  [docs/17-release-gate-and-access-audit.md](/Volumes/MaxRelocated/WMS/docs/17-release-gate-and-access-audit.md).
- Local facts now recorded: Render backend service identity and Docker/backend
  root from the runbook, checked-in `render.yaml` `plan: free`,
  commit-triggered auto deploy, unsynced `DATABASE_URL`, no managed Postgres
  or backup policy in the Blueprint, no `preDeployCommand`, and local Alembic
  head revision `012`.
- External confirmations are explicitly blocked from assumption: live Render
  plan and instance sizing, production Postgres provider/plan, backup and
  restore posture, latest backup, and production `alembic_version` must be
  confirmed in the external platform or trusted production shell.
- Suggested gate commands now cover target SHA, production health,
  `alembic heads`, production `alembic current`, and the trusted-shell
  migration/re-check sequence.

## 2026-05-05 Inventory And Dashboard Operator Focus

This pass starts the parallel B/C/D lane after the UI language guard release
gate.

- Inventory phone lookup tightened:
  - the phone surface now exposes a stable `single-record-lookup` contract.
  - the alternate stock list is collapsed by default so the first phone screen
    stays on one current record, one current question, search, and one primary
    action.
- Inventory adjustment safety strengthened:
  - manual adjustment requests now require a non-trivial reason at the API
    boundary.
  - the inventory service rejects blank reasons before mutating stock.
  - regression coverage verifies adjustment reason audit notes, quantity math,
    outbound readiness refresh, and no mutation when the reason is blank.
- Cycle count audit evidence strengthened:
  - cycle-count transaction notes now include system quantity, counted quantity,
    and variance in the format the UI activity parser can render.
  - regression coverage verifies stock mutation and transaction evidence.
- Dashboard next-work contract strengthened:
  - the mobile next-work card now exposes a stable `single-next-work` contract.
  - action-first mobile smoke now asserts the Dashboard contract, Inventory
    lookup contract, collapsed alternate record list, one primary action, and
    no horizontal overflow.
- Verification completed:
  - backend targeted pytest `inventory_adjustment or cycle_count_transaction`:
    passed, `3` tests
  - backend `ruff check app/api/v1/endpoints/operations.py
    app/services/inventory_service.py tests/test_regressions.py`: passed
  - frontend `npm run check:ui-language`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run smoke:admin-mobile-governance`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
  - local preview `npm run audit:action-first-mobile`: passed for Dashboard,
    Inventory, Putaway, Picking, Shipping, Billing, Clients, and SKUs
  - `git diff --check`: passed
- Release gate completed:
  - commit `aff3a76` pushed to `main`: `Tighten inventory dashboard mobile
    focus`
  - GitHub CI run `25401391702`: passed
  - Render Backend Deploy run `25401391744`: passed
  - Vercel deployment `dpl_5VKuRmRTha3zLCKFf6NxwRRxo85y` promoted to
    `https://app.maxsmartwms.online`
  - production alias responded `HTTP/2 200` on 2026-05-05 21:52 UTC
  - production `npm run uat:mobile-orchestrator`: passed for Admin, Agent,
    Dashboard, Inventory, Master Data, Migration, Picking, Putaway, Receiving,
    and Shipping
  - production cleanup passed: deleted `7` test tenants and `76` test rows,
    leaving `GREENECOPO` and `PLATFORM` preserved

## 2026-05-05 WMS UI Language Rules And Guard

This pass turns the senior process language guidance into a documented and
automated UI copy guard.

- UI language rules documented:
  - added `docs/ui-language-rules.md` with the page contract, glossary, button
    rules, status/action split, error recovery template, mobile copy limits, and
    review checklist.
- Static language guard added:
  - added frontend `check:ui-language` script.
  - the script checks operator translation fallback copy, i18n strings, mobile
    title length, button label length, blocked internal terms, and recovery
    body next actions.
- CI gate upgraded:
  - GitHub Actions now runs `npm run check:ui-language` before frontend build.
- Operator copy tightened:
  - replaced visible `live receiving`, `live picking`, `source staging`,
    `snapshot`, and `workbench` wording in core receiving, picking, putaway,
    shipping, dashboard, and inventory strings.
  - shortened several action labels including receiving start, label print,
    dock choice, cycle count, and count submit actions.
- Verification completed:
  - frontend `npm run check:ui-language`: passed, checking `3396` operator
    strings and `243` button labels
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run smoke:admin-mobile-governance`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
  - `git diff --check`: passed
- Release gate completed:
  - commit `0b392e8` pushed to `main`: `Add WMS UI language guard`
  - GitHub CI run `25399311597`: passed, including the new UI language guard
  - Vercel deployment `dpl_HxP99vjDrk68WNM7te1Z2ciLLv3o` promoted to
    `https://app.maxsmartwms.online`
  - production alias responded `HTTP/2 200` on 2026-05-05 20:37 UTC

## 2026-05-05 Admin Mobile Governance CI And Full Surface Pass

This pass completes the requested 1-6 follow-up after the first admin mobile
governance tightening release.

- CI gate upgraded:
  - GitHub Actions now installs Playwright Chromium, starts the built frontend
    preview, and runs `smoke:admin-mobile-governance:visual` in the frontend
    job.
- Clients and Billing Settings phone path tightened:
  - Clients/Billing Settings keeps the selected-client/readiness phone path.
  - add-client creation, rate-card setup, billing profile, and portal setup are
    explicitly desktop-preferred from the phone view.
- Master data and receiving settings phone path tightened:
  - Warehouses, SKUs, Receiving Code Settings, and Receiving Label Settings now
    expose mobile governance markers and collapse create/edit controls away from
    the phone primary path.
- Migration/Import Center phone path tightened:
  - Migration now exposes a phone governance panel and collapsed import
    boundary.
  - file upload, mapping, manual record creation, and final import confirmation
    stay in the desktop workbench.
- Agent tool governance matrix added:
  - Agent Console now has an explicit `TOOL_GOVERNANCE` matrix with risk,
    permission, confirmation level, and mobile policy for phase-1 tools.
  - phone tool policy is derived from the matrix instead of ad hoc naming
    rules.
- Production UAT orchestration upgraded:
  - the mobile UAT orchestrator now includes admin mobile governance coverage
    for Admin, Agent, Master Data, and Migration surfaces.
- Verification completed:
  - `git diff --check`: passed
  - frontend `npm run smoke:admin-mobile-governance`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
  - local preview `npm run smoke:admin-mobile-governance:visual`: passed for
    Agent Settings, Agent Console, Users, Clients/Billing Settings, Warehouses,
    SKUs, Receiving Code Settings, Receiving Label Settings, and Migration
- Release gate completed:
  - commit `3f157ba` pushed to `main`: `Expand admin mobile governance gates`
  - GitHub CI run `25398840307`: passed, including the CI Playwright visual
    guard
  - Vercel deployment `dpl_EQCkrG66npQAnLFvKpCMTrHA2gDo` promoted to
    `https://app.maxsmartwms.online`
  - production alias responded `HTTP/2 200` on 2026-05-05 19:56 UTC

## 2026-05-05 Admin Mobile Governance Tightening

This pass continues the admin mobile governance plan after the initial 1-2
implementation.

- Agent Settings phone path tightened:
  - phone now shows provider health, enabled state, validation state, and the
    desktop-first governance notice.
  - the full provider form, secret entry, advanced model settings, and complete
    tool catalog are hidden from the phone primary path and remain desktop.
- Agent Console phone path tightened:
  - phone now has its own tool-boundary panel for low-risk read and preview
    tools.
  - CSV upload and the full desktop tool catalog are hidden from the phone
    primary path.
  - tool catalog entries now expose an explicit phone/desktop policy boundary.
- Users phone path tightened:
  - add-user, permission matrix, and password/role setup are no longer visible
    as a full form in the phone primary path.
  - phone users can review the list and open one selected account, while account
    creation remains desktop-preferred.
- Verification added:
  - frontend `smoke:admin-mobile-governance:visual` uses Playwright with API
    mocks at a 390px viewport to check visibility, collapsed defaults, hidden
    desktop-only surfaces, and horizontal overflow.
- Verification completed:
  - `git diff --check`: passed
  - frontend `npm run smoke:admin-mobile-governance`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
  - local preview `npm run smoke:admin-mobile-governance:visual`: passed for
    Agent Settings, Agent Console, Users, and Billing Settings/Clients
- Release gate completed:
  - commit `631a2ce` pushed to `main`: `Tighten admin mobile governance paths`
  - GitHub CI run `25398075016`: passed
  - Vercel deployment `dpl_542nn74Pf6y8RLuCFwWAC6SJ2sec` promoted to
    `https://app.maxsmartwms.online`
  - production alias responded `HTTP/2 200` on 2026-05-05 19:40 UTC

## 2026-05-05 Admin Mobile Governance Implementation

This pass implements steps 1-2 after the desktop-first admin audit.

- Agent administration phone boundaries landed:
  - Agent Settings now exposes a phone-only governance panel with provider
    health, enabled/validation state, and explicit desktop preference for
    secrets, full tool catalog review, and high-risk governance.
  - Agent Console now exposes a phone-only governance panel that frames phone
    use around low-risk read tools and import previews, while routing imports,
    billing/permission changes, and high-risk confirmations to iPad or desktop.
- Users and Billing Settings audit landed:
  - Users now has a phone-only desktop-first management notice before access
    counts and dense management controls.
  - Billing Settings keeps its phone desktop-first notice and now carries the
    shared admin mobile governance marker.
- Verification added:
  - frontend `smoke:admin-mobile-governance` guards the admin mobile test ids,
    desktop-first copy, and Agent Console permission-gated tool contract.
- Verification completed:
  - `git diff --check`: passed
  - frontend `npm run smoke:admin-mobile-governance`: passed
  - frontend `npm run smoke:agent-governance-docs`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
- Release gate completed:
  - commit `efb9ede` pushed to `main`: `Implement admin mobile governance surfaces`
  - GitHub CI run `25395776207`: passed
  - Vercel deployment `dpl_981WYSYLd2AYNx8a6E241dvd1DE3` promoted to
    `https://app.maxsmartwms.online`
  - production alias responded `HTTP/2 200` on 2026-05-05 18:53 UTC

## 2026-05-05 Desktop-First Admin Mobile Audit And Agent Governance Spec

This pass completes steps 3-4 after the mobile current-object release.

- Desktop-first admin mobile audit completed:
  - added [docs/22-desktop-first-mobile-admin-audit.md](/Volumes/MaxRelocated/WMS/docs/22-desktop-first-mobile-admin-audit.md)
    as the page-level contract for Billing, Billing Settings, Clients, SKUs,
    Warehouses, Users, settings, Migration, Agent Settings, and Agent Console.
  - the rule is explicit: phone views may support quick lookup and
    selected-record review, while bulk import, billing, permission, and
    destructive management stay out of the primary phone path.
  - [docs/09-action-first-page-discipline.md](/Volumes/MaxRelocated/WMS/docs/09-action-first-page-discipline.md)
    now links to the formal audit.
  - [docs/20-manual-uat-checklist.md](/Volumes/MaxRelocated/WMS/docs/20-manual-uat-checklist.md)
    now includes phone checks for desktop-first admin pages, Agent Settings,
    and Agent Console.
- BYO Model Agent Console governance spec strengthened:
  - [docs/06-agent-console-spec.md](/Volumes/MaxRelocated/WMS/docs/06-agent-console-spec.md)
    now matches the current provider set: OpenAI, Claude, Gemini, Kimi,
    MiniMax, DeepSeek, Azure OpenAI, AWS Bedrock, Google Vertex AI, and
    OpenAI-compatible endpoints.
  - added a tool governance matrix covering risk, permission gate,
    confirmation requirement, and phase-1 behavior.
  - added the confirmation payload contract for medium/high-risk tools and the
    desktop/mobile boundary for Agent Settings and Agent Console.
- Governance doc gate added:
  - frontend `smoke:agent-governance-docs` verifies the desktop-first audit,
    Agent Console spec, page discipline link, and manual UAT rows stay present.
- Verification completed:
  - `git diff --check`: passed
  - frontend `npm run smoke:agent-governance-docs`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1976` modules transformed

## 2026-05-05 Release Evidence And Mobile Current Object Polish

This pass starts the next 1-4 plan by completing steps 1-2.

- Release evidence closed for the previous recovery hardening pass:
  - [docs/project-plan.md](/Volumes/MaxRelocated/WMS/docs/project-plan.md)
    now records commit `c9da5f0`, CI run `25394276603`, production deployment
    `dpl_6Ducp4p4x4DW4gqJaTJTLUeDNFbV`, and production recovery smoke.
- Mobile current-object hierarchy tightened:
  - Picking active task now exposes a compact phone-only current-object strip
    with order, source location, and SKU.
  - Shipping active task now exposes a compact phone-only current-object strip
    with order, active step, and checked line count.
  - the strips use stable test ids: `picking-mobile-current-object` and
    `shipping-mobile-current-object`.
- Smoke coverage strengthened:
  - recovery action smoke asserts the Picking current-object strip is visible
    on the missing-scan exception path.
  - Shipping flow smoke asserts the Shipping current-object strip is visible
    before pack recovery checks.
- Verification completed:
  - `git diff --check`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
  - local preview `npm run smoke:recovery-actions`: passed
  - local preview `node ./scripts/verify-shipping-flow.mjs`: passed, including
    mobile current-object coverage and shipped status
- Release gate completed:
  - commit `6ea8656` pushed to `main`: `Polish mobile current object hierarchy`
  - GitHub CI run `25394796773`: passed
  - Vercel deployment `dpl_9AaYLyky6A4mW58gqrsW411YmHQ3` promoted to
    `https://app.maxsmartwms.online`
  - production `npm run smoke:recovery-actions`: passed
  - production `node ./scripts/verify-shipping-flow.mjs`: passed, including
    mobile current-object coverage and shipped status

## 2026-05-05 Structured Recovery Codes And Recovery Click Coverage

This pass completes the first two follow-ups after the Picking/Shipping mobile
path release.

- Putaway recovery classification tightened:
  - Putaway recovery now maps backend `error_code` values through an explicit
    structured code table before falling back to legacy message matching.
  - covered code groups include source staging, source stock, allocation,
    destination, same-SKU policy, lot/expiry, inbound release, and stale task
    failures.
- Picking recovery classification tightened:
  - Picking recovery now maps backend `error_code` values through an explicit
    structured code table before falling back to legacy message matching.
  - covered code groups include unavailable tasks, rejected quantities, and
    stock changes.
- Recovery click smoke expanded:
  - Putaway recovery smoke now clicks `choose_slot`, `back_to_list`, and
    `refresh_task`.
  - Picking recovery smoke now clicks `adjust_quantity`, `back_to_list`, and
    `refresh_tasks`.
  - structured code assertions confirm the recovery panel exposes the expected
    prefixed `data-recovery-code`, primary action, and safe exit.
- Verification completed:
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
  - local preview `npm run smoke:recovery-actions`: passed
  - frontend `npm run smoke:recovery-matrix`: passed
- Release gate completed:
  - commit `c9da5f0` pushed to `main`: `Harden recovery code routing and click
    coverage`
  - GitHub CI run `25394276603`: passed
  - Vercel deployment `dpl_6Ducp4p4x4DW4gqJaTJTLUeDNFbV` promoted to
    `https://app.maxsmartwms.online`
  - production `npm run smoke:recovery-actions`: passed

## 2026-05-05 Picking Shipping Paths And Mobile UAT Orchestrator

This pass completes the ordered follow-up to add Picking and Shipping path
contracts plus a unified mobile UAT orchestrator.

- Picking mobile paths added:
  - Picking mobile next action now exposes `data-picking-path` with
    `allocate`, `scan`, and `exception`.
  - active Picking task mobile surface also exposes `data-picking-path`.
  - recovery smoke now verifies the missing scan code scenario maps the active
    Picking task to `exception`.
- Shipping mobile paths added:
  - Shipping mobile next action now exposes `data-shipping-path` with `pack`,
    `handoff`, and `exception`.
  - active Shipping order mobile surface also exposes `data-shipping-path`.
  - Shipping flow smoke now verifies picked-order queue and active surfaces both
    map to `pack`.
- Mobile UAT orchestrator updated:
  - `uat:mobile-orchestrator` now runs action-first mobile surfaces,
    Receiving-to-Putaway handoff, Putaway/Picking recovery actions, Shipping
    flow, and cleanup.
  - coverage expectations now include Dashboard and Inventory in addition to
    Receiving, Putaway, Picking, and Shipping.
- Action-first smoke strengthened:
  - `audit:action-first-mobile` asserts Picking and Shipping path metadata is
    stable in addition to visible next-action and collapsed queue details.
- UAT checklist strengthened:
  - [docs/20-manual-uat-checklist.md](/Volumes/MaxRelocated/WMS/docs/20-manual-uat-checklist.md)
    now separates Picking allocate/scan paths and Shipping pack/handoff paths.
- Verification completed:
  - `git diff --check`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
  - local preview `npm run audit:action-first-mobile`: passed
  - local preview `npm run smoke:recovery-actions`: passed
  - local preview `node ./scripts/verify-shipping-flow.mjs`: passed
- Release gate completed:
  - commit `d7281fe` pushed to `main`: `Add picking and shipping mobile paths`
  - GitHub CI run `25388770504`: passed
  - Vercel deployment `dpl_EGKNRadCkctUAm4jVvGuyDizhHkb` promoted to
    `https://app.maxsmartwms.online`
  - production `npm run uat:mobile-orchestrator`: passed
  - production coverage confirmed Dashboard, Inventory, Receiving, Putaway,
    Picking, and Shipping
  - production cleanup removed `3` test tenants and `40` tenant-scoped rows,
    with `0` operational rows touched

## 2026-05-05 Mobile Workflow Gate Recovery And Putaway Path Expansion

This pass completes the follow-up plan after the Putaway/Picking/Shipping
contract guard pass.

- CI gate recovered:
  - GitHub CI `25384608477` was rerun after the backend job had previously
    been cancelled by the runner.
  - the rerun completed successfully for both frontend and backend jobs.
- Receiving-Putaway smoke harness fixed:
  - `verify-receiving-putaway-action-surfaces.mjs` now waits for the created
    inbound order to appear in the active inbound list before opening the page.
  - it also explicitly opens the focused Putaway task from the queue before
    asserting mobile active-task controls.
  - production `smoke:receiving-putaway` passed end to end: receiving scan,
    staging, receipt confirmation, putaway task creation, mobile Putaway
    primary-action contract, putaway confirmation, and success next-step.
- Action-first mobile smoke expanded:
  - `audit:action-first-mobile` now covers Dashboard, Inventory, Putaway,
    Picking, Shipping, Billing, Clients, and SKUs.
  - Putaway asserts collapsed mobile queue options.
  - Picking and Shipping assert mobile next-action surfaces, collapsed queue
    counts, and no horizontal overflow.
- Putaway mobile paths expanded:
  - active Putaway primary action now exposes `data-putaway-path` with
    `recommended`, `manual`, and `exception`.
  - `data-putaway-primary-action` remains stable as `use_recommended_slot` or
    `confirm_putaway`.
  - smoke coverage asserts the recommended slot path maps to `recommended`.
- UAT checklist strengthened:
  - [docs/20-manual-uat-checklist.md](/Volumes/MaxRelocated/WMS/docs/20-manual-uat-checklist.md)
    now separates Putaway recommended, manual, and exception-path checks.
- Verification completed:
  - `git diff --check`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
  - local preview `npm run audit:action-first-mobile`: passed
  - local preview `npm run smoke:recovery-actions`: passed
  - local preview `node ./scripts/verify-shipping-flow.mjs`: passed
  - production `npm run smoke:receiving-putaway`: passed with the harness fix
  - cleanup removed `6` test tenants and `87` tenant-scoped rows, with `0`
    preserved operational rows deleted
- Release verification completed:
  - commit `b2c3803` pushed to `main`
  - GitHub CI `25387608198`: passed
  - Vercel production deployment `dpl_Hzwqm4dMkbjpnpgYMdZCNivGpv6f`
    aliased to `https://app.maxsmartwms.online`
  - production `npm run audit:action-first-mobile`: passed across Dashboard,
    Inventory, Putaway, Picking, Shipping, Billing, Clients, and SKUs
  - production `npm run smoke:receiving-putaway`: passed
  - production `npm run smoke:recovery-actions`: passed
  - production `node ./scripts/verify-shipping-flow.mjs`: passed
  - production cleanup removed `4` test tenants and `42` tenant-scoped rows,
    with `0` preserved operational rows deleted

## 2026-05-05 Putaway Picking Shipping Contract Guard Pass

This pass continues the ordered mobile execution template rollout after the
Inventory path contract.

- Putaway mobile primary action guard completed:
  - the mobile Putaway active-task surface now exposes a stable
    `putaway-mobile-primary-action` test contract.
  - `data-putaway-primary-action` separates `use_recommended_slot` from
    `confirm_putaway`.
  - secondary suggested slots and manual slot selection now expose stable
    collapsed-detail guards through `putaway-mobile-other-suggestions` and
    `putaway-mobile-manual-slot`.
- Picking recovery guard strengthened:
  - `verify-recovery-action-clicks.mjs` now covers the existing missing scan
    code recovery path.
  - the smoke asserts `picking.missing_scan_code`, recommended action
    `back_to_list`, a safe exit, and the four recovery sections.
- Shipping success transition guard strengthened:
  - `verify-shipping-flow.mjs` now asserts pack and ship success next-step
    panels remain visible after a short refresh/loading window.
- Verification completed:
  - `git diff --check`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
  - local preview `npm run smoke:recovery-actions`: passed
  - local preview `node ./scripts/verify-shipping-flow.mjs`: passed, including
    `packNextStepStillVisible` and `shipNextStepStillVisible`
  - cleanup removed `3` test tenants and `38` tenant-scoped rows, with `0`
    preserved operational rows deleted
- Release verification completed:
  - commit `c732727` pushed to `main`
  - GitHub CI `25384494107`: passed
  - Vercel production deployment `dpl_7kFfci2Yi4zXy6GGkmZwU2LiUE9D`
    aliased to `https://app.maxsmartwms.online`
  - production `npm run smoke:recovery-actions`: passed
  - production `node ./scripts/verify-shipping-flow.mjs`: passed, including
    `packNextStepStillVisible` and `shipNextStepStillVisible`
  - production cleanup removed `1` Shipping smoke tenant and `16`
    tenant-scoped rows, with `0` preserved operational rows deleted
- Known test harness note:
  - `smoke:receiving-putaway` currently opens Receiving to a clear queue after
    creating and starting the test inbound, so the script times out waiting for
    the receiving scanner before it reaches the new Putaway mobile assertions.
  - Putaway mobile primary-action coverage is therefore enforced in the mocked
    recovery smoke for this pass.

## 2026-05-05 Inventory Paths And Workflow Template Gap Review

This pass continues the ordered plan after the Inventory primary task contract.

- Inventory mobile paths completed:
  - the Inventory mobile recommended action now exposes a stable
    `data-inventory-path` contract with three execution paths:
    `lookup`, `record`, and `exception`.
  - `lookup` covers setup/empty/available-stock search states.
  - `record` covers the selected-stock count or adjust path.
  - `exception` covers staging, blocked, and allocated stock review paths.
- Action-first smoke extended:
  - `audit:action-first-mobile` now verifies the Inventory path value and the
    mapping between action keys and path categories.
  - Dashboard and Inventory still assert exactly one primary action, no
    horizontal overflow, and collapsed secondary controls.
- Putaway/Picking/Shipping template gap review completed through local backend
  `AgentTeamService`:
  - MiniMax, Qwen, Kimi, and DeepSeek reviewed the current mobile templates.
  - Shared priority 1: make state-transition feedback uniform across
    Putaway, Picking, and Shipping, anchored by `putaway-success-next-step`,
    `picking-success-next-step`, and `shipping-success-next-step`.
  - Shared priority 2: keep Picking recovery paths explicit for wrong pick or
    missing scan code scenarios.
  - Shared priority 3: keep Shipping success feedback visible after pack/ship
    actions before any refresh/loading state replaces it.
  - Shared priority 4: reduce Putaway competing primary actions where manual
    override/force placement appears beside the normal recommended action.
  - Deferred items: visual polish for current-object headers, container/trailer
    context, and generic low-frequency validation panels.
- Inventory UAT checklist strengthened:
  - [docs/20-manual-uat-checklist.md](/Volumes/MaxRelocated/WMS/docs/20-manual-uat-checklist.md)
    now separates phone Inventory checks for primary task, search, selected
    record, on hand/available/allocated, details, count/adjust, and collapsed
    filters.
- Verification completed:
  - `git diff --check`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
  - local preview `npm run audit:action-first-mobile`: passed
  - production cleanup removed `2` action-mobile test tenants and `4`
    tenant-scoped rows across the pre-deploy production-domain check and the
    local-preview check, with `0` preserved operational rows deleted
- Release verification completed:
  - commit `64f6ffc` pushed to `main`
  - GitHub CI `25377597698`: passed
  - Vercel production deployment `dpl_3Ce2tQezsF4V9ed7BQrGL8yNipjd` aliased to
    `https://app.maxsmartwms.online`
  - production `npm run audit:action-first-mobile`: passed
  - production cleanup removed `1` action-mobile test tenant and `2`
    tenant-scoped rows, with `0` preserved operational rows deleted

## 2026-05-05 Inventory Mobile Primary Task Contract

This pass completes the next ordered step after Dashboard mobile action-first.

- Inventory mobile first screen tightened:
  - the phone Inventory primary task now exposes the same contract language as
    Dashboard: current object, current question, next step, search input, and
    exactly one recommended action.
  - search remains in the first screen because it is the object-finding input
    for Inventory execution.
  - view switching, focus chips, warehouse/client filters, and reset controls
    remain behind collapsed `View and filters` progressive detail.
- Action-first smoke hardened:
  - `audit:action-first-mobile` now asserts Dashboard and Inventory each expose
    exactly one primary action.
  - it also asserts Dashboard secondary queues and Inventory secondary controls
    are collapsed by default.
  - Inventory now has a stable `inventory-mobile-current-object` assertion in
    addition to current question and recommended action.
- Verification completed:
  - `git diff --check`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
  - local preview `npm run audit:action-first-mobile`: passed
  - production cleanup removed `1` action-mobile test tenant and `2`
    tenant-scoped rows from the local-preview check, with `0` preserved
    operational rows deleted
- Release verification completed:
  - commit `9e42be8` pushed to `main`
  - GitHub CI `25377108807`: passed
  - Vercel production deployment `dpl_7dYKiRLgZAkm1kWxb76HeKjPjqbB` aliased to
    `https://app.maxsmartwms.online`
  - production `npm run audit:action-first-mobile`: passed
  - production cleanup removed `1` action-mobile test tenant and `2`
    tenant-scoped rows, with `0` preserved operational rows deleted

## 2026-05-05 Dashboard Mobile Action-First And UAT Lanes

This pass continues the recommended C-D-E plan after release gate hardening.

- Multi-model coordination completed through local backend `AgentTeamService`:
  - MiniMax, Qwen, Kimi, and DeepSeek were confirmed configured.
  - The shared recommendation was to execute Dashboard mobile first, avoid
    desktop regressions, reuse the existing mobile action-first surfaces, and
    keep Inventory changes conservative until the Dashboard contract is stable.
- Dashboard mobile action-first completed:
  - the phone Dashboard first screen now presents a primary task contract:
    current object, current question, why now, and exactly one primary action.
  - secondary operator queues moved behind `Other work queues` progressive
    detail instead of competing with the first-screen action.
  - setup guidance remains available as a collapsed secondary path.
- Inventory mobile status:
  - the existing `inventory-mobile-primary-task` contract was kept intact for
    this pass.
  - the action-first smoke continues to verify Inventory's current question,
    next step, and stable recommended action.
- UAT checklist layering completed:
  - [docs/20-manual-uat-checklist.md](/Volumes/MaxRelocated/WMS/docs/20-manual-uat-checklist.md)
    now splits UAT into mobile execution, desktop management, recovery
    contract, release gate, and cleanup/data-safety lanes.
- Verification completed:
  - `git diff --check`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
  - local preview `npm run audit:action-first-mobile`: passed
  - production cleanup removed `2` action-mobile test tenants and `4`
    tenant-scoped rows across the failed production-domain pre-deploy check and
    local-preview check, with `0` preserved operational rows deleted
- Release verification completed:
  - commit `ed6040c` pushed to `main`
  - GitHub CI `25376601983`: passed
  - Vercel production deployment `dpl_JEGKEgYdwFyv6DepVtZojxVcpY4J` aliased to
    `https://app.maxsmartwms.online`
  - production `npm run audit:action-first-mobile`: passed
  - production cleanup removed `1` action-mobile test tenant and `2`
    tenant-scoped rows, with `0` preserved operational rows deleted

## 2026-05-05 Release Gate Hardening And Receiving-Putaway Smoke

This pass starts the next recommended plan with the safety-net work first.

- CI/release gate hardening:
  - GitHub CI frontend job now runs `npm run smoke:recovery-matrix` before the
    production build.
  - The manual `production-smoke` workflow now runs the recovery matrix guard
    before browser smokes.
  - The same workflow now runs `npm run uat:mobile-orchestrator` after the
    receiving-to-putaway smoke, then always runs production test-data cleanup.
  - The release gate and UAT runbooks now include the recovery matrix and mobile
    orchestrator commands as required baseline checks.
- Receiving/Putaway action-surface smoke:
  - `verify-receiving-putaway-action-surfaces.mjs` now fills the visible scanner
    input instead of the first matching scanner input, avoiding hidden mobile or
    collapsed inputs during local preview and production smoke runs.
- Verification completed:
  - `git diff --check`: passed
  - frontend `npm run smoke:recovery-matrix`: passed
  - production `npm run smoke:receiving-putaway`: passed
  - production cleanup removed `1` test tenant and `21` tenant-scoped rows, with
    `0` preserved operational rows deleted

## 2026-05-05 Mobile UAT Orchestrator And Matrix Guard

This pass completed the requested next steps 1-2 after the shared recovery
panel extraction.

- Multi-model coordination completed through local backend `AgentTeamService`:
  - MiniMax, Qwen, Kimi, and DeepSeek were confirmed configured.
  - The combined guidance was to reuse stable Playwright gates rather than
    rewrite all workflow scripts around one shared data set in this pass.
- Mobile UAT orchestrator added:
  - `npm run uat:mobile-orchestrator`
  - the orchestrator runs the stable mobile Receiving recovery/happy path,
    Putaway/Picking recovery action checks, Shipping mobile recovery/handoff,
    and production test-data cleanup
  - it fails if Receiving, Putaway, Picking, and Shipping are not all covered
    by successful stages
  - the initially included `verify-receiving-putaway-action-surfaces.mjs` stage
    was removed from this orchestrator because it is not stable against local
    preview; the existing script remains available as a separate smoke
- Recovery matrix validator added:
  - `npm run smoke:recovery-matrix`
  - it parses [docs/21-recovery-code-coverage.md](/Volumes/MaxRelocated/WMS/docs/21-recovery-code-coverage.md)
    and checks documented codes against source, referenced automation scripts,
    automated code assertions, selector mentions, and at least one automated row
    per workflow
- Local verification completed:
  - `git diff --check`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
  - frontend `npm run smoke:recovery-matrix`: passed
  - local preview `npm run uat:mobile-orchestrator`: passed, covering
    Receiving, Putaway, Picking, and Shipping
  - production cleanup removed `2` test tenants and `32` tenant-scoped rows
    from the orchestrator run, with `0` preserved operational rows deleted
- Release verification completed:
  - commit `ad25b8f` pushed to `main`
  - GitHub CI `25375577951`: passed
  - Vercel production deployment `dpl_Dqm8hZRccqS5y44JkNfQaV6ftyxq` aliased to
    `https://app.maxsmartwms.online`
  - production `npm run smoke:recovery-matrix`: passed
  - production `npm run uat:mobile-orchestrator`: passed, covering Receiving,
    Putaway, Picking, and Shipping
  - production cleanup removed `2` test tenants and `32` tenant-scoped rows,
    with `0` preserved operational rows deleted

## 2026-05-05 Shared Recovery Panel And Coverage Matrix

This pass completed the requested next steps 1-2 after all four workflows had
the same recovery contract.

- Multi-model coordination completed through local backend `AgentTeamService`:
  - MiniMax, Qwen, Kimi, and DeepSeek were confirmed configured.
  - The first parallel run hit a provider read timeout, so the review was
    retried per provider and usable model feedback was collected.
  - The combined recommendation was a conservative shell extraction: centralize
    panel layout, section test ids, and `data-recovery-*` attributes while
    keeping workflow-specific action handlers, buttons, and links in each flow.
- Shared component completed:
  - `WorkflowRecoveryPanel` now owns the four-section structure for Receiving,
    Putaway, Picking, and Shipping.
  - Existing flow selectors remain stable:
    `receiving-recovery-panel`, `putaway-recovery-panel`,
    `picking-recovery-panel`, and `shipping-recovery-panel`.
  - Existing action selectors remain stable, including
    `{flow}-recovery-action-{action}` and `shipping-recovery-safe-exit`.
  - Flow-specific logic remains local: Putaway still renders router links for
    upstream correction, Shipping still uses `ActionButton`, and each workflow
    still owns action labels and handlers.
- Recovery code coverage matrix added:
  - [docs/21-recovery-code-coverage.md](/Volumes/MaxRelocated/WMS/docs/21-recovery-code-coverage.md)
    records each current Receiving, Putaway, Picking, and Shipping recovery
    code, scenario, recommended action, safe exit, and automation coverage.
- Local verification completed:
  - `git diff --check`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1976` modules transformed
  - local preview `verify-recovery-action-clicks.mjs`: passed
  - local preview `verify-mobile-receiving-flow.mjs`: passed
  - local preview `verify-shipping-flow.mjs`: passed
  - production cleanup removed `2` test tenants and `32` tenant-scoped rows
    from the local-preview API verification runs, with `0` preserved
    operational rows deleted
- Release verification completed:
  - commit `69e5a01` pushed to `main`
  - GitHub CI `25374825238`: passed
  - Vercel production deployment `dpl_CjrFya1prnPuzi69Y3LN2sJnfgiS` aliased to
    `https://app.maxsmartwms.online`
  - production `verify-recovery-action-clicks.mjs`: passed
  - production `verify-mobile-receiving-flow.mjs`: passed
  - production `verify-shipping-flow.mjs` initially confirmed the shared
    recovery structure and shipped summary, but read one stale packed status
    from the outbound order list; the script now polls the order list and ship
    summary until they agree
  - production `verify-shipping-flow.mjs`: passed after the polling hardening,
    including final shipped status and persisted tracking
  - production cleanup removed `3` test tenants and `48` tenant-scoped rows
    from the production verification runs, with `0` preserved operational rows
    deleted

## 2026-05-05 Full Recovery Contract Pass

This pass completed the requested multi-model steps 1-5 after the
Shipping/Picking recovery structure baseline.

- Multi-model coordination completed through local backend `AgentTeamService`:
  - DeepSeek, Qwen, Kimi, and MiniMax all responded with execution-risk review.
  - The synthesis agreed to ship Putaway/Receiving parity now, keep the shared
    component refactor conservative, and use stable selector assertions for
    automation.
- Receiving recovery now exposes the same four-section contract as the other
  operator workflows:
  - what happened
  - why the workflow cannot continue
  - recommended action
  - return entry
  - the panel exposes `data-recovery-code`, `data-recovery-action`, and
    `data-recovery-safe-exit`.
- Putaway recovery now exposes the same four-section contract and typed
  recovery codes for source staging, source stock, allocation, destination,
  policy, inbound release, stale task, and fallback confirmation failures.
- A Receiving recovery bug was fixed while adding automation:
  - `clear_scan`, `continue_next`, `review_inbound`, and `scan_again` now reset
    the scan-label mutation error, so the recovery panel clears instead of
    reappearing from stale mutation state.
- Shared component status:
  - the product contract is now aligned across Receiving, Putaway, Picking, and
    Shipping.
  - a shared `WorkflowRecoveryPanel` extraction is intentionally deferred until
    after this parity release has production evidence, because all four flows
    now share selectors and section semantics without a broad refactor.
- Automated checks were updated:
  - `verify-recovery-action-clicks.mjs` asserts Putaway and Picking recovery
    panel structure, recovery code, recommended action, and safe exit.
  - `verify-mobile-receiving-flow.mjs` asserts Receiving recovery structure on
    an unknown scan, clicks `clear_scan`, then continues the normal mobile
    receiving flow.
  - `verify-shipping-flow.mjs` continues to assert Shipping recovery structure
    and was rerun as a cross-flow regression.
- Manual UAT checklist was updated with explicit Receiving, Putaway, and
  all-four-flow recovery structure checks.
- Local verification completed:
  - `git diff --check`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1975` modules transformed
  - local preview `verify-recovery-action-clicks.mjs`: passed
  - local preview `verify-mobile-receiving-flow.mjs`: passed, including
    `receiving.scan_no_match`, recommended `clear_scan`, and safe
    `back_to_orders`
  - local preview `verify-shipping-flow.mjs`: passed, including Shipping
    recovery structure and final shipped status
  - production cleanup removed `3` test tenants and `43` tenant-scoped rows
    across the Receiving and Shipping verification runs, with `0` preserved
    operational rows deleted
- Release verification completed:
  - commit `889412d` pushed to `main`
  - GitHub CI `25374041617`: passed
  - Vercel production deployment `dpl_FYknJ7Z1QTPMrKgbtAxGhccDgSUB` aliased to
    `https://app.maxsmartwms.online`
  - production `verify-recovery-action-clicks.mjs`: passed
  - production `verify-mobile-receiving-flow.mjs`: passed, including
    `receiving.scan_no_match`, recommended `clear_scan`, and safe
    `back_to_orders`
  - production `verify-shipping-flow.mjs`: passed on rerun, including
    `shipping.resetPackCheck`, final `shipped` status, and persisted tracking
  - production cleanup removed `3` test tenants and `48` tenant-scoped rows
    from the production verification runs, with `0` preserved operational rows
    deleted

## 2026-05-05 Shipping/Picking Recovery Structure Pass

This pass completed the requested multi-model lanes 1-4 for the next
action-first WMS UI hardening step.

- Multi-model coordination completed through the configured backend
  `AgentTeamService` providers:
  - DeepSeek reviewed the recovery-panel contract and recommended preserving
    current behavior while adding stable recovery metadata.
  - Qwen reviewed automation coverage and recommended selector-first assertions
    for panel, code, recommended action, and safe exit.
  - Kimi reviewed Shipping/Picking operator edge cases and confirmed both
    workflows need explicit return entries.
  - MiniMax reviewed UAT/release risk and recommended standardizing data
    attributes before larger layout refactors.
- Shipping recovery now exposes the four-section product contract:
  - what happened
  - why the workflow cannot continue
  - recommended action
  - return entry
  - the panel also exposes `data-recovery-code`, `data-recovery-action`, and a
    stable safe-exit button selector.
- Picking recovery now exposes the same four-section contract, with typed
  recovery codes for wrong location, wrong SKU, stale task, missing scan code,
  quantity rejection, stock changes, and fallback confirmation failure.
- Automated checks were updated:
  - `verify-shipping-flow.mjs` asserts the Shipping recovery panel structure,
    recovery code, recommended action, and safe exit during mobile wrong-SKU
    recovery.
  - `verify-recovery-action-clicks.mjs` asserts the Picking recovery panel
    structure, recovery code, recommended action, and safe exit before clicking
    recovery actions.
- Manual UAT checklist was updated with explicit Shipping, Picking, and
  cross-flow recovery-structure checks.
- Local verification completed:
  - `git diff --check`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1975` modules transformed
  - local preview `verify-recovery-action-clicks.mjs`: passed
  - local preview `verify-shipping-flow.mjs`: passed, including Shipping
    recovery structure and final shipped status
  - production cleanup removed `2` test tenants and `29` tenant-scoped rows,
    with `0` preserved operational rows deleted

## 2026-05-05 Multi-Model Release Coordination

The requested multi-model coordination pass completed with all configured
backend agents responding through `AgentTeamService`:

- MiniMax
- Qwen
- Kimi
- DeepSeek

The four worker lanes were used as planning input and reconciled into the
release documents instead of committing temporary raw agent output:

- Worker 1, production verification scripts:
  - release-gate command order and evidence requirements are recorded in
    [docs/17-release-gate-and-access-audit.md](/Volumes/MaxRelocated/WMS/docs/17-release-gate-and-access-audit.md)
- Worker 2, database/RLS verification:
  - Alembic `012`, RLS, policy, and index checks are recorded in
    [docs/17-release-gate-and-access-audit.md](/Volumes/MaxRelocated/WMS/docs/17-release-gate-and-access-audit.md)
- Worker 3, Inventory/Dashboard next-line discovery:
  - the next implementation lane is captured in
    [docs/15-performance-and-database-plan.md](/Volumes/MaxRelocated/WMS/docs/15-performance-and-database-plan.md)
- Worker 4, UAT checklist cleanup:
  - formal evidence and cleanup requirements are captured in
    [docs/20-manual-uat-checklist.md](/Volumes/MaxRelocated/WMS/docs/20-manual-uat-checklist.md)

2026-05-05 coordination update:

- Backend status check:
  - production `/health` returned `200 ok`
  - live backend build SHA is `23bd74d343db78d4bcd57f741ca541d16c293aaa`
  - the earlier Cloudflare `520` was transient; Render logs showed the service
    restarted and then accepted requests again
- DB/RLS Gate:
  - local Docker Postgres `alembic upgrade head` passed to revision `012`
  - RLS inspection passed for `idempotency_records`, `pick_allocations`,
    `putaway_allocations`, and `tasks`
  - `idempotency_records` indexes confirmed:
    `uq_idempotency_tenant_key` and `ix_idempotency_tenant_operation`
  - production DB SQL inspection remains a deploy-time external gate because
    the Render free tier does not support one-off jobs
- UAT Evidence Gate:
  - recovery action smoke passed against local preview
  - mobile Receiving UAT passed against local preview plus production API
  - Shipping flow smoke passed against local preview plus production API
  - Pack completeness smoke passed after backend recovery
  - production cleanup exposed a release-blocking FK drift case where
    `pick_allocations` referenced outbound lines selected for cleanup through a
    different `tenant_id`; cleanup now deletes such dependent allocations by
    related outbound order/line before deleting lines
  - targeted cleanup regression passed, full backend regression passed
- Inventory/Dashboard next lane:
  - split into four parallel work packages: Inventory mobile lookup, Inventory
    adjustment safety, Dashboard next-work, and Verification

## 2026-05-05 Parallel Mobile Workflow Pass

This pass ran three coordinated mobile workflow lanes in parallel after the
offline recovery follow-ups:

- A lane, Receiving:
  - mobile Receiving keeps current package identity visible with package,
    SKU/line, and remaining quantity
  - queued offline receipt now has a mobile notice with scan-next and
    back-to-queue actions
  - damaged quantity greater than received quantity is blocked inline before
    confirmation
  - `verify-mobile-receiving-flow.mjs` now proxies API calls through Playwright
    so local preview can be checked against the configured API
- B lane, Putaway and Picking:
  - Putaway mobile queue hides filters and route controls behind a reveal
  - Putaway mobile active work focuses on one task, one recommended slot
    decision, one physical slot scan, and one confirm path
  - Putaway recovery hides normal slot/scan/confirm controls while active
  - Picking success feedback now sits beside the active scan or quantity input
  - Picking recovery keeps normal scan/confirm controls hidden while active
- C lane, Shipping:
  - mobile Shipping is now two clear steps: pack check and carrier handoff
  - mobile pack confirm is hidden until all picked SKU lines are checked
  - mobile carrier handoff captures carrier/tracking first, then moves to a
    separate review step before final shipment confirmation
  - documents, service level, and shipping cost stay behind secondary details
  - wrong-SKU recovery hides normal scanner/pack controls and restores scanner
    after reset
- Verification completed after integrating all lanes:
  - `git diff --check`: passed
  - backend `ruff check app/ tests/ alembic/versions/`: passed
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed, `1975` modules transformed
  - backend `pytest tests/test_security.py -q`: `15 passed`
  - backend targeted Putaway/Picking regression subset: `6 passed`
  - backend `pytest tests/test_regressions.py -q`: `131 passed`
  - local preview `npm run smoke:recovery-actions`: passed
  - local preview `verify-mobile-receiving-flow.mjs`: passed with no
    horizontal overflow and package identity / damaged quantity validation
  - local preview `verify-shipping-flow.mjs`: passed, including mobile recovery
    surface assertions and shipped status
  - `verify-pack-completeness.mjs`: passed with early-pack `409`, complete pack
    verification, and final shipped status
  - production cleanup removed `17` test tenants and `243` tenant-scoped rows,
    with `0` preserved operational rows deleted

## 2026-05-05 Follow-up Plan Items Completed

This pass closed the first three non-blocking follow-ups from the offline
recovery release plan.

- Fresh database migration path is now self-contained:
  - Alembic `001` creates current SQLAlchemy model tables before applying the
    historical RLS-only migrations.
  - Historical `005` and `011` are idempotent when the startup/bootstrap path
    already created `pick_allocations` or `idempotency_records`.
  - New Alembic `012` enables and forces RLS on `pick_allocations`, with the
    standard tenant isolation and platform-admin bypass policies.
  - SQLite tenant filtering now includes both `pick_allocations` and
    `putaway_allocations`.
- Putaway and Picking recovery classification no longer depends only on message
  text:
  - Putaway confirmation failures now return `error_code` values for stale task,
    source staging, source inventory, allocation, destination policy, and inbound
    stage failures.
  - Pick confirmation failures now return `error_code` values for missing/stale
    tasks, task ownership/AGV assignment, quantity problems, reserved quantity
    problems, and source stock changes.
  - The frontend recovery panels prefer structured `error_code` values and keep
    the previous text matching as backward-compatible fallback.
- Automated recovery-action click coverage was added:
  - `npm run smoke:recovery-actions` runs a Playwright smoke against the real
    frontend with mocked API responses.
  - The smoke clicks Putaway recovery actions for choosing another slot and
    returning to the putaway list.
  - The smoke clicks Picking recovery actions for adjusting quantity and
    returning to the pick list.
- Verification completed:
  - blank Postgres `alembic upgrade head`: passed to revision `012`
  - RLS/policy/index inspection on the blank database: passed for the critical
    tenant tables, including `pick_allocations` and `idempotency_records`
  - backend `ruff check app/ tests/ alembic/versions/`: passed
  - backend `pytest tests/test_security.py -q`: `15 passed`
  - backend targeted Putaway/Picking regression subset: `6 passed`
  - backend `pytest tests/test_regressions.py -q`: `131 passed`
  - frontend `npm run lint -- --quiet`: passed
  - frontend `npm run build`: passed
  - local preview `npm run smoke:recovery-actions`: passed

## 2026-05-05 Idempotency And Offline Recovery Gate

This pass hardens the operator workflows for weak network, duplicate taps,
browser retry, and scanner reconnect cases. The goal is to make Receiving,
Putaway, Picking, Packing, and Shipping mutations safe to retry while keeping
mobile operators on one clear recovery path.

- Multi-model review completed across backend/data correctness, mobile product
  UX, and release readiness.
- Backend idempotency implemented for high-risk mutation endpoints:
  - receiving start, receive package, receive printed label, complete receiving
  - putaway confirm and batch confirm
  - pick confirm
  - pack verify
  - ship confirm
- New tenant-scoped `idempotency_records` table and Alembic migration were
  added. The migration includes tenant key uniqueness, operation lookup index,
  and Postgres RLS policies.
- Backend startup schema bootstrap now also enables and refreshes RLS policies
  for `idempotency_records`, covering the current deployment pattern where
  missing model tables are created on application startup before migrations are
  stamped.
- Frontend offline outbox implemented:
  - network failures queue mutations in IndexedDB with the same
    `X-Idempotency-Key`
  - queued work is scoped to the originating tenant and user before replay
  - repeated offline taps reuse the queued mutation instead of adding duplicates
  - replay treats body-level business failures (`success: false`,
    `verified: false`) as failed queued actions, not synced work
  - successful replay invalidates React Query state so pages refresh after
    background sync
- Receiving mobile recovery was tightened:
  - queued receipt confirmations now show an information notice instead of a
    red error
  - the active package is cleared and the operator returns to the scan step
    rather than getting stuck on the queued package
- Scanner socket reconnect now uses bounded exponential backoff and ignores bad
  JSON frames without breaking the connection loop.
- Picking Work now prioritizes tasks assigned to the current signed-in user
  before falling back to unassigned tasks. The task lookup now requests the
  current user's assigned tasks server-side, and pick confirmation rejects tasks
  assigned to another human operator or to AGV work.
- Local verification completed:
  - backend `ruff` on changed backend files: passed
  - backend idempotency and assigned-pick regression subset: `6 passed`
  - backend full regression file: `131 passed`
  - backend end-to-end flow: `6 passed`
  - frontend `npm run lint`: passed with existing warnings only
  - frontend `npm run build`: passed
  - Docker Postgres `alembic stamp 010` -> `alembic upgrade head`: passed for
    migration `011`, with `idempotency_records`, indexes, forced RLS, and both
    policies present
  - Docker Postgres startup schema bootstrap from an empty database: passed,
    with `idempotency_records`, indexes, forced RLS, and both policies present
- Release gate still required before production rollout:
  - run the new Alembic migration or restart the backend schema bootstrap
    against the production Postgres/Neon database and confirm
    `idempotency_records`, unique key, index, RLS, and policies
  - run automated production UAT after deployment
  - run a manual weak-network/offline UAT pass on phone for receiving,
    putaway, picking, and shipping
  - verify scanner reconnect from a real mobile device or app shell
  - note: full Alembic from a blank database remains an existing repository
    limitation because early migrations assume model tables already exist; the
    supported fresh-database path is startup `create_all` bootstrap plus
    migration stamping until a full baseline migration is authored.

## 2026-05-05 Exception Recovery Release

The live workflow exception pass is complete and deployed. The goal was to
remove dead-end errors from Receiving, Putaway, Picking, and Shipping so an
operator always sees one clear recovery action and one safe route back to the
right work list.

- Multi-model review completed across system integrity, mobile product UX, and
  release/UAT readiness.
- P1 review findings were fixed before deployment:
  - Receiving recovery actions are capped to one primary action plus back to
    the work queue.
  - Picking hides normal scan/confirm actions while a recovery prompt is active,
    so stale or rejected tasks cannot keep inviting repeated failed confirms.
  - Shipping hides normal pack/ship work while a recovery prompt is active and
    shows a direct back-to-shipping-list escape in the recovery card.
- Production frontend deployment completed:
  - commit: `68fd1c5060a351838374cbbf62f90d8417d56673`
  - Vercel deployment: `dpl_5REENgC2LoKBapimLNbuod3Wb5uv`
  - production bundle: `index-BNcOY5TN.js`
  - production domain: `https://app.maxsmartwms.online`
  - backend health stayed on `3cbebb2fb9bd7ec45c97484fee41fbf6d8b005c4`
    because this pass did not change backend code.
- Verification completed after deploy:
  - local `npm run build`: passed
  - local `npm run lint -- --quiet`: passed
  - local and production `verify-receiving-package-fallback.mjs`: passed
  - `smoke:production-bootstrap`: passed
  - `smoke:pack-completeness`: passed
  - `smoke:receiving-putaway`: passed after the script selector was updated for
    the new dynamic scanner placeholder
  - `verify-shipping-flow.mjs`: passed
  - `uat:mobile-receiving`: passed
  - `uat:production`: passed with all page checks true and `consoleErrors: 0`
  - `audit:production-pages`: passed with `70` pages checked, `0` failures, and
    `0` console errors
  - `uat:production:cleanup`: passed, deleting `8` test tenants and `140` test
    rows; post-cleanup test tenant count was `0`
- Remaining non-blocking follow-up:
  - Replace Putaway/Picking string-based error classification with structured
    backend error codes when the backend contract is next touched.
  - Add automated clicks for the new recovery buttons; the current automated
    gate verifies happy paths and page health, while the manual UAT checklist
    now records the exception matrix.

## 2026-05-03 Plan Items 1-6 Closeout

Ownership for this pass is end-to-end: mobile workflow code, shared UI primitives, Figma design-system artifacts, UAT/iOS/performance documentation, deployment evidence, and cleanup.

2026-05-04 update: [docs/09-action-first-page-discipline.md](/Volumes/MaxRelocated/WMS/docs/09-action-first-page-discipline.md) now records the mobile operator principle from the Receiving cleanup. Future mobile passes on Dashboard, Putaway, Inventory, Picking, Shipping, Billing, and Master Data should follow the same rule: show one recommended action on the first screen, move counts/filters/history behind secondary reveals, and if the action is blocked, send the user to the exact setup/import/dashboard/context needed to unblock it.

2026-05-04 mobile page-principle update: the same document now adds the
one-screen primary-task rule. Mobile pages should aim to let the operator finish
the current primary task without scrolling; scrolling is allowed only for lists,
history, optional fields, or detail. This becomes the acceptance standard for the
next mobile refactor pass.

Recommended rollout order for the next pass:

1. Receiving: finish the phone scan/dock/quantity/confirm flow as the reference
   implementation, including single-screen steps, compact suggestions, clear
   validation, and obvious return paths.
2. Putaway: align active task execution with Receiving: one task, one final-slot
   decision, one confirm path; move planning context and route detail behind
   reveals.
3. Picking: align pick task list and active pick task with the same structure:
   list first, one active task per screen, scan feedback next to the active
   input, confirm action near the bottom.
4. Shipping: split packing and handoff into clear mobile steps; keep documents,
   carrier metadata, and service-level context secondary.
5. Inventory: make the phone page a lookup/count-adjust surface rather than a
   desktop table; keep filters compact and details behind row drill-in.
6. Dashboard: reduce the mobile dashboard to next recommended work plus a small
   navigation grid; hide analytics-style panels from the first viewport.
7. Billing, Master Data, Users, Settings: treat as desktop-first admin areas;
   mobile should show readable lists, explicit selected-record editing, and no
   dense multi-column management surface by default.

1. Mobile-first WMS page language: complete. Inventory, Picking, and Shipping now use compact mobile task-card lists and next-action focus surfaces instead of exposing desktop tables/workbench detail on phone. Shared `DataTable`, `MobileFlowGuide`, and `TaskCard` were tightened so mobile details collapse, step labels remain readable, and long task titles wrap. The documented baseline is: orient quickly, show the active task/blocker, put scan/form/confirm actions before secondary context, keep counts compact, and move history or supervisor detail behind explicit reveals.
2. Figma adoption: complete for v1. The Figma file now owns foundations, mobile workflow rules, page patterns, component handoff for DataTable, StatusBadge, Button, FilterPill, ScanPanel, MetricTile, MobileFlowGuide, TaskCard, FormField, and AppShell, plus the `16 Mobile UAT Flow / 2026-05-03` reference page. Production code and browser checks remain the source of behavior and validation.
3. UAT scenario pack: complete. [docs/16-uat-runbook.md](/Volumes/MaxRelocated/WMS/docs/16-uat-runbook.md) now records the formal scenario pack, automated baseline, evidence batch format, exception scenarios, issue template, cleanup process, and exit criteria.
4. iOS/iPad validation checklist: complete. [docs/18-ios-ipad-build-runbook.md](/Volumes/MaxRelocated/WMS/docs/18-ios-ipad-build-runbook.md) records the Capacitor build path, production endpoint requirements, simulator proof point, real-device readiness, and native iPhone/iPad validation checklist.
5. Monitoring/performance release gate: complete. [docs/15-performance-and-database-plan.md](/Volumes/MaxRelocated/WMS/docs/15-performance-and-database-plan.md) now ties together Neon staging query-plan evidence, RLS/index checks, production health/build SHA, GitHub CI, production page audit, UAT automation, cleanup, and the dashboard aggregate watch threshold.
6. Final status: complete for the pre-change baseline and in progress for this mobile-flow pass until the new commit is deployed and the production gate is rerun. The previous full automated release gate passed on production commit `6329c321690641901000ff8732046be1350543cd`; the reconciled previous production baseline was `f264d1ccda99e0e3009d406cdad375854463afd4` on Render service `wms-quickstart` / `srv-d7ako4ggjchc73eh8g70`, with GitHub CI run `25270291831` passing. This section should be updated again after the current mobile-flow commit is live.

## 2026-04-29 Progress Record

### Stage ownership rules added for receiving, putaway, picking, and shipping

- The inbound and outbound workflow state matrix is now documented in
  [`docs/14-stage-status-workflow.md`](/Volumes/MaxRelocated/WMS/docs/14-stage-status-workflow.md).
- Backend service guards now reject out-of-stage actions instead of allowing
  accidental cross-stage mutations:
  - receiving can only start from `expected` / `arrived`
  - receiving can only complete from `receiving`
  - putaway can only confirm inbound tasks after the inbound order is `putaway`
  - picking allocation only runs on `pending` outbound orders
  - pick-task release only runs on `allocated` outbound orders
  - shipping pack verification only runs on `picked` / `packing`
  - ship confirm only runs on `packed`
- Frontend active lists are now stage-scoped:
  - Receiving active work is limited to `expected`, `arrived`, and `receiving`
  - Receiving shows downstream `putaway` records only as `Putaway handoff`
  - Picking lists `pending`, `allocated`, and `picking`
  - Shipping lists `picked`, `packing`, and `packed`
- Putaway location suggestions now only consolidate into storage slots, so
  staging locations are no longer offered as final putaway destinations.
- Local verification completed:
  - backend full regression: `122 passed`
  - frontend production build: passed
  - frontend lint: passed with existing warnings only
- Production deployment and smoke verification completed:
  - code commit: `a17c870 Enforce warehouse stage ownership`
  - backend health: `a17c870e2642f7b74b996f47ca3825859fc0b23b`
  - Vercel deployment: `dpl_J1zoaNGq1CZJyTEsKPriZA5TxcHv`
  - production domain: `https://app.maxsmartwms.online`
  - API/browser smoke batch: `stage50555366`
  - verified `409` guards for premature receiving completion, pick release
    before allocation, pack before pick, repeated allocation, repeated pick
    release, and ship before pack
  - verified the normal outbound path still closes: allocate -> create pick
    task -> confirm pick -> verify pack -> ship confirm
  - verified putaway suggestions do not return a staging location as a final
    destination
  - verified the production receiving page loads the smoke inbound order with
    `0` browser console errors
- Note: the older registration-based production smoke script is currently
  blocked by email verification sending. The stage-ownership smoke therefore
  used a temporary tenant-admin user in the QA tenant and deactivated it after
  completion.

### Production receiving and putaway regression closed out

- A production QA run was completed against the live tenant using QA-prefixed
  inbound orders from run `qa0429064310`.
- The API checks covered the main receiving-to-putaway paths:
  - normal receiving into staging and putaway to an empty slot
  - same-SKU putaway merge
  - split putaway across two destinations
  - different-lot destination warning
  - different-SKU destination block
  - missing staging-location block
  - unknown receiving barcode rejection
- Follow-up UI fixes were shipped after the regression surfaced confusing
  exception feedback:
  - receiving detail pages now block completion based on unreceived SKU units,
    not only package-record existence
  - manual scan failures now show the attempted code and the backend rejection
    reason
  - putaway destination policy warnings are visible before the split panel is
    expanded, and blocked confirmations stay disabled
- Frontend production deployment verified:
  - commit: `31641e1 Improve receiving and putaway exception feedback`
  - Vercel deployment: `dpl_GywWdFiLKAHEqYgpVmeEzoQXhNPE`
  - production domain: `https://app.maxsmartwms.online`
- Verification completed after deploy:
  - `npm run build`
  - `npm run smoke:receiving-package-fallback`
  - `npm run lint` passed with existing warnings only
  - production browser regression for receiving blocker, barcode error, and
    putaway destination blocking
  - browser console errors: `0`

### Engineering environment cleanup started

- The repository now documents the current production baseline and local
  workspace hygiene in
  [`docs/13-engineering-environment.md`](/Volumes/MaxRelocated/WMS/docs/13-engineering-environment.md).
- `.gitignore` now explicitly covers local build/cache output while allowing
  safe env example templates to be tracked.
- `backend/.env.render.example` is now treated as a trackable production
  configuration template instead of being hidden by the broad `.env.*` ignore
  rule.
- Actual deletion of local caches or generated outputs remains a separate
  operator action because local env files, databases, Vercel project metadata,
  virtual environments, and dependencies must not be removed accidentally.

## 2026-04-20 Progress Record

### Receiving desktop empty state now follows the same page-discipline rules as mobile

- A real production desktop walkthrough of `Dashboard -> Receiving -> Receiving Work` showed that the mobile cleanup had worked, but the desktop empty state still felt too much like an operations board:
  - the large dark receiving hero still implied active work
  - the right rail still showed full `Work queue` and `Shift handoff` sections with zero-value cards
  - `Open import center` was duplicated across the page
- The desktop receiving surface was tightened so the no-work state now behaves more like a quiet action board:
  - the dark hero becomes a calm `Receiving is clear right now` panel
  - support tiles are removed when there is no active receiving work
  - the right rail collapses into a single `Queue is clear right now` card
  - duplicate import actions and repeated zero-value queue counts were removed
- The default `All Orders` empty state was also reduced:
  - lifecycle and package filters no longer open by default when there is no active inbound work
  - the page now shows a light `Order history` entry instead, with explicit actions to browse all orders or reveal archived history only when needed
- A second production walkthrough confirmed the updated desktop empty state now keeps one primary CTA, one quiet hero, and one light queue card instead of multiple explanation blocks.

## 2026-04-19 Progress Record

### Receiving queues now surface supervisor-review package work

- The receiving workbench now highlights a `Supervisor review` signal instead of leaving higher-touch package exceptions buried inside generic package filters.
- The signal is triggered when an inbound order has dock-opened package activity and still needs one of:
  - open receiving work
  - internal label printing
  - downstream putaway
  - or mixed pre-booked and dock-opened package origins
- This rollup is now visible across:
  - `/orders/inbound`
  - receiving filter chips
  - the right-rail work queue
  - inbound detail package summary
  - inbound history summary
- The result is a more explicit supervisor-facing package queue without splitting the product into a second management surface.
- Frontend for this slice was deployed to production successfully, but the backend verification is currently blocked by deployment infrastructure:
  - GitHub Actions workflow `render-backend-deploy.yml` ran on push and exited successfully
  - the job log shows `RENDER_DEPLOY_HOOK_URL` is not configured
  - because of that, no backend deploy was actually triggered from GitHub
  - production `/health` stayed on backend build `5b49c63` after the push
- 2026-04-26 update: this older deploy-hook gap is superseded. Render now
  auto-deploys `main`, and `render-backend-deploy.yml` verifies the live
  `/health.build_sha` instead of requiring `RENDER_DEPLOY_HOOK_URL`.

### Receiving queue actions now respect operational priority

- `Supervisor review` and `Recently changed` no longer fall back to generic table ordering when the team clicks in from the right-hand queue rail.
- The receiving workbench now picks the next inbound order for those signals using operational priority:
  - mixed package origin and still-open dock work first for supervisor review
  - latest activity timestamp first for recently changed
- The inbound list also now surfaces inline chips for:
  - `Supervisor review`
  - `Changed recently`
  so the queue state is easier to scan before opening the detail or live receiving view.

## Current Focus

### UX Hardening: Trust, Guidance, and Navigation

Goal: make the product feel easier to understand, easier to move through, and more credible for first-time 3PL users evaluating a trial.

#### Workstream 1: Human-friendly imagery

- Add real visual anchors to the public site and auth surfaces instead of relying mostly on text and icon blocks.
- Introduce warehouse-themed illustrations or product screenshots on the landing page and login page.
- Use visuals to explain the operator journey: receive, control, pick, ship, bill, and client visibility.

#### Workstream 2: Cross-page navigation

- Add a consistent in-app orientation bar with breadcrumbs and obvious return paths.
- Surface a clear “back to dashboard” action from operational pages.
- Add “previous area” and “next area” links so users can move through the warehouse flow without relying only on the left sidebar.

#### Workstream 3: Guided first-run experience

- Keep the dashboard checklist tied to real setup progress.
- Extend guidance beyond headings so users know what to do after finishing a task on each page.
- Tighten empty states and action hints around warehouse setup, first inbound, first inventory action, and first outbound action.

#### Workstream 4: Comparative product polish

- Review public open-source WMS products for presentation patterns, navigation ideas, and feature storytelling.
- Borrow what works best for trust-building:
  - stronger screenshots and feature proof
  - clearer warehouse workflow framing
  - obvious demo / live-product affordances

## Immediate Execution

1. Add image-led sections to the landing page and login page.
2. Add global breadcrumbs and cross-page movement cues inside the app shell.
3. Re-test the product from the trial-user perspective after the navigation update.
4. Continue with richer screenshots and workflow-specific visual proof in the next pass.

## Next Focus

### BYO Model Agent Console

Goal: let customers use an in-product AI operations console while keeping model choice, jurisdiction, and data handling under their control.

#### Workstream 1: Customer-supplied model providers

- Support bring-your-own-model configuration instead of binding the product to one default LLM vendor.
- Let each tenant choose an approved provider such as Azure OpenAI, AWS Bedrock, Google Vertex AI, DeepSeek, or a private model endpoint.
- Keep model routing and credentials tenant-scoped.

#### Workstream 2: Controlled WMS tool layer

- Expose a whitelist of business-safe tools instead of letting the model write directly to the database.
- Route actions through existing authenticated APIs such as inbound import, inventory lookup, client creation, and outbound order management.
- Require explicit user confirmation for high-risk actions such as billing changes, bulk writes, and destructive updates.

#### Workstream 3: Governance, audit, and compliance

- Record who invoked the agent, which model provider handled the request, what tools were called, and what changes were proposed or applied.
- Allow customers to set their own retention, logging, and approval policy according to internal legal or procurement rules.
- Keep region and provider choice visible so regulated customers can avoid unapproved cross-border model use.

#### Workstream 4: Practical first release scope

- Start with a browser-based Agent Console inside the authenticated product instead of a standalone external CLI.
- Focus the first release on high-value operational tasks:
  - inbound CSV mapping and import
  - inventory search and explanation
  - client and SKU setup help
  - outbound order intake guidance
  - migration field-mapping assistance

## Agent Console Immediate Execution

1. Write the BYO model and tool-governance specification.
2. Define the first approved tool whitelist and confirmation rules.
3. Add admin-facing provider settings for tenant-scoped model configuration.
4. Build the first in-app Agent Console around inbound import, migration mapping, and inventory lookup.

## 2026-04-10 Progress Record

### What has been hardened so far

- Guidance and onboarding were expanded across login, dashboard, setup, receiving, putaway, inventory, and picking so the product behaves more like an operator workflow and less like a static demo.
- Multi-language support was pushed through public pages and in-app operations in Traditional Chinese, English, Spanish, Hungarian, and German, including navigation, dashboard activity, inventory activity, and key warehouse flows.
- Receiving and putaway were connected into a clearer closed loop:
  - receive into staging
  - create or recover putaway tasks
  - plan locations visually
  - confirm formal putaway
- Inventory was reshaped from a flat table into a control surface with view switching, graphic location reading, cycle count, adjustment, and recent activity.
- Sidebar navigation was grouped into operational sections so the app feels less like an unstructured menu dump.

### Working lessons we should keep applying

- Every operator-facing sentence should come from i18n keys. Hardcoded English always resurfaces during real walkthroughs.
- Shared task queues must always be filtered by business intent. A picking page must not accidentally read putaway or cycle-count work just because everything is `pending`.
- Buttons need a visible downstream step. If the user cannot tell what happens next, the flow is not done yet.
- Warehouse pages should prefer visual mental models over database mental models:
  - aisle
  - rack
  - level
  - slot
  instead of raw IDs wherever possible.
- Closed-loop design matters more than isolated features. Every operational action should end in a clear new state, visible follow-up, or confirmation path.
- Production testing with the real tenant account catches issues that local mock data misses, especially for i18n, role visibility, and workflow state transitions.

### Picking-specific audit note

- Picking should only fetch `task_type=pick` tasks at both the queue view and the execution flow.
- The picking flow still needs a later enhancement to validate scanned location/SKU values against expected barcodes instead of accepting any scan event.
- Empty states should explain whether the missing work is:
  - not released yet
  - already completed
  - blocked by missing outbound allocation

## 2026-04-11 Progress Record

### Delivery progress

- Import Center was expanded into a unified intake surface for three document families:
  - inbound orders
  - outbound orders
  - inventory records
- Each document family now supports both file import and single-record entry so users are not blocked when a customer does not have a CSV ready.
- The public/auth domain strategy was hardened so canonical app traffic now lands on `app.maxsmartwms.online`, while:
  - `maxsmartwms.online`
  - `www.maxsmartwms.online`
  permanently redirect to the app domain and preserve paths such as `/login`.
- A self-service password reset flow was added across backend and frontend:
  - forgot password request
  - reset token validation
  - reset password submission
  - login-page recovery entry point

### Production validation completed

- Production API and frontend health were re-checked and are healthy:
  - backend health endpoint now returns deployment metadata:
    - `status`
    - `version`
    - `build_sha`
    - `branch`
    - `service_id`
  - frontend is serving successfully from Vercel
- Production warehouse flow was verified end-to-end across pages:
  - receiving
  - putaway
  - inventory
  - picking
  - shipping
- Outbound flow was also verified through live status transitions:
  - pending
  - picking
  - picked
  - packed
  - shipped
- The `wuqxmark@gmail.com` tenant-admin account was manually recovered in production after the email reset flow failed, and login was re-validated successfully.

### Current production risks and follow-up

- Password recovery is functionally shipped, but email delivery is still not production-ready.
- Root cause found in live logs:
  - SMTP delivery fails on Render with `Network is unreachable`
- Current consequence:
  - forgot-password requests return success to avoid email enumeration
  - but recovery emails are not actually delivered
- Temporary workaround:
  - manual admin/database password reset
- Recommended follow-up:
  - replace the current SMTP path with a stable API-based email provider
  - then re-test both verification email and password reset email in production
- 2026-04-26 update: the backend now documents the Resend HTTP API path for
  production email, keeps SMTP as a fallback only, and has regression coverage
  for provider selection.

### User management hierarchy follow-up

- The product role model is now treated as a three-level operating hierarchy:
  - `platform_admin` is the system super admin
  - `tenant_admin` is the company admin
  - `operator` and `client_viewer` are company child users
- Company admins should manage only their child users inside their own tenant.
- Child-user permissions are clamped by role so stale or direct API payloads
  cannot give operators or client viewers user-management authority.
- Super admin bootstrap is documented in
  [`docs/12-user-management-hierarchy.md`](docs/12-user-management-hierarchy.md).

### Sellable shipping follow-up

- Shipping now exposes the existing packing slip PDF generator as a visible
  dispatch action in the selected-order workbench.
- The packing slip endpoint now returns a controlled 404 when an order is not
  in the current tenant scope, and filenames are sanitized from order numbers.
- The PDF uses packed/shipped included quantities and escapes customer/order
  text before handing it to ReportLab.

### Handoff note for next agent upgrade

- Canonical frontend domain:
  - `https://app.maxsmartwms.online`

## 2026-04-15 Progress Record

### Dashboard shifted toward a ShipOut-style operations entry page

- The homepage was reworked away from a control-room / onboarding-heavy dashboard and toward a faster warehouse entry surface.
- The first screen now prioritizes:
  - business entry cards
  - active work queues
  - a compact daily summary
  - recent warehouse movement
- Heavy explanatory blocks were demoted so operators can move into:
  - receiving
  - putaway
  - inventory
  - picking
  - shipping
  - billing
  with less reading friction.

### Implementation approach kept existing backend contracts

- The new dashboard still reuses the current frontend data sources:
  - `kpi-dashboard`
  - `activity-log`
  - `setup-progress-dashboard`
- No backend contract changes were required for the homepage shift.
- New copy was introduced through translation lookups with safe fallback strings so the page can render immediately while locale files catch up later.

### Design and delivery notes

- The redesign was intentionally aligned to the ShipOut-style home-page mental model:
  - start with the next warehouse job
  - use queue counts as handoff signals
  - keep setup/help visible but secondary
- The page was rebuilt and deployed to production after the restructure.
- Resulting dashboard bundle remains compact:
  - `DashboardPage` ~ `17.76 kB` / `4.49 kB gzip`

### Dashboard refinement follow-up

- The first screen was tightened again after the initial homepage shift:
  - setup readiness now sits below the primary business-entry grid instead of competing with it
  - the top explainer copy was shortened so the page reads more like an operator entry page and less like a product narrative
- New dashboard copy was added to:
  - English
  - Traditional Chinese
  - Spanish
  - Hungarian
  - German
- The live homepage now keeps the core ShipOut-style hierarchy intact:
  - business entry first
  - work queue second
  - summary and activity after that
- Canonical backend domain:
  - `https://api.maxsmartwms.online`
- Latest production backend deploy for password reset:
  - commit `baca63d`
  - Render deploy `dep-d7d0961kh4rs739gauig`
- Latest repo commit for canonical domain redirect rules:
  - `8f3c88c Force canonical frontend domain redirects`

### Billing workbench progress

- Billing was split into two clearer surfaces:
  - `billing` for execution
  - `billing-settings` for master-data configuration
- Billing execution now behaves like a period workbench instead of a mixed setup screen:
  - choose client
  - choose period
  - preview charges
  - generate draft invoice
  - track draft / sent / paid / overdue
- Billing settings now carries:
  - rate-card management
  - issuer billing profile
  - bill-to profile
  - tax region
  - payment terms
- Tax handling was hardened for two supported regions:
  - US = Sales Tax
  - EU = VAT
- Invoice totals now round to currency precision, and production validation confirmed:
  - billing preview
  - draft generation
  - sent / paid status updates
  - PDF download
- Billing queue visibility was improved:
  - queue spotlight cards
  - actionable status summary
  - clickable spotlight filtering
  - tighter empty-state handling
- UI polish delivered on billing:
  - removed large empty preview area by turning empty preview help into a compact expandable block
  - prevented status badges from wrapping into vertical-looking Chinese text

### Engineering environment maintenance

- Frontend build currently passes with `npm run build`.

## 2026-04-15 Progress Record

### Receiving, putaway, and AGV-ready status

- Receiving now supports both internal system labels and external warehouse-facing codes:
  - tracking number
  - carton mark
  - customer barcode
- External code scanning still resolves back to the internal `ReceivingLabel` so traceability stays standardized.
- `HandlingUnit` is now part of the live receiving-to-putaway path and is carried forward into pending putaway and AGV task context.
- Putaway now supports split allocations across multiple final destinations while keeping the existing task and inventory transaction model intact.
- Putaway execution guidance now distinguishes:
  - worker
  - AGV
  - hybrid
- Putaway task routing is now easier to work through in production:
  - tasks can be searched by handling unit, inbound order, SKU, source, and external code
  - execution routes can be filtered by worker, AGV, and hybrid
  - oldest pending tasks are prioritized consistently in both sorting and default focus
  - task and group cards now surface waiting age so operators can clear the oldest work first
- Split putaway now has a true closed loop:
  - the UI can plan multiple destinations
  - the backend persists allocations
  - inventory transactions are written per allocation
  - completion feedback lists each final destination and quantity
- Legacy putaway and AGV payload drift was reduced:
  - stale batch-confirm code paths were removed from the putaway workbench
  - suggestion-copy rendering now comes from one source instead of duplicated helper paths
  - historical putaway tasks without handling units are now backfilled from legacy receiving labels

### Frontend engineering cleanup

- Large frontend bundle pressure was materially reduced:
  - route-level lazy loading was added
  - vendor chunks were split more deliberately
  - non-English locale dictionaries now load on demand
- The main shared bundle dropped from roughly `2.0 MB / 508 KB gzip` earlier in the week to about `204 KB / 56 KB gzip`.
- Locale loading was then smoothed so stored non-English users do not briefly flash back to English while their dictionary loads.
- Putaway and billing workbenches were both trimmed to remove stale local mirrors and dead branches that no longer drive the live UI.
- Unused putaway rack-batch locale copy was pruned after the corresponding batch path was fully removed, keeping translations aligned with the real product surface.
  - hybrid
  and provides route reasons for the recommended execution mode.

### Production deployment observability

- Backend health is now version-aware and returns:
  - `build_sha`
  - `branch`
  - `service_id`
- Canonical production backend health check:
  - `https://api.maxsmartwms.online/health`
- This removes the previous ambiguity around whether Render had actually reached the latest backend commit.
- Production Render deployment was later re-checked directly and confirmed to be healthy:
  - auto deploy is enabled
  - the live service is tracking `main`
  - `/health` can now be used as the source of truth for which backend commit is live
- A legacy data repair was also carried through production:
  - older pending `putaway` tasks that predated `HandlingUnit` rows are now rebuilt from their legacy receiving labels
  - production verification confirmed `AGV pending` missing handling-unit context dropped from `5` tasks to `0`

### Putaway UI progress

- Putaway now supports three live grouping views:
  - by handling unit
  - by inbound order
  - by SKU
- Putaway task search and filtering now support:
  - handling unit code
  - inbound order
  - SKU label
  - source location
  - external warehouse-facing codes
  - execution-mode filtering across worker / AGV / hybrid
- Putaway task ordering now aligns with the operator guide:
  - oldest pending staging work is shown first
  - filtering and grouping still preserve that oldest-first priority
  - bulk selection now also shifts focus to the first currently filtered task, so the active work panel stays aligned with the set the operator just selected
  - switching into bulk/source-group planning now clears any single-task destination and split plan residue, so the board does not inherit a stale final-slot decision from the previous task
- Putaway task cards now expose waiting age:
  - oldest task age per group
  - waiting time per task card
  so operators can see both sequence and urgency without opening the task first
- The task board now surfaces:
  - current handoff
  - AGV eligibility
  - route reason
  - handling unit identity
- Split putaway planning now exposes:
  - primary final storage location
  - additional destinations
  - split summary
  - per-location result feedback after confirmation
- Putaway task focus is now resolved directly from the enriched and filtered task list:
  - the current selection respects search, execution-mode filtering, and oldest-first ordering
  - the default fallback no longer bypasses that logic by reaching back into the raw task payload
- The batch planning flow was also simplified to the one path that operators actually use:
  - place work on the board
  - review the plan
  - confirm putaway
  and the old, no-longer-visible batch confirm branches were removed from both code and locale dictionaries.
- The right-side putaway workspace was also simplified from explanation-heavy guidance into a shorter execution checklist:
  - check the source
  - pick the final slot
  - confirm the move
  with the live source barcode, current target slot, and split summary visible inline.
- Handling units now move through a clearer lifecycle:
  - `expected`
  - `staged`
  - `putaway_pending`
  - `stored`
- Task responses now expose the same handling-unit identity that AGV pending work already sees, including:
  - handling unit code
  - handling unit status
  - package count
  - measured weight
- AGV pending responses now mirror those same handling-unit fields at the top level while still returning the nested handling-unit block, so frontend consumers and future AGV integrations do not need separate translation logic.
- AGV pending responses also expose top-level source and destination barcodes so downstream AGV/WCS consumers can read movement endpoints without unpacking nested location objects first.
- Production verification for the live receiving -> putaway -> AGV-ready flow is now scripted in:
  - `/Volumes/MaxRelocated/WMS/tools/verify_production_putaway_flow.py`
  so the team can re-run a real external-code receive, putaway creation, AGV pending check, and split putaway confirmation against production without rebuilding the sequence by hand.
  - the verifier now accepts `WMS_VERIFY_TIMEOUT` and `WMS_VERIFY_RETRIES`, so transient production latency no longer forces the whole acceptance run to fail at a hard 15-second timeout
  - the verifier now also expects explicit production targets (`WMS_VERIFY_WAREHOUSE_CODE`, `WMS_VERIFY_CLIENT_CODE`, `WMS_VERIFY_SKU_CODE`, `WMS_VERIFY_SOURCE_BARCODE`) unless `WMS_VERIFY_ALLOW_AUTOSELECT=1` is deliberately enabled, so maintenance checks do not mutate whichever live tenant records happen to sort first
- Production verification has already confirmed that the live AGV pending payload returns:
  - `source_barcode`
  - `handling_unit_code`
  - `handling_unit_status`
  alongside the execution guidance fields on the same task.

### Frontend performance note

- Route-level lazy loading was added to reduce the initial application bundle.
- The previous single large entry chunk has been broken into page-level chunks.
- Vendor chunking was added on top of route-level lazy loading so the main shared bundle first dropped from roughly `1.18 MB / 344 KB gzip` to about `925 KB / 261 KB gzip`.
- The next major reduction came from lazy-loading non-English locale dictionaries:
  - the main shared bundle is now about `205 KB / 56.5 KB gzip`
  - `zh-Hant`, `es`, `hu`, and `de` now ship as separate on-demand chunks instead of living in the initial app payload.
- This removes the previous large shared-chunk warning from the main entry path while keeping English available immediately at startup.
- The locale loader now also preloads the active saved language before rendering the app surface, so non-English users do not flash back through English after the dictionary split.
- Billing workbench cleanup also removed the last unused rate-card and billing-profile draft state from `BillingPage`, so invoice-readiness checks now read directly from live tenant and client billing profiles instead of stale page-local mirrors.
- Billing workbench cleanup continued with one more pass:
  - stale table config left over from the pre-workbench layout was removed
  - the page is now more clearly limited to period execution, invoice follow-up, and readiness review
- Billing workbench state was then tightened again so execution state resets now come from one consistent source:
  - newly created invoices are surfaced immediately in the summary panel before the background invoice list refresh lands
  - changing the client or period now clears the current billing workspace in one effect instead of mixing effect-driven resets with duplicate inline reset code
  - if the client list changes underneath the page, the workbench now snaps back to the first valid client instead of holding a stale selection id
  - the latest-invoice summary now consistently reads from one `latestInvoice` source instead of locally falling back to older draft state
  - invoice number suggestion now comes from the shared suggestion effect only, instead of also being re-applied from the billing preview success path
- Receiving flow state was also tightened:
  - switching between inbound orders now clears the prior scan session, received-line list, and staging input
  - the same reset path now also clears stale mutation success/error state so a new inbound order does not inherit the previous order's mutation lifecycle
  - returning to the order picker now uses the same shared reset path as the rest of the receiving session
  - label external-code copy and initial-step derivation now each come from a single helper path instead of duplicated inline logic
  - the prepare-step “back to inbound list” action now uses that same shared return path instead of only flipping the step flag
- Putaway cleanup also continued with one more pass:
  - batch suggestion entries now use the same enriched `rank` + `reasonLabel` shape as single-task suggestions
  - this keeps single-task and batch planning reason copy aligned as suggestion logic evolves
  - batch confirm recovery now tracks failures by `task.id` instead of inbound order number, so partial failures cannot accidentally reselect the wrong task when multiple putaway tasks share one inbound order
  - rack/aisle/zone picker “change scope” actions now reuse one shared reset helper instead of repeating slightly different inline reset chains
  - changing the active putaway task now clears the prior destination and split plan through one shared helper, so the next task does not inherit a stale final-slot decision
  - changing picker scope or invalidating a picker branch now also clears the stale split plan through that same helper, so slot navigation cannot carry an old multi-destination plan into a new destination path
  - batch-board task focus and post-confirm cleanup now use that same helper too, so reselecting a task from the planning board cannot keep a stale single-task destination plan alive
  - single-task and batch-board focus clicks now also share one task-focus helper, so task reselection cannot slowly drift into separate selection rules across the workbench
- Backend test environment was hardened for local async SQLite runs by adding `aiosqlite` to dev dependencies in `backend/pyproject.toml`.
- Backend regression suite has continued to grow and now passes locally with:
  - `53 passed`
- One real backend regression was fixed during maintenance:
  - CSV inventory import now keys inventory upserts by lot number as well as tenant / warehouse / location / SKU, preventing different lots from overwriting one another.

### 2026-04-15 final maintenance acceptance

- A fresh production end-to-end verification run completed successfully against:
  - warehouse `BUDDEMO`
  - client `DANUBE`
  - SKU `DAN-FLOUR-020`
- The live flow now reconfirmed on production is:
  - external tracking -> internal receiving label
  - receive -> complete
  - `HandlingUnit` creation
  - hybrid putaway task generation
  - AGV pending payload with handling-unit context
  - split putaway confirmation with two destination allocations
- Latest successful scripted production acceptance example:
  - inbound order `INB-E2E-37972662`
  - tracking `TRK-E2E-37972662`
  - handling unit `RCV-INB-E2E-37972662-001`
  - putaway task `60f42340-8a5d-4990-ac04-17bfdcca78a3`
  - allocations:
    - `A-01-01-01-01` -> `3`
    - `A-01-01-01-02` -> `2`

### 2026-04-15 maintenance sweep closeout

- A final maintenance sweep found no additional low-risk UI state drift worth changing in:
  - `PutawayPage`
  - `ReceivingFlow`
  - `BillingPage`
- Local verification remained clean:
  - backend regressions: `53 passed`
  - focused workbench regressions: `14 passed, 39 deselected`
  - frontend production build: passed
- Production backend health remained stable during the sweep:
  - `build_sha = 68caf8c352b745a9b0c23c8039a4549867bcfe79`
- At this point the maintenance work moved out of “active cleanup” and into “steady-state verification”:
  - the main operational path is stable
  - remaining work is expected to be net-new feature work or future bug reports, not more structural cleanup on this pass
- One more operator-safety fix was applied after review:
  - `PutawayPage` now only derives `activeTask` from the currently visible filtered task set, so a hidden task cannot remain active in the workbench after the operator narrows the task search to zero results
- Another real backend correctness issue was fixed during review:
  - rate-card listing is now ordered by latest effective date first, so billing screens no longer risk treating an older version as the current rate card.

### Review notes to carry forward

- Billing execution now reads directly from live tenant/client billing profiles, so future billing-settings work should continue to happen in `BillingSettingsPage` rather than reintroducing page-local draft mirrors into `BillingPage`.
- Local Python test execution should prefer `uv run --extra dev pytest -q` so tests do not depend on globally installed tooling.
- When reviewing billing behavior, verify both frontend filtering and backend ordering together. The execution UI assumes the first rate card is the active one, so backend order must stay deterministic.

### 2026-04-15 dashboard and receiving UI shift toward ShipOut entry style

- The dashboard homepage was reworked from a control-room / onboarding-heavy layout into a business-entry homepage:
  - first screen now prioritizes `Receiving`, `Putaway`, `Inventory`, `Picking`, `Shipping`, and `Billing`
  - setup/readiness content was pushed lower so the page leads with work entry, not explanation
- The receiving homepage followed the same direction without changing the underlying receiving flow:
  - `ReceivingPage` now leads with a lighter operations-entry surface instead of role cards, large process explanations, and warehouse-scene storytelling
  - the first screen now emphasizes:
    - inbound waiting
    - receiving now
    - quick-start receiving work
    - a compact work queue
  - support links for import, inventory review, and putaway handoff remain available but no longer dominate the page
- The underlying `ReceivingFlow` state machine and label-driven / external-code-driven backend path were intentionally left unchanged:
  - the change is entry-page mental model only
  - scan, discrepancy, handling-unit, and putaway behavior remain on the existing stable path
- A follow-up pass then reduced friction inside `ReceivingFlow` itself without changing backend contracts:
  - selecting an expected inbound order now opens live receiving immediately instead of routing operators through a heavier intermediate confirmation page
  - the select screen now behaves more like a direct work queue:
    - operators can jump straight to the next active or expected order
    - expected orders open into live receiving automatically
  - the old `prepare` step remains as a safe fallback state, but it is no longer the main path for day-to-day dock work
- Another follow-up pass moved receiving exceptions closer to a ShipOut-style recovery surface:
  - scan and receipt failures now show lightweight recovery panels instead of only raw red error text
  - common dock issues now point operators toward concrete next actions such as:
    - back to work queue
    - clear the current scan
    - review already received lines
    - focus the staging selector
    - try another scan
  - this keeps the backend contract unchanged while making the dock workflow feel less like a blocked form and more like an operator recovery flow
- A further pass also rebalanced the live receiving screen itself toward scan-first work:
  - the scan workspace now leads with the current inbound context and scanner before the staging selector
  - staging remains required for confirming good units, but it is now framed as the next control after scanning instead of the first thing the operator must read
  - this keeps the current validation rules intact while making the page feel more like “scan what is here now” and less like a form-first workflow
- Another scan-first refinement then hid the staging selector until an actual label or carton match exists:
  - before the first successful scan, the page now keeps staging as a compact status hint instead of a full selector block
  - once a receiving target has been identified, the staging selector appears in context right before confirmation
  - this reduces empty-screen form weight and keeps the operator focused on identifying physical freight first
- The scan workspace also gained a stronger task-queue feel:
  - operators can now see at a glance:
    - labels still open
    - labels already received
    - good units still pending
    - the most recent completed receipt
  - this turns the live receiving screen into more of a “current dock task board” instead of only a scanner plus confirmation form
- The confirm-receipt surface is now delayed until a real dock object has been identified:
  - before the first successful scan, operators see only a compact prompt to scan a receiving code
  - the quantity form now appears only after a label / carton / tracking match exists
  - this keeps the screen focused on finding the freight first, which is closer to ShipOut’s field rhythm
- A final receiving-flow polish pass also reordered the scan workspace around the live dock object:
  - after a successful scan, the matched label / carton result is now shown before staging and quantity confirmation
  - staging and confirm controls now follow the identified object instead of preceding it
  - the reference label list stays available, but it sits behind the active object so the screen feels more like “work this freight now” than “browse the system labels first”
- The staging step has also been pulled into the receipt confirmation surface itself:
  - after a match exists, operators now choose the temporary dock / staging slot inside the same confirmation card where they record good and damaged units
  - this keeps the rhythm closer to the dock floor: identify the freight, pick where it is landing, then confirm the receipt in one compact work area
- The remaining system-label list has also been demoted into a true reference surface:
  - once an active label / carton match exists, the list now frames itself as reference labels instead of the primary work object
  - this keeps the scanned freight in the foreground while still giving operators a quick place to reprint labels or jump to the next box when needed
- The receiving landing page has also been rebalanced into a single workbench:
  - the left side now combines the dark receiving entry and compact support actions
  - the right side now carries the work queue and dock-support links as one companion rail
  - the standalone support row was removed so the tabs and receiving order work can move closer to the top of the page
- Internal receiving codes now have a tenant-level rule surface instead of a hard-coded format:
  - new tenant endpoints allow admins to view and update receiving code rules
  - supported rule knobs now include:
    - prefix
    - separator
    - include inbound order number
    - sequence padding
    - uppercase formatting
  - `ReceivingService` now reads those tenant rules when generating new receiving labels, so internal warehouse-owned codes no longer depend on a single hard-coded pattern
  - a dedicated frontend settings page now exposes the rule set with a live sample preview, so admins can tune internal label format without patching code or calling the API directly

## 2026-04-17 Progress Record

### Receiving now treats external codes as pre-confirm evidence and internal codes as post-confirm warehouse IDs

- The receiving flow was reworked so operators can collect outside freight identifiers first, then commit the warehouse-owned internal code only when receipt is confirmed.
- External code capture now supports:
  - live scan
  - photo decode
  - manual entry
- Multiple observed external codes can be attached to the same inbound line before confirmation, and operators can:
  - add more codes
  - edit captured codes
  - delete captured codes
- Confirming the receipt now formalizes that captured-code set onto the internal warehouse object instead of assuming the internal label was already the primary dock object.

### Internal code creation moved from inbound creation time to receipt confirmation time

- `InboundOrderLine` now stores the external freight references and a stable `line_number` so the system can resolve receipt targets before any internal receiving label exists.
- `ReceivingService.create_inbound_order()` no longer pre-creates `ReceivingLabel` and `HandlingUnit` records for every expected line.
- `ReceivingService.receive_label()` now creates the internal receipt objects on demand at confirmation time:
  - `ReceivingLabel`
  - `HandlingUnit`
- This change brings the data model closer to the intended warehouse rule:
  - external references first
  - warehouse-owned internal ID after physical confirmation

### Printing and operator guidance were aligned to the new rule

- The receiving UI no longer presents internal labels as the primary dock object before confirmation.
- The prepare / live receiving surfaces now explain that warehouse labels are issued after confirmation.
- Reprint and batch-print controls now focus only on confirmed internal labels.
- This keeps the print path aligned with the new semantic rule:
  - confirm receipt
  - generate internal code
  - print warehouse label

### Validation status

- Backend regression coverage was updated to match the new confirmation-time internal-code model.
- Full backend regression result:
  - `56 passed`
- Production backend deployment was then advanced to the startup-migration fix:
  - commit `7d14aa3`
- Live backend health metadata now reports:
  - `build_sha = 7d14aa394564d73468e0c1f7f1abdf45691157b8`
  - `branch = main`
  - `service_id = srv-d7ako4ggjchc73eh8g70`

## 2026-04-18 Live Receiving Verification

### Production receiving contract was re-verified against the live API

- A fresh live verification pass was run against production on `2026-04-18` using the current tenant data and warehouse staging slots.
- The live API contract that actually accepted production traffic was confirmed as:
  - inbound creation line payload uses `quantity`
  - scan endpoint expects `label_code`
  - receipt confirmation expects `quantity_received`
  - receipt confirmation requires `staging_location_id` whenever good units are being received
- This means the current operator flow is correct, but any future scripts, migration helpers, or one-off verification commands must follow the production field names instead of older shorthand assumptions such as:
  - `expected_qty`
  - `barcode`
  - `good_qty`

### Real production data checks completed successfully

- Two fresh production receiving checks were completed:
  - single external-code receipt
  - multi-code add/edit/delete before confirmation
- Both flows confirmed the same end-to-end rule:
  - scan or collect external codes first
  - confirm receipt with a staging location
  - generate the internal warehouse label after confirmation
  - mark the resulting internal label printed

### Live results

- Single-code test:
  - order: `INB-LIVE-776459140S`
  - matched by: `external_tracking_number`
  - generated internal label: `RCV-INB-LIVE-776459140S-001`
  - confirmed captured codes: `1`
  - print update count: `1`
- Multi-code test:
  - order: `INB-LIVE-776459143M`
  - matched by: `external_tracking_number`
  - initial observed codes after first scan: `1`
  - observed codes before confirmation after add/edit/delete: `2`
  - confirmed captured codes after receipt: `2`
  - generated internal label: `RCV-INB-LIVE-776459143M-001`
  - print update count: `1`
- Both tests used the live staging location:
  - `QA911225-B25-01-01-01`

### Production verification completed

- A live production verification pass was completed with the tenant admin account after `7d14aa3` went live.
- Verified flow:
  - create inbound order with two external-code-driven lines
  - start receiving
  - scan external tracking code
  - capture additional observed external codes
  - edit one captured code
  - delete another captured code before confirmation
  - confirm each receipt
  - generate internal warehouse labels only after confirmation
  - batch mark both confirmed internal labels as printed
- Verified production result:
  - order number: `INB-CODES-76456327`
  - pre-confirm observed codes preserved:
    - `TRK-CODES-76456327-A`
    - `ALT-76456327-A-EDIT`
  - both observed codes were marked confirmed after receipt
  - confirmed internal labels generated:
    - `RCV-INB-CODES-76456327-001`
    - `RCV-INB-CODES-76456327-002`
  - batch print update count: `2`
  - resulting print counts:
    - `RCV-INB-CODES-76456327-001` -> `1`
    - `RCV-INB-CODES-76456327-002` -> `1`

### Immediate next step

- Shift from rule implementation to UX refinement:
  - make the “external codes first / internal code after confirm” state change even more obvious in the receiving UI
  - tighten the confirmed-label print feedback so operators can see at a glance which internal labels are still not printed

### Receiving label template settings verified in production

- Tenant-level receiving label template settings are now live in production on backend commit `c924d9a`.
- Verified production API behavior:
  - `GET /api/v1/tenants/current/receiving-label-template` returns the current field list and allowed field catalog
  - `PATCH /api/v1/tenants/current/receiving-label-template` persists a new field selection
  - a follow-up `GET` returns the updated selection
- Verified production label-summary payload for confirmed internal labels now includes the printable metadata required by the dynamic template:
  - `sku_code`
  - `sku_name`
  - `reference_number`
  - `package_count`
  - `pallet_count`
  - `rent_free_days`
  - `measured_weight_kg`
  - `measured_length_cm`
  - `measured_width_cm`
  - `measured_height_cm`
  - `receiving_note`
  - plus external references such as `tracking_number`
- After verification, the production tenant template was restored to the default field set:
  - `order_number`
  - `sku_code`
  - `expected_qty`
  - `tracking_number`

### Full live verification passed for template-driven internal label printing

- A second live production verification pass was completed against backend commit `c924d9a` using the current tenant's active client, warehouse, and SKU records.
- Verified flow:
  - update the tenant receiving-label template field set
  - create a new inbound order with two external-code-driven lines
  - start receiving
  - scan the first tracking code
  - add two manual visible codes
  - edit one code
  - delete the other code before confirmation
  - confirm both receipts with packaging, pallet, measurement, and note details
  - fetch confirmed internal label summaries
  - batch mark both internal labels as printed
- Verified production result:
  - order number: `INB-TMPL-76458330`
  - template field set under test:
    - `order_number`
    - `sku_code`
    - `package_count`
    - `pallet_count`
    - `tracking_number`
    - `receiving_note`
  - first confirmed receipt preserved `2` captured external codes at confirmation time
  - confirmed internal labels generated:
    - `RCV-INB-TMPL-76458330-001`
    - `RCV-INB-TMPL-76458330-002`
  - confirmed label summaries carried the configured print-template data, including:
    - `package_count`
    - `pallet_count`
    - `tracking_number`
    - `receiving_note`
    - plus supporting SKU and measurement metadata
  - batch print update count: `2`
  - resulting print counts:
    - `RCV-INB-TMPL-76458330-001` -> `1`
    - `RCV-INB-TMPL-76458330-002` -> `1`

### Inbound lifecycle controls now favor archive and void over unsafe deletion

- Receiving order management now distinguishes between three different cleanup paths:
  - `Delete permanently` only for clean inbound orders that never entered receiving work
  - `Void order` for inbound work that should stop while still preserving an audit trail
  - `Archive order` for hiding inactive inbound orders from the default work queue without destroying history
- Backend lifecycle rules were added to enforce that policy:
  - delete is blocked once any observed codes, confirmed receipt quantities, internal labels, handling units, inventory transactions, or downstream tasks exist
  - void is blocked once confirmed receipt artifacts exist
  - archive is blocked while an order is actively in the `receiving` state
- The inbound-order API now returns lifecycle flags per row so the frontend can present only safe actions:
  - `archived`
  - `can_delete`
  - `can_void`
  - `can_archive`
- The receiving homepage now uses those flags to drive contextual actions:
  - archived orders can be restored
  - clean unstarted orders can be deleted
  - unconfirmed work can be voided
  - archived orders stay hidden unless the operator explicitly turns on `Show archived`
- Focused regressions now cover the new rules:
  - clean unstarted delete succeeds
  - void succeeds before confirmed receipt and is blocked after confirmation
  - archived inbound orders are hidden from the default list and appear only when `include_archived=true`

### Live production verification passed for inbound lifecycle controls

- A live production pass was completed against backend commit `743a601` using the tenant-admin account and active production tenant data.
- Verified lifecycle actions:
  - `Delete permanently` succeeds for a clean inbound order that never entered receiving:
    - `INB-DEL-94552168`
  - `Archive order` hides an inbound order from the default queue while keeping it visible when archived orders are explicitly requested:
    - `INB-ARC-94552168`
    - hidden from default list: `true`
    - visible with archived toggle: `true`
  - `Restore order` returns the archived inbound order back to the default queue:
    - restored visible by default: `true`
  - `Void order` succeeds after live receiving has started and a freight code has been scanned, as long as no confirmed receipt artifacts exist:
    - `INB-VOID-94552168`
    - resulting status: `cancelled`
    - `can_delete = false`
    - `can_void = false`
    - `can_archive = true`
- A reusable production verification script now exists at:
  - [tools/verify_production_inbound_lifecycle.py](/Volumes/MaxRelocated/WMS/tools/verify_production_inbound_lifecycle.py)

### Receiving order selection now exposes a clearer lifecycle and audit surface

- The receiving order selection panel now pulls a fuller inbound detail view instead of only showing top-level status and actions.
- The inbound detail API was expanded to return:
  - archived / voided lifecycle metadata
  - observed freight-code history
  - confirmed internal labels and print counts
  - handling-unit receipt detail per line
- The frontend now uses that detail to show operators:
  - what was scanned
  - what has already been confirmed
  - which internal labels are ready to print or already printed
- The order detail endpoint was also tightened to stay tenant-scoped unless the caller is a platform admin.

### Live production verification also passed for inbound detail lifecycle visibility

- After backend commit `5b2f41f` went live, the production lifecycle verification was rerun against the expanded inbound-detail endpoint.
- Verified detail behavior:
  - archived inbound detail reports `archived = true` while the order is hidden from the default queue
  - restored inbound detail reports `archived = false` after the order returns to active circulation
  - voided inbound detail reports `voided = true`
  - voided inbound detail keeps observed-code history visible:
    - `total_observed_codes = 1`
  - voided inbound detail correctly shows that no internal labels were issued:
    - `total_internal_labels = 0`
- Verified production sample orders:
  - delete path: `INB-DEL-88786331`
  - archive / restore path: `INB-ARC-88786331`
  - void path: `INB-VOID-88786331`

### Receiving now supports a dedicated inbound-detail route and lifecycle queue counts

- The receiving workbench now keeps its queue-first rhythm on [/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx), but selected orders can open a deeper audit view through a dedicated route:
  - `/receiving/orders/:orderId`
- The heavier inbound-history UI was extracted into a shared component:
  - [frontend/src/modules/receiving/InboundOrderHistoryPanel.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderHistoryPanel.tsx)
- That shared history surface is now reused in:
  - the inline receiving selection panel
  - the dedicated inbound detail page at [frontend/src/modules/receiving/InboundOrderDetailPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderDetailPage.tsx)
- The dedicated detail page now gives operators a stable place to review:
  - lifecycle state
  - archive / void / delete eligibility
  - captured freight codes
  - confirmed internal labels and print counts
  - line-level receipt evidence
- The receiving lifecycle filter chips were also tightened so they display live counts for:
  - `Active work`
  - `All orders`
  - `Archived`
  - `Voided`
  - `Completed`
- Layout routing was updated so `/receiving/orders/:orderId` still gets the normal operator breadcrumb/header treatment inside [frontend/src/shared/components/Layout.tsx](/Volumes/MaxRelocated/WMS/frontend/src/shared/components/Layout.tsx).

### Inbound detail is now evolving from an audit panel into a lifecycle and downstream-visibility surface

- The dedicated inbound detail route now layers three views of the same order:
  - lifecycle timeline
  - historical receipt evidence
  - downstream handling-unit / putaway visibility
- The detail API at [backend/app/api/v1/endpoints/order_details.py](/Volumes/MaxRelocated/WMS/backend/app/api/v1/endpoints/order_details.py) now returns:
  - `timeline[]` events built from order creation, observed freight-code capture, internal-label issue/print, putaway-task creation/start/completion, and archive / void lifecycle events
  - `downstream_summary` with lightweight counts for:
    - total putaway tasks
    - open putaway work
    - handling units still `putaway_pending`
    - handling units already `stored`
  - line-level `downstream_tasks[]` so the UI can show where each handling unit is headed after dock confirmation
  - `staging_location_barcode` so the frontend does not need a second lookup to explain dock-to-putaway flow
- The frontend detail route now uses that contract to show:
  - a readable timeline of what happened and in what order
  - a downstream summary band for putaway readiness
  - line-level handling units beside the downstream putaway tasks linked to them
- The detail page now also behaves more like a working surface instead of a static audit panel:
  - lifecycle timeline events can be filtered by `Dock intake`, `Internal labels`, `Downstream work`, or `Lifecycle status`
  - downstream visibility now offers a direct `Open putaway board` action whenever putaway work exists for the order
  - that downstream action now carries the current inbound order into the putaway workbench, which auto-focuses the matching tasks instead of dropping operators into an unfiltered queue
  - line-level downstream cards now also open the putaway board in a tighter context:
    - handling-unit drill-downs focus the matching unit
    - downstream-task drill-downs focus the specific open task when it is still actionable
  - the putaway board now closes the loop with a direct `Back to inbound detail` action whenever the focus came from a lifecycle detail page
- The current goal is still intentionally light:
  - expose downstream visibility from the existing inbound detail contract
  - do not create a second audit model or a heavyweight analytics/timeline subsystem

### Live production verification passed for inbound detail timeline and downstream visibility

- A real production inbound order was run through receiving and inspected through the expanded detail endpoint:
  - order: `INB-DTL-00863427`
  - freight tracking: `TRK-DTL-00863427`
- After the timeline semantics fix went live, a second production verification confirmed the corrected event order:
  - order: `INB-DTL2-76497754`
  - freight tracking: `TRK-DTL2-76497754`
- Verified timeline events now describe the dock flow in a more human-readable order:
  - `order_created`
  - `receiving_started`
  - `external_code_captured`
  - `internal_label_issued`
  - `receiving_completed`
  - `putaway_task_created`
- Verified downstream summary values in production:
  - `putaway_tasks_total = 1`
  - `putaway_tasks_pending = 1`
  - `handling_units_putaway_pending = 1`
  - `handling_units_in_final_storage = 0`
- Verified line-level downstream visibility:
  - `staging_location_barcode = DOCK-01`
  - handling unit status = `putaway_pending`
  - downstream task status = `pending`
  - downstream task source = `DOCK-01`
- Timeline semantics were also tightened so:
  - `order.received_date` now surfaces as `receiving_started`
  - order-level `receiving_completed` is derived from the latest confirmed internal label timestamp instead of the start-receiving timestamp

### Receiving is now starting to separate planning lines from package/MU execution

- The backend receiving contract now has a first explicit execution layer under `InboundOrderLine`:
  - `InboundOrder`
  - `InboundOrderLine`
  - `InboundPackage`
  - `ReceivingLabel / HandlingUnit`
- The goal of this slice is to move the floor workflow closer to ShipOut without throwing away the current line-based planning model:
  - `InboundOrderLine` continues to represent the SKU/planning row
  - `InboundPackage` now represents the package / carton / MU being physically received
  - confirmed packages still issue the warehouse internal label and handling unit used by putaway
- New backend capabilities now exist in [backend/app/services/receiving_service.py](/Volumes/MaxRelocated/WMS/backend/app/services/receiving_service.py) and [backend/app/api/v1/endpoints/receiving.py](/Volumes/MaxRelocated/WMS/backend/app/api/v1/endpoints/receiving.py):
  - list packages for an inbound order
  - create a package under a specific inbound line
  - confirm receipt at package level
  - keep captured observed codes scoped to the package instead of only the line
  - generate one internal label / handling unit / putaway task per confirmed package
- Startup schema backfills in [backend/app/main.py](/Volumes/MaxRelocated/WMS/backend/app/main.py) now cover:
  - `receiving_labels.inbound_package_id`
  - `handling_units.inbound_package_id`
  - `receiving_observed_codes.inbound_package_id`
- `repair_putaway_tasks()` now rebuilds downstream work per handling unit instead of assuming one line maps to one putaway task.
- Focused regression coverage was added in [backend/tests/test_regressions.py](/Volumes/MaxRelocated/WMS/backend/tests/test_regressions.py) and the full suite passed:
  - `62 passed`
- The receiving UI in [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx) now starts surfacing that package layer:
  - the live receiving step shows a package queue
  - scan matches now expose package number / package status
  - confirmation now follows the package endpoint when package context exists
  - after a package is confirmed, the flow tries to advance to the next open package instead of only thinking in labels
  - confirmed internal labels now show which package they came from
- Inbound detail and downstream visibility now also understand the package layer:
  - [backend/app/api/v1/endpoints/order_details.py](/Volumes/MaxRelocated/WMS/backend/app/api/v1/endpoints/order_details.py) now returns `lines[].packages[]`
  - each package payload carries:
    - package status
    - staging barcode
    - observed external codes
    - internal labels
    - handling units
    - downstream putaway tasks
  - [frontend/src/modules/receiving/InboundOrderHistoryPanel.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderHistoryPanel.tsx) now renders package-level receipt evidence instead of flattening everything back to the line
  - [frontend/src/modules/receiving/InboundOrderDownstreamPanel.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderDownstreamPanel.tsx) now drills into package-level handling units and downstream tasks, with direct open actions into the putaway board
- Package status now moves with downstream work instead of stopping at dock staging:
  - `receive_label` marks a package `staged` once good units reach a dock location
  - `complete_receiving` now promotes confirmed packages to `putaway_pending` alongside their handling units
  - `confirm_putaway` now promotes the same packages to `stored` alongside their handling units, so inbound detail does not drift after downstream work completes
- Focused regression coverage now confirms both the package fan-out and the detail payload shape:
  - one line can produce multiple packages, multiple internal labels, and multiple putaway tasks
  - inbound detail returns those packages with nested labels, handling units, and downstream tasks
- Live production verification also passed for the first package-centric floor flow:
  - order `INB-PKG-84485987`
  - one inbound line was split into two packages
  - both packages were scanned and confirmed independently
  - two internal labels were issued:
    - `RCV-INB-PKG-84485987-001`
    - `RCV-INB-PKG-84485987-002`
  - `complete_receiving` created two putaway tasks
  - the two package-derived tasks were then confirmed to different destinations:
    - `A-01-01-01-01`
    - `A-01-01-01-02`
- This is still not the final ShipOut-style package workbench:
  - lifecycle filters and print surfaces are still more label-centric than package-centric
  - the next steps are to push package context further into print, queue management, and broader inbound operations

### Live production verification also passed for package-centric detail and downstream completion

- After backend commit `282f161` went live, the production package/detail flow was rerun end to end with:
  - [tools/verify_production_package_detail_flow.py](/Volumes/MaxRelocated/WMS/tools/verify_production_package_detail_flow.py)
- The latest production verification order was:
  - `INB-PKGDTL-16464412`
- Verified package-centric receiving behavior:
  - one inbound line was split into two packages
  - package `1` and package `2` were both scanned by their external tracking numbers
  - the two packages issued distinct internal labels:
    - `RCV-INB-PKGDTL-16464412-001`
    - `RCV-INB-PKGDTL-16464412-002`
- Verified pending downstream detail state immediately after `complete_receiving`:
  - both packages were `putaway_pending`
  - each package carried exactly one downstream putaway task in inbound detail
  - order-level downstream summary showed:
    - `putaway_tasks_total = 2`
    - `putaway_tasks_pending = 2`
    - `handling_units_putaway_pending = 2`
- Verified downstream completion state after confirming putaway to separate destinations:
  - package `1` was stored at `A-01-01-01-01`
  - package `2` was stored at `A-01-01-01-02`
  - both packages now report `stored`
  - both nested handling units report `stored`
  - both nested downstream tasks report `completed`
  - order-level downstream summary now shows:
    - `putaway_tasks_completed = 2`
    - `handling_units_in_final_storage = 2`

### Package-centric receiving Phase 1 is now complete in production

- Backend commit `66c6835` introduced the first explicit package-centric workbench actions into [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx), while keeping the underlying line-planning model intact.
- The live receiving workbench now supports the core floor actions directly at package level:
  - `Add package`
  - `Split another package`
  - `Edit package`
  - `Remove`
  - direct `Open package` even when no external code exists yet
- Package-level observed codes no longer require an existing label code:
  - captured codes can now be added and listed by `package_id`
  - this lets no-code freight create a package first, capture an external code later, then continue the same receipt flow
- The inline package editor now shows human-readable inbound line context instead of UUID fragments:
  - line number
  - SKU code
  - assigned-versus-expected quantity
- Focused regressions passed for the new package workbench actions:
  - open a no-code package directly
  - capture an observed code against that package
  - update a package before confirmation
  - delete an unconfirmed package
- Live production verification also passed for the full Phase 1 package workbench loop using:
  - [tools/verify_production_package_workbench_flow.py](/Volumes/MaxRelocated/WMS/tools/verify_production_package_workbench_flow.py)
- Production verification order:
  - `INB-PKGWB-68080732`
- Verified production behaviors:
  - created two active packages under one inbound line
  - updated a third draft package and then deleted it successfully
  - opened a no-code package directly with `opened_directly = true`
  - added an external tracking code to that package using only `package_id`
  - scanned both packages by their tracking numbers and matched them back to package `1` and package `2`
  - confirmed both packages independently
  - issued two internal labels:
    - `RCV-INB-PKGWB-68080732-001`
    - `RCV-INB-PKGWB-68080732-002`
  - `complete_receiving` created two downstream putaway tasks
  - final package detail showed both packages in `putaway_pending`, each with:
    - one observed external code
    - one internal label
    - one handling unit
    - one downstream task
- Safe production targets used during this verification:
  - `warehouse_code = BUDDEMO`
  - `client_code = DANUBE`
  - `sku_code = DAN-FLOUR-020`
  - `source_barcode = DOCK-01`

### Package-centric receiving Phase 2 is now reflected in the queue and detail surfaces

- The inbound order list endpoint in [backend/app/api/v1/endpoints/orders.py](/Volumes/MaxRelocated/WMS/backend/app/api/v1/endpoints/orders.py) now returns package-centric operational rollups per order:
  - `total_packages`
  - `packages_open`
  - `packages_putaway_pending`
  - `packages_stored`
  - `packages_needing_action`
  - `internal_labels_total`
  - `internal_labels_print_pending`
- Inbound detail in [backend/app/api/v1/endpoints/order_details.py](/Volumes/MaxRelocated/WMS/backend/app/api/v1/endpoints/order_details.py) now exposes a top-level `package_summary` so the product surface can show package work without flattening nested line/package data.
- The receiving queue and detail views are now more explicitly package-centric:
  - [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx) now shows package-work chips in the inbound table, a second filter row for:
    - `All package work`
    - `Needs action`
    - `Packages open`
    - `Putaway pending`
    - `Print pending`
  - the right-side work queue now includes package rollups for:
    - packages still open
    - packages awaiting putaway
    - internal labels still to print
  - the selected inbound summary now highlights package metrics instead of only lifecycle actions
- The detail surfaces now foreground package work:
  - [frontend/src/modules/receiving/InboundOrderDetailPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderDetailPage.tsx) now shows top summary cards for package tracked/open/putaway/print/stored counts
  - [frontend/src/modules/receiving/InboundOrderHistoryPanel.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderHistoryPanel.tsx) now highlights packages needing action, packages stored, and labels still to print
- Focused validation passed for the new Phase 2 contract:
  - `test_inbound_order_list_exposes_package_operational_summary`
  - `test_inbound_detail_exposes_lifecycle_and_receiving_artifacts`
  - frontend production build also passed
- This keeps the original line-planning model intact while making the operating surface feel more like:
  - inbound orders composed of packages/MUs
  - packages driving dock work, print work, and putaway readiness

### Package-centric receiving Phase 3 now pushes print surfaces toward real package labels

- The receiving label template contract now accepts package-specific supporting fields:
  - `package_number`
  - `package_type`
- Tenant template settings in [backend/app/api/v1/endpoints/tenants.py](/Volumes/MaxRelocated/WMS/backend/app/api/v1/endpoints/tenants.py) continue to preserve existing saved templates, but new configurations can now explicitly include package identity on the printed label.
- The confirmed-label summary returned by [backend/app/api/v1/endpoints/receiving.py](/Volumes/MaxRelocated/WMS/backend/app/api/v1/endpoints/receiving.py) now includes `package_type` alongside `package_number`, so frontend print and preview surfaces do not need to infer package context indirectly.
- The print surface in [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx) is now more package-first:
  - each printed internal label keeps a fixed package header when package context exists
  - confirmed-label cards now show package number / package type more prominently
  - packaging facts such as boxes, pallets, and weight are surfaced directly in the card when available
  - dock notes stay visible at card level so operators can tell which package label they are about to print
- The template settings page in [frontend/src/modules/receiving/ReceivingLabelSettingsPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingLabelSettingsPage.tsx) now previews the internal label more like a real carton/MU sticker:
  - package context appears above the warehouse-owned internal code
  - new package-first field options are available in the selector
  - guidance now explains when package number and package type should be added to the printed sticker
- Focused validation passed for the template-side backend contract:
  - `test_receiving_label_template_endpoint_accepts_package_fields`
  - frontend production build also passed
- This keeps the label template configurable while making the default operator experience feel more like:
  - one physical package
  - one internal label
  - one downstream handling path

### Live production verification now also covers package-centric internal-label printing

- A dedicated production verifier now exists at:
  - [tools/verify_production_package_print_flow.py](/Volumes/MaxRelocated/WMS/tools/verify_production_package_print_flow.py)
- This verification flow now proves the package-centric print contract end to end:
  - switch the tenant template to a package-first field set
  - receive multiple packages under one inbound line
  - confirm that internal-label summaries include package number / package type / packaging facts
  - mark those labels printed in batch
  - restore the previous tenant template afterward
- Live production verification passed using:
  - `warehouse_code = BUDDEMO`
  - `client_code = DANUBE`
  - `sku_code = DAN-FLOUR-020`
  - `source_barcode = DOCK-01`
- Production verification order:
  - `INB-PKGPRT-56904944`
- Verified production outcomes:
  - template field set used during the run:
    - `order_number`
    - `package_number`
    - `package_type`
    - `tracking_number`
    - `package_count`
    - `pallet_count`
    - `weight`
    - `receiving_note`
  - two packages were received:
    - package `1` with type `carton`
    - package `2` with type `crate`
  - two internal labels were issued:
    - `RCV-INB-PKGPRT-56904944-001`
    - `RCV-INB-PKGPRT-56904944-002`
  - package-level print data was present in the label summaries:
    - package number
    - package type
    - package count
    - pallet count
    - measured weight
    - receiving note
  - batch print update count was `2`
  - both labels reported `print_count = 1` after printing

### Package-centric receiving Phase 5 now starts at the upstream input layer

- Upstream inbound creation is no longer forced to stay line-only:
  - [backend/app/api/v1/endpoints/receiving.py](/Volumes/MaxRelocated/WMS/backend/app/api/v1/endpoints/receiving.py) now accepts optional `line_number` and nested `packages` on `CreateInboundRequest`
  - [backend/app/services/receiving_service.py](/Volumes/MaxRelocated/WMS/backend/app/services/receiving_service.py) now validates that upstream package quantities add up to the inbound line quantity, preserves explicit package numbers, and creates draft `InboundPackage` rows immediately when package data is provided
- CSV import is now package-aware without breaking the original line-only flow:
  - optional inbound CSV mappings now include:
    - `line_number`
    - `package_number`
    - `package_type`
    - `package_tracking_number`
    - `package_carton_mark`
    - `package_customer_barcode`
  - when package columns are present, import groups rows into one inbound line and multiple packages under that line
  - when package columns are absent, the previous line-only behavior still works
- The agent import path stays in sync with the main receiving import path:
  - [backend/app/api/v1/endpoints/agent.py](/Volumes/MaxRelocated/WMS/backend/app/api/v1/endpoints/agent.py) now reuses the same package-aware inbound import builder, so inline agent-driven imports do not drift from the regular receiving CSV contract
- The admin hand-entry page now exposes a minimal package-aware intake surface:
  - [frontend/src/modules/admin/DataMigrationPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/admin/DataMigrationPage.tsx) still supports the original “one order / one line” shortcut
  - operators can now optionally pre-book cartons or MUs under that line before the order is saved
  - package quantities are validated client-side so the package split must add up to the line quantity
- Focused validation passed for the upstream package-aware contract:
  - `test_create_inbound_order_accepts_upstream_package_breakdown`
  - `test_import_inbound_orders_csv_groups_package_rows_under_one_line`
  - the existing CSV/order import smoke test still passed
  - frontend production build also passed
- This keeps the planning layer stable while letting upstream intake start to match the package-centric execution model:
  - customer data can arrive as one line plus multiple cartons/MUs
  - packages can exist before the truck reaches the dock
  - the receiving workbench no longer has to invent the entire package structure after the order is already inside the system

### Live production verification now also covers package-aware upstream intake

- A dedicated production verifier now exists at:
  - [tools/verify_production_package_upstream_intake.py](/Volumes/MaxRelocated/WMS/tools/verify_production_package_upstream_intake.py)
- This verifier now proves both upstream entry paths against production:
  - direct API/manual inbound creation with nested `packages`
  - CSV import with package/carton columns already populated
- Live production verification passed using:
  - `warehouse_code = BUDDEMO`
  - `client_code = DANUBE`
  - `sku_code = DAN-FLOUR-020`
  - `source_barcode = DOCK-01`
- Direct API/manual package-aware create verification passed with:
  - order: `INB-UPKG-06626450`
  - one inbound line created as `line_number = 11`
  - two upstream packages pre-booked before dock work:
    - package `2` as `carton`
    - package `5` as `crate`
  - both package tracking scans matched the intended packages:
    - `scan_package_numbers = [2, 5]`
  - both packages were confirmed independently and then `complete_receiving` generated:
    - `issued_internal_labels_count = 2`
    - two downstream putaway tasks
  - resulting internal labels:
    - `RCV-INB-UPKG-06626450-001`
    - `RCV-INB-UPKG-06626450-002`
  - both packages moved into `putaway_pending`
- CSV import package-aware verification passed with:
  - order: `INB-UPCSV-06626450`
  - preview detected:
    - `total_rows = 2`
    - `missing_required = []`
  - import result:
    - `imported = 1`
    - `errors = []`
  - the imported order detail preserved upstream package structure:
    - `line_number = 22`
    - `line_expected_qty = 8`
    - package numbers:
      - `1`
      - `2`
    - package types:
      - `carton`
      - `crate`
    - package expected quantities:
      - `3`
      - `5`
    - package tracking numbers:
      - `TRK-UPCSV-06626450-1`
      - `TRK-UPCSV-06626450-2`
- This means upstream package awareness is now verified end to end in production:
  - the order can arrive with package structure already defined
  - that structure survives both API intake and CSV import
  - and the downstream package-centric receiving flow can continue from it without inventing packages later at the dock

### Package origin is now visible across receiving and inbound detail surfaces

- The package execution layer no longer hides whether a package came from upstream planning or was created later at the dock:
  - [backend/app/api/v1/endpoints/receiving.py](/Volumes/MaxRelocated/WMS/backend/app/api/v1/endpoints/receiving.py) now returns `package_origin` on `/receiving/inbound/{order_id}/packages`
  - [backend/app/api/v1/endpoints/order_details.py](/Volumes/MaxRelocated/WMS/backend/app/api/v1/endpoints/order_details.py) now returns the same `package_origin` in inbound detail
- Current origin contract is intentionally simple and operational:
  - `prebooked`
    - package already existed before receiving started
  - `dock_created`
    - package was opened after dock receiving had already begun
- This origin is now visible in the main operator surfaces:
  - [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx)
    - package queue cards now show:
      - `Pre-booked`
      - `Opened at dock`
  - [frontend/src/modules/receiving/InboundOrderHistoryPanel.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderHistoryPanel.tsx)
    - inbound history now keeps the same badge and explanation at package level
  - [frontend/src/modules/receiving/InboundOrderDownstreamPanel.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderDownstreamPanel.tsx)
    - downstream drill-down now keeps the origin visible while following handling units and putaway tasks
- Focused validation passed for the contract:
  - `test_package_origin_distinguishes_prebooked_and_dock_created`
  - `test_inbound_detail_exposes_lifecycle_and_receiving_artifacts`
  - frontend production build also passed
- This keeps the upstream package-aware intake work visible after the order reaches the dock:
  - operators can tell whether a package was expected before arrival
  - or whether the warehouse team had to create it on the fly during intake

### Package origin now rolls up into queue filters and operational summaries

- Package origin is no longer just a badge buried inside receiving cards or inbound detail:
  - [backend/app/api/v1/endpoints/orders.py](/Volumes/MaxRelocated/WMS/backend/app/api/v1/endpoints/orders.py) now includes:
    - `packages_prebooked`
    - `packages_dock_created`
    on inbound list rows
  - [backend/app/api/v1/endpoints/order_details.py](/Volumes/MaxRelocated/WMS/backend/app/api/v1/endpoints/order_details.py) now includes the same split in `package_summary`
- [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx) now treats origin as an operational filter, not just a descriptive label:
  - package chips on each inbound row now show:
    - `pre-booked`
    - `dock-opened`
  - package work filters now include:
    - `Pre-booked`
    - `Opened at dock`
  - the receiving work queue now exposes both rollups so supervisors can quickly see:
    - how much package work arrived already structured from upstream
    - how much package work had to be created at the dock
- Focused validation was extended so the list contract proves this mixed-origin case:
  - `test_inbound_order_list_exposes_package_operational_summary`
    - now asserts:
      - `packages_prebooked == 1`
      - `packages_dock_created == 1`
  - `test_package_origin_distinguishes_prebooked_and_dock_created`
    - still proves package-level origin on receiving/detail endpoints
- This pushes the package-aware model one step closer to a true operating queue:
  - package origin can now drive what the team chooses to work next
  - not just how they explain an already-selected package afterward

### Package-origin queue rollups are now verified against production

- Production backend was confirmed live on:
  - `033582dd9b07a694544800878b9516fc2008ea3c`
- A dedicated verifier now exists at:
  - [tools/verify_production_package_origin_queue_flow.py](/Volumes/MaxRelocated/WMS/tools/verify_production_package_origin_queue_flow.py)
- Live verification passed using:
  - `warehouse_code = BUDDEMO`
  - `client_code = DANUBE`
  - `sku_code = DAN-FLOUR-020`
  - `source_barcode = DOCK-01`
- Production order used for the mixed-origin queue check:
  - `INB-PKGORG-87072304`
- Verification confirmed the exact operational split the receiving queue now depends on:
  - one `prebooked` package created before dock receiving started
  - one `dock_created` package opened after receiving started
  - first confirmed package generated internal label:
    - `RCV-INB-PKGORG-87072304-031`
- List-level rollups matched the expected mixed-origin state:
  - `total_packages = 2`
  - `packages_open = 2`
  - `packages_putaway_pending = 0`
  - `packages_stored = 0`
  - `packages_needing_action = 2`
  - `packages_prebooked = 1`
  - `packages_dock_created = 1`
  - `internal_labels_total = 1`
  - `internal_labels_print_pending = 1`
- Inbound detail matched the same contract:
  - `package_summary.packages_prebooked = 1`
  - `package_summary.packages_dock_created = 1`
  - package `1` returned `package_origin = prebooked`
  - package `2` returned `package_origin = dock_created`
- This means package origin is now not just visible but operationally trustworthy:
  - the queue can distinguish what arrived already structured from upstream
  - and what the dock team had to create on the fly during intake

### Package operations now open straight into the next matching work surface

- The receiving workbench now treats package filters as actionable routing, not just queue labels:
  - [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx)
    - adds a `Package work focus` banner above the inbound table
    - picks the next matching inbound order for:
      - `Needs action`
      - `Packages open`
      - `Print pending`
      - `Pre-booked`
      - `Opened at dock`
    - sends `Putaway pending` straight to `/putaway` with inbound focus context
    - makes the right-side queue cards actionable with:
      - `Open work`
      - `Open putaway`
- [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx) now accepts an initial package focus mode and uses it to keep operators on the right work:
  - `prebooked`
  - `dock_created`
  - `package_open`
  - `needs_action`
  - `print_pending`
- When the focus is package work, the flow auto-opens the next matching package if it can resolve one by external code or direct package open.
- When the focus is print work, the flow keeps the confirmed internal label section in view so the team can print without hunting through the page again.
- The active focus is now visible inside the receiving flow with a clear `Clear focus` action, so the operator can intentionally drop back to the full package queue.
- Frontend validation passed:
  - `npm run build`
- Frontend production deployment completed:
  - `dpl_68CSRYoV931WfcxJBNMgaVVx8D8i`
  - aliased at:
    - [app.maxsmartwms.online](https://app.maxsmartwms.online)
- This closes an important operational gap:
  - package rollups no longer just describe work
  - they now hand the operator directly into the right next surface:
    - `Receiving`
    - or `Putaway`

### Package drill-down and putaway return feedback now preserve package context

- `Inbound detail` and the embedded history/downstream panels can now send the operator back into `Receiving` at the exact package that still needs action:
  - [frontend/src/modules/receiving/InboundOrderHistoryPanel.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderHistoryPanel.tsx)
  - [frontend/src/modules/receiving/InboundOrderDownstreamPanel.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderDownstreamPanel.tsx)
  - package cards now expose:
    - `Open package in receiving`
    - `Open package print`
- [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx) now reads a `receiving.focusContext` session token, not just `receiving.selectedOrderId`, so it can reopen:
  - a specific open package
  - or the print section for a specific package
- [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx) now supports:
  - `initialPackageId`
  - `initialPrintPackageId`
  - direct package drill-in highlights inside:
    - the package queue
    - the confirmed internal labels section
- [frontend/src/modules/putaway/PutawayPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/putaway/PutawayPage.tsx) now writes a one-shot return notice when putaway is confirmed from inbound-focused context.
- [frontend/src/modules/receiving/InboundOrderDetailPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderDetailPage.tsx) now reads that notice and shows a `Returned from putaway` banner, so the operator immediately sees:
  - which handling unit just completed
  - whether it went to one final location or a split set of locations
- This tightens the loop from:
  - `Inbound detail/history`
  - to `Receiving`
  - to `Putaway`
  - and back to `Inbound detail`
  without dropping the package-level context along the way.

### Receiving queues now surface recently changed package activity

- [backend/app/api/v1/endpoints/orders.py](/Volumes/MaxRelocated/WMS/backend/app/api/v1/endpoints/orders.py) now returns `latest_activity_at` on each inbound order row.
  - it is derived from the newest order/package/internal-label timestamp already attached to that inbound order
- [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx) now uses that signal to add:
  - a `Recently changed` package filter
  - a `Recently changed` queue card in the right-side work queue
  - a package-ops routing path that can open:
    - `Receiving`
    - `Putaway`
    - or the inbound detail page itself, depending on what the latest order still needs
- This means the package operations surface is no longer only split by current work type (`open / print / putaway / pre-booked / dock-created`);
  it can now also answer:
  - `Which inbound orders changed most recently?`
  - `What should the team review right now before that context goes stale?`

### Receiving selections now explain why an order is in focus and what to do next

- [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx) now gives the selected inbound order its own operational briefing block:
  - `Latest activity`
  - `Recommended next step`
  - `Why this order is in focus`
- The panel derives package-level reasons directly from the current order state, including:
  - mixed pre-booked + dock-opened package origins
  - still-open packages
  - print-pending internal labels
  - putaway-pending packages
  - recent package activity
- The same reasoning now also appears in the `Package work focus` banner above the inbound list, so queue routing is no longer a black box.
- This makes the receiving workbench feel more like a supervisor dispatch surface:
  - the team can see not just which order bubbled to the top
  - but also why it surfaced and what action should happen next

### Inbound history now promotes the exact packages that still need action

- [frontend/src/modules/receiving/InboundOrderHistoryPanel.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderHistoryPanel.tsx) now includes a `Package review queue` above the full line-by-line history.
- The queue flattens package work across the order and prioritizes packages that still need:
  - dock receiving follow-through
  - internal label printing
  - downstream putaway
- Each actionable package card now gives direct routing into the right surface:
  - `Open package in receiving`
  - `Open package print`
  - `Open package putaway`
- This closes another operator gap in the detail surface:
  - supervisors no longer need to scan the entire history tree to find the next package that still needs work
  - the history panel itself now acts as a package-level dispatch list

### Inbound detail now opens with a clearer supervisor handoff summary

- [frontend/src/modules/receiving/InboundOrderDetailPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderDetailPage.tsx) now surfaces two top-level briefing cards before the lifecycle timeline:
  - `What changed last`
  - `What is still blocked`
- The handoff summary reads directly from:
  - the newest timeline event
  - package blockers already present on the order summary
- That means a lead or supervisor can open the detail page and immediately see:
  - the latest real package/downstream change
  - whether the remaining work is receiving, printing, or putaway
  - the most appropriate next action button
- This keeps the detail page aligned with the rest of the package-centric operations surface:
  - not just audit visibility
  - but direct operational guidance

### Receiving now includes a dedicated shift handoff board

- [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx) now gives the right rail a second operator layer below the raw work queue:
  - `Supervisor review`
  - `Recently changed`
  - `Print pending`
  - `Putaway pending`
- Each handoff card now answers four practical questions in one place:
  - which inbound order should a lead look at next
  - what changed recently
  - why it is being surfaced
  - which work surface should open next
- This pushes the receiving home page further toward a real shift-lead board instead of a passive queue summary:
  - the queue still counts work
  - the handoff board now turns those counts into the next concrete dispatch decision

### Selected inbound orders now expose a direct package dispatch queue

- [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx) now adds a `Package dispatch` section inside the selected-order briefing area.
- Instead of stopping at order-level guidance, the workbench now flattens the order's packages and promotes the ones that still need:
  - dock receiving follow-through
  - internal label printing
  - downstream putaway
- Each package card now carries enough context to dispatch it immediately:
  - package number and type
  - line number and SKU context
  - primary freight code when available
  - direct actions into:
    - `Receiving`
    - `Print`
    - `Putaway`
    - or full inbound detail review
- This closes another operator gap between queue signals and actual work:
  - leads can still reason at the order level
  - but they no longer need to open the full detail page just to send one specific package to its next surface

### Package dispatch now follows the active queue lane and can expand beyond the first four packages

- The selected-order `Package dispatch` queue now responds to the active package work lane on the receiving workbench:
  - `Needs action`
  - `Supervisor review`
  - `Packages open`
  - `Print pending`
  - `Putaway pending`
  - `Pre-booked`
  - `Opened at dock`
  - `Recently changed`
- If that lane narrows the useful package set, the dispatch panel now explains the current filter and only promotes the packages that belong in that lane.
- The dispatch panel also no longer hard-stops at four cards:
  - it still starts compact
  - but operators can now expand to review every matching package on the order before dispatching the next action
- This keeps the receiving home page aligned with the rest of the package-centric operations surface:
  - the queue decides which kind of work matters most
  - the selected order immediately shows the concrete packages inside that lane

### Package dispatch now explains ownership and the live blocker on each package

- [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx) now goes beyond simple action buttons on each selected-order package card.
- Each package dispatch card now also surfaces:
  - the latest package activity time
  - the recommended owner
  - the primary blocker that still needs to be cleared
- The current routing logic stays the same:
  - `Receiving`
  - `Print`
  - `Putaway`
  - or `Full detail`
  but the operator no longer has to infer *why* that route is right from status chips alone.
- This pushes the workbench closer to a real supervisor exception board:
  - package-level decisions are faster
  - ownership is clearer
  - and the blocker state is visible before anyone clicks through

### Receiving home now includes a cross-order supervisor exception package board

- [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx) now exposes a `Supervisor exception packages` section in the main left workspace, below the package work filters and above the inbound order table.
- Unlike the selected-order dispatch queue, this board is cross-order:
  - it pulls package exceptions from the current supervisor/recent activity/print/putaway signals
  - flattens them into a single package list
  - and promotes the specific packages that still need a lead decision or follow-through
- Each package card now shows:
  - order number
  - package number, type, SKU
  - latest activity age
  - recommended owner
  - primary blocker
  - direct action into `Receiving`, `Print`, `Putaway`, or full detail
- This makes the receiving home page feel less like an order queue with helpers and more like a real package-centric supervisor board:
  - the right rail still explains where attention belongs
  - the left workspace now surfaces the actual package exceptions that need action next

### Supervisor exception packages now break into owner lanes

- The cross-order exception board in [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx) no longer shows one undifferentiated list.
- Leads can now switch the board between:
  - `All exceptions`
  - `Dock receiving`
  - `Label printing`
  - `Putaway team`
  - `Supervisor review`
- Each lane shows its own live package count, so the board now reads more like a dispatch surface:
  - first identify *which team* owns the next move
  - then open the specific package that still needs action

### Receiving home now has a mobile-first operator layer

- [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx) now separates the phone-sized experience from the heavier desktop supervisor board instead of trying to show everything at once.
- On mobile:
  - the selected inbound collapses into a short `Current receiving focus` block
  - only the 3 critical metrics stay visible:
    - packages open
    - labels to print
    - packages awaiting putaway
  - the top 2 actionable packages stay in view with direct actions
  - the broader queue signals move into a lighter `Operator focus` strip plus a collapsed `Show supervisor tools` drawer
  - the desktop `DataTable`, right-rail queue, handoff board, support cards, and cross-order exception board stop competing for the first screen
- This should make the mobile experience feel more like:
  - first understand the next move
  - then act on the next package
  - only then expand into supervisor context if needed

### ReceivingFlow now follows the same mobile-first rhythm

- [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx) now gives phones a compact `Current receiving focus` card before the broader desktop-style dock dashboard.
- The scan step now prioritizes:
  - the current package and next action
  - the scanner surface
  - the confirm receipt form
  - then secondary context such as the package queue, print queue, and received history
- On mobile:
  - the heavy package queue moves behind a `Show package queue` drawer
  - confirmed internal labels move behind a lighter `Show confirmed labels` drawer
  - received history moves behind a `Show received packages` drawer
  - print template explanation no longer competes for the first action surface
- This keeps the operator on:
  - scan
  - confirm the current package
  - print or switch only when the immediate dock task is done

### Matched package details no longer dominate the first mobile screen

- The matched package section in [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx) now tells phones the current blocker first instead of opening with the full detail matrix.
- On mobile, once a package is matched:
  - the first card now shows the package, the remaining quantity, and the current blocker
  - the primary action jumps straight to the thing blocking progress:
    - choose staging
    - or confirm receipt
  - package facts and captured external codes moved behind secondary drawers
- Desktop keeps the richer readout, but phones now stay focused on:
  - what is blocking this package
  - what action clears that blocker
  - only then the deeper reference detail

### Confirm Receipt now treats mobile as a required-fields-first task

- The mobile confirm surface in [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx) now separates required dock checks from optional package detail capture.
- On phones:
  - the receipt card leads with a short `Confirm current package` explanation
  - staging and quantity stay visible as the required fields
  - packaging, pallet, weight, dimension, and dock note fields move into an `Add packaging or measurement details` drawer
- This means the first visible receipt form now answers:
  - what must be entered to unblock this package
  - and which details are optional follow-up capture instead of required progress blockers

### Confirm Receipt now explains why the button is blocked

- The mobile receipt card in [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx) now has an explicit `Receipt status` block directly above the confirm action.
- Phones now show one of three states before the action button:
  - `Scan a package first`
  - `Pick staging before confirming`
  - `Ready to confirm this package`
- The confirm button is also full-width on mobile, so the page now answers both:
  - what is blocking this package right now
  - and exactly when the primary action becomes available

### The main mobile receipt button now drives the next blocker resolution

- The primary mobile action in [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx) no longer just explains the blocked state. It now actively takes the operator to the thing that clears the blocker.
- On phones, the main button now changes between:
  - `Scan a package first`
  - `Choose staging to continue`
  - `Confirm this package receipt`
- The staging card also now shows an inline ready/pending state, so the operator can tell at a glance whether the dock slot requirement is already cleared.
- This keeps the first action surface aligned with the real task:
  - if no package is open, go to scan
  - if staging is still missing, go fix staging
  - if required checks are clear, confirm the receipt

### Mobile now surfaces the last confirmed package before deeper queue context

- The top mobile focus block in [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx) now includes a compact `Just confirmed` card whenever the latest package confirmation issued an internal label.
- Phones now answer three questions immediately after a confirmation:
  - which package was just confirmed
  - which internal label was issued
  - whether the next move should be print, continue with the open package, scan the next package, or move into putaway
- The larger success card stays on desktop, but mobile now gets the same success signal in the first screen where the operator is already working.

### Receiving page discipline now follows a stricter ShipOut-style rule set

- We formalized a simple rule for receiving surfaces:
  - one screen should present one dominant action
  - explanation should sit next to the action instead of in separate full-width banners
  - secondary context should live in chips, drawers, or drill-down views instead of competing with the first screen
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - the mobile operator board now shows the current lane instead of a second explanatory title block
  - the archived toggle was reduced from a sentence bar to a compact state chip plus action
  - `Package work focus` was compressed into order + lane + latest activity, without an extra reasons banner
  - selected-order desktop sections now merge `recommended next step`, `latest activity`, and focus reasons into one compact action strip
  - `Package dispatch` and `Supervisor exception packages` no longer lead with explanatory body copy
- In [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx):
  - the matched package surface no longer opens with a full explanation block
  - mobile blocker cards now show the blocker and action without a second paragraph
  - confirm receipt now removes extra preview, waiting, staging-help, and optional-details explanation bars on phone
  - print and template sections also dropped duplicate explanatory copy so the action stays visually dominant
- The intent is to keep the first mobile screen answering only:
  - what package is active
  - what is blocking it
  - what action clears that blocker next

### Mobile receiving surfaces now trade metric cards for tighter action chips

- After the first page-discipline pass, we tightened the mobile path again so it feels less like a mini-dashboard and more like a task runner.
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - the selected inbound card now uses compact chips for open / print / putaway counts instead of a three-card metric block
  - the mobile queue preview now surfaces only the next package instead of showing multiple package cards at once
- In [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx):
  - the mobile live-receiving header now uses chips for queue counts instead of another metric grid
  - `Queue focus` is hidden once a package is already open, so the active package becomes the only working context on screen
  - the matched package card on phones now keeps only expected / already received as compact chips instead of a wider three-metric block
- This keeps the mobile flow closer to the intended discipline:
  - orientation in one glance
  - one active package at a time
  - one obvious next move

### Desktop receiving surfaces now follow the same action-first discipline

- We carried the same page-discipline rule into desktop receiving instead of keeping a separate “dashboard-like” desktop language.
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - the selected inbound desktop panel now uses compact package-state chips instead of a wide metric-card grid
  - `Package dispatch` cards keep blocker, owner, and latest activity as compact chips instead of reintroducing explanatory copy blocks
- In [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx):
  - the live receiving desktop header now compresses order / reference / staging into chips
  - package queue counts are now chips instead of a second dashboard row
  - the desktop success state for a newly issued internal label keeps the label and action, but drops the extra hint paragraph
  - desktop package queue and queue-focus cards no longer lead with explanatory body copy
- This keeps both desktop and mobile closer to the same rule set:
  - orient quickly
  - see the active package or lane
  - take the next action without reading through extra helper panels

### Detail, queue, and prepare surfaces now drop redundant explanation cards

- We pushed the same discipline one layer deeper so the quieter mobile/operator style also reaches detail, queue, and prepare states.
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - the page title, work queue, shift handoff, mobile inbound queue, hero entry cards, and support tiles no longer spend vertical space on repeat explanation text
  - package dispatch and supervisor exception cards now surface line/order/quantity as compact chips instead of body paragraphs
- In [frontend/src/modules/receiving/InboundOrderDetailPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderDetailPage.tsx):
  - the header and status area now lean on state chips rather than long descriptive paragraphs
  - package metric cards are now metric-only instead of metric-plus-explanation
  - the return notice and “next move” areas keep the action but drop secondary narration
- In [frontend/src/modules/receiving/InboundOrderHistoryPanel.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/InboundOrderHistoryPanel.tsx) and [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx):
  - package review queues and prepare/opening states now remove background explanation text that repeated the obvious state
- The working rule is now stricter:
  - if a title, chips, and one button already explain the state, we remove the extra paragraph
- We also trimmed repeated state summaries:
  - the selected-order desktop panel now keeps only the counts that drive the next action
  - inbound detail now keeps a smaller four-metric summary instead of a broad six-card dashboard
  - inbound history now keeps the audit signals that matter most instead of repeating every lifecycle count again

### Real mobile walkthrough exposed the last low-value chrome on receiving

- We ran a real mobile-style production walkthrough against [https://app.maxsmartwms.online](https://app.maxsmartwms.online) using a tenant admin session and checked the route chain:
  - operations dashboard
  - jump into receiving
  - receiving empty state
- The walkthrough confirmed that the biggest remaining distraction on phone was no longer the receiving flow itself, but the chrome around it:
  - the mobile route header still duplicated too much navigation context
  - `Receiving` empty state still showed both a top import action and a second import action inside the card
  - zero-value operator focus cards still kept talking even when there was no active inbound work
- We tightened those surfaces again:
  - the shared mobile page header now keeps only breadcrumb + `Back to dashboard`, and drops the extra `Next` pill
  - the receiving page now hides the top `Open import center` button on phone and keeps only the in-card action
  - the mobile receiving hero now becomes a quiet empty-state card when both `ready` and `live` are zero
  - the mobile `Operator focus` board now disappears entirely when there is no active receiving work
- The current result is intentionally simpler:
  - the phone empty state still preserves archive/filter controls lower on the page
  - but the first screen now answers only one question: whether there is any inbound work to do right now

### Active receiving surfaces now drop dashboard-style summary blocks

- We continued the same page-discipline cleanup into active receiving instead of stopping at quiet states.
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - the desktop active hero no longer carries three explanation cards plus a second support-card row
  - it now keeps one primary action and a compact chip strip for ready/live/open/print state
- In [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx):
  - the live receiving desktop header now keeps one chip row instead of a header row plus a second mini-dashboard row
  - the package queue cards now use chips for expected / received / damaged instead of three nested metric boxes
  - matched-package desktop details now stay on one compact summary row instead of a nine-cell stat wall
  - external-code summaries are now chips, not another paragraph-style block
- The working rule stayed the same:
  - if a surface already has the current package, blocker, and next action, we remove the extra dashboard treatment

### Shared receiving chrome and flow focus were reduced again

- We kept the same page-discipline pass going after the active-surface cleanup instead of re-expanding the chrome.
- In [frontend/src/shared/components/Layout.tsx](/Volumes/MaxRelocated/WMS/frontend/src/shared/components/Layout.tsx):
  - the shared route header dropped the extra `You are in ...` context pill
  - the desktop `Next` route shortcut was removed so the header now stays closer to breadcrumb + back instead of acting like a second navigation bar
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - mobile empty receiving no longer adds a second dashed helper paragraph below the quiet card
  - desktop quiet receiving no longer repeats the same empty-state explanation inside the hero and queue side card
- In [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx):
  - mobile current-focus no longer spends a line on reference text that does not change the next action
  - the dedicated `Queue focus` explanation card was removed because the focus is already expressed by the primary action and queue chips
  - the package queue empty state is now a shorter action row instead of a mini explainer block
- The working rule is now even stricter:
  - if navigation context, queue focus, or empty-state copy does not change what the operator does next, it should not keep its own block on screen

### Active receiving side panels and optional-detail sections were trimmed again

- We kept the same reduction pass going inside active receiving instead of stopping after the shared chrome cleanup.
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - the desktop `Work queue` and `Shift handoff` side panels no longer spend a large sentence on top of cards that already explain themselves through lane title, count, reasons, and action
  - empty handoff lanes now collapse to one quiet status pill instead of another explanatory paragraph
- In [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx):
  - packaging and measurements optional-detail sections now rely on their section title plus fields instead of another helper paragraph
  - the mobile package-queue drawer no longer opens with a prose instruction block before the queue itself
- The working rule stayed the same:
  - if a section already has a clear title and obvious controls, we remove the extra sentence before it

### Active-state repetition was reduced again

- We kept the same page-discipline pass moving through active surfaces instead of stopping after the last copy cleanup.
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - the selected desktop order panel dropped the extra package metric row because the recommended action and package dispatch already explain what still needs work
  - the recommended next-step strip now stays on one latest-activity signal plus the rare supervisor-review chip instead of re-listing three reasons that the dispatch cards already restate
  - the `Package dispatch` header no longer spends a title sentence before the dispatch cards
- In [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx):
  - mobile and desktop live-receiving headers no longer surface `Awaiting putaway`, keeping the first screen focused on work still at the dock
  - the mobile confirm area no longer shows a separate `Receipt status` card because the current blocker plus the primary action already answer whether the operator can confirm
- We also removed the dead helper code and i18n keys that used to support those cards, so the code now matches the lighter interface instead of carrying stale explanation paths.

### Selected-order and live-receiving headers were compressed again

- We kept the same cleanup moving through active work, not empty states.
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - the standalone `Recommended next step` block was removed from the selected desktop order panel
  - its primary action now lives directly in the `Package dispatch` header, so the selected order moves from summary → dispatch without an extra middle section
- In [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx):
  - mobile `Current receiving focus` now only shows the queue chips that are actually non-zero
  - the mobile recent-receipt card no longer repeats `Next package ready` because the action button already tells the operator whether to print, continue, or scan next
  - the desktop live-receiving header now stays on inbound + staging only; queue counts remain further down in the package and print sections where they actually drive work
  - the desktop `Measurements & note` box also dropped its last helper sentence because the section title and fields already explain the job

### Queue and dispatch now avoid echoing blocker state

- We kept trimming active receiving on the rule that one surface should answer one question.
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - package dispatch cards no longer repeat extra open / print / putaway state pills after the blocker chip has already explained what is blocking the package
- In [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx):
  - the desktop and mobile package queue headers now only show `open` instead of reporting both open and confirmed, because the confirmed-label section already owns the print-ready story below
  - the desktop recent-receipt banner no longer repeats `Next package ready`; the remaining action button already carries that next step

### Current-package first screens now keep only blocker-level quantity

- We continued the same active-flow cleanup with the rule that the first package surface should answer “what is this, what is left, what blocks it, what do I press”.
- In [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx):
  - the mobile `Current package` card now keeps only the package identity plus `Still to receive`; `Expected` and `Already received` moved down into the details drawer
  - the desktop matched-package strip also dropped `Expected` and `Already received`, so the first horizontal row now favors package identity, remaining quantity, and detected code
- The effect is smaller than a structural rewrite, but it keeps the active first screen from reading like a small dashboard before the operator even reaches the blocker action.

### First-action surfaces now avoid repeating the same label in prose

- We continued the same pass with a stricter rule: if the primary button already says the next action, we do not spend another sentence above it repeating the same words.
- In [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx):
  - the mobile `Next action` card dropped the duplicate action sentence and now goes straight from eyebrow to buttons
  - the mobile `Current blocker` card now relies on the blocker button itself instead of restating the same blocker label in a second line
  - the desktop matched-package strip also dropped the repeated code-type chip because the matched-by text above and the detected code chip already carry that context
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - owner and recent-activity chips now show the actual signal directly instead of prefixing each one with `Recommended owner:` or `Latest package activity:`
- We also removed the dead helper functions and unused i18n keys that powered those deleted explanation paths, keeping the code aligned with the lighter interface.

### Confirm and dispatch surfaces now drop secondary explanation copy

- We continued the same active-flow cleanup with the rule that a dispatch card or confirm section should only show information that changes the next click.
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - selected-order `Package dispatch` cards now keep the action-driving chips only: line, quantity, blocker, and primary code
  - owner and latest-activity chips were removed from that first surface because they were context, not the next move
- In [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx):
  - the mobile `Required now` eyebrow card was removed because staging plus quantity fields already state the blocking work
  - quantity and packaging sections no longer spend an extra body sentence before the fields
- The effect is modest, but it keeps the active confirm surface closer to a form that drives one action instead of a form wrapped in repeated explanation.

### Active package surfaces now trust blocker state more than status badges

- We continued the same active-flow reduction by removing status badges that only repeated what blocker and next-action surfaces already made clear.
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - selected-order dispatch cards and supervisor exception cards now keep origin, blocker, and primary-code context, but no longer add a second package status chip at the top
- In [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx):
  - the matched current-package card no longer shows a standalone status badge because the current blocker and remaining quantity already drive the next move
- The intent is not to hide useful state; it is to stop spending top-row space on status labels that do not change the operator's next click.

### Work queue cards now act as actual lane entry points

- We closed a real functional gap in the right-side receiving queue: the cards used to count work, but not reliably open it.
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - `ReceivingQueueCard` is now clickable as a whole lane card instead of hiding the action behind a small secondary button
  - `Ready to open` now opens the next expected inbound into the orders workspace
  - `Receiving now` now resumes the next active receiving flow directly
- This makes the queue actually behave like a queue: counts still summarize the lanes, but every active lane now leads somewhere useful.

### Shift handoff now stays on true handoff lanes only

- Once the right-side `Work queue` became fully actionable, `Shift handoff` started repeating the same print-pending and putaway-pending lanes.
- In [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - `Shift handoff` now keeps only the lanes that are genuinely handoff-oriented: `Supervisor review` and `Recently changed`
  - `Print pending` and `Putaway pending` stay in the actionable `Work queue`, where they already send the operator straight into work
- This sharpens the division of labor on the right side:
  - `Work queue` = act now
  - `Shift handoff` = review and transfer context

### Putaway workbench now opens on work, not explanation

- We started carrying the same page discipline into [frontend/src/modules/putaway/PutawayPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/putaway/PutawayPage.tsx).
- The top-level `Putaway flow` hero and separate `Operator guide` card were removed, along with their dead helper components and copy paths.
- The page header now stays on the title plus compact status chips, and the first large surface is the pending-task board instead of a pair of explanation cards.
- Inside the left task rail:
  - the search and visible-task summary were compressed into one lighter tool row
  - execution-route totals moved into the route filter pills instead of living in a second set of summary cards
- The effect is the same discipline we already applied to `Receiving`: first show the work, then the filters, and let deeper explanation live inside the task and board surfaces instead of occupying the whole first screen.
- We then pushed the same cleanup one level deeper into the batch board:
  - the live-status, board, before-state, and step-three panels dropped their helper paragraphs
  - the board now relies on titles, counts, and action buttons instead of explaining the same move in prose before every section

### Putaway active task surfaces now trust titles, chips, and buttons more

- We continued the same reduction inside [frontend/src/modules/putaway/PutawayPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/putaway/PutawayPage.tsx), but this time on the active-task side instead of the queue side.
- The biggest changes:
  - the move checklist no longer repeats instructional detail under every step
  - the current-decision panel now collapses into compact chips instead of stacked explanation paragraphs
  - batch final review, after-state, planner, and visual picker setup no longer spend the first line teaching the operator how to use them
  - destination help paragraphs were removed once the picker, slot suggestions, and confirm button were already making the next action obvious
- The intent is to make `Putaway` feel like the tightened `Receiving` flow: identify the task, choose the slot, confirm the move, and let explanation retreat behind the controls instead of competing with them.

### Putaway active task no longer repeats the same decision three times

- We kept reducing the `Putaway` active-task path by removing a full duplicate layer of decision summary from [frontend/src/modules/putaway/PutawayPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/putaway/PutawayPage.tsx).
- The operator now sees:
  - the task identity and route chips
  - the key snapshot counts
  - a single move checklist
  - then destination choice and confirm
- We removed the extra `Current decision` card and the extra three-card route summary because they were restating the same handoff, quantity, route, and next-move signals that were already visible above and below.
- This keeps the active path closer to the page discipline we set for `Receiving`: one primary decision surface, not three stacked summaries of the same move.

### Putaway checklist now keeps only the true actions

- We then took one more pass through the same active task surface and removed the last passive step from the checklist.
- In [frontend/src/modules/putaway/PutawayPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/putaway/PutawayPage.tsx):
  - the checklist now only shows `Pick the final slot` and `Confirm the move`
  - the extra `Current location` snapshot was removed because the source staging location is already visible in the task header card
- This makes the checklist more honest: the operator is not actually performing three separate actions here, just choosing the slot and confirming the move.

### Receiving active path now keeps captured codes and print-template context off the first screen

- We continued the same active-flow reduction in [frontend/src/modules/receiving/ReceivingFlow.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingFlow.tsx), but this time by pushing secondary context behind explicit reveals.
- The two biggest changes:
  - desktop `Captured external codes` now stays collapsed unless the operator is actively editing a code, typing a new one, or still has unconfirmed observed codes to resolve
  - desktop `Print template` moved into a lighter reveal so the confirmed-label area no longer shows the whole template field list before the operator actually needs it
- This keeps the first screen closer to the page discipline we set for the module: identify the package, see what is blocked, confirm receipt, and only then pull open secondary management surfaces when they are actually needed.

### Action-first page discipline is now documented and script-verified

- We promoted the current `Receiving` + `Putaway` interaction rules into a dedicated baseline document at [docs/09-action-first-page-discipline.md](/Volumes/MaxRelocated/WMS/docs/09-action-first-page-discipline.md).
- The document freezes the working rules we have been iterating toward:
  - one primary action per first screen
  - blocker says the problem
  - button says the action
  - secondary context stays behind explicit reveals
  - empty states stay quiet
- We also added a browser-level sanity script at [frontend/scripts/verify-receiving-putaway-action-surfaces.mjs](/Volumes/MaxRelocated/WMS/frontend/scripts/verify-receiving-putaway-action-surfaces.mjs) so this is no longer just a visual opinion:
  - it seeds a fresh tenant and package-centric inbound order
  - verifies the active receiving surface opens on the current package and primary action
  - verifies secondary receiving context is collapsed by default
  - then completes the same flow into putaway and verifies the stripped-down two-step move checklist is what the operator sees

### Resuming an active receiving order now lands on package work, not just the scan shell

- While wiring up the new action-surface verifier, we found one real friction point in [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx):
  - entering a `receiving` order from the desktop workbench could still land the operator on the generic scan shell, even when the order already had open package work waiting
- We tightened `launchSelectedOrderToFlow()` so a plain `Resume receiving` on an already-live order now defaults to `package_open` focus.
- The effect is small but important:
  - the operator no longer has to re-decide whether to scan, browse the queue, or reopen the next box
  - the workbench now moves straight into the next still-open package by default

### Receiving-to-putaway action-surface verification now runs end-to-end

- We finished the last remaining gap in [frontend/src/modules/putaway/PutawayPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/putaway/PutawayPage.tsx):
  - single-task focus from inbound detail no longer falls back into the batch planning workspace
  - putaway success now renders at the page level instead of disappearing with the active-task card as soon as the pending task clears
- With that in place, [frontend/scripts/verify-receiving-putaway-action-surfaces.mjs](/Volumes/MaxRelocated/WMS/frontend/scripts/verify-receiving-putaway-action-surfaces.mjs) now passes against production end to end:
  - seeds a fresh tenant, warehouse, client, SKU, inbound order, and dock-created package
  - resumes the live receiving order into package work
  - scans the package and confirms receipt
  - verifies the secondary print-template context stays collapsed
  - completes receiving through the API
  - lands putaway on the focused active task with the stripped-down two-step move checklist
  - confirms the move and verifies the top-level success state remains visible after the task clears
- This gives us a real baseline, not just a design intention:
  - `Receiving` and `Putaway` now share the same action-first rules
  - the happy path from package receipt to final storage is script-verified in production

### Picking and shipping now follow the same first-screen discipline

- We extended the same action-first baseline to the next adjacent operator pages:
  - [frontend/src/modules/picking/PickingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/picking/PickingPage.tsx)
  - [frontend/src/modules/shipping/ShippingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/shipping/ShippingPage.tsx)
- In `Picking`:
  - removed the separate flow hero and new-user guide rail
  - replaced them with one compact workbench surface: counts, next action, and direct move into orders/tasks/pick work
  - kept the live task list and task snapshot as the work surface instead of surrounding them with explanation cards
- In `Shipping`:
  - removed the dispatch-flow hero, guide rail, shipping-picture panel, and after-shipping teaching block
  - replaced them with one compact shipping workbench surface: ready-order counts and a direct `Open next order` action
  - tightened the selected-order handoff so it starts on the order, status chips, lines, and pack/ship actions instead of a descriptive paragraph
- This keeps the operator-facing modules aligned:
  - `Receiving` and `Putaway` stay the most action-dense workflows
  - `Picking` and `Shipping` now open with the same order of information: identity, current queue, main action, then detailed work

### Putaway active task surface now keeps secondary context behind explicit reveals

- We took another pass through [frontend/src/modules/putaway/PutawayPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/putaway/PutawayPage.tsx) because the active task surface was still carrying too much first-screen detail compared with the receiving baseline.
- The biggest reductions were:
  - the three-card route snapshot was replaced with compact chips for quantity waiting, planned final slots, and the currently selected destination
  - external-code context was removed from the first screen and folded into a lighter `Task details` disclosure
  - handling unit status, package count, and measured weight now live in that same disclosure instead of always-visible snapshot cards
  - `Visual storage picker` and `Split putaway plan` now start as disclosures, opening themselves only when the operator is already working inside them
- This keeps the active task screen closer to the discipline we set for the operator flows:
  - identify the move
  - see the minimum route context
  - choose the slot
  - confirm
- Build verification passed after the change:
  - `npm run build` in [frontend](/Volumes/MaxRelocated/WMS/frontend)

### Shipping action cards now lead with status and form fields instead of explanation copy

- We took a small but high-value pass through [frontend/src/modules/shipping/ShippingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/shipping/ShippingPage.tsx) to keep the selected-order work area aligned with the same action-first discipline as receiving and putaway.
- The active shipping surface now removes the explanatory body paragraphs from the two main action cards:
  - `Confirm packing matches the picked work`
  - `Confirm carrier handoff and tracking`
- In their place:
  - packing now shows compact status chips such as `All lines picked` or `Finish picks first`
  - shipping now shows compact readiness chips for `Carrier` and `Tracking`
  - the operator then moves straight into the actual fields and action button
- We also removed the repeated `Selected {order}` chip from the top shipping workbench because that identity is already established again in the selected-order panel below.
- This keeps the shipping first screen closer to the baseline:
  - status shows what is blocked
  - the form shows what must be entered
  - the button shows the next action

### Receiving home now separates the routing page from the current-order workspace more clearly

- We took a structural pass through [frontend/src/modules/receiving/ReceivingPage.tsx](/Volumes/MaxRelocated/WMS/frontend/src/modules/receiving/ReceivingPage.tsx) to make the page behave more clearly as a routing page first and a current-order workspace second.
- The main change is that once an inbound order is selected:
  - the cross-order `Work queue`, `Shift handoff`, mobile `Operator focus`, `Package work focus`, and `Supervisor exception packages` stop competing for attention
  - the right rail switches to a much quieter `Work queue` reminder with a single `Clear selection` escape hatch
  - the selected-order panel keeps only the current order actions and package dispatch in the first screen
- We also pushed the heavier order-management and audit surfaces further back:
  - `Archive / Restore / Void / Delete` now live under a `More order actions` disclosure
  - `InboundOrderHistoryPanel` now lives under a `Review history and audit` disclosure
- This keeps the page closer to the intended split:
  - `ReceivingPage` decides where to go
  - `ReceivingFlow` does the live work on the current package

### Formal UAT runbook is now ready

- After the 2026-05-02 production pre-UAT pass, the live environment was cleaned
  back to a zero-test-data state:
  - test tenant candidates: `0`
  - test data rows: `0`
  - preserved tenants: `PLATFORM`, `GREENECOPO`
  - preserved tenant operational rows: `0`
- The automated acceptance pass covered:
  - MailerSend provider diagnostics
  - public registration email creation
  - platform-admin bootstrap
  - receiving through putaway, inventory, picking, packing, and shipping
  - receiving package fallback
  - receiving/putaway action surfaces
  - pack completeness guardrails
  - shipping tracking persistence
  - billing rate card, calculation, invoice generation, sent, paid, and invoice-list status
  - production page audit across desktop and mobile
  - core table sorting and tab interaction smoke
- A formal UAT execution guide now lives at
  [docs/16-uat-runbook.md](/Volumes/MaxRelocated/WMS/docs/16-uat-runbook.md).
- The next product step is manual user acceptance testing, not more automated
  smoke expansion, unless a UAT issue exposes a concrete regression gap.

### Formal UAT acceptance script now passes on production

- Added [frontend/scripts/verify-uat-acceptance.mjs](/Volumes/MaxRelocated/WMS/frontend/scripts/verify-uat-acceptance.mjs) as the repeatable formal UAT baseline.
- The script creates an isolated Acceptance UAT tenant, then validates:
  - receiving with two prebooked packages
  - receiving completion to putaway
  - two putaway task confirmations
  - inventory quantity movement and over-pick non-mutation
  - shortage outbound allocation blocking
  - normal picking, packing, shipping, and tracking persistence
  - billing calculation, invoice generation, sent, and paid transitions
  - production page visibility at the correct workflow stage
- The 2026-05-02 run passed for batch `UAT-20260502-01`:
  - evidence tenant: `Acceptance UAT UAT-20260502-01 Full Flow uat13138995`
  - backend build SHA: `0942693ee11a09205d5a8195efe28220261c8900`
  - billing total: `5.75`
  - browser console errors: `0`
- The earlier apparent over-pick issue was confirmed to be a test-harness timing
  and selection issue; production correctly rejects `quantity_picked` greater
  than the pick task quantity and does not mutate inventory.
- After tester confirmation, UAT cleanup was completed:
  - dry-run found `7` Acceptance UAT tenants and `249` tenant-scoped rows
  - cleanup deleted `7` test tenants and `249` tenant-scoped rows
  - preserved tenants were `PLATFORM` and `GREENECOPO`
  - preserved-tenant operational rows deleted: `0`
  - final dry-run confirmed test tenant candidates `0`, test rows `0`, and
    preserved-tenant operational rows `0`

### Release gate commands and access-control audit are now fixed

- Productized formal UAT and cleanup as npm commands in
  [frontend/package.json](/Volumes/MaxRelocated/WMS/frontend/package.json):
  - `npm run uat:production`
  - `npm run uat:production:cleanup`
  - `npm run audit:access-control`
- Added [frontend/scripts/verify-access-control.mjs](/Volumes/MaxRelocated/WMS/frontend/scripts/verify-access-control.mjs) to create a temporary access-audit tenant, verify role boundaries, and clean the temporary tenant.
- Added [frontend/scripts/cleanup-production-test-data.mjs](/Volumes/MaxRelocated/WMS/frontend/scripts/cleanup-production-test-data.mjs) so production test cleanup is repeatable and conservative.
- Added [docs/17-release-gate-and-access-audit.md](/Volumes/MaxRelocated/WMS/docs/17-release-gate-and-access-audit.md) as the fixed pre-release checklist.
- Updated [docs/16-uat-runbook.md](/Volumes/MaxRelocated/WMS/docs/16-uat-runbook.md) and [docs/12-user-management-hierarchy.md](/Volumes/MaxRelocated/WMS/docs/12-user-management-hierarchy.md) to point to these commands.
- Ran the production access-control audit successfully:
  - temporary audit tenant created and deleted
  - tenant admin scope and role-promotion blocks passed
  - operator and client-viewer permission clamping passed
  - protected user-management and billing endpoints returned `403` for child
    users
  - cleanup deleted `1` audit tenant and `5` tenant-scoped rows
  - preserved operational rows deleted: `0`
  - final cleanup dry-run confirmed test tenants `0`, test rows `0`, and
    preserved operational rows `0`

### 2026-05-03 release gate was rerun collaboratively

- Render production was redeployed to
  `6329c321690641901000ff8732046be1350543cd`; `/health` returned `ok` for
  branch `main` on service `srv-d7ako4ggjchc73eh8g70`.
- The fixed release gate from
  [docs/17-release-gate-and-access-audit.md](/Volumes/MaxRelocated/WMS/docs/17-release-gate-and-access-audit.md)
  was run against production:
  - `npm run smoke:mail-provider`
  - `npm run smoke:registration-email`
  - `npm run smoke:production-bootstrap`
  - `npm run audit:access-control`
  - `npm run uat:production`
  - `npm run audit:production-pages`
  - `npm run smoke:receiving-package-fallback`
  - `npm run lint -- --quiet`
  - `npm run uat:production:cleanup`
- All commands passed.
- Formal UAT now defaults to the current date when `WMS_UAT_BATCH` is not set,
  avoiding stale evidence names such as a May 3 run labeled May 2.
- The final formal UAT run used batch `UAT-20260503-01` and evidence tenant
  `Acceptance UAT UAT-20260503-01 Full Flow uat83902632`.
- The production page audit checked `70` page and viewport combinations with
  `failures=0` and `consoleErrorCount=0`.
- Final cleanup deleted the UAT tenant and confirmed test tenant candidates
  `0`, test rows `0`, and preserved operational rows `0`.
- Remaining human work is manual sign-off, not an automated release blocker:
  a tester should still execute the runbook in
  [docs/16-uat-runbook.md](/Volumes/MaxRelocated/WMS/docs/16-uat-runbook.md)
  and record any real-user issues before final acceptance.
- Manual UAT step 1 is now prepared as a tester-facing packet in
  [docs/20-manual-uat-checklist.md](/Volumes/MaxRelocated/WMS/docs/20-manual-uat-checklist.md).
  It includes session header, device matrix, test data naming, scenario IDs,
  issue log template, daily closeout, and sign-off criteria.

### Final production deployment record was reconciled

- After the release gate evidence was committed, Render production was updated
  once more to
  `f264d1ccda99e0e3009d406cdad375854463afd4`.
- Production `/health` returned:
  - status: `ok`
  - branch: `main`
  - Render service: `wms-quickstart`
  - service ID: `srv-d7ako4ggjchc73eh8g70`
  - endpoint: `https://api.maxsmartwms.online/health`
  - build SHA: `f264d1ccda99e0e3009d406cdad375854463afd4`
- GitHub CI for `f264d1ccda99e0e3009d406cdad375854463afd4` passed in run
  `25270291831`
  (`https://github.com/maxwu1978/wms-quickstart/actions/runs/25270291831`).
- This reconciles the evidence chain:
  - `6329c321690641901000ff8732046be1350543cd` was the full automated release
    gate execution target
  - `f264d1ccda99e0e3009d406cdad375854463afd4` is the final deployed baseline
    after recording that evidence and fixing the UAT default batch label

### 2026-05-05 idempotency and offline recovery release passed production gates

- Hardened retry-sensitive workflow mutations with tenant-scoped idempotency:
  receiving start/package receive/label receive/complete, putaway confirm,
  pick confirm, pack verify, and ship confirm now accept
  `X-Idempotency-Key`.
- Added the browser offline outbox for these operator mutations. Queued records
  are scoped to the current tenant and user, replay with the same idempotency
  key, surface business failures as failed queued actions, and invalidate live
  query data after successful replay.
- Bounded scanner WebSocket reconnect behavior so camera/scanner sessions do
  not leave stale sockets or timers behind.
- Tightened pick-task ownership:
  - operators can only query their own assigned human pick tasks
  - confirming another operator's assigned pick task is rejected
  - AGV-assigned tasks cannot be completed by the human pick confirmation path
- Fixed the shipping-flow smoke script so it verifies the current single-order
  shipping detail surface instead of requiring the older table-style detail.
- Committed and pushed the release as
  `68a6442d7608fad525617c7069790a9d385feb9f`
  (`Harden workflow retries and offline recovery`).
- Frontend production was deployed and aliased:
  - deployment ID: `dpl_CfJZ5PuFwhB8aXBTKcHRXaqnitib`
  - deployment URL:
    `https://wms-quickstart-frontend-88hor54af-maxw-2608s-projects.vercel.app`
  - production alias: `https://app.maxsmartwms.online`
- Render production `/health` confirmed:
  - status: `ok`
  - branch: `main`
  - service ID: `srv-d7ako4ggjchc73eh8g70`
  - build SHA: `68a6442d7608fad525617c7069790a9d385feb9f`
- Local release gates passed before deployment:
  - backend lint for changed idempotency, picking, receiving, tasks, and
    migration files
  - `pytest tests/test_regressions.py -q -k "idempotency_key or assigned_pick_task"`
  - `pytest tests/test_regressions.py -q`
  - `pytest tests/test_end_to_end_flow.py -q`
  - frontend `npm run lint` with only pre-existing warnings
  - frontend `npm run build`
  - migration gate from `010` to `011`
  - fresh startup schema bootstrap for `idempotency_records` RLS and policies
- Production verification passed after deployment:
  - `npm run smoke:production-bootstrap`
  - `npm run uat:production`
    - batch: `UAT-20260505-01`
    - evidence tenant:
      `Acceptance UAT UAT-20260505-01 Full Flow uat64481698`
    - backend build SHA:
      `68a6442d7608fad525617c7069790a9d385feb9f`
    - receiving packages: `2`
    - putaway tasks: `2`
    - final outbound status: `shipped`
    - tracking persisted: `true`
    - billing total: `5.75`
    - browser console errors: `0`
  - `npm run audit:production-pages`
    - checked pages/viewports: `70`
    - failures: `0`
    - console errors: `0`
  - `npm run smoke:receiving-putaway`
  - `npm run smoke:pack-completeness`
  - `node ./scripts/verify-shipping-flow.mjs`
  - `npm run uat:mobile-receiving`
  - `npm run smoke:receiving-package-fallback`
  - `npm run uat:production:cleanup`
- Production cleanup confirmed:
  - first cleanup removed `5` test tenants and `101` tenant-scoped rows
  - final cleanup removed `5` more smoke/mobile test tenants and `92`
    tenant-scoped rows
  - final dry-run showed test tenant candidates `0`, test rows `0`, and
    preserved operational rows deleted `0`
- CI and final backend deployment reconciliation:
  - GitHub CI initially caught a backend import-order issue in
    [backend/app/models/__init__.py](/Volumes/MaxRelocated/WMS/backend/app/models/__init__.py);
    the fix was committed as
    `23bd74d343db78d4bcd57f741ca541d16c293aaa`.
  - GitHub CI run `25363290180` passed:
    backend ruff, mypy, full tests, frontend typecheck, and frontend build.
  - Render backend deploy run `25363290252` passed, and production `/health`
    returned build SHA
    `23bd74d343db78d4bcd57f741ca541d16c293aaa`.
  - Production smoke on this final SHA passed with bootstrap tenant
    `BTBOOT013472`.
  - Production UAT on this final SHA passed with evidence tenant
    `Acceptance UAT UAT-20260505-01 Full Flow uat66204170`,
    final outbound status `shipped`, billing total `5.75`, tracking persisted,
    all page checks true, and browser console errors `0`.
  - Final cleanup removed `3` test tenants and `88` tenant-scoped rows; final
    dry-run again showed test tenant candidates `0`, test rows `0`, and
    preserved operational rows deleted `0`.
- Known non-blocking migration limitation remains: a completely blank database
  cannot run the full historical Alembic chain from `base` because the older
  `001_enable_rls.py` migration assumes application tables already exist. The
  supported current fresh environment path is application startup schema
  bootstrap plus migration stamp; a future baseline migration can remove this
  legacy limitation.

### 2026-05-05 workspace consolidation completed

- Confirmed the active WMS engineering workspace is:

  ```text
  /Volumes/MaxRelocated/WMS
  ```

- Found a duplicate old workspace at `/Volumes/ORICO/WMS`. It was an older Git
  working copy on branch `codex/receiving-backend-sync`, with uncommitted
  putaway/backend sync changes and several old docs/drawing files.
- Preserved the old copy before removing the naming collision:
  - copied CARQUEST layout drawings into
    [`docs/assets/warehouse-layouts/carquest/`](/Volumes/MaxRelocated/WMS/docs/assets/warehouse-layouts/carquest/)
  - saved the old working-copy diff, status, recent log, legacy docs, and old
    Claude/README notes under
    [`docs/archive/orico-wms-20260505/`](/Volumes/MaxRelocated/WMS/docs/archive/orico-wms-20260505/)
  - verified the copied drawing files by SHA-256 checksum
- Renamed the full old ORICO copy to:

  ```text
  /Volumes/ORICO/_archived_20260505/orico-old-workcopy
  ```

- Confirmed `/Volumes/ORICO/WMS` no longer exists and `find /Volumes -maxdepth
  3 -type d -name WMS` now returns only `/Volumes/MaxRelocated/WMS`.
- Cleaned stale deployment docs by moving AWS Activate and early Vercel/Render
  notes into
  [`docs/archive/legacy-deployment/`](/Volumes/MaxRelocated/WMS/docs/archive/legacy-deployment/).
  Current deployment truth remains
  [`docs/10-render-deploy-operations.md`](/Volumes/MaxRelocated/WMS/docs/10-render-deploy-operations.md)
  and
  [`docs/13-engineering-environment.md`](/Volumes/MaxRelocated/WMS/docs/13-engineering-environment.md).

### 2026-05-05 mobile action-first page pass started

- Committed the page-style operating rules in
  [`docs/09-action-first-page-discipline.md`](/Volumes/MaxRelocated/WMS/docs/09-action-first-page-discipline.md)
  and extended the manual UAT packet in
  [`docs/20-manual-uat-checklist.md`](/Volumes/MaxRelocated/WMS/docs/20-manual-uat-checklist.md).
- Multi-model review split:
  - DeepSeek reviewed Receiving as the mobile template.
  - Qwen reviewed Putaway/Picking/Shipping alignment.
  - Kimi reviewed Dashboard next-work routing.
  - MiniMax reviewed Inventory/Billing/Master Data simplification.
- Implemented the first low-risk UI pass:
  - Receiving mobile success state now says what was confirmed and whether the
    next action is print label, scan next package, putaway, or inbound review.
  - Dashboard mobile next-work card now includes why that action matters before
    routing the operator onward.
  - Putaway success feedback now names the next step and can open the next task.
  - Inventory mobile lookup now states the current question and next action
    while keeping filters/details secondary.
- Deferred broad Billing/Master Data rewrites intentionally. Those pages remain
  desktop/iPad management surfaces for this pass; mobile simplification is
  captured as UAT policy rather than a risky release-time redesign.
- Verification passed:
  - `git diff --check`
  - `npm run lint -- --quiet`
  - `npm run build`

### 2026-05-05 mobile action-first follow-up completed

- Ran a five-way model split for the follow-up plan:
  - DeepSeek reviewed production smoke criteria for Dashboard, Receiving,
    Putaway, and Inventory.
  - Qwen reviewed durable selectors and automated script coverage.
  - Kimi reviewed low-risk Picking and Shipping success-transition alignment.
  - MiniMax reviewed the focused mobile UAT packet and blocker criteria.
  - All four reviewed the desktop-first mobile simplification boundary for
    Billing, Client settings, and SKU master data.
- Added stable mobile action-first selectors and script coverage:
  - `audit:action-first-mobile` verifies Dashboard next work, Dashboard why-now,
    Inventory current question/next action, and desktop-first notices on
    Billing, Clients, and SKUs.
  - `uat:mobile-receiving` now requires a next-step instruction after receipt
    confirmation.
  - `smoke:receiving-putaway` now requires Putaway success to explain the next
    step when the success panel is visible.
- Extended UI feedback:
  - Picking completion now has a first-class next-step panel pointing to
    Shipping.
  - Shipping pack and ship success messages now say what to do next.
  - Billing, Client settings, and SKU master data phone views now show explicit
    management-workspace notices, while leaving desktop/iPad behavior intact.
- Updated the UAT packet to capture device model/OS, mobile action-first
  evidence, and P0/P1/P2 blocker definitions for phone scenarios.
- Local verification passed:
  - `git diff --check`
  - `npm run lint -- --quiet`
  - `npm run build`

### 2026-05-05 production action-first release gate closed

- Ran the final multi-model coordination split for plan items 1 through 5:
  - DeepSeek reviewed production page audit pass/fail criteria.
  - Qwen reviewed production UAT, cleanup, and evidence expectations.
  - Kimi reviewed Picking/Shipping next-step assertion strategy.
  - MiniMax reviewed manual UAT packet, blocker tracking, cleanup, and release
    closeout evidence.
- Production page audit passed against
  `https://app.maxsmartwms.online` and
  `https://api.maxsmartwms.online/api/v1`:
  - checked pages: `70`
  - failures: `0`
  - console errors: `0`
  - portal audit: checked
  - platform audit: checked
  - layout audit tenant: `Layout Audit layout77850110`
- Formal production UAT passed after adding the Picking UI next-step assertion:
  - batch: `UAT-20260505-01`
  - evidence tenant:
    `Acceptance UAT UAT-20260505-01 Full Flow uat78067781`
  - production backend health build SHA:
    `7efbbe196ab230b99305ab45f788700eba6d9359`
  - receiving package count: `2`
  - putaway tasks created: `2`
  - inventory after putaway: `5`
  - inventory after rejected over-pick: `5`
  - inventory after ship flow: `3`
  - shortage release blocked: `true`
  - over-pick rejected: `true`
  - Picking success next-step visible: `true`
  - final outbound status: `shipped`
  - tracking persisted: `true`
  - billing total: `5.75`
  - all page checks: `true`
  - browser console errors: `0`
- Strengthened Shipping release evidence:
  - Shipping pack success and ship success now include explicit next-step
    instructions in English, Traditional Chinese, Spanish, Hungarian, and
    German.
  - [frontend/scripts/verify-shipping-flow.mjs](/Volumes/MaxRelocated/WMS/frontend/scripts/verify-shipping-flow.mjs)
    now asserts both pack and ship success next-step feedback with a
    multilingual pattern.
  - Local production preview plus production API passed the Shipping flow:
    pack action visible, ship action visible, single-SKU pack check complete,
    pack next-step visible, ship next-step visible, tracking scan persisted,
    mobile recovery hid unsafe pack actions, horizontal overflow `0`, and final
    order status `shipped`.
- Final CI and deployment evidence:
  - commit: `03b76af` (`Close action-first release gates`)
  - GitHub CI run `25372075326` passed:
    backend ruff, mypy, full tests, frontend typecheck, and frontend build.
  - Vercel production deployment
    `dpl_eq8mtPo3jpaHjxgd8vSWfro4QZB7` was promoted to
    `https://app.maxsmartwms.online`.
  - Production Shipping gate passed on the deployed bundle:
    pack next-step visible `true`, ship next-step visible `true`, tracking
    persisted, mobile recovery hid unsafe actions, horizontal overflow `0`, and
    final order status `shipped`.
- Final local release checks passed:
  - `git diff --check`
  - `npm run lint -- --quiet`
  - `npm run build`
- Production test data cleanup passed:
  - initial release cleanup deleted test tenants: `5`
  - initial release cleanup deleted tenant-scoped rows: `130`
  - post-deployment Shipping cleanup deleted test tenants: `1`
  - post-deployment Shipping cleanup deleted tenant-scoped rows: `16`
  - preserved operational rows deleted: `0`
  - final dry-run test tenant candidates: `0`
  - final dry-run test rows: `0`
- Handoff note for the next product line:
  - Mobile execution gates now cover Dashboard next work, Receiving confirmation,
    Putaway success, Picking success, and Shipping pack/ship success.
  - The next design/product line can focus on deeper Inventory and Dashboard
    recommendation logic, with Billing/Master Data remaining desktop-first
    management surfaces unless a dedicated mobile admin workflow is scoped.

### 2026-05-05 Dashboard and Inventory mobile recommendation pass

- Ran a four-model review split for the next product line:
  - DeepSeek reviewed conservative Dashboard priority rules.
  - Qwen reviewed Inventory mobile execution focus.
  - Kimi reviewed stable automation selectors.
  - MiniMax reviewed frontend-only release risk and UAT evidence.
- Dashboard mobile next work now uses a conservative data-prioritized queue
  instead of only the static operations order:
  - Receiving wins when inbound is pending.
  - Putaway wins when staged tasks are pending after receiving pressure.
  - Picking wins when outbound work is pending after inbound/putaway pressure.
  - Inventory wins when no live queue is pressing but stock exists.
  - Setup and no-work remain explicit fallback states.
- Dashboard automation now reads stable attributes from the mobile next-work
  surface:
  - `data-recommended-route`
  - `data-recommended-key`
  - `data-recommended-priority`
- Inventory mobile first screen now chooses one recommended action from existing
  frontend state:
  - setup
  - staging
  - blocked
  - allocated
  - selected record count
  - available stock lookup
  - empty/receiving fallback
- Inventory detailed filters, record details, and history remain secondary; the
  desktop management table is unchanged.
- Local preview plus production API verification passed:
  - `WMS_AUDIT_APP_URL=http://127.0.0.1:4178 npm run audit:action-first-mobile`
  - checked Dashboard, Inventory, Billing, Clients, and SKUs
  - Dashboard recommendation exposed a stable route/key/priority
  - Inventory recommendation exposed a stable action key
  - mobile horizontal overflow checks passed
- Production cleanup after the failed production-bundle probe and local preview
  audit deleted `2` test tenants and `4` tenant-scoped rows; preserved
  operational rows deleted remained `0`.
- Final deployment evidence:
  - commit: `942d3dc` (`Prioritize mobile dashboard and inventory actions`)
  - GitHub CI run `25372707291` passed:
    backend ruff, mypy, full tests, frontend typecheck, and frontend build.
  - Vercel production deployment
    `dpl_5QH6wfjirwvrepgTGEoMf8hMVppG` was promoted to
    `https://app.maxsmartwms.online`.
- Production `npm run audit:action-first-mobile` passed against the deployed
    bundle, including Dashboard recommendation route/key/priority and Inventory
    recommended action key.
  - Post-deployment cleanup deleted `1` test tenant and `2` tenant-scoped rows;
    final dry-run showed test tenant candidates `0`, test rows `0`, and
    preserved operational rows deleted `0`.

### 2026-05-06 Agent Evidence And Skill Contract Gate

- Closed the first agent write-gate batch after the CLI/Skill enablement plan:
  - Evidence persistence landed through `agent_evidence`, including tenant
    scope, payload hash, token hash, before/after state, planned request,
    result, expiry, and execution status.
  - Receiving live preview now persists an evidence record and returns a
    server-generated confirmation token plus `evidence_id`.
  - Agent Receiving confirmation now requires the live-preview token, matching
    payload hash, matching persisted evidence token hash, non-expired preview,
    and `X-Idempotency-Key`.
  - The normal operator UI receive endpoint remains unchanged; the new confirm
    endpoint is the agent-specific write gate.
  - Putaway now has CLI dry-run planners for `next`, `confirm`, and `block`,
    while production Putaway execution remains disabled for agents.
- Agent operating documentation was updated:
  - [docs/06-agent-console-spec.md](/Volumes/MaxRelocated/WMS/docs/06-agent-console-spec.md)
    now describes persisted evidence for the first Receiving write gate.
  - [docs/24-agent-capabilities-reference.md](/Volumes/MaxRelocated/WMS/docs/24-agent-capabilities-reference.md)
    documents the enabled Receiving write gate and Putaway dry-run commands.
  - [docs/25-cli-reference.md](/Volumes/MaxRelocated/WMS/docs/25-cli-reference.md)
    records Receiving confirmation execution requirements and Putaway dry-run
    behavior.
  - [docs/26-wms-agent-operator-sop.md](/Volumes/MaxRelocated/WMS/docs/26-wms-agent-operator-sop.md)
    and
    [.codex/skills/wms-agent-operator/SKILL.md](/Volumes/MaxRelocated/WMS/.codex/skills/wms-agent-operator/SKILL.md)
    now cover Receiving, Putaway, Picking, Shipping, and Inventory, with
    prohibited actions and disabled write boundaries made explicit.
- Agent contract verification was strengthened:
  - `frontend/scripts/verify-agent-operation-contract.mjs` now checks Skill
    presence, five-workflow SOP coverage, prohibited-action language, disabled
    write coverage, CLI capabilities, dry-run behavior, and production guard
    rejection.
- Verification and release evidence:
  - commit: `be4ac3f` (`Persist agent evidence for receiving write gate`)
  - GitHub CI run `25441686516`: passed.
  - Render Backend Deploy run `25441686617`: passed.
  - production health: `ok`, build SHA
    `be4ac3fbb00c3a77adfcb9153cdf7b0da55041ed`, branch `main`.
  - local verification before push:
    `backend/tests/test_regressions.py` `137 passed`, ruff passed, mypy passed,
    `npm run check:agent-contract` passed, `git diff --check` passed.
- Next agent-operability work:
  - A line: Putaway production write gate using the same persisted evidence
    pattern as Receiving.
  - B line: Picking and Shipping CLI dry-run planners and recovery output.
  - C line: Inventory count/adjust dry-run planners with risk, permission,
    evidence, and recovery contracts.
  - D line: keep Skill/Docs/Contract guard updated as each command family is
    enabled.
  - E line: add a production agent smoke that captures capability discovery,
    health, preview/dry-run results, contract checks, and build SHA evidence.

### 2026-05-06 Agent Dry-Run Expansion And Production Smoke

- Continued the parallel A/B/C/E plan after the Skill contract gate:
  - B line completed for the first dry-run batch:
    - `wms picking next --dry-run`
    - `wms picking next --dry-run --live-preview`
    - `wms picking confirm --dry-run`
    - `wms picking short --dry-run`
    - `wms shipping next --dry-run`
    - `wms shipping pack --dry-run`
    - `wms shipping ship --dry-run`
  - C line completed for the first dry-run batch:
    - `wms inventory count --dry-run`
    - `wms inventory adjust --dry-run`
    - `wms inventory hold --dry-run`
  - E line completed for the first production smoke:
    - `npm run smoke:agent-production` captures production health/build SHA,
      local capability discovery, and representative Picking, Shipping, and
      Inventory dry-run evidence.
- CLI capability discovery now reports `30` commands and marks the new Picking,
  Shipping, and Inventory planners as `dry-run-only`.
- Documentation and guard updates:
  - [docs/24-agent-capabilities-reference.md](/Volumes/MaxRelocated/WMS/docs/24-agent-capabilities-reference.md)
    now documents Picking, Shipping, and Inventory dry-run capabilities.
  - [docs/25-cli-reference.md](/Volumes/MaxRelocated/WMS/docs/25-cli-reference.md)
    now includes command examples and the production agent smoke command.
  - [docs/26-wms-agent-operator-sop.md](/Volumes/MaxRelocated/WMS/docs/26-wms-agent-operator-sop.md)
    now points agents to the documented dry-run command families.
  - `frontend/scripts/verify-agent-operation-contract.mjs` now asserts the new
    command families are present and return non-mutating planner output.
- Verification:
  - `npm run check:agent-contract`: passed.
  - `npm run smoke:agent-production`: passed.
  - Representative CLI dry-runs for `shipping ship`, `inventory adjust`, and
    `picking short`: passed.
  - `git diff --check`: passed.
- Production smoke evidence:
  - backend health status: `ok`
  - production build SHA:
    `be4ac3fbb00c3a77adfcb9153cdf7b0da55041ed`
  - branch: `main`
- Remaining A line:
  - Putaway production write gate still needs backend preview/evidence/token
    validation before agent execution can be enabled. The current Putaway
    command remains dry-run-only.

### 2026-05-06 Putaway Agent Write Gate

- Completed A line for the first Putaway agent write gate:
  - `POST /api/v1/fulfillment/putaway/confirm/preview` validates task state,
    source staging stock, destination policy, and allocations through the
    existing Putaway service, then rolls back business-state changes.
  - Successful live preview persists an `agent_evidence` record and returns a
    `put-confirm:*` confirmation token plus `evidence_id`.
  - `POST /api/v1/fulfillment/putaway/confirm/agent` requires the preview
    token, matching persisted token hash, matching payload hash, non-expired
    evidence, and `X-Idempotency-Key`.
  - The normal product UI endpoint `POST /api/v1/fulfillment/putaway/confirm`
    remains unchanged.
  - `node tools/wms.mjs putaway confirm --dry-run --live-preview ...` now calls
    the server preview endpoint.
  - `node tools/wms.mjs putaway confirm --confirm put-confirm:... --production-confirm --idempotency-key ...`
    now calls the agent write gate.
- Contract/docs updated:
  - Putaway capability reference now documents preview and agent execution
    gates.
  - CLI reference now records the Putaway live-preview and execution commands.
  - Agent SOP/Skill now allow Putaway execution only through the governed agent
    confirmation path.
  - Agent contract guard now verifies Putaway dry-run planner output and
    missing production guard rejection.
- Verification added:
  - Regression test confirms Putaway preview persists evidence without moving
    inventory, and token confirmation then completes the task and moves stock.

### 2026-05-06 Picking Shipping Inventory Agent Write Gates

- Completed the next agent-operability pass:
  - Added a shared `AgentEvidenceService` for canonical payload hashing,
    confirmation-token hashing, preview evidence persistence, preview lookup,
    and executed/failed evidence marking.
  - Added `POST /api/v1/fulfillment/pick/confirm/preview` for live Picking
    preview with rollback, persisted evidence, and `pick-confirm:*` token
    issuance.
  - Added `POST /api/v1/fulfillment/pick/confirm/agent` for agent-only Picking
    confirmation with matching token hash, matching payload hash, non-expired
    evidence, and required `X-Idempotency-Key`.
  - Added `POST /api/v1/fulfillment/ship/confirm/preview` and
    `POST /api/v1/fulfillment/ship/confirm/agent` for agent-only Shipping ship
    confirmation.
  - Added `POST /api/v1/inventory/ops/adjust/preview` and
    `POST /api/v1/inventory/ops/adjust/agent` for agent-only Inventory
    adjustment.
  - The normal product UI endpoint `POST /api/v1/fulfillment/pick/confirm`
    remains unchanged, as do the normal Shipping and Inventory UI endpoints.
  - `node tools/wms.mjs picking confirm --dry-run --live-preview ...` now calls
    the server preview endpoint.
  - `node tools/wms.mjs shipping ship --dry-run --live-preview ...` and
    `node tools/wms.mjs inventory adjust --dry-run --live-preview ...` now call
    the server preview endpoints.
  - `node tools/wms.mjs picking confirm --confirm pick-confirm:... --production-confirm --idempotency-key ...`
    now calls the agent write gate.
  - Shipping ship and Inventory adjust now have matching `--confirm`,
    `--production-confirm`, and `--idempotency-key` CLI execution paths.
- Contract/docs updated:
  - Capability reference and CLI reference now document Picking, Shipping ship,
    and Inventory adjust preview and agent execution gates.
  - Agent SOP/Skill now allow these operations only through governed agent
    paths. This was superseded later on 2026-05-06 when Picking short,
    Shipping pack, Inventory count, and Inventory hold were enabled through
    matching agent gates.
  - Agent contract guard now verifies the new preview planner endpoints and
    missing production guard rejection.
- Parallel review outcomes at that point:
  - Shipping pack, Inventory count, and Inventory hold were held back during
    this batch, then enabled in the following Agent Gate Coverage Completion
    batch after their contracts were narrowed.

### 2026-05-06 Agent Gate Coverage Completion

- Completed the next five closure items for governed agent operation:
  - Capability discovery now exposes `agent_write_gate` metadata for every
    enabled write-capable CLI command, including preview endpoint, agent
    endpoint, and token prefix.
  - Shipping pack verification now has `POST
    /api/v1/fulfillment/pack/verify/preview` and `POST
    /api/v1/fulfillment/pack/verify/agent`, with persisted evidence,
    confirmation-token validation, payload-hash matching, and required
    `X-Idempotency-Key`.
  - Picking short-pick execution now has `POST
    /api/v1/fulfillment/pick/short/preview` and `POST
    /api/v1/fulfillment/pick/short/agent`, using a required reason and
    available quantity.
  - Inventory count now uses the canonical cycle-count path with `POST
    /api/v1/cycle-count/record/preview` and `POST
    /api/v1/cycle-count/record/agent`.
  - Inventory hold now uses the inventory rules freeze path with `POST
    /api/v1/inventory/rules/freeze/preview` and `POST
    /api/v1/inventory/rules/freeze/agent`.
- Documentation and agent skill updates:
  - Capability, CLI, SOP, and local `wms-agent-operator` skill docs now treat
    Picking short, Shipping pack, Inventory count, and Inventory hold as
    enabled only through live-preview evidence plus agent write gates.
  - Inventory release remained disabled until a separate release preview,
    evidence, idempotency, and audit contract was added in the next batch.
- Verification scope:
  - Regression coverage now confirms each new preview persists evidence without
    business-state mutation and that the matching token can execute the agent
    write path.
  - Agent contract and production smoke scripts now check enabled gate metadata,
    dry-run planner endpoints, and missing production guard rejection for the
    expanded command set.

### 2026-05-06 Agent Readiness And Inventory Release Gate

- Completed the next A-E closure pass:
  - A line: reconciled old project-plan wording so historical planner-only
    notes now point to the later enabled gates instead of contradicting them.
  - B line: added Inventory release/unfreeze preview and agent endpoints:
    `POST /api/v1/inventory/rules/unfreeze/preview` and `POST
    /api/v1/inventory/rules/unfreeze/agent`.
  - C line: added read-only diagnostic CLI/API coverage for inbound detail,
    outbound detail, inventory list, inventory transaction history, and agent
    evidence listing.
  - D line: split external-model operating guidance into focused local skills:
    `wms-receiving-operator`, `wms-fulfillment-operator`,
    `wms-inventory-operator`, `wms-release-gate-verifier`, and
    `wms-recovery-debugger`.
  - E line: added `npm run check:agent-readiness` to verify required skills,
    enabled write-gate metadata, CLI docs, and representative dry-run output.
- Inventory import, delete, and bulk mutation remain disabled for agents.

### 2026-05-06 Agent Import Preview And Evidence Diagnostics

- Completed the next 1-2 plan:
  - Added `POST /api/v1/agent/inventory/import/preview` and
    `wms inventory import preview --file ...` for read-only inventory import
    diagnosis.
  - Inventory import preview now reports suggested mapping, mapping used,
    missing fields, row-level SKU/location/client validation, operation impact
    (`create`, `update`, `noop`, `error`), quantity delta, and recovery
    guidance without writing inventory or issuing confirmation tokens.
  - Added evidence diagnostics:
    - `GET /api/v1/agent/evidence/{evidence_id}`
    - `GET /api/v1/agent/evidence/failed`
    - `GET /api/v1/agent/evidence/{evidence_id}/replay-preview`
    - matching CLI commands: `evidence detail`, `evidence failed`, and
      `evidence replay-preview`.
  - Updated inventory/recovery skills and readiness/contract checks so external
    model agents can inspect import previews and failed evidence before retrying
    any workflow.
- Boundary remains:
  - Inventory import writes, inventory delete, and bulk mutation stay disabled
    for agents.

### 2026-05-06 Local WMS Agent MVP Scaffold

- Continued the external-model operation plan by adding a local governed agent
  shell:
  - Added `local-agent/` as a separate FastAPI package with its own
    `pyproject.toml`, `.env.example`, README, and `wms-local-agent` entrypoint.
  - Implemented WMS login through `/api/v1/auth/login` and in-memory session
    storage. The WMS password is never persisted.
  - Implemented a WMS API client for `/agent/settings` and `/agent/tools/run`.
    Tool calls use the authenticated user's bearer token and the API URL chosen
    at login.
  - Added WMS skill discovery from `.codex/skills/wms-*/SKILL.md` plus simple
    intent-based skill selection.
  - Added a rule-based read router for the initial MVP: inventory, clients,
    inbound, outbound, and billing rate-card reads.
  - Added a minimal local HTML UI with signed-out, ready, quick-action, latest
    result, and logout states.
  - Added redacted local JSONL audit logging for login, logout, blocked write
    attempts, and tool results.
  - Added unit coverage for secret redaction, read/write routing, and skill
    selection.
- Boundary remains:
  - Natural-language write requests are blocked locally until a WMS preview
    returns an explicit confirmation token and a dedicated confirmation card
    executes the agent endpoint.

### 2026-05-06 Local Agent Model Adapter And Confirmation Card

- Continued the requested 1-2 local-agent plan:
  - Added a provider-neutral OpenAI-compatible model adapter for DeepSeek and
    similar chat-completions providers.
  - The model prompt receives only role, tenant id, permissions, public tool
    catalog fields, selected skill excerpts, and the current request.
  - Added tests proving WMS bearer tokens, model API keys, and hidden tool
    secrets are not included in model messages.
  - Added confirmation-card extraction for WMS preview payloads that include
    `confirmation_payload.confirmation_token`, `planned_request.endpoint`, and
    `planned_request.body`.
  - Added `POST /api/confirm` to convert a validated WMS `/preview` endpoint to
    the matching `/agent` endpoint, attach the confirmation token, and submit
    `X-Idempotency-Key`.
  - Updated the local UI to show a confirmation card with action, risk,
    evidence id, endpoint, Confirm, and Cancel when a preview payload requires
    confirmation.
  - Added unit coverage for model prompt redaction and confirmation request
    construction.
- Boundary remains:
  - Chat text alone still cannot execute writes. Confirmation requires a WMS
    preview token and a confirmation-card action.

### 2026-05-06 Local Agent Smoke, Live Dry-Run, Startup, And Skill

- Completed the requested 1-4 local-agent follow-up:
  - Added local-agent smoke coverage for unauthenticated prompt blocking,
    mocked WMS login, tool catalog loading, read routing, write-chat blocking,
    invalid confirmation rejection, valid preview-token confirmation, and audit
    redaction.
  - Added `local-agent/scripts/verify_live_dry_run.py` for optional live
    API checks. Without `LOCAL_AGENT_TEST_EMAIL` and
    `LOCAL_AGENT_TEST_PASSWORD`, it exits safely with a skipped result.
  - Added `tools/local-agent.mjs` with `start` and `smoke` commands for a
    simpler launch and verification path.
  - Added `.codex/skills/wms-local-agent-operator/SKILL.md` so other model
    agents have explicit login, read, confirmation, audit, and hard-stop
    instructions.
  - Extended the agent readiness gate to verify the new local-agent operator
    skill.
- Boundary remains:
  - Live dry-runs require explicit test credentials. Confirmation execution
    still requires WMS preview evidence, a confirmation token, and idempotency.

### 2026-05-06 Local Agent Multi-Provider Roster

- Continued the local-agent closure line:
  - Local agent config now reads a redacted backend model roster for MiniMax,
    Qwen, Kimi, and DeepSeek from `backend/.env`.
  - `/api/config` exposes provider key, label, base URL, model, configured
    status, selected provider, selected model, and source without exposing API
    keys.
  - `WMS_LOCAL_AGENT_MODEL_PROVIDER` can select a configured backend provider
    (`minimax`, `qwen`, `kimi`, or `deepseek`) for local planning; explicit
    `WMS_LOCAL_AGENT_MODEL_*` credentials still take precedence.
  - The local UI now shows the configured backend roster beside the selected
    model status.
  - README and `wms-local-agent-operator` skill now instruct external model
    agents to inspect `/api/config` before planning.
- Boundary remains:
  - Provider keys remain local secrets. `/api/config`, logs, model prompts, and
    skill instructions must expose only redacted readiness metadata.

### 2026-05-06 Settings-First Agent Reads

- Started the settings-first read roadmap from
  `docs/28-wms-agent-feature-map.md`:
  - Added governed read tool `settings.agent.get`.
  - Added CLI command `node tools/wms.mjs agent settings`.
  - The result exposes agent enabled state, provider label/type, base URL,
    model name, region, `has_api_key`, logging/training policy, confirmation
    policy, allowed tools, tool catalog, and validation status.
  - The result does not expose provider API keys.
  - Added the remaining Phase A settings read tools:
    `settings.receiving_codes.get`, `settings.receiving_labels.get`,
    `settings.users.list`, `settings.permissions.explain`,
    `settings.client_profile.get`, `settings.billing.explain`, and
    `settings.warehouse_locations.list`.
  - Added matching CLI commands under `wms settings ...`.
  - Capability and CLI references now document the settings read command set.
- Next settings-first reads:
  - Add deeper detail tools only where list/read summaries are not enough:
    individual user detail, individual warehouse detail, and rate-card detail.

### 2026-05-06 Current-Tenant Demo Reset

- Added a tenant-owned demo reset endpoint:
  - `POST /api/v1/maintenance/current-tenant/demo-data/reset`
  - Requires tenant admin role and confirmation string
    `RESET_CURRENT_TENANT_DEMO_DATA`.
  - Preserves the tenant record, users, and subscriptions.
  - Clears current-tenant business/demo rows only, then seeds a clean demo
    client, warehouse, zones, locations, SKUs, billing profile, receiving code
    rules, receiving label template, and rate card.
- Verification:
  - Regression coverage confirms old business data is removed, users and
    subscriptions remain, seeded demo entities exist, and existing agent console
    settings are preserved.
- Boundary remains:
  - This endpoint is for tenant-owned demo workspaces. It should not be used as
    a platform-wide cleanup tool.

### 2026-05-08 WCS / AGV Certification Closure

- Advanced the WCS/AGV closure plan across the six active lines:
  - Added dry-run preview support for WCS ready-vehicle config and
    quality-complete payloads, plus CLI commands
    `wcs ready-config --dry-run` and `wcs quality-complete --dry-run`.
  - Tightened Warehouse Planner WCS mapping review: all mapping rows are shown,
    virtual dock doors count as external points, and saving now requires a
    current successful validation.
  - Extended the local agent blueprint panel with local draft validation and a
    direct WMS preview action while keeping import/write confirmation separate.
  - Extended the AGV simulator with saved exchanges, local exchange replay,
    pause/resume/reset/fail smoke coverage, and consistent `stepStatus=40`
    exception semantics.
  - Recorded the latest safe Dallas certification evidence in
    `docs/34-wcs-agv-integration-plan.md`.
- Boundary remains:
  - Live WCS dispatch, production callback writes, non-validate-only mapping
    imports, and production DDL require explicit operator approval.

### 2026-05-08 WCS / AGV Closure Review

- Current release gate:
  - Commit `f74a911f14dca8b9df7feba3c5866108837dd5a6` is deployed on
    production.
  - GitHub Actions run `25558178544` passed.
  - Render deploy gate run `25558178546` passed.
  - Production `/health` returned `status=ok` for build
    `f74a911f14dca8b9df7feba3c5866108837dd5a6`.
- Documentation cleanup:
  - `docs/34-wcs-agv-integration-plan.md` now treats blueprint/WCS draft,
    WCS ready/QC preview, operator recovery visibility, and AGV simulator
    replay as completed platform work.
  - Remaining WCS work is narrowed to live sandbox certification and external
    infrastructure sign-off.
  - `docs/10-render-deploy-operations.md` now reflects local Alembic head
    `015` instead of the older `012` reference.
- Agent/CLI cleanup:
  - The installable bundled `wms-wcs-operator` skill now matches the source
    WCS skill and includes ready-config, quality-complete, point mappings, and
    live-call hard stops.
  - `npm run check:agent-readiness` now checks the source and bundled WCS
    skill plus WCS CLI capability metadata.
  - `wcs point-mappings import` now requires `--validate-only` for review or
    `--confirm-import` after explicit operator approval.
  - The current CLI capability count is 83 commands; historical command counts
    earlier in this plan are retained as point-in-time notes.
- Hard gates still open:
  - Live WCS dispatch and production callback writes still require explicit
    operator approval.
  - Production database provider, backup/restore policy, instance plan, and
    `alembic_version` remain external confirmations from trusted operator
    access.

### 2026-05-08 WCS Sandbox Certification Attempt

- Operator approval was received for WCS live sandbox certification.
- Completed platform-side certification checks are recorded in
  [35-wcs-sandbox-certification-report.md](35-wcs-sandbox-certification-report.md).
- Passed:
  - production API health;
  - Dallas WCS config read with callback URL and redacted credentials;
  - point-mapping export, validate, validate-only import, and approved
    `--confirm-import`;
  - dispatch preview gate for task `24d4420e-5110-4cf2-8f38-d63217166a89`;
  - ready-config and quality-complete previews;
  - local AGV simulator Dallas smoke with route, `20` / `25` / `30` callback
    statuses, replay `200`, and failed-task path.
- Blocker:
  - Dallas WCS base URL is still `https://wcs-simulator.invalid`, which does
    not resolve. Live external WCS dispatch, live ready-config, live
    quality-complete, production callback writes, callback idempotency, `40`
    recovery, and inventory movement verification cannot be certified until a
    reachable WCS sandbox base URL is configured.
- External infrastructure gate remains open because local `backend/.env`
  points `DATABASE_URL` at sqlite and cannot prove production Postgres schema
  state.

### 2026-05-08 WCS Sandbox Enablement Follow-up

- Multi-line review split the next blocker into two platform tasks:
  - make the AGV simulator reachable as a public WCS sandbox;
  - provide a safe CLI/API path to update Dallas WCS `base_url` and credentials
    without manual DB edits.
- Implemented:
  - `agv-simulator` WCS-compatible vendor endpoints:
    `/task/wlTaskInfo/addTransportTask`,
    `/task/wlReadyAgvRobot/editReadyConfig`, `/QualityComplete`, and
    `/loginToken`;
  - Dallas simulator smoke now covers vendor-compatible paths in addition to
    local simulator paths;
  - Render blueprint includes `wms-agv-sandbox` with `/api/health`;
  - backend adds redacted WCS config update preview/apply endpoints that
    preserve omitted secrets;
  - CLI adds `wcs config update --dry-run|--confirm-config`.
- Remaining before live certification, completed in the next section:
  - create or deploy the public `wms-agv-sandbox` service;
  - run `wcs config update --dry-run` and `--confirm-config` with the deployed
    sandbox URL;
  - rerun dispatch preview, then request approval for the live dispatch path.

### 2026-05-08 WCS Live Sandbox Certification Completion

- Created the public Render AGV sandbox service:
  - service ID `srv-d7v5s1pj2pic73e5e0v0`;
  - URL `https://wms-agv-sandbox.onrender.com`;
  - health returned `ok=true`.
- Updated Dallas WCS config through the guarded preview/apply path:
  - dry-run showed `changed_keys=["base_url"]`;
  - approved `--confirm-config` changed Dallas from
    `https://wcs-simulator.invalid` to
    `https://wms-agv-sandbox.onrender.com`;
  - redacted config read confirmed callback URL, credentials, and 128 point
    mappings remained present.
- Fixed the live callback blocker:
  - the first sandbox callback reached production but returned `404` because
    the unauthenticated webhook route had not applied tenant/RLS session
    context before matching `WcsTaskBinding`;
  - commit `5486d341e5a18d142299553f99d401dee8e69222` now applies tenant
    context in `/wcs/webhook/{tenant_id}/taskfinish` and adds a regression
    test for the endpoint path.
- Release gates for the fix passed:
  - local `ruff`, `mypy app`, full backend `pytest -q`, and `git diff --check`;
  - GitHub Actions CI run `25582133151` passed;
  - Render backend deploy run `25582133140` passed;
  - production `/health` now reports build
    `5486d341e5a18d142299553f99d401dee8e69222`.
- Certified the approved live sandbox path:
  - live dispatch created WCS task `1778278075237001` for WMS task
    `24d4420e-5110-4cf2-8f38-d63217166a89`;
  - sandbox `stepStatus=20` callback returned `200` and moved the binding to
    `in_progress`;
  - sandbox `stepStatus=30` callback returned `200`, moved the binding and WMS
    task to `completed`, and assigned the task to `agv:sim-agv-01`;
  - duplicate completion callback returned `200`, left the binding completed,
    and left exactly one putaway transaction for inbound reference
    `57f75167-061f-4e5b-93da-96418fa67c60`;
  - inventory movement verification found one AGV putaway transaction,
    quantity `5`, into `DAL-B-01-01-01-01`;
  - live sandbox ready-config and quality-complete calls both returned success.
- Remaining WCS certification items:
  - complete external production infrastructure sign-off for DB provider,
    backup/restore policy, instance plan, and production `alembic_version`.

### 2026-05-09 WCS Exception Callback Certification

- Completed the remaining WCS-specific exception certification path:
  - created a fresh Dallas sandbox move task
    `23d5d652-4ec0-4575-9f1d-dc6471a10ffe` under the approved test tenant;
  - dispatch preview gate passed for source
    `DAL-STO-DAL-A-01-01-01-01` and destination
    `DAL-STO-DAL-B-01-01-01-01`;
  - live sandbox dispatch created WCS task `1778298018550001`;
  - AGV simulator emitted `stepStatus=40`;
  - WMS accepted the callback, moved the binding and task to `failed`, set
    `retry_count=1`, and recorded `failure_reason=simulated AGV error`;
  - exception-path inventory movement remained at `0` transactions.
- WCS-specific simulator certification is now complete for:
  - dispatch preview and live dispatch;
  - running callback `20`;
  - completion callback `30`;
  - duplicate completion idempotency;
  - exception callback `40`;
  - ready-config and quality-complete sandbox calls.
- Remaining gates:
  - external production infrastructure sign-off for DB provider, backup/restore
    policy, instance plan, and production `alembic_version`;
  - vendor-specific ready-config and quality-complete field review when a real
    WCS sandbox is available.
- Follow-up improvement:
  - add a guarded API/CLI sandbox certification task factory so future WCS
    failure-path tests do not require direct Postgres test-task insertion.

### 2026-05-09 Production Infrastructure Gate Review

- Confirmed through Render CLI:
  - production backend service `srv-d7ako4ggjchc73eh8g70` is
    `wms-quickstart`, branch `main`, root `backend`, Docker runtime,
    region `oregon`, free web service plan, auto deploy enabled;
  - AGV sandbox service `srv-d7v5s1pj2pic73e5e0v0` is `wms-agv-sandbox`,
    root `agv-simulator`, Docker runtime, region `oregon`, free web service
    plan, health check `/api/health`, auto deploy enabled;
  - production database `dpg-d7akc4fkijhs73dp4ukg-a` is Render Postgres
    `WMS-VM`, database `appdb_0zfl`, Postgres `18`, plan `basic_256mb`,
    disk `15GB`, role `primary`, status `available`, high availability
    disabled, and disk autoscaling disabled.
- Confirmed through read-only `render psql` schema sampling:
  - required WCS/layout/task/agent evidence/idempotency columns are present in
    the checked contract tables;
  - RLS and forced RLS are enabled on `agent_evidence`,
    `idempotency_records`, `locations`, `tasks`, `wcs_task_bindings`, and
    `zones`;
  - production `alembic_version` still reports `003` while local head is
    `015`.
- Gate status:
  - service topology is confirmed for the current Render path;
  - production schema appears functionally healed for the checked WCS/Agent
    contract;
  - production migration provenance remains blocked until a trusted migration
    plan either advances/stamps Alembic safely or documents why startup schema
    healing remains the accepted production path.
- Still needs external dashboard confirmation:
  - workspace plan and backup/PITR recovery window;
  - latest successful backup/export and restore owner;
  - whether free web service plans and disabled HA/disk autoscaling are
    acceptable for the first real customer release.

### 2026-05-09 Multi-Line Gate Follow-Up

- A line, Alembic/schema:
  - expanded the read-only schema contract to cover the missing 004-015
    migration surface, including `pick_allocations`, outbound readiness ranks,
    performance indexes, WCS unique task index, and `pick_allocations` RLS;
  - production expanded audit found no missing checked columns, but found one
    missing index
    `ix_outbound_orders_tenant_warehouse_shipping_readiness_created_desc` and
    `pick_allocations` RLS/forced RLS disabled;
  - `alembic_version` remains `003`, so the recommended path is backup
    confirmation -> targeted idempotent DDL -> read-only contract rerun ->
    `alembic stamp head` only after zero schema gaps.
- B line, infrastructure:
  - Render CLI confirms service and database topology;
  - backup/PITR window, latest backup/export, restore owner, and acceptance of
    free web service plans plus disabled HA/disk autoscaling remain dashboard
    sign-off items.
- C line, WCS certification task factory:
  - added tenant-admin guarded preview/create endpoints and CLI command
    `wms wcs certification task --dry-run|--confirm-create`;
  - the factory creates only an internal pending AGV `move` task with
    `reference_type=wcs_sandbox_cert` and never dispatches to WCS;
  - WCS operator skills and agent readiness checks now include the new command.

### 2026-05-09 Production Schema Gap Patch Prepared

- Prepared the explicit production-only SQL patch at
  [`backend/scripts/prod_schema_gap_patch_20260509.sql`](/Volumes/MaxRelocated/WMS/backend/scripts/prod_schema_gap_patch_20260509.sql).
- The script is intentionally not wired into startup, CI, or Render deploys. It
  must only be run after Render/Postgres backup or PITR readiness is confirmed
  in the Dashboard.
- A follow-up Render `psql` read-only snapshot showed
  `ix_outbound_orders_tenant_warehouse_shipping_readiness_created_desc` is now
  present, while `pick_allocations` RLS remains `false/false`.
- Scope is now limited to the remaining RLS gap: enable and force
  `pick_allocations` RLS with tenant isolation and platform-admin bypass
  policies.
- After the script runs, rerun `backend/scripts/check_schema_contract.py`
  against production. Only if it reports zero missing schema/RLS/index gaps
  should the team consider stamping production Alembic to local head `015`.

### 2026-05-09 Production RLS Patch Executed

- Operator approval was received and the `pick_allocations` RLS patch was
  executed through Render CLI using `render psql ... -c`.
- Post-patch read-only verification:
  - `pick_allocations` RLS and forced RLS are now `true/true`;
  - `tenant_isolation` and `admin_bypass` policies are present;
  - required RLS table failures are `<none>`;
  - production `alembic_version` remains `003`.
- Production health and `npm run smoke:agent-production` passed on backend
  build `5091de5a00d0108c8a78fa115acdfbaadf9dab7a`.
- During verification, PostgreSQL exposed the outbound readiness index under
  its 63-character truncated identifier
  `ix_outbound_orders_tenant_warehouse_shipping_readiness_created_`. The schema
  contract checker now accepts that PostgreSQL alias for the intended Alembic
  index name.
- Remaining migration-provenance item: decide whether to stamp production
  Alembic to local head `015` now that the checked schema/index/RLS gaps are
  resolved.

### 2026-05-09 Alembic Stamp Gate Prepared

- Prepared guarded source SQL at
  [`backend/scripts/prod_alembic_stamp_015_20260509.sql`](/Volumes/MaxRelocated/WMS/backend/scripts/prod_alembic_stamp_015_20260509.sql).
- The stamp script is a provenance update only; it does not replay migrations.
- Guard conditions:
  - production `alembic_version` must be exactly `003`, or already `015` for a
    no-op;
  - required index set must be present, including the PostgreSQL 63-character
    truncated alias for the outbound shipping readiness index;
  - required RLS tables must have RLS enabled and forced.
- Current read-only production gate before stamp:
  - `missing_indexes=<none>`;
  - `rls_failures=<none>`;
  - `alembic_version=003`;
  - production health is `ok` on backend build
    `08393e89f3a71905cf8c3ec6eb33dfdc4bc5bf1d`.
- The actual stamp remains pending explicit operator approval because it writes
  production migration metadata.

### 2026-05-09 Production Alembic Stamp Completed

- Operator approved the production Alembic stamp to local head `015`.
- Executed the guarded stamp SQL through Render CLI. The guard passed and
  `alembic_version` now reports `015`.
- Final production schema gate:
  - `missing_indexes=<none>`;
  - `rls_failures=<none>`;
  - `alembic_version=015`.
- Production health passed on backend build
  `84ee9610a4600dd8b2ca89b7d817acb2c514baff`.
- `npm run smoke:agent-production` passed after the stamp.
- Migration-provenance gate is now closed for the checked WCS/Agent production
  schema surface.

### 2026-05-09 WCS Vendor Field And Infrastructure Review

- Completed the WCS vendor field review against the provided
  `AGV/WCS接口API.html` contract:
  - ready-config path `/task/wlReadyAgvRobot/editReadyConfig` requires
    `wrarSign`, `wrarApiSign`, and `wrarApiNum`;
  - quality-complete path `/QualityComplete` accepts `wtaskstepTid`,
    `wtaskinfoPsn`, `qualityStatus`, `unqualifiedBuffer`, and `params`;
  - production preview commands returned `writes=false` and matched those
    field names.
- Conclusion: no adapter field variant is required for the provided WCS API
  document. Re-open this item only if the live vendor sandbox differs from that
  contract.
- Added read-only Render CLI evidence to the deployment runbook:
  - backend service `wms-quickstart` / `srv-d7ako4ggjchc73eh8g70`, Docker,
    `backend`, `main`, Oregon, one instance, free plan, commit auto-deploy;
  - AGV sandbox service `wms-agv-sandbox` /
    `srv-d7v5s1pj2pic73e5e0v0`, Docker, `agv-simulator`, health check
    `/api/health`;
  - production database Render Postgres `WMS-VM`,
    `dpg-d7akc4fkijhs73dp4ukg-a`, plan `basic_256mb`, 15 GB, Postgres 18,
    status `available`;
  - `render psql WMS-VM` confirms production `alembic_version=015`.
- Previously remaining infrastructure gate items were accepted in the
  follow-up signoff below: PITR availability, restore owner, and
  release-window acceptance of the current free one-instance backend plan.

### 2026-05-09 Production Infrastructure Signoff Accepted

- Render CLI/API evidence confirms:
  - production database `WMS-VM` is Render Postgres, status `available`, plan
    `basic_256mb`, Postgres 18, 15 GB disk;
  - Render API recovery status is `AVAILABLE`, with
    `startsAt=2026-05-05T09:00:08Z`;
  - production `alembic_version=015`.
- Operator accepted the current release/test-stage infrastructure posture:
  - restore owner: current Render account `Max Wu <wuqxmark@gmail.com>`;
  - backend `free` one-instance service plan accepted for the current
    release/test stage;
  - Render Postgres `basic_256mb` accepted for the current release/test stage.
- Production infrastructure gate is now passed for the current release/test
  stage.
- Follow-up before irreplaceable customer data or sustained production traffic:
  create an on-demand logical export if a downloadable archive is required in
  addition to PITR, and revisit the backend service plan before any SLA or
  sustained production traffic commitment.

### 2026-05-09 Render Logical Export Created

- Operator requested completion of the pre-real-data logical export step.
- Render API `POST /v1/postgres/dpg-d7akc4fkijhs73dp4ukg-a/export` returned
  `202`, indicating the export request was accepted.
- Follow-up polling of `GET /v1/postgres/dpg-d7akc4fkijhs73dp4ukg-a/export`
  confirmed the export is listed:
  - export id: `dpg-d7akc4fkijhs73dp4ukg-a/2026-05-09T15:10Z`;
  - created at: `2026-05-09T15:10:00Z`.
- This closes the pre-real-data downloadable logical export gate. If an
  off-platform archive is required, download and retain this export from the
  Render Recovery page before it expires.

### 2026-05-09 Final Release Gate After Infrastructure Signoff

- Final release gate passed after operator accepted the infrastructure posture.
- Production health:
  - `https://api.maxsmartwms.online/health` returned `status=ok`;
  - build `84ee9610a4600dd8b2ca89b7d817acb2c514baff`;
  - service `srv-d7ako4ggjchc73eh8g70`.
- Production schema/RLS/Alembic:
  - `alembic_version=015`;
  - RLS and forced RLS are enabled for `agent_evidence`,
    `idempotency_records`, `locations`, `pick_allocations`, `tasks`,
    `wcs_task_bindings`, and `zones`.
- Latest CI on `main` remained green:
  - `25602547508` / `Record WCS vendor field review`.
- Production agent smoke:
  - `npm --prefix frontend run smoke:agent-production`: passed;
  - failures: `[]`.
- AGV simulator smoke:
  - `npm --prefix agv-simulator run smoke:dallas`: passed;
  - route rendering, WCS callback statuses, exchange replay `200`,
    ready-config, quality-complete, and failed-task coverage were exercised.
- Current closure state:
  - WCS/AGV sandbox certification is closed for the provided vendor contract;
  - production schema and migration provenance gates are closed;
  - infrastructure gate is accepted for the release/test stage;
  - remaining follow-up is operational, not a blocker: create a logical export
    before irreplaceable customer data if a downloadable archive is required,
    and revisit service plans before sustained production traffic or SLA
    commitment.

### 2026-05-13 AGV Planning Standard Added

- Operator provided the AGV field drawing guide V1.0 as the source standard for
  future warehouse planning and AGV route design.
- Added `docs/36-agv-planning-standard.md` with:
  - field-survey inputs;
  - CAD layer, scale, drawing-order, and annotation rules;
  - AGV safety clearance and aisle-width thresholds;
  - one-way loop, intersection, wait-zone, crossing, charging, and station
    placement rules;
  - rack-storage, standard-pallet slot, location-code, and allocation rules;
  - floor-storage lane and batch-isolation rules for pallet-jack/forklift AGV;
  - WMS metadata requirements for storing physical dimensions, drawing
    coordinates, AGV accessibility, aisle policy, docking direction, route role,
    safety assumptions, and unresolved field-survey assumptions.
- `docs/34-wcs-agv-integration-plan.md` now points layout generation, WCS
  point-code draft generation, and AGV route planning to this standard.
- The WCS operator skill in `wms-agent/skills` and the bundled local-agent copy
  now instruct agents to reference this standard before layout, route, station,
  or WCS point-mapping work.

### 2026-05-13 Dallas AGV Layout v2 Implementation

- Rebuilt the Dallas warehouse plan against the new AGV standard:
  - `DAL-A`, `DAL-B`, and `DAL-C` are customer-cargo-sized floor-storage
    areas, not GMA slots;
  - the west side is enclosed, so A now exposes a 12 ft non-storage `A-CONN`
    connector and 16 visible 6 ft x 5 ft x 9 ft slots for 68 x 58 x 100 in
    cargo;
  - B/C each expose 16 visible 9 ft x 5 ft x 9 ft slots for 104 x 55 x 98 in
    cargo plus clear residual bands in the map;
  - ABC horizontal allocation remains 120 ft total
    (`A-CONN 12 ft + A 28 ft + B 40 ft + C 40 ft`), and the 34 ft
    rack-to-ABC depth is now `upper AGV aisle 12 ft + floor-storage depth
    22 ft`; the lower AGV lane is outside ABC storage and does not consume
    that original depth;
  - AGV routes stay outside A/B/C floor-storage slots; `A-CONN` connects the
    upper aisle to the lower lane through non-storage space carved from A;
  - `ABC-LOWER` is a non-storage AGV lane below A/B/C and may be used as the
    controlled return/travel area back toward the dock corridor;
  - only `DAL-RACK`, the top row near the office, is 4-level rack storage;
  - `DOCK-23` through `DOCK-30` are external dock-door transport interfaces,
    not warehouse storage locations;
  - the drive aisle and dock corridor are route/reference areas.
- The AGV simulator now exposes Dallas layout v2 with route nodes,
  controlled one-way AGV paths, wait/charge stations, slow zones, and safety
  boundaries. Its UI renders the map on a scrollable/full-screen canvas.
- The simulator dynamically generates the Dallas WCS draft:
  - 108 storage points;
  - 8 external dock-door points;
  - 3 AGV station/buffer points.
- Backend `warehouse.blueprint.preview` and confirmed blueprint writes now
  accept and persist:
  - `planning_standard`, `route_policy`, `route_nodes`, `agv_paths`,
    `stations`, and `safety_zones`;
  - route metadata on zones and generated locations;
  - station and external-point WCS metadata.
- The local agent blueprint draft now emits the same AGV planning fields,
  includes station WCS points, and carries route metadata in WCS mapping
  drafts.

### 2026-05-14 Dallas CAD/Rack Detail Closure

- Closed the current Dallas CAD annotation pass after operator confirmation of
  the office-side rack parameters:
  - `DAL-RACK` remains the only rack-storage zone near the office;
  - rack layout is 15 bays x 4 levels = 60 rack storage points;
  - each rack level uses 65 in clear height;
  - rack depth is based on GMA pallet depth, 40 in / 3.33 ft;
  - GMA pallet footprint is recorded as 48 in x 40 in.
- Updated the Dallas AGV simulator fixture so rack dimensions are stored with
  the layout data, including `bay_count`, `bay_width_ft`,
  `level_clear_height_in`, `level_clear_height_ft`, `pallet_width_in`,
  `pallet_depth_in`, and `pallet_depth_ft`.
- Updated the local agent blueprint prompt/parser so future generated Dallas
  layouts can carry the same rack dimensions into blueprint payloads and WCS
  draft metadata.
- Added repeatable CAD export support:
  - `npm --prefix agv-simulator run cad:dallas` generates
    `exports/dallas-agv-layout-v2-cad.dxf`;
  - `npm --prefix agv-simulator run cad:dallas:rack` generates
    `exports/dallas-rack-detail-v1-cad.dxf`.
- Main CAD plan now keeps rack text short in the drawing body and puts detailed
  rack height/depth information in the right-side dimension ledger to avoid
  label overlap.
- A separate rack detail DXF now shows:
  - rack front elevation;
  - side profile with 40 in GMA depth;
  - GMA pallet footprint reference;
  - rack data panel with 65 in level height and 60 storage-point count.
- Added `docs/37-cad-layout-export-standard.md` and linked the standard into
  the AGV layout planner workflow. The standard now requires separate detail
  sheets when rack/equipment dimensions would crowd the main plan.
- Generated artifact check:
  - `exports/dallas-agv-layout-v2-cad.dxf` exists and includes
    `Level 65in; depth 40in GMA`, `Rack level clear height: 65in`, and
    `Rack depth: GMA pallet depth 40in`;
  - `exports/dallas-rack-detail-v1-cad.dxf` exists and includes
    `DAL-RACK detail - rack near office`, `Depth 40in GMA`, `RACK DATA`, and
    the GMA pallet footprint notes.
- This closes the current CAD/rack documentation and artifact confirmation
  step. The next main-line step is a full gate pass across simulator smoke,
  backend blueprint regression, agent readiness, and local-agent static tests.

### 2026-05-14 Dallas CAD/Rack Gate Verification

- Completed the planned local gate pass for the Dallas CAD/rack closure.
- AGV simulator and CAD gates passed:
  - `npm --prefix agv-simulator run check`;
  - `npm --prefix agv-simulator run cad:dallas`;
  - `npm --prefix agv-simulator run cad:dallas:rack`;
  - `npm --prefix agv-simulator run smoke:dallas`.
- Dallas simulator smoke evidence:
  - layout: `Dallas AGV standard layout v2`;
  - mapping count: 119;
  - storage points: 108;
  - dock points: 8;
  - station points: 3;
  - exchange replay returned `200`;
  - WCS callback statuses covered `20`, `25`, and `30`.
- Backend blueprint focused regression passed:
  - `uv run pytest tests/test_regressions.py::test_agent_warehouse_blueprint_preview_and_confirm_create_dallas_layout -q`.
- Agent readiness gate passed:
  - `npm --prefix frontend run check:agent-readiness`;
  - WCS command metadata covered config, config update, certification task,
    bindings, gate-check, dispatch, callback replay, ready-config,
    quality-complete, point-mapping list/validate/import.
- Local agent static gate passed:
  - `cd wms-agent && uv run pytest tests/test_local_agent_static.py`;
  - result: 6 tests passed.
- Artifact spot-check passed:
  - main CAD includes `Level 65in; depth 40in GMA`,
    `Rack level clear height: 65in`, and
    `Rack depth: GMA pallet depth 40in`;
  - rack detail CAD includes `DAL-RACK detail - rack near office`,
    `Depth 40in GMA`, `RACK DATA`, and GMA pallet footprint references;
  - Dallas fixture and local-agent prompt include `level_clear_height_in` and
    `pallet_depth_in`.
- Workspace hygiene gate passed:
  - `git diff --check`.
- Gate conclusion:
  - Dallas CAD/rack changes are locally verified.
  - Dock doors remain external transport points, not WMS storage locations.
  - WCS draft still separates storage, dock, and station/buffer points.
  - Next main-line step is to create customer-reviewable PDF/PNG previews from
    the accepted DXF artifacts.

### 2026-05-14 Dallas Customer Review Preview Export

- Completed the third main-line step by adding a repeatable customer-review
  export path for the accepted Dallas DXF/CAD artifacts.
- Added `agv-simulator/scripts/export-dallas-review-assets.mjs` and
  `npm --prefix agv-simulator run review:dallas`.
- The review export reads the Dallas fixture and writes:
  - `exports/dallas-agv-layout-v2-review.html`;
  - `exports/dallas-agv-layout-v2-review.png`;
  - `exports/dallas-agv-layout-v2-review.pdf`;
  - `exports/dallas-rack-detail-v1-review.html`;
  - `exports/dallas-rack-detail-v1-review.png`;
  - `exports/dallas-rack-detail-v1-review.pdf`.
- Review layout behavior:
  - DXF remains the CAD source of record;
  - HTML is the reproducible render source for customer previews;
  - PNG/PDF are optimized for review without requiring CAD software;
  - both PDFs export as single-page review sheets;
  - PNG exports are 3200 x 2200 for high-resolution visual review.
- Main layout review sheet includes:
  - A/B/C storage slot layout;
  - A-CONN and ABC-LOWER non-storage AGV lanes;
  - dock doors labeled as transport interfaces;
  - route direction arrows, wait point, dock wait point, charger;
  - review ledger for width split, depth split, rack height/depth, and WCS
    draft count.
- Rack detail review sheet includes:
  - front elevation for 15 bays x 4 levels;
  - 65 in level clear-height dimension;
  - side profile with 40 in GMA pallet depth;
  - GMA 48 in x 40 in pallet footprint reference;
  - rack data ledger and field-verification note.
- Verification passed:
  - `npm --prefix agv-simulator run check`;
  - `npm --prefix agv-simulator run review:dallas`;
  - generated PDFs were confirmed as one page each;
  - generated PNGs were confirmed as nonblank 3200 x 2200 files;
  - generated HTML contains the expected Dallas, rack, 65 in, GMA, dock, and
    WCS draft review text;
  - `git diff --check`.
- Next main-line step is to use the local agent/blueprint flow to regenerate
  the Dallas layout from the stored prompt and compare it against these review
  artifacts before any mapping confirm/import.

### 2026-05-14 Dallas Local Agent Blueprint Flow Verification

- Completed the fourth main-line step by regenerating the Dallas warehouse
  layout through the local agent blueprint UI path and comparing it against the
  current simulator fixture and customer-review artifacts.
- Added `wms-agent/scripts/verify-dallas-blueprint-flow.mjs`.
- The verification script:
  - opens `wms-agent/local_agent/static/index.html` with Playwright;
  - loads the stored Dallas blueprint prompt from the UI placeholder;
  - generates the draft through the same local blueprint engine used by the
    client;
  - exports `exports/dallas-local-agent-blueprint-draft.json`;
  - captures `exports/dallas-local-agent-blueprint-review.png`;
  - compares local-agent output with
    `agv-simulator/fixtures/dallas-layout-wcs-point-mapping-draft.json` and
    the current review HTML artifacts.
- Local-agent parser correction:
  - narrative context lines are no longer treated as storage zones when the
    prompt contains structured zone lines;
  - the stored Dallas prompt now includes the explicit `TOP-AISLE` non-storage
    AGV aisle;
  - warehouse-code inference now uses the first storage zone, so a leading
    access aisle such as `TOP-AISLE` does not turn Dallas into `TOP`;
  - the generated station set now includes `WAIT-TOP`, `WAIT-DOCK`, and
    `CHG-01`.
- Verification evidence from `node wms-agent/scripts/verify-dallas-blueprint-flow.mjs`:
  - warehouse code: `DAL`;
  - zones/access areas: `TOP-AISLE`, `DAL-A`, `A-CONN`, `DAL-B`, `DAL-C`,
    `DAL-RACK`, `ABC-LOWER`, `DRV`, `DOCK`;
  - generated storage locations: `108`;
  - WCS draft points: `119`;
  - WCS point roles: `108 storage`, `8 dock`, `2 buffer`, `1 agv_station`;
  - station codes: `WAIT-TOP`, `WAIT-DOCK`, `CHG-01`;
  - dock doors remain external transport interfaces and create `0` WMS storage
    locations.
- Rack and cargo dimensions were checked through the local-agent output:
  - `DAL-RACK`: 15 bays x 4 levels, 60 locations, 65 in level clear height,
    48 in x 40 in GMA pallet basis;
  - `DAL-A`: 16 locations sized 6 ft x 5 ft x 9 ft inside a 28 ft x 22 ft
    storage area;
  - `DAL-B` / `DAL-C`: 16 locations each sized 9 ft x 5 ft x 9 ft inside
    40 ft x 22 ft storage areas.
- Regression commands passed:
  - `node wms-agent/scripts/verify-dallas-blueprint-flow.mjs`;
  - `node --check wms-agent/scripts/verify-dallas-blueprint-flow.mjs`;
  - `cd wms-agent && uv run pytest tests/test_local_agent_static.py`;
  - `npm --prefix agv-simulator run check`;
  - `npm --prefix agv-simulator run review:dallas`;
  - `git diff --check`.
- Step 4 conclusion:
  - the local agent can regenerate the accepted Dallas layout from the stored
    prompt without creating fake zones from narrative text;
  - local-agent blueprint output is consistent with the simulator/review
    artifacts at the zone, storage-count, rack-dimension, dock, station, and
    WCS-point-count level;
  - no `warehouse.blueprint.preview` write, mapping import, or confirm action
    was executed in this step.
- Next main-line step is a validate-only backend/WCS preview comparison for the
  generated blueprint JSON, followed by explicit approval before any mapping
  confirm/import.

### 2026-05-14 Dallas Backend/WCS Validate-Only Closure

- Completed the fifth main-line step by running the local-agent Dallas blueprint
  JSON through backend preview and WCS point-mapping validation without
  executing any production write, blueprint confirm, or mapping import.
- Added `backend/scripts/verify_dallas_blueprint_validate_only.py`.
- The validate-only script:
  - reads `exports/dallas-local-agent-blueprint-draft.json`;
  - calls the governed backend `warehouse.blueprint.preview` tool path;
  - compares backend-regenerated WCS point codes with the local-agent draft;
  - materializes preview-only WMS locations inside an in-memory SQLite database
    so the WCS validator can match storage points by barcode;
  - calls `validate_wcs_point_mappings`;
  - calls `import_wcs_point_mappings` with `validate_only=True`;
  - writes `exports/dallas-backend-wcs-validate-only-summary.json`.
- Contract fixes made during this step:
  - local-agent generated location barcodes now match backend/WMS format
    (`DAL-A-01-01-01-01`) instead of the previous local-only
    `A01/R01/L01/P01` format;
  - backend blueprint dimensions now accept rack inch metadata such as
    `pallet_width_in`, `pallet_depth_in`, and `level_clear_height_in`, and
    derives the equivalent GMA feet values for validation.
- Validate-only evidence:
  - backend preview warehouse: `DAL Warehouse`;
  - backend preview writes: `false`;
  - backend preview blocking errors: `[]`;
  - backend preview summary: `9 zones`, `108 locations`, `4 storage zones`,
    `8 dock doors`, `119 WCS draft points`;
  - local-agent and backend WCS point-code sets are identical;
  - first WCS point code: `DAL-STO-DAL-A-01-01-01-01`;
  - WCS role counts: `108 storage`, `8 dock`, `2 buffer`, `1 agv_station`;
  - WCS validate summary: `119 rows`, `108 mapped locations`,
    `108 AGV-accessible locations`, `0 unmapped AGV-accessible locations`,
    `11 external points`;
  - validate-only import path returned the same summary and wrote no WCS
    mappings.
- Regression commands passed:
  - `node wms-agent/scripts/verify-dallas-blueprint-flow.mjs`;
  - `cd backend && uv run python scripts/verify_dallas_blueprint_validate_only.py`;
  - `cd backend && uv run pytest tests/test_regressions.py::test_agent_warehouse_blueprint_preview_and_confirm_create_dallas_layout -q`;
  - `cd wms-agent && uv run pytest tests/test_local_agent_static.py`;
  - `npm --prefix agv-simulator run check`;
  - `git diff --check`.
- Step 5 conclusion:
  - Dallas local-agent blueprint output, backend preview output, and WCS
    validate-only behavior are aligned for warehouse code, barcode format,
    storage counts, rack GMA metadata, dock external points, stations, and WCS
    point codes;
  - no `warehouse-blueprints/agent` confirm was executed;
  - no WCS point-mapping import was executed.
- Next main-line step requires explicit operator approval before any real
  warehouse blueprint confirm or WCS mapping import against a persistent
  environment.

### 2026-05-14 Dallas Persistent Apply Gate Prepared

- Operator approved proceeding past the validate-only gate.
- Added `backend/scripts/apply_dallas_blueprint_live.py` as the guarded
  persistent-environment executor.
- The script requires both explicit confirmation environment variables before
  it can write:
  - `WMS_DALLAS_APPLY_CONFIRM=ALLOW_DALLAS_BLUEPRINT_WRITE`;
  - `WMS_DALLAS_IMPORT_CONFIRM=ALLOW_DALLAS_WCS_MAPPING_IMPORT`.
- The live executor sequence is:
  - authenticate with `WMS_TOKEN` or `WMS_EMAIL` / `WMS_PASSWORD`;
  - verify production `/health`, optionally matching `WMS_EXPECTED_BUILD_SHA`;
  - run live `POST /api/v1/agent/warehouse-blueprints/preview`;
  - stop before writing if preview has blocking errors or unexpected counts;
  - run `POST /api/v1/agent/warehouse-blueprints/agent` with the preview
    confirmation token and an idempotency key;
  - validate the generated WCS point mappings against the confirmed warehouse;
  - import WCS point mappings only after validation passes;
  - write redacted execution summaries under `tmp/dallas-live-apply-*`.
- No persistent write has been executed yet in this step.
- Pre-deploy local gates passed after adding the live executor:
  - `cd backend && uv run python -m py_compile scripts/apply_dallas_blueprint_live.py scripts/verify_dallas_blueprint_validate_only.py`;
  - `cd backend && uv run pytest tests/test_regressions.py::test_agent_warehouse_blueprint_preview_and_confirm_create_dallas_layout -q`;
  - `cd backend && uv run python scripts/verify_dallas_blueprint_validate_only.py`;
  - `cd wms-agent && uv run pytest tests/test_local_agent_static.py`;
  - `node wms-agent/scripts/verify-dallas-blueprint-flow.mjs`;
  - `npm --prefix agv-simulator run check`;
  - `npm --prefix agv-simulator run smoke:dallas`;
  - `npm --prefix frontend run check:agent-readiness`;
  - `git diff --check`.
- Next required sequence:
  - commit and push the Dallas/AGV/WCS/backend/local-agent changes;
  - wait for Render production `/health` to report the pushed build SHA;
  - run the guarded live executor against the approved test account;
  - verify the created Dallas warehouse, 108 WMS locations, and 119 imported
    WCS point mappings.

### 2026-05-14 Dallas Persistent Test Account Apply Closed

- Code gate was committed and pushed as `99af518e7a3e4d08a8de94ae54d43edaaee24e18`.
- Render production `/health` reported:
  - `status=ok`;
  - `build_sha=99af518e7a3e4d08a8de94ae54d43edaaee24e18`.
- Live target account: approved Dallas test tenant for
  `wuqingxin1978@icloud.com`.
- Live blueprint preview found an existing `DAL` warehouse instead of an empty
  target:
  - warehouse id: `db096932-cbae-4cbe-8a24-28e05dda6c6c`;
  - existing code/name: `DAL` / `Dallas Warehouse`;
  - preview draft stayed aligned at `9 zones`, `108 planned locations`, and
    `119 WCS draft points`;
  - no warehouse-blueprint confirm was executed because the existing warehouse
    already contained matching zone/location codes.
- Existing-warehouse cleanup:
  - WCS validation initially found `12` unmapped AGV-accessible legacy locations
    in `DAL-A` racks `05` to `07`;
  - these were the old A-zone columns consumed by the new A-area connector lane;
  - the 12 legacy locations were first made `is_agv_accessible=false` and
    `blocked` through the `warehouse-location` preview/confirm gate;
  - their stale `wcs_point_metadata` was cleared through the same gate;
  - the 12 legacy A racks were then deleted through the official warehouse rack
    delete API, which includes inventory checks.
- Persistent WCS mapping import result:
  - import endpoint returned `status=configured`;
  - WCS validation summary after cleanup/import:
    `119 rows`, `108 mapped locations`, `108 AGV-accessible locations`,
    `0 unmapped AGV-accessible locations`, `11 external points`;
  - final WCS export summary:
    `108` WMS locations, `108` AGV-accessible locations, `119` mapped items,
    `108` AGV-mapped storage items, `11` external WCS points,
    `0` non-AGV mapped items, `0` unmapped locations.
- Live artifacts were written under
  `tmp/dallas-live-wcs-existing-import-20260514230648/`.
- Step 5 conclusion:
  - the Dallas test account now matches the reviewed AGV layout v2 storage
    count and WCS mapping count;
  - dock doors remain external WCS interface points, not WMS storage locations;
  - the persistent apply path uncovered one follow-up improvement: the WCS
    import response uses `status=configured` rather than `ok=true`, so future
    run scripts should treat that as a successful import response.

### 2026-05-14 Real Customer Onboarding Closure Plan Completed

- Completed the six-step closure plan after the Dallas persistent WCS apply:
  1. export artifact cleanup;
  2. Dallas live apply script hardening;
  3. pre-real-data backup/logical export gate;
  4. real demand import templates;
  5. WCS/AGV operational gates;
  6. release/capacity gate preparation.
- Export artifact handling:
  - added `exports/README.md` to classify customer/vendor review artifacts
    versus agent/backend verification artifacts;
  - added `exports/.gitignore` so generated CAD/PDF/PNG/JSON outputs stay
    local and do not keep the working tree dirty;
  - removed local OS/backup scratch files from `exports/`.
- Live apply script hardening:
  - `backend/scripts/apply_dallas_blueprint_live.py` now accepts the WCS import
    success response shape `status=configured`;
  - the script now has an explicit existing-warehouse path guarded by
    `WMS_DALLAS_ALLOW_EXISTING_WAREHOUSE=true`;
  - the known Dallas layout-v2 legacy A-zone cleanup is separately guarded by
    `WMS_DALLAS_EXISTING_CLEANUP_CONFIRM=ALLOW_DALLAS_EXISTING_LAYOUT_CLEANUP`;
  - the script now validates the final export state:
    `108` WMS locations, `108` AGV mapped storage items, `11` external WCS
    points, `0` non-AGV mapped items, and `0` unmapped locations.
- Real customer onboarding runbook:
  - added `docs/38-real-customer-onboarding-runbook.md`;
  - the runbook links the existing Render PITR/logical export posture, AGV
    planning standard, CAD export standard, blueprint validate-only gate,
    persistent apply gate, import preview/confirm gate, WCS/AGV certification
    gate, and release/capacity gate.
- Intake templates added under `docs/templates/customer-onboarding/`:
  - `warehouse-layout-intake.csv`;
  - `client-sku-master.csv`;
  - `inbound-orders.csv`;
  - `outbound-orders.csv`;
  - `inventory-snapshot.csv`;
  - `wcs-point-mappings.csv`.
- WCS/AGV plan docs now clarify that the 2026-05-09 logical export already
  exists and that a fresh export/download is only needed if the operator wants
  a newer off-platform archive before real customer data.
- Production capacity remains accepted for release/test only:
  - backend service is still expected to be revisited before sustained
    production traffic or SLA commitment;
  - the onboarding runbook keeps this as a required release/capacity gate.
