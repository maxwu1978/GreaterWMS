# WMS UAT Runbook

This runbook is the handoff document for formal release acceptance after
production cleanup.

## Current Gate

As of the 2026-05-06 release closure, the production UAT baseline is clean:

- Test tenant candidates: `0`
- Test data rows: `0`
- Preserved tenants: `PLATFORM`, `GREENECOPO`
- Preserved-tenant operational rows: `0`
- 2026-05-06 status: automated UAT, production page audit, and cleanup passed.
  The release evidence and sign-off are recorded in
  [`docs/23-uat-execution-log.md`](/Volumes/MaxRelocated/WMS/docs/23-uat-execution-log.md).

The latest automated acceptance pass covered:

- Mail provider diagnostic
- Public registration email creation
- Password reset email provider-chain fallback is covered by backend
  regression tests.
- Platform-admin test tenant bootstrap
- Receiving to putaway to inventory to picking to packing to shipping
- Receiving package fallback
- Receiving/putaway action surfaces
- Pack completeness guardrails
- Shipping tracking and status persistence
- Billing rate card, calculation, invoice, sent, paid, and invoice-list status
- Production page audit across desktop and mobile
- Core table sorting/tab interaction smoke

Native iPad/iPhone smoke and release preparation are tracked separately in
[`docs/18-ios-ipad-build-runbook.md`](/Volumes/MaxRelocated/WMS/docs/18-ios-ipad-build-runbook.md).

## UAT Principles

- Use one test batch at a time.
- Keep production credentials and provider API keys out of notes and tickets.
- Use automated UAT as the default release gate. Manual testing is reserved for
  evidence review, real-device checks such as scanner/camera feel, or
  exceptions that automation cannot observe.
- Do not mix scripted smoke tenants with manual tenant data unless the batch ID
  is recorded.
- Every failed scenario needs an expected result, actual result, severity, and
  whether data cleanup is required.

## Batch Naming

Use one visible batch ID for all automated or manual records:

```text
UAT-YYYYMMDD-##
```

Recommended examples:

- Inbound order: `INB-UAT-YYYYMMDD-01`
- Outbound order: `OUT-UAT-YYYYMMDD-01`
- Reference: `REF-UAT-YYYYMMDD-01`
- Tracking: `TRK-UAT-YYYYMMDD-01`
- Carton mark: `CTN-UAT-YYYYMMDD-01`
- Invoice: `INV-UAT-YYYYMMDD-01`

## Automated Baseline

Run these from `frontend` with `.env.audit.local` populated.

```bash
npm run smoke:mail-provider
npm run smoke:registration-email
npm run smoke:production-bootstrap
npm run smoke:recovery-matrix
npm run audit:access-control
npm run smoke:warehouse-lifecycle
npm run smoke:receiving-putaway
npm run uat:mobile-orchestrator
npm run smoke:pack-completeness
node ./scripts/verify-shipping-flow.mjs
npm run audit:production-pages
npm run smoke:receiving-package-fallback
npm run lint -- --quiet
```

For the transactional email gate, `smoke:mail-provider` must show a supported,
ready requested provider or an intentional fallback provider, with redacted
attempt errors only. `smoke:registration-email` proves the public verification
path; backend regression tests cover the matching password-reset provider
chain.

## 2026-05-06 Production QA Readiness Checklist

Production page-level automated QA is blocked until the release owner confirms
all four conditions below. These scripts use production URLs by default, so do
not treat them as read-only browser checks.

| Area | Required condition | Blocking risk | Evidence to record before running |
| --- | --- | --- | --- |
| Bootstrap credential | `.env.audit.local` or shell env has `WMS_AUDIT_PLATFORM_EMAIL` and `WMS_AUDIT_PLATFORM_PASSWORD` for a platform account allowed to call `/maintenance/test-tenant/bootstrap` and `/maintenance/test-data/cleanup` | Unverified registration fallback can leave tenants unable to log in, skip platform route coverage, or fail cleanup | Credential owner, target `WMS_AUDIT_API_URL`, target `WMS_AUDIT_APP_URL`, and confirmation that the account is platform-scoped |
| Email delivery | `WMS_AUDIT_MAIL_TO` points to a monitored inbox and the production provider status is ready | Registration/email smoke may create a tenant but no visible verification email, leaving ambiguous pass/fail evidence | Provider status, selected provider, recipient mailbox owner, and whether delivery is enabled |
| Test tenant cleanup | `WMS_CLEANUP_PRESERVE_TENANTS` includes at least `PLATFORM,GREENECOPO`, and cleanup dry-run shows only disposable QA tenants/rows | Cleanup can delete automated QA tenants and tenant-scoped rows; wrong preserve list is a release blocker | Before dry-run summary, preserve list, deleted tenant count, deleted row count, preserved operational rows deleted = `0` |
| Mobile orchestrator | Playwright/Chromium dependencies are installed and production app/API targets match the release candidate | The orchestrator creates production QA data across receiving, putaway, picking, shipping, admin, agent, master data, and migration checks, then invokes cleanup | Command output summary with covered flows, cleanup result, app URL, API URL, and screenshot path for any failure |

Command classification for the 2026-05-06 gate:

| Command | Production behavior | 2026-05-06 action |
| --- | --- | --- |
| `npm run smoke:mail-provider` | Logs in as platform admin, reads provider status, sends one diagnostic email | Run only when the monitored recipient and provider owner are ready |
| `npm run smoke:registration-email` | Registers a production test tenant and sends the registration email path | Record as required, but do not run until email delivery is explicitly ready |
| `npm run smoke:production-bootstrap` | Creates a verified production test tenant through platform maintenance bootstrap | Record as required, but do not run until platform credentials are confirmed |
| `npm run audit:production-pages` | Creates a production layout-audit tenant, seeds warehouse/client/SKU/inbound data, audits desktop/mobile pages, and may include portal/platform routes | Record as blocked until bootstrap credential and cleanup readiness are confirmed |
| `npm run uat:mobile-orchestrator` | Runs multiple production page/workflow checks and then invokes production test-data cleanup | Record as blocked until bootstrap credential, cleanup readiness, and Playwright readiness are confirmed |
| `npm run uat:production:cleanup` | Performs cleanup dry-run, then executes real cleanup if test tenants or rows exist, then dry-runs again | Do not run casually; run only as the approved cleanup step with preserve list evidence |

Minimum go/no-go rule: if any of bootstrap credential, email delivery, cleanup
dry-run safety, or mobile orchestrator readiness is unknown, production
page-level automated QA remains blocked. In that state, only local read-only
checks such as `npm run check:ui-language`, `npm run lint -- --quiet`, file
inspection, or script syntax review should be run.

For a formal, single-command acceptance pass that creates an isolated
Acceptance UAT tenant and checks API state plus production pages at the correct
workflow stage, run:

```bash
npm run uat:production
```

After evidence review, clean automated UAT data:

```bash
npm run uat:production:cleanup
```

Pass criteria:

- All commands exit `0`.
- Page audit reports `failures=0` and `consoleErrorCount=0`.
- Lifecycle status sequence is:
  - inbound: `expected -> receiving -> putaway -> completed`
  - outbound: `pending -> picking -> picked -> packed -> shipped`
- Inventory moves from dock to storage, then decreases after picking.
- Billing test produces a positive invoice total and status can move to `paid`.

For the full release decision checklist, use
[docs/17-release-gate-and-access-audit.md](/Volumes/MaxRelocated/WMS/docs/17-release-gate-and-access-audit.md).

## Offline And Retry Gate

Run this gate whenever idempotency, offline queueing, scanner reconnect, or
mobile operator recovery changes. The intent is to prove that a warehouse
operator can safely continue after a weak network event without double-mutating
inventory, receiving, picking, or shipping state.

Required API checks:

- Repeat the same `X-Idempotency-Key` for receiving, putaway, pick, pack, and
  ship mutations. The second call must return the cached result without a
  second inventory transaction, task completion, or status change.
- Reuse the same `X-Idempotency-Key` with a different payload. The API must
  return `409`.
- Reuse the same `X-Idempotency-Key` in a different tenant. The API must allow
  the request and keep records tenant-scoped.
- Send a blank or oversized idempotency key. The API must return `400`.
- Force one handler failure. No `in_progress` idempotency record should remain.
- Simulate or manually inspect recovery for a stale `in_progress`
  idempotency record after a worker restart or interrupted deploy. A queued
  browser action must have a documented recovery path instead of retrying the
  same key into a permanent `409`.

Required mobile/browser checks:

- Turn the device or browser offline, confirm one receiving package, return
  online, and verify the queued receipt syncs once.
- Repeat the same offline action twice. The outbox should show one queued
  action for that user and tenant, not duplicate records.
- Sign out and sign in as another tenant/user while work is queued. The queued
  action must not replay under the wrong identity.
- Trigger a queued action that the backend rejects with a business failure. The
  outbox must leave it as failed and show attention needed.
- Confirm that successful replay refreshes the visible queue or task list
  without requiring a browser refresh.
- Disconnect and reconnect scanner WebSocket/network once during Receiving or
  Picking; the scanner path should recover without page reload.

## UAT Scenario Pack

Use this pack as the scenario vocabulary for automated UAT evidence and any
exceptional manual checks. The scenarios below are the acceptance lanes to map
against one visible batch ID:

1. Access and setup: registration, verification, login, role landing route, and password-field behavior.
2. Master data: client selection, billing profile, rate card, SKU availability, warehouse availability, and read-only/edit boundaries.
3. Receiving: imported package visibility, scan/manual code entry, invalid barcode feedback, staging requirement, receipt confirmation, and putaway handoff.
4. Putaway: pending task selection, source context, destination choice, same-SKU merge, conflicting-SKU block, confirmation, and inventory update.
5. Inventory: on-hand/allocated/available math, sorting, filters, and movement after receiving, putaway, and picking.
6. Picking: outbound readiness, shortage block, allocation, pick-task creation, location/SKU scan progression, and inventory decrement.
7. Shipping: packing completeness, tracking capture, carrier handoff, and final shipped status.
8. Billing: rate-card-backed preview, invoice generation, sent/paid transitions, positive total, and invoice-list discoverability.

When a manual exception pass is needed, include the exception scenarios listed
below. For mobile-first validation, use a phone-width browser or real mobile
device when the question is physical device behavior: receiving scan/confirm,
putaway destination choice, picking scan progression, shipping pack/ship, and
table/filter navigation.

## 2026-05-02 UAT Execution

Batch: `UAT-20260502-01`

Command:

```bash
node ./scripts/verify-uat-acceptance.mjs
```

Result: passed, then cleaned after tester confirmation.

Evidence tenant used for review:

- `Acceptance UAT UAT-20260502-01 Full Flow uat13138995`

Environment:

- Backend health: `ok`
- Backend build SHA: `0942693ee11a09205d5a8195efe28220261c8900`
- Branch: `main`

Validated outcomes:

- Receiving preserved two prebooked package records into live receiving.
- Receiving completed to `putaway`, generated two putaway tasks, and completed
  to `completed` after both tasks were confirmed.
- Inventory moved to storage with quantity `5`.
- A shortage outbound order did not fully allocate and was blocked from pick
  task release.
- A normal outbound order allocated, created one pick task, rejected over-pick
  quantity `99`, then accepted valid pick quantity `2`.
- Rejected over-pick did not mutate inventory; storage remained `5` before the
  valid pick and ended at `3` after ship flow.
- Packing and shipping completed; outbound final status was `shipped`.
- Shipping tracking number persisted.
- Billing calculated a positive total of `5.75`, generated an invoice, moved it
  to `sent`, then moved it to `paid` with a paid date recorded.
- Production page checks passed for dashboard, receiving, putaway, inventory,
  picking order list, picking task list, shipping, billing, and clients.
- Browser console errors: `0`.

Cleanup:

- Dry-run before cleanup found `7` Acceptance UAT test tenant candidates and
  `249` tenant-scoped test rows.
- Cleanup deleted `7` test tenants and `249` tenant-scoped test rows.
- Preserved tenants were `PLATFORM` and `GREENECOPO`.
- Preserved-tenant operational rows deleted: `0`.
- Final dry-run confirmed:
  - test tenant candidates: `0`
  - test tenant rows: `0`
  - preserved-tenant operational rows: `0`

Notes:

- An earlier UAT attempt checked completed workbench pages after the order had
  already left the active queue. The formal script now checks each page at the
  workflow stage where that record is expected to be visible.
- Evidence data was retained for review during the pass, then cleaned after
  confirmation.

## 2026-05-03 Release Gate Execution

Target deployment:

- Backend health: `ok`
- Backend build SHA: `6329c321690641901000ff8732046be1350543cd`
- Branch: `main`
- Render service ID: `srv-d7ako4ggjchc73eh8g70`

Final production deployment after recording the gate evidence:

- Backend health: `ok`
- Backend build SHA: `f264d1ccda99e0e3009d406cdad375854463afd4`
- Branch: `main`
- Render service: `wms-quickstart`
- Render service ID: `srv-d7ako4ggjchc73eh8g70`
- Health endpoint: `https://api.maxsmartwms.online/health`
- GitHub CI run: `25270291831`, passed
- GitHub CI URL:
  `https://github.com/maxwu1978/wms-quickstart/actions/runs/25270291831`
- Note: the full release gate below ran on `6329c321690641901000ff8732046be1350543cd`.
  The final `f264d1ccda99e0e3009d406cdad375854463afd4` deployment contains the
  recorded evidence and the UAT batch default-date fix, and health was verified
  after the Render deploy completed.

Commands run from `frontend`:

```bash
npm run smoke:mail-provider
npm run smoke:registration-email
npm run smoke:production-bootstrap
npm run audit:access-control
npm run uat:production
npm run audit:production-pages
npm run smoke:receiving-package-fallback
npm run lint -- --quiet
npm run uat:production:cleanup
```

Result: passed.

Confirmed outcomes:

- MailerSend diagnostic send succeeded with `deliveredBy=mailersend`.
- Public registration created a starter tenant and sent a verification email.
- Platform bootstrap created a verified tenant admin without email verification.
- Access-control audit passed:
  - tenant admin scope and role-promotion blocks passed
  - operator permissions were clamped to `receiving.execute`
  - client viewer permissions were clamped to `portal.view`
  - child users received `403` from user-management and tenant-admin billing
    routes
  - cleanup deleted `3` test tenants and `9` tenant-scoped rows
  - preserved operational rows deleted: `0`
- Formal UAT passed for batch `UAT-20260503-01`:
  - evidence tenant: `Acceptance UAT UAT-20260503-01 Full Flow uat83902632`
  - receiving package count: `2`
  - receiving completed status: `completed`
  - putaway tasks: `2`
  - inventory after putaway: `5`
  - rejected over-pick left inventory at `5`
  - inventory after ship flow: `3`
  - shortage outbound release was blocked
  - normal outbound final status: `shipped`
  - tracking number persisted
  - billing total: `5.75`
  - invoice moved `sent -> paid` with paid date recorded
  - production page checks passed with console errors `0`
- Production page audit checked `70` page and viewport combinations:
  - failures: `0`
  - console errors: `0`
  - portal audit: checked
  - platform audit: checked
- Receiving package fallback smoke passed after production build.
- Final cleanup deleted `1` UAT tenant and `43` tenant-scoped rows, then
  confirmed:
  - test tenant candidates: `0`
  - test tenant rows: `0`
  - preserved-tenant operational rows: `0`

Non-blocking observation:

- The page audit still reports mobile table overflow observations on some
  inventory and portal table surfaces, but the audit threshold did not mark
  them as failures. Track this as a future responsive table polish item, not a
  release blocker.

## Manual UAT Scope

Use [docs/20-manual-uat-checklist.md](/Volumes/MaxRelocated/WMS/docs/20-manual-uat-checklist.md)
as the tester-facing packet for the manual pass. This runbook defines the
formal scope and exit rules; the checklist provides scenario IDs, device
coverage, issue-log columns, and daily closeout fields for real execution.

### 1. Access And Setup

- Sign in as tenant admin.
- Confirm the landing route is the tenant dashboard, not the platform admin
  workspace.
- Confirm password fields can toggle visibility.
- Request a password reset and confirm the reset email is delivered.
- Confirm public registration sends verification email.
- Confirm a new verified account can sign in.

Pass criteria:

- User role and landing page match the account type.
- Verification, password reset, and login do not require manual database
  intervention.

### 2. Master Data

- Select one client from the Clients table.
- Confirm the selected client detail panel is read-only until a client is
  intentionally selected for editing.
- Review profile, billing profile, rate card, and portal settings.
- Confirm SKU and warehouse records are available for the test client.

Pass criteria:

- Selected client is obvious.
- Only the selected client is editable.
- Client billing profile and rate card can support invoice generation.

### 3. Receiving

- Import or create one inbound order with at least two package records.
- Open Receiving.
- Confirm the order appears in the active list with stable numbering.
- Open live receiving.
- Scan or type a valid tracking/carton/customer code.
- Confirm package queue shows imported package records.
- Receive one package fully.
- Test one invalid barcode and verify the rejected code is visible.
- Complete receiving only after required quantities/staging are valid.

Pass criteria:

- Imported package data appears before receiving starts.
- Manual barcode input gives clear feedback.
- Incomplete receiving cannot accidentally disappear from work.
- Completed receiving creates putaway work.

### 4. Putaway

- Open Putaway.
- Confirm the task shows a clear task number and source context.
- Choose a final storage location through zone/aisle/rack/level/position where
  applicable.
- Confirm same-SKU merge behavior.
- Attempt different-SKU conflict if data is available.
- Complete putaway.
- Return to the list and confirm the task is no longer open.

Pass criteria:

- Source staging location is visible.
- Different-SKU conflicts are blocked by default.
- Same-SKU merge follows the configured rule.
- Confirmation produces a visible success state and updates inventory.

### 5. Inventory

- Confirm on-hand, allocated, and available quantities.
- Use table sorting on SKU, client, location, on hand, and available.
- Click location/SKU filters where available.
- Confirm inventory reflects receiving, putaway, and picking results.

Pass criteria:

- No unexpected negative quantity.
- Available = on-hand minus allocated.
- Sorting/filtering does not change row/action identity.

### 6. Picking

- Create or import an outbound order that has enough stock.
- Confirm the outbound list shows pick readiness before opening the order.
- Allocate stock.
- Generate/enter picking work.
- Confirm location scan clears the location step.
- Confirm SKU scan clears the SKU step and the scan field is reset between
  steps.
- Confirm the final pick action is visible and completes one task at a time.

Pass criteria:

- Orders with shortage are clearly identified in the list.
- Ready orders can move to pick tasks without hidden setup.
- Pick confirmation decrements inventory and moves the order to `picked`.

### 7. Shipping

- Open a picked order.
- Scan or click suggested SKU/package codes for packing.
- Confirm packing only becomes available when the required units are packed.
- On phone-width viewports, confirm the pack step shows SKU scan first and
  only shows the pack-confirm action after the SKU check is complete.
- Scan or enter carrier and tracking number.
- On phone-width viewports, confirm carrier/tracking capture advances to a
  separate handoff review step before the final shipment action appears.
- Confirm carrier handoff.
- Verify the order status becomes `shipped`.

Pass criteria:

- Packing and shipping steps are distinct.
- Documents, service level, and shipping-cost details stay secondary on phone.
- Tracking number is persisted.
- Shipping summary and order list agree.

### 8. Billing

- Confirm the client has a rate card.
- Preview billing for the UAT period.
- Confirm line items match the operational activity used in UAT.
- Generate invoice.
- Mark sent.
- Mark paid.
- Confirm the invoice remains discoverable after status changes.

Pass criteria:

- Invoice total is positive when activity exists.
- Status transitions are visible instead of making the invoice look lost.
- Sent/paid statuses update list counts and row status consistently.

## Exception Scenarios

Run at least these negative tests:

- Unknown receiving barcode
- Receiving without staging location
- Putaway task with missing source staging location
- Putaway into conflicting SKU location
- Outbound order with stock shortage
- Picking wrong location code
- Picking wrong SKU code
- Shipping before packing complete
- Shipping wrong packed SKU scan
- Billing without active rate card
- Invoice generation with incomplete formal billing profile

Pass criteria:

- Error message states what is wrong and what to do next.
- Failed operations do not mutate inventory or order status.
- User can return to the previous list without losing context.
- Normal pack/ship controls are hidden while Shipping recovery is active.

## Issue Template

```text
Batch ID:
Module:
Scenario:
Expected:
Actual:
Severity: Blocker / High / Medium / Low
Data created:
Can continue UAT? Yes / No
Screenshot or recording:
API response, if available:
```

Severity guidance:

- Blocker: cannot complete receiving, putaway, picking, shipping, billing, or
  login.
- High: data/status/inventory mismatch, incorrect tenant isolation, or unsafe
  action allowed.
- Medium: confusing flow, recoverable wrong message, incomplete validation.
- Low: copy, spacing, non-blocking layout issue.

## Cleanup

After scripted smoke tests, run the production cleanup endpoint through the
platform-admin path:

1. Dry run and review candidates.
2. Execute cleanup.
3. Dry run again and confirm:
   - test tenant candidates: `0`
   - test rows: `0`
   - preserved operational rows: `0`

Manual UAT data under preserved tenants should only be cleared after the tester
confirms the evidence is no longer needed.

## Exit Criteria

UAT can be signed off when:

- All automated baseline checks pass.
- Manual happy path passes from receiving through billing.
- Required exception scenarios produce clear, non-destructive failures.
- No blocker or high severity issue remains open.
- Any medium issues are accepted with an owner and target release.
- Production data is either intentionally retained as evidence or cleaned with
  a recorded cleanup result.
