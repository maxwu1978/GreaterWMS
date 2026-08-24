# Agent Import Task Classification And Write Plan

This plan defines how agent-assisted imports move from read-only preview to
evidence-backed confirmation. Direct import tools remain intentionally blocked;
write execution is allowed only through the `/agent/imports/{family}/agent`
confirmation endpoints after a matching preview has issued evidence.

## Current Boundary

The agent may preview import files, inspect evidence, and confirm import writes
only through evidence-backed `/agent/imports/...` endpoints. It may not directly
execute inbound, outbound, or inventory import write tools.

Blocked direct write tools:

- `receiving.inbound.import_with_mapping`
- `orders.outbound.import_with_mapping`
- `migration.inventory.import`

Allowed read-only import and evidence tools:

- `receiving.inbound.preview_import`
- `orders.outbound.preview_import`
- `migration.inventory.preview`
- `wms inventory import preview`
- `wms evidence detail`
- `wms evidence failed`
- `wms evidence replay-preview`

## Phase Model

Every import family uses the same three-phase model.

| Phase | Mutates business data | Result | Required before next phase |
| --- | --- | --- | --- |
| Preview | No | Mapping, row validation, impact summary, recovery guidance | User reviews accepted/rejected rows and mapping |
| Evidence | No | Persisted `evidence_id`, confirmation token, canonical payload hash | User explicitly confirms the evidence record |
| Confirm | Yes | Import write result, audit/evidence execution status, idempotent replay behavior | Matching token, matching payload hash, `X-Idempotency-Key`, production confirmation |

Preview may be available before evidence if it is purely diagnostic. Confirm
must never accept natural-language approval alone. It must receive the
confirmation token, original payload, and idempotency key.

## Import Task Classification

| Family | Task | Preview behavior | Evidence behavior | Confirm behavior | Current status |
| --- | --- | --- | --- | --- | --- |
| Inbound | Import ASN/PO CSV rows into inbound orders, lines, and package records | Parse CSV, apply/suggest field mapping, validate client/SKU/package fields, group rows by inbound order | Persist proposed order groups, row decisions, mapping, scope, warnings, and recovery text | Create or update inbound import records through an agent-only endpoint | Enabled through `/agent/imports/inbound/agent` |
| Outbound | Import outbound order CSV rows into outbound orders and lines | Parse CSV, apply/suggest mapping, validate client/SKU/ship-to fields, check duplicate order numbers | Persist proposed outbound orders, line decisions, shortage warnings, mapping, scope, and recovery text | Create outbound orders through an agent-only endpoint; allocation remains governed by existing fulfillment rules | Enabled through `/agent/imports/outbound/agent` |
| Inventory | Import inventory balance or migration rows | Parse CSV, validate SKU/location/client/lot/expiry, classify `create`, `update`, `noop`, or `error`, compute quantity delta | Persist proposed inventory row impacts, row-level before/after references, mapping, warnings, and recovery text | Upsert inventory rows through an agent-only endpoint after stronger checks | Enabled through `/agent/imports/inventory/agent` |

## Endpoint Names

Use explicit `/agent/imports/...` endpoints so they do not look interchangeable
with the normal product UI import routes.

| Family | Preview endpoint | Confirm endpoint |
| --- | --- | --- |
| Inbound | `POST /api/v1/agent/imports/inbound/preview` | `POST /api/v1/agent/imports/inbound/agent` |
| Outbound | `POST /api/v1/agent/imports/outbound/preview` | `POST /api/v1/agent/imports/outbound/agent` |
| Inventory | `POST /api/v1/agent/imports/inventory/preview` | `POST /api/v1/agent/imports/inventory/agent` |

Compatibility note: existing read-only tool names may keep using
`receiving.inbound.preview_import`, `orders.outbound.preview_import`, and
`migration.inventory.preview`. The new endpoints are the canonical contract for
agent evidence-backed writes.

Evidence inspection remains under:

- `GET /api/v1/agent/evidence/{evidence_id}`
- `GET /api/v1/agent/evidence/failed`
- `GET /api/v1/agent/evidence/{evidence_id}/replay-preview`

## Payload Hash Inputs

The preview/evidence payload hash must be computed from a canonical JSON object
with stable key ordering. It must exclude confirmation token, idempotency key,
request timestamp, and any transient display-only text.

Common hash inputs:

- `tenant_id`
- `warehouse_id` when the import is warehouse-scoped
- `client_id` or resolved client identity when the import is client-scoped
- authenticated `user_id`
- import family: `inbound`, `outbound`, or `inventory`
- tool/action name
- normalized CSV content digest
- original filename when provided
- explicit field mapping used
- parser version and mapping version
- row count, accepted row count, rejected row count
- normalized accepted row payloads
- normalized rejected row identifiers and error codes
- permission gate

Inbound-specific hash inputs:

- grouped inbound order numbers
- resolved client and warehouse references
- inbound line payloads
- package numbers, package types, expected quantities, and tracking references
- duplicate handling policy

Outbound-specific hash inputs:

- grouped outbound order numbers
- resolved client, SKU, and ship-to references
- outbound line payloads
- requested quantities
- duplicate order policy
- allocation policy flag, if any confirm path triggers allocation side effects

Inventory-specific hash inputs:

- resolved SKU, location, warehouse, client, lot, expiry, and license-plate
  references
- before quantity and status for update/noop rows
- proposed quantity and quantity delta
- operation classification: `create`, `update`, `noop`, or `error`
- inventory source label such as `migration`, `cycle_count_seed`, or
  `customer_file`
- duplicate key policy

## Idempotency

Confirm endpoints must require `X-Idempotency-Key`. The idempotency scope is:

- tenant id
- endpoint/action
- authenticated user id
- canonical payload hash

Expected behavior:

- Same key and same payload returns the original result without re-importing.
- Same key and different payload returns `409 idempotency_payload_mismatch`.
- Blank, oversized, or malformed keys return `400`.
- Failed confirmations mark evidence as failed with structured recovery fields.
- Interrupted confirmations must not leave an `in_progress` idempotency record
  that blocks safe replay forever; stale records need an operator-visible
  recovery path.

Recommended key prefixes:

- `import-inbound:{external-batch-id-or-evidence-id}`
- `import-outbound:{external-batch-id-or-evidence-id}`
- `import-inventory:{external-batch-id-or-evidence-id}`

## Strong Confirmation

High-risk writes require a second local confirmation beyond clicking Confirm.
The local agent must require the operator to type the exact evidence id before
it calls `/api/confirm` for:

- risk `high` or `critical` preview cards
- import confirmation endpoints under `/agent/imports/...`
- billing rate-card, permission, and user-permission updates

This is enforced in the local agent server, not only in browser JavaScript. The
browser renders a small evidence-id input when `strong_confirmation_required`
is present on the confirmation card. The server rejects missing or mismatched
phrases with `409 Strong confirmation must match the evidence id.`

Medium-risk operational previews can still use the standard confirmation card,
confirmation token, payload hash, and idempotency key flow.

## Production Smoke Boundary

The current production-safe smoke scope is preview and diagnostics only:

- capabilities discovery
- import preview with no business mutation
- evidence detail lookup
- evidence replay-preview lookup
- failed evidence list lookup
- negative confirmation attempts that prove missing keys or mismatched payloads
  do not mutate data

Successful import confirmation should remain a local/staging verification step
until rollback tests prove zero business mutation after a forced mid-batch
failure for inbound, outbound, and inventory imports. Current implementation
can return `ok: false` after writing valid rows in a mixed-success batch, so a
production success confirm is intentionally excluded from the smoke plan.

## Rollback And Recovery Text

Preview/evidence responses must include operator-facing recovery text with:

- what happened
- why the import is blocked or risky
- what can be retried safely
- what requires file correction, master-data setup, or human review
- safe diagnostic commands

Confirm implementations must write through a transaction boundary appropriate
to the import family. If any row in an atomic batch fails, rollback business
state and preserve failed evidence. If partial success is ever allowed, it must
be explicit in the evidence and idempotency result, with imported row ids and
failed row ids separated.

Recovery guidance by family:

| Family | Rollback expectation | Recovery text |
| --- | --- | --- |
| Inbound | Roll back order, line, and package writes for an atomic batch failure | Correct CSV mapping/client/SKU/package rows, rerun preview, compare new evidence with old evidence |
| Outbound | Roll back order and line writes for an atomic batch failure; do not silently allocate outside the documented policy | Correct ship-to/SKU/order rows, resolve duplicate order numbers, rerun preview before confirm |
| Inventory | Roll back all inventory upserts for an atomic batch failure; write audit transactions only after import success | Correct SKU/location/client/lot rows, inspect quantity deltas, use evidence replay-preview before any retry |

Safe recovery commands to surface:

```bash
WMS_TOKEN=... node tools/wms.mjs evidence detail --id EVIDENCE-ID
WMS_TOKEN=... node tools/wms.mjs evidence replay-preview --id EVIDENCE-ID
WMS_TOKEN=... node tools/wms.mjs evidence failed --limit 20
WMS_TOKEN=... node tools/wms.mjs inventory import preview --file inventory.csv
```

## Rollout Order

1. Keep all direct import writes blocked and document the blocked state in
   capabilities, CLI, SOP, and skills. Complete.
2. Normalize preview contracts for inbound, outbound, and inventory imports so
   each returns mapping, row decisions, hash inputs, and recovery text without
   confirmation tokens. In progress, with inventory row impact furthest along.
3. Persist preview evidence from the canonical preview endpoint and return
   `evidence_id`, confirmation token, payload hash, and replay eligibility.
   Implemented in the `/preview` response.
4. Add confirm endpoints with required permission, confirmation token,
   payload-hash recomputation, and `X-Idempotency-Key`. CLI callers must also
   require `--production-confirm`. Implemented through
   `/agent/imports/{family}/agent`.
5. Enable inbound import confirm first because it feeds receiving and package
   workflows already covered by evidence-backed operational gates.
6. Enable outbound import confirm second after duplicate-order handling and
   allocation side-effect policy are covered by tests and docs.
7. Enable inventory import confirm last because it is master-data and stock
   affecting; require stronger smoke evidence, rollback tests, and explicit
   audit transaction verification.
8. After each family is enabled, update capability discovery, CLI reference,
   operator SOP, local skills, readiness gate, and production smoke coverage.

## Acceptance Checklist Before Any Import Write Is Enabled

- Direct tool execution remains blocked unless the new `/agent/imports/...`
  confirm endpoint is used.
- Preview and evidence produce identical canonical payload hashes for unchanged
  inputs.
- Confirm rejects missing token, stale token, mismatched payload hash, missing
  production confirmation, and missing idempotency key.
- Idempotent replay is covered for same-key/same-payload and
  same-key/different-payload cases.
- Rollback tests prove no partial business-state mutation after forced failure.
- Evidence detail and failed-evidence diagnostics show enough context for a
  human operator to recover without re-running the write blindly.
- CLI and local-agent capability metadata expose import writes only after the
  backend gate and docs are complete.
