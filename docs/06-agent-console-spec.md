# BYO Model Agent Console Spec

## Objective

Build an authenticated `Agent Console` that helps each customer operate WMS QuickStart with AI while keeping model choice, data residency, and execution scope under customer control.

The platform should not force one default foreign model provider. Instead, each tenant can connect an approved model endpoint and use the agent only through controlled WMS tools.

## Why This Matters

- Some customers have procurement, legal, or government restrictions on which model vendors they may use.
- The product already has role-based permissions, tenant isolation, and operational workflows that can be reused as tool boundaries.
- AI is most useful here as an operator assistant:
  - explain workflows
  - map inbound and migration files
  - search inventory and orders
  - draft or execute safe operational actions

## Core Principles

1. Bring your own model

- The customer chooses and configures the model provider.
- WMS QuickStart stores provider configuration per tenant.
- The product never requires a specific default LLM vendor for production use.

2. Tools, not database access

- The model never writes directly to database tables.
- All agent actions must go through existing authenticated business APIs or dedicated tool wrappers.
- Permissions are enforced at the same level as normal UI and API usage.

3. Confirm before risky writes

- Low-risk reads can run immediately.
- Medium and high-risk writes require explicit confirmation.
- Destructive actions should require stricter confirmation than additive actions.

4. Full auditability

- Every agent run should log:
  - tenant
  - user
  - provider
  - model
  - prompt summary
  - tools called
  - confirmation result
  - resulting object ids

## Supported Provider Model

### Phase 1 provider types

- OpenAI
- Anthropic Claude
- Google Gemini
- Kimi / Moonshot AI
- MiniMax
- DeepSeek
- Azure OpenAI
- AWS Bedrock
- Google Vertex AI
- Private OpenAI-compatible endpoint

### Tenant configuration fields

- `provider_type`
- `provider_label`
- `base_url`
- `model_name`
- `api_key`
- `region`
- `allow_data_logging`
- `allow_model_training`
- `requires_human_confirmation_for_writes`
- `enabled`

### Validation rules

- Provider config must be tenant-scoped.
- Secrets must never be sent back to the browser after save.
- A provider test call should verify:
  - authentication
  - model reachability
  - basic response format

## Agent Execution Model

### Entry surfaces

#### Primary

- In-app authenticated `Agent Console`

#### Secondary, later

- Controlled CLI such as `wmsctl agent`

#### Platform diagnostics

- `/agent/team/status` and `/agent/team/run` are platform-admin diagnostics for controlled multi-model review.
- Tenant admins should continue to use `Agent Settings` and the in-app `Agent Console` as the governed customer-facing AI surfaces.

Phase 1 should stay inside the product UI for easier approvals, logs, and permissions.

### Request flow

1. Authenticated user opens Agent Console.
2. User enters a request.
3. The system loads:
  - tenant provider config
  - role
  - job title
  - permissions
  - current warehouse or client scope if applicable
4. The agent plans allowed tool calls.
5. Read-only calls can execute immediately.
6. Write actions show a confirmation summary.
7. On approval, the tool layer executes via the existing API stack.
8. The result is logged and shown back to the user.

## Agent Operation Contract

This contract is the source of truth for any model or CLI that operates WMS
through governed tools. It applies to the in-app Agent Console, platform
multi-model diagnostics, and the `wms` CLI.

### Command And Tool Naming

- CLI commands use WMS business nouns and imperative verbs:
  `wms inventory lookup`, `wms inbound list`, `wms task list`.
- Agent tools keep dotted stable keys:
  `inventory.search`, `orders.inbound.list`,
  `receiving.inbound.import_with_mapping`.
- Internal implementation names such as workbench, focus, handoff, snapshot, or
  source staging must not be exposed as primary command names.
- Read-only commands may run immediately after normal authentication.
- Medium, high, production-write, and destructive actions must be unavailable or
  blocked until the confirmation contract below is implemented for that command.

### Structured Result Contract

Every CLI or agent tool result should be machine readable and should follow this
shape even when the underlying API returns a richer payload:

```json
{
  "ok": true,
  "action": "inventory.search",
  "entity": {"type": "inventory_collection", "id": null},
  "state_before": null,
  "state_after": null,
  "next_action": "review_result",
  "evidence_id": "2026-05-06T12:00:00.000Z",
  "result": {}
}
```

Required fields:

- `ok`: boolean success marker.
- `action`: stable command or tool key.
- `entity`: affected entity or collection. Use `null` fields for pure reads.
- `state_before` and `state_after`: state transition evidence for writes.
- `next_action`: the safest next step an agent can take.
- `evidence_id`: audit log id, timestamp, run id, or explicit evidence record.
- `result`: command-specific payload.

### Error Recovery Contract

Errors must also be structured. They must not leave an agent at a dead end.

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

`what_happened`, `why_blocked`, `recommended_action`, and `safe_commands` are
required for tool, CLI, permission, provider, and confirmation failures.

### Permission And Confirmation Contract

- The agent must inherit the caller's effective permissions.
- The tool gate must check tenant enablement, caller permission, risk level, and
  API-level permission before execution.
- Natural-language approval inside a model conversation is not authorization for
  writes.
- Medium-risk writes require a reviewed confirmation payload.
- High-risk, production-write, billing, permission, and destructive actions
  require stronger confirmation and explicit audit evidence.
- `--dry-run` should be available before every future write CLI command.
- Production write commands must require an explicit confirmation token or a
  runbook-approved evidence id.
- The first agent write gate is Receiving confirmation. It requires the
  server-generated confirmation token from live preview, a persisted evidence
  record with a matching payload hash, and `X-Idempotency-Key`; the normal
  operator UI endpoint remains unchanged.

### Capability Discovery Contract

Agents should discover the system before acting:

```bash
wms capabilities --json
wms glossary --json
wms workflow list --json
```

When authenticated, agents may also use live tenant capability discovery:

```bash
WMS_TOKEN=... wms capabilities --json --live
```

The current Agent/MCP integration contract lives in
[25-greaterwms-cli-reference.md](25-greaterwms-cli-reference.md). The
tool capability matrix lives in
[24-agent-capabilities-reference.md](24-agent-capabilities-reference.md).

## Initial Tool Whitelist

The first release should treat the whitelist as a product contract, not a prompt
hint. A tool is available only when all three conditions are true:

1. the tenant has enabled the tool in `Agent Settings`
2. the authenticated user has the matching WMS permission
3. the tool wrapper performs the same API-level permission and tenant checks as
   the normal UI flow

### Read tools

- `inventory.search`
- `inventory.explain`
- `clients.list`
- `clients.get`
- `skus.list`
- `warehouses.list`
- `orders.inbound.list`
- `orders.outbound.list`
- `setup.progress`
- `billing.rate_cards.list`

### Guided import and mapping tools

- `receiving.inbound.preview_import`
- `receiving.inbound.import_with_mapping`
- `orders.outbound.preview_import`
- `orders.outbound.import_with_mapping`
- `migration.inventory.preview`
- `migration.inventory.import`

### Controlled write tools

- `clients.create`
- `skus.create`
- `receiving.inbound.create`
- `users.create`
- `users.update_permissions`

### Later tools

- `orders.outbound.create`
- `orders.outbound.import`
- `inventory.adjust`
- `billing.rate_card.create`

## Tool Governance Matrix

| Tool | Risk | Permission gate | Confirmation | Phase 1 behavior |
| --- | --- | --- | --- | --- |
| `setup.progress` | Low | `users.manage` or admin role | No | Read current setup blockers |
| `inventory.search` | Low | `master_data.manage` | No | Search stock and locations |
| `inventory.explain` | Low | `master_data.manage` | No | Explain stock state without mutation |
| `clients.list` | Low | `master_data.manage` | No | List visible clients |
| `clients.get` | Low | `master_data.manage` | No | Read one client profile |
| `skus.list` | Low | `master_data.manage` | No | List SKU master data |
| `warehouses.list` | Low | `master_data.manage` | No | List warehouse contexts |
| `orders.inbound.list` | Low | `inbound_orders.manage` | No | List inbound work |
| `orders.outbound.list` | Low | `outbound_orders.manage` | No | List outbound work |
| `billing.rate_cards.list` | Low | `billing.manage` | No | Read active billing rules |
| `receiving.inbound.preview_import` | Low | `inbound_orders.import` | No | Preview mapping only |
| `receiving.inbound.import_with_mapping` | Medium | `inbound_orders.import` | Yes | Enabled only through evidence-backed `/agent/imports/inbound/agent` |
| `orders.outbound.preview_import` | Low | `outbound_orders.import` | No | Preview outbound order mapping only |
| `orders.outbound.import_with_mapping` | Medium | `outbound_orders.import` | Yes | Enabled only through evidence-backed `/agent/imports/outbound/agent` |
| `migration.inventory.preview` | Low | `master_data.manage` | No | Preview migration rows |
| `migration.inventory.import` | High | `master_data.manage` | Strong confirmation | Enabled only through evidence-backed `/agent/imports/inventory/agent` |
| `clients.create` | Medium | `master_data.manage` | Yes | Create one client from reviewed fields |
| `skus.create` | Medium | `master_data.manage` | Yes | Create one SKU or reviewed set |
| `receiving.inbound.create` | Medium | `inbound_orders.manage` | Yes | Create one inbound order |
| `users.create` | High | `users.manage` | Strong confirmation | Create user with role summary |
| `users.update_permissions` | High | `users.manage` | Strong confirmation | Update permissions with before/after diff |

## Confirmation Payload Contract

Every medium or high-risk tool must pause with a structured confirmation card.
The card must include:

- tool name
- risk level
- tenant and warehouse/client scope when applicable
- caller user id and role
- required permission
- records to be created, updated, or imported
- before/after diff for edits
- row count and rejected row count for imports
- irreversible or billing/permission impact if present

The browser should send an explicit confirmation token or confirmation id back
to the API. The agent may not treat natural-language approval inside the model
conversation as sufficient authorization for writes.

## Desktop And Mobile Boundaries

- `Agent Settings` is desktop-first administration. Phone may show provider
  health, enabled state, and a route to desktop settings, but secret entry,
  complete tool-catalog management, and high-risk governance toggles should be
  treated as desktop-preferred.
- `Agent Console` may run low-risk read tools on phone.
- File upload, import mapping, permission changes, billing changes, and high
  risk confirmations should default to desktop or a deliberately reviewed
  tablet/desktop path.
- On phone, the first viewport should show current provider status, allowed
  scope, and the next safe tool. It should not show the full tool catalog as the
  primary object.

## Risk Classification

### Low risk

- Search
- Listing data
- Explaining current status
- Mapping suggestions without write

These can run without extra confirmation.

### Medium risk

- Creating inbound orders
- Creating clients
- Creating SKUs
- Importing inbound files
- Creating users

These should require confirmation with a preview of what will be created.

### High risk

- Bulk inventory adjustments
- Billing rule changes
- Permission escalation
- Destructive deletes

These should require stronger confirmation and audit emphasis.

## Permission Model

The agent must inherit the caller's effective permissions.

### Examples

- `inbound_orders.manage`
  - may create inbound orders
- `inbound_orders.import`
  - may preview and import inbound CSV files
- `receiving.execute`
  - may start receiving but not create inbound orders unless separately granted
- `outbound_orders.manage`
  - may create outbound orders once that flow exists
- `users.manage`
  - may create or update users
- `master_data.manage`
  - may create clients and SKUs
- `planner.manage`
  - may read or update planner rules if that tool is exposed

The agent should never exceed the permissions of the authenticated user.

## Recommended Admin UI

Add an `Agent Settings` page for tenant admins.

### Sections

1. Provider settings
- choose provider type
- endpoint
- model name
- region
- secret entry

2. Governance
- enable or disable agent
- writes require confirmation
- allow file preview only
- allow billing tools
- allow user-management tools

3. Audit and retention
- keep tool logs for N days
- show last agent runs
- export audit trail

## Recommended Agent Console UI

### Layout

- left: chat / instruction thread
- right: execution summary
  - planned tools
  - risk level
  - warehouse or tenant scope
  - confirmation card

### Suggested starter prompts

- `Map this inbound CSV and import it`
- `Show me which orders are still waiting to receive`
- `Create a new client and SKU set from these details`
- `Explain why this inbound file failed`
- `What setup steps are still missing before live receiving starts?`

## Best First Release Use Cases

### 1. Inbound file mapping

The customer uploads a supplier or customer CSV.

The agent:
- reads headers
- suggests field mappings
- explains missing fields
- asks for confirmation
- imports through the receiving API

### 2. Migration helper

The customer uploads an old inventory file.

The agent:
- identifies column candidates
- flags bad rows
- explains normalization issues
- prepares a review summary before import

### 3. Inventory Q&A

The customer asks operational questions such as:
- what can still ship today
- which lots are close to expiry
- why an outbound request is blocked

The agent answers using read tools only.

## Not In Scope For Phase 1

- direct SQL execution
- self-modifying business rules
- silent bulk writes
- autonomous billing changes
- destructive delete workflows
- unrestricted cross-tenant platform ops through the same customer console

## Implementation Plan

### Backend

1. Add tenant-scoped provider configuration model and API.
2. Add tool wrapper layer for approved operations.
3. Add agent execution log model and API.
4. Add confirmation payload format for write tools.

### Frontend

1. Add `Agent Settings` page for tenant admins.
2. Add `Agent Console` page for allowed users.
3. Show tool plan, scope, and confirmation before writes.
4. Surface audit history and execution result details.

### Security

1. Encrypt stored provider secrets.
2. Redact secrets from logs.
3. Enforce permission checks in every tool wrapper.
4. Require explicit confirmation for medium and high-risk tools.
5. Reject disabled tenant tools even when the user has the underlying WMS
   permission.
6. Log declined confirmations as first-class audit events.

## Acceptance Criteria

- A tenant admin can configure a model provider without exposing secrets back to the browser.
- A permitted user can ask the agent to map and import an inbound CSV.
- The agent can preview the mapping before import.
- The import only executes after explicit confirmation.
- Every tool call is logged with user, tenant, provider, and result.
- A user without `inbound_orders.import` cannot use the agent to import inbound files.
- The same console works with more than one provider type without changing business logic.
