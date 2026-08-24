---
name: wms-local-agent-operator
description: Operate WMS through the local governed agent shell with login, read tools, preview evidence, confirmation cards, and audit checks.
---

# WMS Local Agent Operator

Use this skill when another model or agent needs to operate WMS through the
local agent shell instead of directly using the WMS UI.

## Start

```bash
node tools/local-agent.mjs start
```

Open `http://127.0.0.1:8787`.

Check `/api/config` before planning. It returns the selected model provider,
model source, model name, and a redacted `model_roster` for MiniMax, Qwen, Kimi,
and DeepSeek. It must never expose API keys. Set
`WMS_LOCAL_AGENT_MODEL_PROVIDER` when a specific configured backend provider
should handle local planning.

This process owns only local-agent runtime behavior. Consume documented WMS
platform APIs; do not add platform endpoints, capability metadata, database
changes, migrations, or WMS web Agent Console changes from this lane.

## Login Boundary

- Use `/api/session/login` with the user's WMS credentials.
- Do not store the WMS password.
- Do not send the WMS bearer token to any model provider.
- After login, use the returned `session_id` for local-agent API calls.

## Read Operations

Use `/api/chat` for natural-language read requests, or `/api/tools/run` for an
explicit WMS tool.

Examples:

```json
{"session_id":"SESSION","prompt":"Show inventory for SKU-001"}
{"session_id":"SESSION","tool_name":"inventory.search","args":{"query":"SKU-001","limit":8}}
```

Settings reads are first-class local-agent tasks:

```json
{"session_id":"SESSION","tool_name":"settings.users.get","args":{"user_id":"USER-ID"}}
{"session_id":"SESSION","tool_name":"settings.warehouse.get","args":{"warehouse_id":"WH-ID"}}
{"session_id":"SESSION","tool_name":"settings.rate_card.get","args":{"rate_card_id":"RATE-CARD-ID"}}
```

Settings previews are allowed as preview output. Medium-risk settings previews
may produce a confirmation card, but the preview itself is not permission to
write:

```json
{"session_id":"SESSION","tool_name":"settings.sku.preview","args":{"sku_id":"SKU-ID","changes":{"name":"New name"}}}
{"session_id":"SESSION","tool_name":"settings.warehouse_location.preview","args":{"location_id":"LOC-ID","changes":{"current_status":"blocked"}}}
```

Allowed model-selected tools must be present in the WMS `allowed_tools` list.
If the model suggests anything else, fall back to deterministic routing or ask
for clarification.

Use `/api/plans/compare` to compare all configured local model planners without
executing a WMS tool. Treat the result as diagnostic only. The local policy
adjudicator may select a safe allowed suggestion and must reject direct write
tools.

## Confirmation Boundary

Never execute a write from chat text such as "yes" or "go ahead".

Writes require a WMS preview payload containing:

- `confirmation_required_for_write: true`
- `planned_request.endpoint` ending in `/preview`
- `planned_request.body`
- `confirmation_payload.confirmation_token`

Settings writes are currently limited to receiving code, receiving label,
client profile scalar fields, SKU scalar fields, and warehouse location
operational fields. Billing, nested client settings, SKU attributes, users,
permissions, provider secrets, and allowed-tool governance previews are
preview-only unless a later runbook explicitly enables their `/agent` write
gate.

High-risk Settings work must stay read-only or preview-only. Before another
agent suggests a high-risk write, require a design/runbook that defines allowed
fields, redaction, evidence, idempotency, audit proof, and recovery.

Import writes are enabled only through evidence-backed previews:

```json
{"session_id":"SESSION","tool_name":"migration.inventory.preview","args":{"csv_text":"sku_code,location_barcode,quantity\nSKU-1,A1,7\n"}}
```

Direct import tools such as `receiving.inbound.import_with_mapping`,
`orders.outbound.import_with_mapping`, and `migration.inventory.import` remain
blocked in `/api/tools/run`; use `/api/confirm` with the preview payload.
If an import confirm returns row errors, assume the write was rolled back. Fix
the CSV or mapping and rerun preview; do not reuse the old confirmation token.

Only then call `/api/confirm`:

```json
{"session_id":"SESSION","preview_payload":{...},"idempotency_key":"stable-key"}
```

The local agent converts the WMS `/preview` endpoint to `/agent`, attaches the
confirmation token, and sends `X-Idempotency-Key`.

## Audit And Recovery

Use `/api/audit?limit=20` to inspect recent local-agent actions. Audit output
must redact bearer tokens, passwords, API keys, secrets, and confirmation
tokens.

If a WMS call fails:

1. Read the structured `detail`.
2. Check whether the request was read-only, preview-only, or confirmation.
3. For confirmation failures, rerun the WMS live preview before retrying.
4. Never reuse a stale confirmation token after state may have changed.

## Hard Stops

- Do not connect directly to the production database.
- Do not bypass WMS permissions.
- Do not copy WMS bearer tokens into model prompts, logs, or messages.
- Do not call WMS `/agent` endpoints without a preview token and idempotency key.
