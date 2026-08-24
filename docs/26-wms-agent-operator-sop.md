# WMS Agent Operator SOP

> **Legacy notice:** This SOP describes the retired MaxSmart agent CLI and is
> kept for historical reference only. Do not run the commands below. Current
> integrations use the local governed agent in `wms-agent/`, launched with
> `node tools/local-agent.mjs`, or the MCP adapter in `mcp-server/`. See
> `docs/25-greaterwms-cli-reference.md` for the supported entry points.

This SOP defines the first governed operating procedure for agents assisting
with WMS Receiving, Putaway, Picking, Shipping, and Inventory workflows. It
complements the Agent Console contract in
[06-agent-console-spec.md](06-agent-console-spec.md), the tool matrix in
[24-agent-capabilities-reference.md](24-agent-capabilities-reference.md), and
the retired local CLI contract. The current CLI reference is
[25-greaterwms-cli-reference.md](25-greaterwms-cli-reference.md).

The default stance is conservative: agents may discover, read, explain, plan,
preview, and recover. They may not perform production writes unless the
documented product confirmation, evidence, permission, and API guardrails are
available for that exact command.

## Scope

In scope:
- Receiving agent assistance for inbound order lookup, package scan planning,
  dock/staging selection planning, receive confirmation preview, and recovery
  guidance.
- Putaway agent assistance for task discovery, task-state explanation,
  destination validation, and escalation to the governed UI path.
- Picking agent assistance for task discovery, pick-state explanation,
  confirmation preview/execution, and short-pick preview/execution through
  governed gates.
- Shipping agent assistance for outbound order discovery, pack verification,
  ship confirmation, and carrier handoff planning through governed gates where
  enabled.
- Inventory agent assistance for stock lookup, count, adjustment, and hold
  preview/execution through governed gates.
- Settings agent assistance for safe reads and before/after previews of users,
  warehouses, receiving settings, client profiles, SKUs, locations, and rate
  cards.
- Structured evidence capture for dry-runs, previews, errors, and confirmed
  writes when enabled.

Out of scope for this first version:
- direct database access
- autonomous production writes outside documented agent gates
- putaway execution without product confirmation
- pick substitution or broader pick exception execution
- shipping label, void, or carrier exception execution
- receiving execution without product confirmation
- inventory import, destructive deletes, bulk mutation, billing changes, and
  permission changes

## Settings Agent SOP

### Goal

Let other agents inspect configuration and preview proposed settings changes
without turning preview output into a write authorization.

### Allowed Reads

```bash
WMS_TOKEN=... node tools/wms.mjs agent settings
WMS_TOKEN=... node tools/wms.mjs settings users --limit 20
WMS_TOKEN=... node tools/wms.mjs settings user --user-id USER-ID
WMS_TOKEN=... node tools/wms.mjs settings client-profile --client-id CLIENT-ID
WMS_TOKEN=... node tools/wms.mjs settings warehouse --warehouse-id WH-ID
WMS_TOKEN=... node tools/wms.mjs settings rate-card --rate-card-id RATE-CARD-ID
```

### Allowed Previews

```bash
WMS_TOKEN=... node tools/wms.mjs settings receiving-codes preview --settings '{"prefix":"PKG"}'
WMS_TOKEN=... node tools/wms.mjs settings sku preview --sku-id SKU-ID --changes '{"name":"New name"}'
WMS_TOKEN=... node tools/wms.mjs settings warehouse-location preview --location-id LOC-ID --changes '{"current_status":"blocked"}'
```

Every settings preview must be treated as `writes: false`. A future settings
write still needs its own explicit write tool, permission gate, confirmation
policy, and before/after evidence.

High-risk Settings remain design-only. Billing rate-card apply, users,
permissions, provider secrets, model roster settings, allowed-tool governance,
nested client settings, SKU attributes, destructive deletes, and bulk mutation
must follow [High-Risk Settings Agent Runbook](29-high-risk-settings-agent-runbook.md)
before any write gate is enabled.

## Required References

- [06-agent-console-spec.md](06-agent-console-spec.md): source of truth for
  agent operation contract, structured results, error recovery, permissions,
  confirmations, and evidence.
- [24-agent-capabilities-reference.md](24-agent-capabilities-reference.md):
  implementation-facing capability matrix, including Receiving dry-run and
  live-preview status.
- [25-greaterwms-cli-reference.md](25-greaterwms-cli-reference.md): current
  GreaterWMS CLI commands and safety boundaries.

## Before Any Action

1. Confirm the user is authenticated and operating in the intended tenant,
   warehouse/client scope, and role.
2. Confirm the workflow: Receiving, Putaway, Picking, Shipping, or Inventory.
3. Confirm the requested outcome: read, explain, plan, dry-run, preview,
   recover, or execute.
4. Discover capabilities before selecting commands:

```bash
node tools/wms.mjs capabilities --json
node tools/wms.mjs glossary --json
node tools/wms.mjs workflow list --json
```

5. For live tenant capability discovery, use:

```bash
WMS_TOKEN=... node tools/wms.mjs capabilities --json --live
```

6. Treat every result as structured JSON. Do not infer success from prose,
   partial output, or model confidence.

## Receiving Agent SOP

### Goal

Help an operator validate the next safe Receiving step without silently moving
inventory or receiving stock.

### Required Inputs

- tenant and warehouse/client scope
- authenticated user and permission context
- inbound order id
- package id or scanned package/code value
- staging or dock location id when relevant
- expected quantity when relevant
- current task goal: scan, choose dock, confirm receipt, or recover

### Allowed Flow

1. Use read-only commands to understand current work:

```bash
WMS_TOKEN=... node tools/wms.mjs inbound list --limit 20
WMS_TOKEN=... node tools/wms.mjs warehouse list
WMS_TOKEN=... node tools/wms.mjs sku list --limit 20
WMS_TOKEN=... node tools/wms.mjs inventory lookup --query SKU-001 --limit 20
```

2. For scan planning, use dry-run:

```bash
WMS_TOKEN=... node tools/wms.mjs receiving scan --dry-run --order-id INB-123 --code PKG-001
```

3. For server-side scan validation, use live preview:

```bash
WMS_TOKEN=... node tools/wms.mjs receiving scan --dry-run --live-preview --order-id INB-123 --code PKG-001
```

4. For dock or staging choice planning:

```bash
WMS_TOKEN=... node tools/wms.mjs receiving choose-dock --dry-run --order-id INB-123 --package-id PKG-ID --staging-location-id DOCK-ID
```

5. For server-side dock or staging validation:

```bash
WMS_TOKEN=... node tools/wms.mjs receiving choose-dock --dry-run --live-preview --order-id INB-123 --package-id PKG-ID --staging-location-id DOCK-ID
```

6. For receive confirmation planning:

```bash
WMS_TOKEN=... node tools/wms.mjs receiving confirm --dry-run --order-id INB-123 --package-id PKG-ID --quantity 10 --staging-location-id DOCK-ID
```

7. For server-side receive confirmation preview:

```bash
WMS_TOKEN=... node tools/wms.mjs receiving confirm --dry-run --live-preview --order-id INB-123 --package-id PKG-ID --quantity 10 --staging-location-id DOCK-ID
```

8. Stop before execution unless live preview returns a governed confirmation
   token and `evidence_id`, and the API accepts both through the documented
   write path.

### Receiving Recovery

When a Receiving command fails or the operator reports an exception, run
recovery as a dry-run first:

```bash
WMS_TOKEN=... node tools/wms.mjs receiving recover --dry-run --error-code package_already_received
```

Use live preview when authenticated backend guidance is needed:

```bash
WMS_TOKEN=... node tools/wms.mjs receiving recover --dry-run --live-preview --error-code package_already_received
```

Recovery output must include:
- `ok: false` for failures or `ok: true` for successful recovery guidance
- `error_code`
- `what_happened`
- `why_blocked`
- `recommended_action`
- `safe_commands`

Only follow `safe_commands` that are relevant to the same tenant, scope,
inbound order, and operator permission. If the recovery result does not provide
a safe command, stop and escalate to a human operator or product administrator.

## Putaway Agent SOP

### Goal

Help an operator find and validate Putaway work while keeping final task
completion behind the governed preview, evidence, confirmation token, and
idempotency gate.

### Required Inputs

- tenant and warehouse/client scope
- authenticated user and permission context
- task id when known
- inventory, package, or license plate reference when known
- source location
- proposed destination location
- quantity
- current task goal: list, explain, validate, or escalate

### Allowed Flow

1. Discover pending Putaway work:

```bash
WMS_TOKEN=... node tools/wms.mjs task list --status pending --type putaway --limit 20
```

2. For confirmation planning:

```bash
WMS_TOKEN=... node tools/wms.mjs putaway confirm --dry-run --task-id TASK-ID --destination-location-id LOC-ID --quantity 5
WMS_TOKEN=... node tools/wms.mjs putaway recover --dry-run --error-code destination_blocked
```

3. For server-side validation:

```bash
WMS_TOKEN=... node tools/wms.mjs putaway confirm --dry-run --live-preview --task-id TASK-ID --destination-location-id LOC-ID --quantity 5
```

4. Use read-only inventory, SKU, warehouse, and task context to validate that
   the destination and quantity look plausible.
5. Produce an operator-facing plan that names the task, item, source,
   destination, quantity, and unresolved blockers.
6. If the user asks to complete Putaway, execute only through the documented
   agent write gate after live preview returns a confirmation token and
   `evidence_id`.

### Putaway Limit

The normal product `/putaway/confirm` endpoint remains for the UI. Agents must
not call it directly. Agent execution must use the `/putaway/confirm/agent`
gate with the live-preview token, persisted evidence, matching payload hash,
and idempotency key.

## Picking Agent SOP

### Goal

Help an operator understand Picking work and confirm or short picks only
through governed agent gates, without silently substituting or changing
inventory outside the documented flow.

### Required Inputs

- tenant and warehouse/client scope
- authenticated user and permission context
- pick task id or outbound order id when known
- SKU, source location, requested quantity, and scanned code when relevant
- current task goal: list, explain, validate, short-plan, or escalate

### Allowed Flow

1. Use read-only commands to understand outbound work:

```bash
WMS_TOKEN=... node tools/wms.mjs outbound list --limit 20
WMS_TOKEN=... node tools/wms.mjs inventory lookup --query SKU-001 --limit 20
```

2. Use only documented `picking * --dry-run` commands that appear in
   `node tools/wms.mjs capabilities --json`.
   For recovery planning, use:

```bash
WMS_TOKEN=... node tools/wms.mjs picking recover --dry-run --error-code insufficient_stock
```

3. For pick confirmation or short-pick confirmation, prefer `--live-preview`
   and capture the returned `confirmation_token` and `evidence_id`.
4. Production Picking confirmation and short-pick execution are enabled only
   through documented agent write gates with `--confirm`,
   `--production-confirm`, and `--idempotency-key`.
5. If the user asks to substitute stock or mark a broader task exception, stop
   at the plan and route them to the normal product UI or a human operator with
   the correct permission.

### Picking Limit

Picking confirmation and short-pick execution are enabled in this SOP, and only
through agent write gates after live preview returns a confirmation token and
persisted `evidence_id`. Substitution and broader exception writes remain
disabled.

## Shipping Agent SOP

### Goal

Help an operator understand Shipping work and verify pack or confirm shipment
handoff only through governed agent gates, without silently voiding or changing
carrier state outside the documented flow.

### Required Inputs

- tenant and warehouse/client scope
- authenticated user and permission context
- outbound order id, shipment id, or package/carton id when known
- carrier, service, tracking, package, and document context when relevant
- current task goal: list, explain, validate, pack-plan, ship-plan, or escalate

### Allowed Flow

1. Use read-only commands to understand outbound work:

```bash
WMS_TOKEN=... node tools/wms.mjs outbound list --limit 20
```

2. Use only documented `shipping * --dry-run` commands that appear in
   `node tools/wms.mjs capabilities --json`.
   For recovery planning, use:

```bash
WMS_TOKEN=... node tools/wms.mjs shipping recover --dry-run --error-code order_not_packed
```

3. For pack verification or shipment confirmation, prefer `--live-preview` and
   capture the returned `confirmation_token` and `evidence_id`.
4. Production Shipping pack verification and shipment confirmation are enabled
   only through documented agent write gates with `--confirm`,
   `--production-confirm`, and `--idempotency-key`.
5. If the user asks to void, print a completed label, or perform carrier work
   outside ship confirmation, stop at the plan and route them to the normal
   product UI or a human operator with the correct permission.

### Shipping Limit

Shipping pack verification and ship confirmation are enabled in this SOP, and
only through agent write gates after live preview returns a confirmation token
and persisted `evidence_id`. Void, label-completion, and carrier exception
writes remain disabled.

## Inventory Agent SOP

### Goal

Help an operator find and explain inventory while allowing inventory count,
adjustment, hold, and release only through governed agent gates; imports and
destructive changes stay inside governed product paths.

### Required Inputs

- tenant and warehouse/client scope
- authenticated user and permission context
- SKU, location, lot, expiry, license plate, or package reference when known
- requested count or adjustment and reason when relevant
- current task goal: lookup, explain, count-plan, adjust-plan, or escalate

### Allowed Flow

1. Use read-only inventory discovery:

```bash
WMS_TOKEN=... node tools/wms.mjs inventory lookup --query SKU-001 --limit 20
WMS_TOKEN=... node tools/wms.mjs inventory import preview --file inventory.csv
WMS_TOKEN=... node tools/wms.mjs inventory recover --dry-run --error-code quantity_conflict
WMS_TOKEN=... node tools/wms.mjs evidence detail --id EVIDENCE-ID
```

2. Use only documented `inventory * --dry-run` commands that appear in
   `node tools/wms.mjs capabilities --json`.
3. For inventory count, adjustment, hold, or release, prefer `--live-preview` and
   capture the returned `confirmation_token` and `evidence_id`.
4. Production Inventory count, adjustment, hold, and release are enabled only
   through documented agent write gates with `--confirm`,
   `--production-confirm`, and `--idempotency-key`.
5. Import writes use the same preview-token pattern:
   `inbound import preview --confirm`, `outbound import preview --confirm`, or
   `inventory import preview --confirm` with `--production-confirm` and
   `--idempotency-key`.
6. Direct import tools remain blocked. If an import preview is not confirmable
   or returns row errors, stop at the evidence and ask the operator to fix the
   CSV or master data before retrying.

### Inventory Limit

Inventory count, adjustment, hold, release, and the three guided import writes
are enabled in this SOP, and only through agent write gates after live preview
or import preview returns a confirmation token and persisted `evidence_id`.
`bulk-mutate`, bulk mutation, and destructive writes remain disabled.

### Import Failure Recovery

If an import confirm returns `ok: false`, treat it as an atomic failed write:
the backend rolls back partial row changes, marks evidence failed, and returns
the row errors. Fix the CSV or mapping, rerun preview, and use the new
confirmation token. Do not reuse a stale token after changing the file.

## Error Recovery Standard

All tool, CLI, permission, provider, and confirmation failures must follow the
error recovery contract from [06-agent-console-spec.md](06-agent-console-spec.md):

```json
{
  "ok": false,
  "error_code": "WMS_CLI_ERROR",
  "what_happened": "The requested CLI command did not complete.",
  "why_blocked": "The command is unsupported or the API rejected it.",
  "recommended_action": "Run capabilities discovery and choose an allowed command.",
  "safe_commands": [
    "wms capabilities --json",
    "wms workflow list --json"
  ]
}
```

Agent response rules:
- summarize `what_happened` plainly
- explain `why_blocked` without inventing missing system behavior
- run only relevant `safe_commands`
- keep the user inside the same tenant and warehouse/client scope
- escalate when no safe command is available

Workflow recovery helpers:

```bash
WMS_TOKEN=... node tools/wms.mjs receiving recover --dry-run --error-code ERROR
WMS_TOKEN=... node tools/wms.mjs putaway recover --dry-run --error-code ERROR
WMS_TOKEN=... node tools/wms.mjs picking recover --dry-run --error-code ERROR
WMS_TOKEN=... node tools/wms.mjs shipping recover --dry-run --error-code ERROR
WMS_TOKEN=... node tools/wms.mjs inventory recover --dry-run --error-code ERROR
```

These helpers return recovery guidance only. They do not call write endpoints
and do not authorize retrying a confirmed write.

## Prohibited Actions

Agents must not:
- write directly to database tables
- call undocumented endpoints for Receiving or Putaway
- call undocumented endpoints for Picking, Shipping, or Inventory
- bypass tenant isolation, user permissions, or API-level permission checks
- treat model conversation approval as authorization for writes
- execute production Receiving writes without a governed confirmation token or
  confirmation id
- execute Putaway confirmation without the governed agent confirmation token
- execute Picking, Shipping, or Inventory write commands outside documented
  agent gates
- fabricate successful receives, moved inventory, completed tasks, evidence ids,
  confirmation tokens, or before/after states
- hide rejected rows, blocked states, permission failures, or unsupported
  commands
- perform destructive deletes, billing changes, permission changes, or bulk
  inventory adjustments from this SOP

## Completion Standard

An agent may mark work complete only when all applicable checks are satisfied:

- every command/tool result has `ok === true`, or the failure has been recovered
  or escalated
- the stable `action` key or CLI command is recorded
- the affected `entity` or collection is identified
- `state_before` and `state_after` are recorded for any confirmed write-capable
  flow
- `evidence_id`, audit id, run id, or timestamp is captured when present
- `next_action` is followed or explicitly escalated
- the final user-facing status clearly says whether the work was read-only,
  dry-run, live-preview, recovered, escalated, or actually executed

For Receiving dry-runs and live previews, completion means the plan or preview
was produced. It does not mean stock was received.

For Putaway, completion means the task context or operator plan was produced.
It does not mean inventory was moved.

## Evidence Requirements

Capture enough evidence for audit and handoff:

- timestamp and run id when available
- tenant id, warehouse/client scope, and authenticated user id
- provider and model when the Agent Console was used
- command or agent tool key
- permission gate and risk level
- request parameters, excluding secrets
- structured success or error payload
- `evidence_id`, audit id, or confirmation id when returned
- before/after state for any enabled confirmed write
- resulting order ids, package ids, task ids, location ids, or inventory ids
- final `next_action`

Evidence must not include API keys, bearer tokens, provider secrets, or hidden
cross-tenant data.

## Initial Adoption Checklist

- Confirm docs 06, 24, and 25 still match backend capability discovery.
- Verify Receiving dry-run commands return structured JSON.
- Verify unsupported writes return structured recovery output.
- Verify Putaway task listing works for an authenticated operator.
- Train agents to distinguish dry-run/live-preview from execution.
- Keep this SOP as historical reference only; do not use its retired commands.
