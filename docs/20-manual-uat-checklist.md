# Manual UAT Checklist

This checklist is the field packet for human UAT after automated production
gates pass. Use it on real phones, iPads, and desktop browsers. The goal is to
record whether a warehouse operator can complete the work without engineering
help, not to repeat the automated smoke scripts.

## Session Header

Record this before testing starts:

| Field | Value |
| --- | --- |
| Batch ID | `UAT-YYYYMMDD-##` |
| Tester |  |
| Date / time |  |
| Environment | Production / Staging |
| App URL | `https://app.maxsmartwms.online` |
| API URL | `https://api.maxsmartwms.online/api/v1` |
| Tenant / workspace |  |
| Login account |  |
| Browser / app shell | Safari / Chrome / iOS app / iPad app |
| Device model / OS |  |
| Network | Wi-Fi / 5G / warehouse network |
| Build or deployment evidence | Vercel deployment ID / commit SHA |

## Evidence Requirements

Attach or record these fields for every formal UAT batch:

| Field | Value |
| --- | --- |
| Release owner |  |
| Target Git SHA |  |
| Backend build SHA |  |
| Vercel deployment ID |  |
| API health result |  |
| Alembic revision |  |
| RLS check result |  |
| Automated gate commands | Pass / Fail / Not run |
| Manual device matrix | Pass / Fail / Not run |
| Mobile action-first evidence | Screenshots/video for Dashboard, Receiving, Putaway, Inventory, Picking, Shipping |
| Cleanup deleted tenants |  |
| Cleanup deleted rows |  |
| Preserved operational rows deleted | Must be `0` |
| Open blocker/high issues |  |

Do not paste passwords, provider keys, API tokens, database URLs, or raw
connection strings into this checklist.

## 2026-05-06 Production QA Readiness

Complete this before starting production page-level automated QA. Mark
`Blocked` instead of running a command when the owner or evidence is missing.

| Gate | Owner | Evidence required | Status |
| --- | --- | --- | --- |
| Bootstrap credential | Release owner / platform admin | `WMS_AUDIT_PLATFORM_EMAIL` and `WMS_AUDIT_PLATFORM_PASSWORD` are available outside the checklist; account can bootstrap verified QA tenants and run cleanup | Not run / Ready / Blocked |
| Email delivery | Release owner / email provider owner | `WMS_AUDIT_MAIL_TO` monitored inbox, provider status ready, diagnostic recipient approved | Not run / Ready / Blocked |
| Test tenant cleanup | Release owner / ops | Preserve list includes `PLATFORM,GREENECOPO`; cleanup dry-run reviewed; preserved operational rows to delete = `0` | Not run / Ready / Blocked |
| Mobile orchestrator | QA owner | Playwright/Chromium available; `WMS_AUDIT_APP_URL` and `WMS_AUDIT_API_URL` point to the target production release; cleanup step owner is present | Not run / Ready / Blocked |

Production-write commands to record, not execute without explicit release-owner
approval:

| Command | Why it needs approval | Result / evidence |
| --- | --- | --- |
| `npm run smoke:registration-email` | Creates a production test tenant and exercises the real email path |  |
| `npm run smoke:production-bootstrap` | Creates a verified production test tenant through the platform maintenance API |  |
| `npm run audit:production-pages` | Creates and seeds a production layout-audit tenant before browser page checks |  |
| `npm run uat:mobile-orchestrator` | Creates production workflow QA data across mobile/admin surfaces and invokes cleanup |  |
| `npm run uat:production:cleanup` | Can perform real production test-data deletion after its dry-run |  |

Read-only local checks may be run before the production gates, for example
`npm run check:ui-language`, `npm run lint -- --quiet`, and script/document
inspection. A passing read-only check does not unblock production QA unless the
four readiness gates above are also ready.

## Device Matrix

Run at least one full operator path on phone and one supervisor/table path on
iPad or desktop.

| Device | Required coverage | Result | Notes |
| --- | --- | --- | --- |
| iPhone portrait | Login, receiving, scan/manual entry, staging, confirm receipt, picking, shipping | Not run / Pass / Fail |  |
| iPhone landscape | Primary actions visible on receiving, picking, shipping | Not run / Pass / Fail |  |
| iPad portrait | Dashboard, receiving, putaway, inventory, picking, shipping, billing, clients | Not run / Pass / Fail |  |
| iPad landscape | Tables, filters, split panels, dialogs | Not run / Pass / Fail |  |
| Desktop browser | Admin, master data, billing, reporting-style tables | Not run / Pass / Fail |  |

## Layered Acceptance Lanes

Use these lanes to split UAT across reviewers without losing the release story.
Each lane can be assigned independently, but all blockers still roll up to the
same batch ID.

| Lane | Owner | Required coverage | Evidence |
| --- | --- | --- | --- |
| Mobile execution | Floor tester | Dashboard next work, Receiving, Putaway, Inventory lookup/count, Picking, Shipping | Phone screenshots or short clips showing current object, current question, one primary action, and post-success next step |
| Desktop management | Supervisor / admin tester | Setup, clients, SKUs, billing, import center, tables, filters, bulk/admin controls | Desktop or iPad screenshots showing selected row, filters, and resulting state |
| Recovery contract | QA / product tester | Receiving, Putaway, Picking, Shipping recovery panels | Screenshot for each panel showing what happened, why blocked, recommended action, and safe return |
| Release gate | Release owner | CI, backend health, migration/RLS, recovery matrix, production UAT, mobile orchestrator | Command names, run IDs, deployment ID, backend SHA, and pass/fail |
| Cleanup and data safety | Release owner / ops | Automated cleanup, preserved tenants, manual test data handoff | Deleted test tenant count, deleted row count, preserved operational rows deleted = `0` |

Lane exit rule: a lane can pass with notes only when the operator can finish
the task, the saved data is correct, and the next step is visible. Any missing
primary action, dead-end error, or preserved-tenant data deletion is a blocker.

## Test Data

Use one visible batch ID across all records. Keep codes readable so screenshots
can be traced without opening the database.

Suggested naming:

| Record | Naming pattern |
| --- | --- |
| Client | `Client UAT-YYYYMMDD-##` |
| SKU | `SKU-UAT-YYYYMMDD-A` |
| Warehouse | `WH-UAT-YYYYMMDD` |
| Dock / staging | `DOCK-UAT-YYYYMMDD-01` |
| Storage location | `A-01-01-01-01` or a warehouse-specific slot |
| Inbound order | `INB-UAT-YYYYMMDD-01` |
| Outbound order | `OUT-UAT-YYYYMMDD-01` |
| Tracking | `TRK-UAT-YYYYMMDD-01` |
| Carton mark | `CTN-UAT-YYYYMMDD-01` |
| Invoice | `INV-UAT-YYYYMMDD-01` |

Minimum data set:

- One client with billing enabled and an active rate card.
- One warehouse with dock/staging and at least two final storage locations.
- Two SKUs with distinct names and barcodes.
- One inbound order with at least two package records.
- One outbound order with enough stock.
- One outbound order with shortage.
- One picked order ready for shipping.

## Pass / Fail Rules

Mark each scenario as:

- Pass: the tester completed the task without help and data matched the expected
  state.
- Pass with note: the task completed, but wording, spacing, or sequence should
  be improved.
- Fail: the task could not be completed, produced wrong data, or required
  engineering intervention.
- Blocked: prerequisite data, account access, or device permission was missing.

Severity:

- Blocker: cannot complete login, receiving, putaway, picking, shipping, billing,
  or a camera/photo scan required for native release.
- High: inventory/status/tenant isolation mismatch, unsafe action allowed, or
  data lost.
- Medium: confusing but recoverable workflow, missing next-step copy, or
  incomplete validation.
- Low: copy, spacing, visual polish, or non-blocking layout issue.

Mobile workflow acceptance:

- Primary task contract: the first phone viewport identifies the current object,
  current step or blocker, and one control to continue.
- State transition feedback: every successful receive, putaway, pick, pack, or
  ship action says what completed and what to do next.
- No dead-end error: every blocking error offers one recommended recovery action
  plus a safe route back to the correct work list.
- No dead-end error structure: every recovery panel makes four things visible
  without engineering help: what happened, why the workflow cannot continue,
  the recommended action, and the safe return entry.
- Progressive detail: counts, history, alternative codes, audit records, and
  admin actions are collapsed or behind a secondary reveal.
- Desktop/mobile split: mobile executes current work; desktop or admin areas own
  import, billing, master data, bulk actions, and complex filtering.

For each phone scenario, record `Mobile tested: Y/N`, device model, browser/app
shell, and one screenshot or short clip showing the primary action plus the
post-success next step. P0 blockers are data loss or a missing saved
transaction; P1 blockers are core workflows that cannot finish without a
workaround; P2 issues are visual or copy problems where the workflow still
finishes safely.

## Access And Navigation

| ID | Scenario | Device | Expected result | Result | Issue ID |
| --- | --- | --- | --- | --- | --- |
| M-UAT-ACC-01 | Sign in as tenant admin | Phone + desktop | Lands in tenant dashboard, not platform admin |  |  |
| M-UAT-ACC-02 | Toggle password visibility | Phone | Password can be shown/hidden without layout break |  |  |
| M-UAT-ACC-03 | Open side/menu navigation | Phone | Menu opens, active page is obvious, no horizontal overflow |  |  |
| M-UAT-ACC-04 | Move dashboard -> receiving -> dashboard | Phone | Back/next context is clear |  |  |
| M-UAT-ACC-05 | Session background/relaunch | iOS app or browser | Expected auth state is preserved or intentionally reset |  |  |
| M-UAT-ACC-06 | Sign out and sign back in | Phone | User returns to the correct tenant workspace |  |  |
| M-UAT-ACC-07 | Review phone dashboard first viewport | Phone | Shows next recommended work and route, not a dense KPI/dashboard board | Automated pass: production `uat:mobile-orchestrator`, 2026-05-05 |  |

## Master Data And Client Setup

| ID | Scenario | Device | Expected result | Result | Issue ID |
| --- | --- | --- | --- | --- | --- |
| M-UAT-MD-01 | Open Clients | iPad / desktop | Client list uses the standard table language |  |  |
| M-UAT-MD-02 | Select a client for editing | iPad / desktop | Selected row is obvious before detail fields are editable |  |  |
| M-UAT-MD-03 | Review Profile tab | iPad / desktop | Name, code, contact, billing switch, portal access are clear |  |  |
| M-UAT-MD-04 | Review Billing Profile tab | iPad / desktop | Bill-to identity and invoice settings are understandable |  |  |
| M-UAT-MD-05 | Review Rate Cards tab | iPad / desktop | Active card and missing-card states are clear |  |  |
| M-UAT-MD-06 | Open SKU and warehouse records | iPad / desktop | Test SKU and locations are available for operations |  |  |
| M-UAT-MD-07 | Review desktop-first admin pages on phone | Phone | Billing settings, Clients, SKUs, Users, and settings pages show quick review or selected-record editing, not bulk management in the first viewport |  |  |
| M-UAT-MD-08 | Review Agent Settings on phone | Phone | Provider health and enabled state are readable; secret entry, full tool catalog, and high-risk governance are treated as desktop-preferred |  |  |
| M-UAT-MD-09 | Review Agent Console on phone | Phone | Low-risk read tools are reachable; import mapping, permission changes, billing changes, and high-risk confirmations are not primary phone actions |  |  |
| M-UAT-MD-10 | Review Warehouse and SKU admin pages on phone | Phone | Warehouse/SKU identity and counts are readable; create/edit controls are collapsed or desktop-preferred |  |  |
| M-UAT-MD-11 | Review Receiving Code and Label Settings on phone | Phone | Current sample/status is readable; code pattern and print-template edits are desktop-preferred |  |  |
| M-UAT-MD-12 | Review Migration / Import Center on phone | Phone | Import readiness and handoff rules are readable; upload, mapping, manual creation, and final import confirmation are desktop-preferred |  |  |

## Receiving

| ID | Scenario | Device | Expected result | Result | Issue ID |
| --- | --- | --- | --- | --- | --- |
| M-UAT-REC-01 | Open Receiving list | Phone | Next action, counts, and active orders are readable |  |  |
| M-UAT-REC-02 | Open Receiving Work | Phone | Work list appears before live detail; active phone screen has one primary action and an obvious back-to-queue path |  |  |
| M-UAT-REC-03 | Open inbound with imported packages | Phone | Package records appear before scanning |  |  |
| M-UAT-REC-04 | Type valid tracking code manually | Phone | Matching package appears and input feedback is clear |  |  |
| M-UAT-REC-05 | Try unknown barcode | Phone | Rejected code is shown with what to do next |  |  |
| M-UAT-REC-05A | Review Receiving recovery panel | Phone | Panel shows what happened, why receiving cannot continue, recommended action, and safe return to work queue |  |  |
| M-UAT-REC-06 | Confirm without staging location | Phone | System blocks receipt, focuses dock/staging, and explains the staging requirement beside the active control |  |  |
| M-UAT-REC-07 | Choose dock/staging location | Phone | Location can be selected without long awkward dropdowns |  |  |
| M-UAT-REC-08 | Edit receive/damaged quantities | Phone | Quantity is visible, editable, validates damaged-vs-received directly, and syncs to the package |  |  |
| M-UAT-REC-09 | Confirm one package receipt | Phone | Success state appears and package state changes |  |  |
| M-UAT-REC-10 | Leave and re-open unfinished inbound | Phone | Order remains discoverable in the correct work queue |  |  |
| M-UAT-REC-11 | Complete all packages | Phone | Receiving completes and putaway tasks are created |  |  |
| M-UAT-REC-12 | Camera scan | Phone / iOS app | Camera permission opens and a real label decodes |  |  |
| M-UAT-REC-13 | Read photo | Phone / iOS app | Photo permission opens and a saved label decodes |  |  |
| M-UAT-REC-14 | Confirm receipt while offline | Phone | Work is queued once, shown as a sync-pending mobile notice, and the operator gets scan-next plus back-to-queue actions |  |  |
| M-UAT-REC-17 | Review active receiving package identity | Phone | Current order, package, SKU/line, remaining quantity, dock/staging, quantity, and confirm step are visible in the focused phone flow without opening secondary details |  |  |
| M-UAT-REC-15 | Reconnect after queued receipt | Phone | Queued receipt syncs once and the package/order state refreshes without duplicate receipt |  |  |
| M-UAT-REC-16 | Reuse already received code | Phone + desktop | Page explains the code is closed and offers a direct continue/open-next path |  |  |

## Putaway

| ID | Scenario | Device | Expected result | Result | Issue ID |
| --- | --- | --- | --- | --- | --- |
| M-UAT-PUT-01 | Open Putaway | Phone | Task list uses the receiving-style task card language |  |  |
| M-UAT-PUT-02 | Open one task | Phone | Back path, source staging, SKU, and quantity are clear |  |  |
| M-UAT-PUT-02A | Review Putaway primary action | Phone | First screen exposes exactly one primary action: use recommended slot or confirm putaway |  |  |
| M-UAT-PUT-02B | Review Putaway recommended path | Phone | Recommended slot path exposes one primary action and keeps manual/other slots collapsed |  |  |
| M-UAT-PUT-02C | Review Putaway manual path | Phone | Manual slot path stays behind explicit manual selection and does not compete with the primary recommendation |  |  |
| M-UAT-PUT-02D | Review Putaway exception path | Phone | Blocked destination or policy conflict routes into recovery with a safe return instead of showing normal confirm controls |  |  |
| M-UAT-PUT-03 | Choose final slot by split selectors | Phone / iPad | Zone/aisle/rack/level/position selection is usable |  |  |
| M-UAT-PUT-04 | Use other location code | Phone / iPad | Manual code entry is available when needed |  |  |
| M-UAT-PUT-05 | Same-SKU merge | iPad / desktop | Merge behavior follows configured warehouse rule |  |  |
| M-UAT-PUT-06 | Different-SKU conflict | iPad / desktop | Different SKU is blocked by default with clear message |  |  |
| M-UAT-PUT-07 | Split putaway quantity | iPad / desktop | Split quantities can be edited and total remains correct |  |  |
| M-UAT-PUT-08 | Confirm putaway | Phone | Success is visible and task returns to the correct list |  |  |
| M-UAT-PUT-09 | Review Putaway recovery panel | Phone / desktop | Panel shows what happened, why putaway cannot continue, recommended action, and safe return to putaway list or upstream correction |  |  |

## Inventory

| ID | Scenario | Device | Expected result | Result | Issue ID |
| --- | --- | --- | --- | --- | --- |
| M-UAT-INV-01 | Open Inventory | Phone | Focus summary and list are readable without horizontal scroll |  |  |
| M-UAT-INV-02 | Review Inventory primary task | Phone | First screen shows current object, current question, next step, one recommended action, and search input; alternate record list stays collapsed until opened | Automated pass: production `uat:mobile-orchestrator`, 2026-05-05 |  |
| M-UAT-INV-03 | Search one stock record by SKU/location/client | Phone | Search narrows the stock list without opening view/filter controls |  |  |
| M-UAT-INV-04 | Open one stock record | Phone | Selected row shows on hand, available, allocated, and stable row identity |  |  |
| M-UAT-INV-05 | Expand record details | Phone | Secondary details expand without changing the selected record |  |  |
| M-UAT-INV-06 | Enter count or adjust path | Phone | Count/adjust path starts from the selected record and keeps filters collapsed by default |  |  |
| M-UAT-INV-07 | Open View and filters | Phone | View, focus chips, warehouse/client filters, and reset controls are available only after expanding details |  |  |
| M-UAT-INV-08 | Sort by SKU/client/location/quantity | Phone + desktop | Sort controls are visible in the appropriate view and row identity stays stable |  |  |
| M-UAT-INV-09 | Confirm on-hand after putaway | iPad / desktop | On-hand quantity matches putaway result |  |  |
| M-UAT-INV-10 | Confirm available after allocation | iPad / desktop | Available = on hand minus allocated |  |  |

## Picking

| ID | Scenario | Device | Expected result | Result | Issue ID |
| --- | --- | --- | --- | --- | --- |
| M-UAT-PIC-01 | Open Picking | Phone | Outbound list and next action are clear |  |  |
| M-UAT-PIC-02 | Review pick readiness in list | Phone | Ready vs shortage is visible before opening |  |  |
| M-UAT-PIC-03 | Open shortage order | Phone | Shortage reason and next step are visible |  |  |
| M-UAT-PIC-04 | Allocate ready order | Phone / iPad | Ready order creates pick task without hidden setup |  |  |
| M-UAT-PIC-04A | Review Picking allocate path | Phone | Mobile next action exposes allocate path before released scan work exists |  |  |
| M-UAT-PIC-05 | Open Picking Work list | Phone | Task list appears before one-task scan flow |  |  |
| M-UAT-PIC-05A | Review Picking scan path | Phone | Active pick task exposes scan path for location/SKU/quantity steps |  |  |
| M-UAT-PIC-06 | Scan location | Phone | Location step clears and scan field resets |  |  |
| M-UAT-PIC-07 | Scan wrong SKU | Phone | Wrong SKU is rejected without mutating inventory |  |  |
| M-UAT-PIC-07A | Review Picking recovery panel | Phone | Panel shows what happened, why picking cannot continue, recommended action, and safe return to pick list |  |  |
| M-UAT-PIC-07B | Open task with missing scan code | Phone | Page blocks scan confirmation and routes back to pick list or refresh tasks |  |  |
| M-UAT-PIC-08 | Scan correct SKU | Phone | SKU step clears and confirm step appears |  |  |
| M-UAT-PIC-09 | Confirm pick | Phone | One task completes and inventory/order state updates |  |  |
| M-UAT-PIC-10 | Return to pick list | Phone | User returns to the correct task/order context |  |  |
| M-UAT-PIC-11 | Confirm pick while offline | Phone | Pick confirm queues once, syncs on reconnect, and does not double-decrement inventory |  |  |

## Shipping

| ID | Scenario | Device | Expected result | Result | Issue ID |
| --- | --- | --- | --- | --- | --- |
| M-UAT-SHP-01 | Open Shipping | Phone | Queue and next action are clear |  |  |
| M-UAT-SHP-02 | Open picked order | Phone | Back path and order summary are clear |  |  |
| M-UAT-SHP-03 | Scan/click SKU for packing | Phone | Packing count increments for the intended line |  |  |
| M-UAT-SHP-03A | Review Shipping pack path | Phone | Mobile queue and active order expose pack path before carrier handoff |  |  |
| M-UAT-SHP-04 | Try confirm packing early | Phone | Early confirmation is blocked |  |  |
| M-UAT-SHP-04A | Review Shipping recovery panel | Phone | Panel shows what happened, why shipping cannot continue, recommended action, and safe return to shipping list |  |  |
| M-UAT-SHP-05 | Confirm complete packing | Phone | Packing step completes and Step 2 appears |  |  |
| M-UAT-SHP-05A | Wait after packing success | Phone | Pack success next-step remains visible after refresh/loading settles |  |  |
| M-UAT-SHP-06 | Scan tracking number | Phone | Tracking number field supports scanner/manual entry |  |  |
| M-UAT-SHP-06A | Review Shipping handoff path | Phone | Packed order exposes handoff path with carrier and tracking as the primary work |  |  |
| M-UAT-SHP-07 | Confirm carrier handoff | Phone | Order becomes shipped and summary agrees |  |  |
| M-UAT-SHP-07A | Wait after shipment success | Phone | Ship success next-step remains visible after refresh/loading settles |  |  |
| M-UAT-SHP-08 | Pack or ship while offline | Phone | Action queues once, later syncs, and rejected business failures remain visible as failed queued work |  |  |
| M-UAT-SHP-08 | Re-open shipping list | Phone | Shipped order is no longer in active queue, but remains traceable where expected |  |  |

## Billing

| ID | Scenario | Device | Expected result | Result | Issue ID |
| --- | --- | --- | --- | --- | --- |
| M-UAT-BIL-01 | Open Billing | iPad / desktop | Workbench follows the standard page language |  |  |
| M-UAT-BIL-02 | Preview billing | iPad / desktop | Preview includes expected operational activity |  |  |
| M-UAT-BIL-03 | Generate invoice | iPad / desktop | Invoice total and line items are understandable |  |  |
| M-UAT-BIL-04 | Download PDF | iPad / desktop | PDF opens/downloads and matches invoice data |  |  |
| M-UAT-BIL-05 | Mark sent | iPad / desktop | Row remains discoverable and status/count updates |  |  |
| M-UAT-BIL-06 | Mark paid | iPad / desktop | Row remains discoverable and paid date/status update |  |  |
| M-UAT-BIL-07 | Missing rate card | iPad / desktop | System explains setup requirement before billing run |  |  |

## Exception Recovery Checks

Run these after each happy path is understood. The pass condition is not only
that the system rejects the bad action; the page must also show one clear
operator recovery action and one safe escape route.

| ID | Scenario | Device | Expected result | Result | Issue ID |
| --- | --- | --- | --- | --- | --- |
| M-UAT-EXC-REC-01 | Receiving: scan a package code that is already received | Phone / desktop | Page offers to skip the closed code and continue to the next package or review the inbound |  |  |
| M-UAT-EXC-REC-02 | Receiving: complete inbound while packages or staging are still unresolved | Phone / desktop | Page points to open next package or dock/staging correction, not a raw error only |  |  |
| M-UAT-EXC-PUT-01 | Putaway: confirm to a blocked, wrong, or policy-conflicting final slot | Phone / desktop | Page tells operator to choose another slot and keeps a route back to the putaway list |  |  |
| M-UAT-EXC-PUT-02 | Putaway: task has no source staging or source stock changed | Phone / desktop | Page points to receiving or inventory correction and offers refresh/back to list |  |  |
| M-UAT-EXC-PIC-01 | Picking: scan the wrong source location or SKU | Phone / desktop | Page offers rescan or back to pick list and does not bypass the required physical scan |  |  |
| M-UAT-EXC-PIC-02 | Picking: task disappears or API rejects confirmation | Phone / desktop | Page offers refresh task and return to pick list instead of staying stuck |  |  |
| M-UAT-EXC-SHP-01 | Shipping: scan an already-confirmed, wrong, or unpicked SKU during pack check | Phone / desktop | Page offers scan next SKU or reset pack check |  |  |
| M-UAT-EXC-SHP-02 | Shipping: confirm handoff without carrier/tracking or after order state changed | Phone / desktop | Page focuses tracking, routes to picking, refreshes order, or returns to shipping list |  |  |
| M-UAT-EXC-STRUCT-01 | Recovery panel structure | Phone / desktop | Receiving, Putaway, Picking, and Shipping recovery panels expose what happened, why blocked, recommended action, and return entry; no raw error-only dead end |  |  |

## Cross-Flow Data Checks

Run these after the happy path:

| ID | Check | Expected result | Result | Issue ID |
| --- | --- | --- | --- | --- |
| M-UAT-DATA-01 | Inbound status after receipt | `putaway` or next valid state, not lost from work |  |  |
| M-UAT-DATA-02 | Putaway status after final slot | Task closed, inventory moved from staging to storage |  |  |
| M-UAT-DATA-03 | Inventory after pick | Storage quantity decreases by picked amount |  |  |
| M-UAT-DATA-03A | Inventory adjustment audit | Adjustment requires a reason, writes an adjustment transaction, and refreshes outbound readiness when affected stock changes | Automated pass: backend targeted regression, CI `25401391702`, 2026-05-05 |  |
| M-UAT-DATA-03B | Cycle count audit | Count variance writes a cycle-count transaction with system quantity, counted quantity, and variance visible in activity/audit evidence |  |  |
| M-UAT-DATA-04 | Outbound after pick | Status becomes `picked` when tasks complete |  |  |
| M-UAT-DATA-05 | Outbound after shipping | Status becomes `shipped` and tracking persists |  |  |
| M-UAT-DATA-06 | Billing after invoice status changes | Sent/paid rows remain traceable |  |  |
| M-UAT-DATA-07 | Browser console | No visible runtime error or blank page |  |  |

## Issue Log Template

Use one row per issue. Keep the scenario ID and data code exact.

| Issue ID | Scenario ID | Severity | Device | Data / order | Expected | Actual | Can continue? | Owner | Target fix | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| UAT-001 |  | Blocker / High / Medium / Low |  |  |  |  | Yes / No |  |  | Screenshot / video / API response |

Detailed issue note:

```text
Issue ID:
Scenario ID:
Batch ID:
Device / browser:
Account:
Data record:
Steps to reproduce:
Expected:
Actual:
Severity:
Can continue UAT:
Screenshot / recording:
API response or console error:
Decision:
Owner:
Target release:
```

## Daily UAT Closeout

At the end of each test session, record:

| Item | Result |
| --- | --- |
| Scenarios run |  |
| Passed |  |
| Failed |  |
| Blocked |  |
| New blocker/high issues |  |
| Data that must be kept as evidence |  |
| Data safe to clean |  |
| Tester recommendation | Continue / Pause / Sign off |

## Sign-Off Checklist

Manual UAT can be signed off when:

- Automated baseline remains green for the tested release.
- Phone happy path passes from receiving through shipping.
- iPad/desktop supervisor path passes for tables, filters, clients, and billing.
- Required exception scenarios fail safely with clear next steps.
- No blocker or high severity issue remains open.
- Medium issues have explicit acceptance, owner, and target release.
- Test data is either retained as evidence or cleaned with a recorded result.
