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

## Initial Tool Whitelist

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

## Acceptance Criteria

- A tenant admin can configure a model provider without exposing secrets back to the browser.
- A permitted user can ask the agent to map and import an inbound CSV.
- The agent can preview the mapping before import.
- The import only executes after explicit confirmation.
- Every tool call is logged with user, tenant, provider, and result.
- A user without `inbound_orders.import` cannot use the agent to import inbound files.
- The same console works with more than one provider type without changing business logic.
