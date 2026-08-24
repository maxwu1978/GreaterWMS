---
name: wms-agent-operator
description: Use when operating WMS receiving, putaway, picking, shipping, or inventory workflows through governed agent tools or CLI dry-runs.
---

# WMS Agent Operator

Use this skill when an agent is asked to assist with WMS Receiving, Putaway,
Picking, Shipping, or Inventory operations. The skill is an operator SOP, not
permission to bypass product guards.

Primary SOP: [docs/26-wms-agent-operator-sop.md](../../../docs/26-wms-agent-operator-sop.md)

Required references:
- [docs/06-agent-console-spec.md](../../../docs/06-agent-console-spec.md)
- [docs/24-agent-capabilities-reference.md](../../../docs/24-agent-capabilities-reference.md)
- [docs/25-cli-reference.md](../../../docs/25-cli-reference.md)

## Operating Contract

Always inherit the authenticated user's tenant, warehouse/client scope, role,
and effective permissions. Never write directly to database tables. Use only
governed Agent Console tools, product APIs, or the documented CLI commands.

Before acting, run or request capability discovery:

```bash
node tools/wms.mjs capabilities --json
node tools/wms.mjs glossary --json
node tools/wms.mjs workflow list --json
```

When authenticated tenant state is required:

```bash
WMS_TOKEN=... node tools/wms.mjs capabilities --json --live
```

## Receiving SOP

1. Identify tenant, warehouse/client scope, inbound order id, package id or
   scanned code, intended staging location, quantity, and caller permission.
2. Use read-only discovery first, such as `wms inbound list`, warehouse lookup,
   SKU lookup, or inventory lookup.
3. For scan, dock selection, receive confirmation, or recovery, start with
   Receiving dry-run commands. Only Receiving confirmation has an enabled write
   gate, and it must use the server token from live preview.
4. Prefer `--live-preview` when authenticated validation is needed. Treat
   preview output as evidence, not execution.
5. Stop before production writes unless live preview returns an explicit
   confirmation token and persisted `evidence_id`, then execute only through the
   documented Receiving confirmation endpoint with an idempotency key.

Receiving dry-run commands:

```bash
WMS_TOKEN=... node tools/wms.mjs receiving scan --dry-run --order-id INB-123 --code PKG-001
WMS_TOKEN=... node tools/wms.mjs receiving choose-dock --dry-run --order-id INB-123 --package-id PKG-ID --staging-location-id DOCK-ID
WMS_TOKEN=... node tools/wms.mjs receiving confirm --dry-run --order-id INB-123 --package-id PKG-ID --quantity 10 --staging-location-id DOCK-ID
WMS_TOKEN=... node tools/wms.mjs receiving recover --dry-run --error-code package_already_received
```

## Desktop Admin Reads

Use these read-only commands when an agent needs management context without
opening the app UI:

```bash
WMS_TOKEN=... node tools/wms.mjs admin subscription-status
WMS_TOKEN=... node tools/wms.mjs admin warehouse-setup
WMS_TOKEN=... node tools/wms.mjs admin billing-readiness
WMS_TOKEN=... node tools/wms.mjs admin integration-status --client-id CLIENT-ID
WMS_TOKEN=... node tools/wms.mjs admin audit-summary --limit 20
```

These commands are diagnostic only. Capability metadata must show
`agent_write_gate.enabled=false`.

## Putaway SOP

1. Identify tenant, warehouse/client scope, task id, inventory or package id,
   source location, destination location, quantity, and caller permission.
2. List candidate putaway work through documented read-only commands:

```bash
WMS_TOKEN=... node tools/wms.mjs task list --status pending --type putaway --limit 20
```

3. Validate destination location, SKU, quantity, and task state through existing
   read APIs or governed tools.
4. For putaway confirmation planning, use dry-run first:

```bash
WMS_TOKEN=... node tools/wms.mjs putaway confirm --dry-run --task-id TASK-ID --destination-location-id LOC-ID --quantity 5
```

5. For server-side validation, use live preview and capture the returned
   `confirmation_token` and `evidence_id`.
6. Production Putaway confirmation is enabled only through the documented agent
   write gate with `--confirm`, `--production-confirm`, and `--idempotency-key`.
   Do not use the normal UI endpoint directly from an agent.

## Picking SOP

1. Identify tenant, warehouse/client scope, pick task id, outbound order id,
   SKU, location, requested quantity, and caller permission.
2. Use read-only discovery first, such as `wms outbound list` or documented
   `picking next --dry-run` commands.
3. For pick confirmation or short-pick execution, use live preview first and
   capture the returned `confirmation_token` and `evidence_id`.
4. Production Picking confirmation and short-pick execution are enabled only
   through documented agent write gates with `--confirm`,
   `--production-confirm`, and `--idempotency-key`. Do not use the normal UI
   endpoint directly from an agent.
5. Do not substitute stock or mark broader task exceptions from this skill until
   documented dry-run, evidence, confirmation token, idempotency, and recovery
   checks exist.

## Shipping SOP

1. Identify tenant, warehouse/client scope, outbound order id, package/carton
   context, carrier or tracking context, and caller permission.
2. Use read-only discovery first, such as `wms outbound list` or documented
   `shipping pack --dry-run` and `shipping ship --dry-run` commands.
3. For pack verification or shipment confirmation, use live preview first and
   capture the returned `confirmation_token` and `evidence_id`.
4. Production Shipping pack verification and shipment confirmation are enabled
   only through documented agent write gates with `--confirm`,
   `--production-confirm`, and `--idempotency-key`.
5. Do not print labels as completed, void shipments, or perform carrier
   exception work from this skill until documented dry-run, evidence,
   confirmation token, idempotency, and recovery checks exist.

## Inventory SOP

1. Identify tenant, warehouse/client scope, SKU, location, lot/expiry when
   relevant, requested count or adjustment, reason, and caller permission.
2. Use read-only discovery first:

```bash
WMS_TOKEN=... node tools/wms.mjs inventory lookup --query SKU-001 --limit 20
```

3. For inventory count, adjustment, hold, or release, use live preview first
   and capture the returned `confirmation_token` and `evidence_id`, then
   execute only with `--confirm`, `--production-confirm`, and
   `--idempotency-key`.
4. Do not import, delete, or bulk-mutate inventory from this skill until
   documented dry-run, evidence, confirmation token, idempotency, and recovery
   checks exist.

## Error Recovery

For any failed tool or CLI call, require structured recovery fields:
- `ok: false`
- `error_code`
- `what_happened`
- `why_blocked`
- `recommended_action`
- `safe_commands`

Follow only safe commands that match the current task and permission scope. If
no safe command is returned, stop and escalate with the captured error.

Common recovery choices:
- capability mismatch: rerun `node tools/wms.mjs capabilities --json`
- missing auth or scope: run `WMS_TOKEN=... node tools/wms.mjs auth whoami`
- receiving exception: run `receiving recover --dry-run`, optionally with
  `--live-preview`
- putaway exception: run `putaway recover --dry-run --error-code ERROR`
- picking exception: run `picking recover --dry-run --error-code ERROR`
- shipping exception: run `shipping recover --dry-run --error-code ERROR`
- inventory exception: run `inventory recover --dry-run --error-code ERROR`
- unsupported write: stop and use the governed UI path

## Prohibited Actions

Do not:
- execute direct SQL or mutate database rows
- use unlisted endpoints, hidden implementation names, or internal staging
  concepts as commands
- call undocumented endpoints
- bypass tenant, permission, or warehouse/client scope
- treat natural-language approval as write authorization
- treat model conversation approval as authorization
- run silent production writes, destructive actions, billing changes, or
  permission changes
- invent confirmation tokens, evidence ids, before/after states, or successful
  execution results
- continue after a failed tool if recovery output has no safe command for the
  task

## Completion Standard

Call the task complete only after:
- `ok === true` has been checked for every tool result
- `action` and affected `entity` or collection are recorded
- `state_before` and `state_after` are captured for any write-capable flow
- `evidence_id` or equivalent audit id is captured when present
- `next_action` has been followed or explicitly escalated
- all user-facing claims match the actual dry-run, preview, or execution state

## Evidence Requirements

Record enough evidence for another operator to reconstruct the run:
- timestamp or run id
- tenant and user identity, without exposing secrets
- provider/model if the Agent Console was used
- CLI command or tool key
- permission and scope used
- request parameters excluding secrets
- structured result or recovery payload
- confirmation token/id only when produced by the governed product flow
- resulting object ids, task ids, or audit ids when any write is completed
