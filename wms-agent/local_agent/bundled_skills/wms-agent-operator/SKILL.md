---
name: wms-agent-operator
description: Use when operating WMS receiving, putaway, picking, shipping, or inventory workflows through the governed Agent API, local WMS Agent, or MCP.
---

# WMS Agent Operator

Use this skill when an agent assists with WMS Receiving, Putaway, Picking,
Shipping, or Inventory operations. This is an operating procedure, not
permission to bypass product guards.

Primary references:

- docs/06-agent-console-spec.md
- docs/24-agent-capabilities-reference.md
- docs/25-greaterwms-cli-reference.md
- docs/26-wms-agent-operator-sop.md
- docs/41-project-handoff.md

## Current Entry Points

This repository does not contain tools/wms.mjs or tools/greaterwms.mjs. Do not
invent or execute those paths.

Use one of these supported surfaces:

- platform Agent API under /api/v1/agent;
- local WMS Agent launched with node tools/local-agent.mjs;
- MCP adapter under mcp-server/.

For local smoke verification:

    node tools/local-agent.mjs smoke

## Operating Contract

Always inherit the authenticated user's tenant, warehouse/client scope, role,
and effective permissions. Never write directly to database tables. Never call
an undocumented endpoint or bypass a server-side permission check.

Before acting:

1. Verify the user/session through the supported WMS login boundary.
2. Read current tenant capability and permission state.
3. Resolve the target warehouse, client, SKU, order, task, and current status.
4. Explain the next valid action and any missing information.
5. Use read-only operations before planning a write.

## Write Contract

For every medium- or high-risk write:

1. Call the documented preview endpoint.
2. Check the exact object, payload, evidence/source, permission, warehouse scope,
   and idempotency requirements.
3. Show the user the operation, impact, exception path, and next step.
4. Confirm through the governed UI/API flow, not from plain chat text.
5. Send a stable X-Idempotency-Key for the exact retryable operation.
6. Report the resulting record, state transition, audit/evidence reference, and
   recovery action.

Confirmation state and sensitive credentials must remain server-side or in the
protected local session. Do not expose passwords, API keys, bearer tokens,
confirmation tokens, or provider secrets to a model prompt or audit log.

## Workflow Boundaries

- Receiving owns inbound dock receipt into staging.
- Putaway owns movement from staging to storage.
- Picking owns allocation and pick tasks.
- Shipping owns pack verification and final dispatch.
- Inventory changes require the inventory permission and the applicable count,
  adjustment, hold, or release gate.
- External instructions must retain source evidence when required by the
  platform contract.

## Recovery

If an operation fails:

1. Read the structured error and current object state.
2. Load evidence/audit detail when an evidence reference exists.
3. Do not retry a changed payload with the old confirmation state.
4. Re-run preview after state or payload changes.
5. Preserve the same idempotency key only for an exact replay.
6. Escalate permission, schema, or missing-capability issues instead of guessing.

## Prohibited Actions

- direct production database access;
- silent production writes;
- bypassing tenant or warehouse scope;
- accepting plain "yes" as standalone production authorization;
- creating a replacement confirmation token;
- hiding shortages, damage, exceptions, or failed evidence;
- treating a historical CLI example as an available command.
