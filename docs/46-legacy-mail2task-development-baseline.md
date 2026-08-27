# Legacy GreaterWMS Mail2Task Development Baseline

Effective date: 2026-08-26

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

The shared operational table implementation is
`templates/src/components/GreaterWmsOperationsTable.vue`. It is the original
GreaterWMS `q-table` contract extracted from `operationsBoard.vue`; both
`operationsBoard.vue` and `sourceIntake.vue` use this component and only supply
their own columns and body-cell slots. The shared visual contract is
`templates/src/css/greaterwms-pattern.sass`, which owns the GreaterWMS card and
table geometry: 50px header alignment, 200px drawer alignment, navy 38px table
headers, 48px minimum rows, zebra/hover states, and horizontal overflow. A
page-specific Tailwind or React recreation is not an equivalent implementation.

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

## Sunny / Maggie / Mark workflow slice

`SourceIntakeRecord` is the email projection. `MailTask` is the canonical
operational row, so multiple messages with the same inbound/outbound reference
share one task status. The first role-aware slice uses the following handoff:

```text
Mail Skill -> Maggie prepares WMS
Inbound:   Maggie -> Mark site work -> Maggie closes WMS
Outbound:  Maggie -> Sunny final approval -> Mark site work -> Maggie closes WMS
Exception: current owner -> Sunny review -> Reopen
```

The task API records the WMS system/reference and handoff evidence but does not
silently create or change ASN, Outbound, Receiving, Putaway, or Inventory rows.
The named legacy staff accounts `sunny`, `maggie`, and `mark` are used as the
current rollout role hints; generic warehouse accounts continue to use the
broader compatibility role matrix until CIO configures a formal staff-role
registry.

## Current personnel relationship update

Recorded 2026-08-27 from the current operating model. This section is a
business-role record only; it does not change the Mail2Task page, API, or
permissions in this revision. It supersedes the earlier planning assumption
that Sunny would perform the actual paperwork operation or remain the final
operator of outbound documents.

```text
Kelly <-> Xuejie
  Mutual backup coverage. Their work is intentionally complementary and
  should not be forced into rigid exclusive subcategories.

Kelly
  Primary: ocean freight.
  Secondary: domestic transportation and weekend air-freight support.

Xuejie
  Primary: domestic transportation.
  Support: ocean freight work together with Kelly.

Teddy
  Primary: air freight and its associated domestic transportation.
  Boundary: Teddy's work does not overlap with Xuejie's domestic-transport
  responsibility.

Sunny
  Future scope: inbound and outbound appointment coordination only.
  Paperwork: receives information and forwards it directly to Maggie.
  Boundary: does not process the actual paperwork or files.
```

The practical routing rule is therefore: route air-freight and associated
domestic-transport work to Teddy; route ocean-freight work to Kelly with
Xuejie as backup/support; route ordinary domestic-transport work to Xuejie
unless it is part of Teddy's air-freight scope; and route paperwork execution
to Maggie after Sunny forwards the information. When a message cannot be
assigned to one of these boundaries, keep the task in review rather than
inventing a finer split.

The Mail2Task page keeps the original GreaterWMS Vue 2 + Quasar shell and adds
only the task/ref, task status, owner/handoff, assignment, approval, and WMS
reference controls. The Dashboard remains the warehouse execution board.

The list has a strict identifier separation: `Task ID` displays the stable
MailTask database identifier as `MT-####`, while `Ref` displays only the
external business reference extracted from the email. The legacy
reference-derived `task_ref` remains an internal compatibility key and is not
used as the visible Task ID.

For local visual review only, start the frontend in Quasar development mode and
open `/#/mail2task?preview=mail2task`. This route is enabled only when the
build is in development mode and the hostname is local (`localhost`,
`127.0.0.1`, or `::1`). It uses in-memory demonstration rows and never calls
mailbox, WMS, assignment, or task-write APIs. Production builds and normal
authenticated routes cannot enable this preview flag.

## Required verification

From `templates/`:

```bash
npm run check:greaterwms-table
npm run lint
npm run build
```

`check:greaterwms-table` is a mandatory guardrail. It fails if either
`operationsBoard.vue` or `sourceIntake.vue` introduces a second inline
`q-table` or private table-layout rules. `npm run build` runs this check first,
so a visual implementation cannot silently diverge from the canonical
GreaterWMS table contract.

From the repository root, the Django source tests covering source evidence,
deduplication, provenance, state transitions, and role access must also pass.

Future work must add a feature-parity matrix before porting any additional
legacy module into the FastAPI/React tree.
