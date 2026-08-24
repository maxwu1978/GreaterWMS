# Agent Capabilities Reference

> Reconciled 2026-08-24: this is the capability matrix and backend contract,
> not an executable CLI guide. The old tools/wms.mjs path is absent from this
> checkout. Use docs/25-greaterwms-cli-reference.md for current local-agent and
> MCP entry points.

This reference lists the governed tool capabilities that WMS exposes to agents.
The product contract is [06-agent-console-spec.md](06-agent-console-spec.md);
this document is the implementation-facing matrix for other models, CLI work,
and QA.

## Source Of Truth

- Backend tool catalog:
  [backend/app/api/v1/endpoints/agent.py](../backend/app/api/v1/endpoints/agent.py)
- Runtime capability discovery:
  [backend/app/api/v1/endpoints/agent.py](../backend/app/api/v1/endpoints/agent.py)
- Agent operation contract:
  [06-agent-console-spec.md](06-agent-console-spec.md#agent-operation-contract)
- UI language and business vocabulary:
  [ui-language-rules.md](ui-language-rules.md)

Backend `TOOL_CATALOG`, tenant `allowed_tools`, caller permissions, and this
reference should stay aligned. If they drift, backend code is the runtime source
of truth and this reference must be updated.

## Capability Discovery

Agents should discover local capabilities before acting:

```bash
node tools/wms.mjs capabilities --json
node tools/wms.mjs glossary --json
node tools/wms.mjs workflow list --json
```

Authenticated agents can request tenant-specific live settings:

```bash
WMS_TOKEN=... node tools/wms.mjs capabilities --json --live
```

## Read-only Capabilities

These are business read-only tools. In the current backend, `POST
/api/v1/agent/tools/run` also records an `agent_console_runs` audit entry, so the
database is not strictly untouched.

| Tool | CLI command | Permission gate | Result use |
| --- | --- | --- | --- |
| `settings.agent.get` | `wms agent settings` | `users.manage` or admin role | Read agent provider, allowed tools, confirmation policy, and validation state |
| Direct API | `wms agent provider-health` | `users.manage` or admin role | Read redacted provider configuration and validation health from `/agent/settings` |
| Direct API | `wms agent allowed-tools` | `users.manage` or admin role | Read enabled tools joined with risk and permission metadata |
| Direct API | `wms agent confirmation-policy` | `users.manage` or admin role | Read write confirmation policy and enabled write-gate summary |
| Direct API | `wms agent model-roster` | `users.manage` or admin role | Read redacted tenant model selection and validation state |
| Direct/API composite | `wms admin subscription-status` | authenticated tenant user | Read current plan and usage limits |
| Direct/API composite | `wms admin warehouse-setup` | `users.manage` or admin role | Read setup progress and blockers |
| Direct/API composite | `wms admin billing-readiness` | `billing.manage` | Read billing profile/rate-card readiness without mutating billing |
| Direct API | `wms admin integration-status --client-id ID` | tenant admin | Read Shopify/Amazon configured status for one client |
| Direct API | `wms admin audit-summary` | `master_data.manage` | Read recent and failed agent evidence counts |
| `settings.receiving_codes.get` | `wms settings receiving-codes` | `users.manage` | Read receiving package/code matching rules and sample output |
| `settings.receiving_labels.get` | `wms settings receiving-labels` | `users.manage` | Read printable receiving label fields and available fields |
| `settings.users.list` | `wms settings users` | `users.manage` | List users, roles, active state, and effective permission names |
| `settings.users.get` | `wms settings user --user-id ID` | `users.manage` | Read one user without password, reset, or verification tokens |
| `settings.permissions.explain` | `wms settings permissions` | `users.manage` | Explain current-user permissions and role defaults |

User-management CLI writes are now available through a separate evidence-backed
gate. Platform admins can target any tenant; tenant admins remain limited to
operator and client-viewer users in their own tenant.

| CLI command | Risk | Required guard | Backend endpoint |
| --- | --- | --- | --- |
| `wms users create` | High | `--dry-run --live-preview`, then `--confirm`, `--evidence-id`, `--production-confirm`, and `--idempotency-key` | `POST /api/v1/users/management/{preview|agent}` |
| `wms users update` | High | Same evidence and strong-confirmation gate; supports role, permissions, profile, client, and active-state changes | `POST /api/v1/users/management/{preview|agent}` |
| `wms users reset-password` | High | Password must come from `--password-env`; same evidence and strong-confirmation gate | `POST /api/v1/users/management/{preview|agent}` |
| `wms users cleanup` | Critical | `--keep-email`, live preview, then `--confirm`, `--evidence-id`, `--production-confirm`, and `--idempotency-key`; platform admin only | `POST /api/v1/users/cleanup/{preview|agent}` |
| `wms users deactivate-except` | High | `--keep-email`, live preview, then the standard evidence, production-confirm, and idempotency gates; platform admin only | `POST /api/v1/users/deactivation/{preview|agent}` |
| `settings.client_profile.get` | `wms settings client-profile` | `master_data.manage` | Read client profile and redacted client settings |
| `settings.billing.explain` | `wms settings billing` | `billing.manage` | Explain billing mode, redacted billing profiles, and active rate-card coverage |
| `settings.warehouse_locations.list` | `wms settings warehouse-locations` | `master_data.manage` | Read warehouse, zone, and location settings for planning |
| `settings.warehouse.get` | `wms settings warehouse --warehouse-id ID` | `master_data.manage` | Read one warehouse with zones and location summary |
| `settings.rate_card.get` | `wms settings rate-card --rate-card-id ID` | `billing.manage` | Read one rate card with client context and redacted rules |
| `inventory.search` | `wms inventory lookup` | `master_data.manage` | Find stock, SKU, and location context |
| Direct API | `wms inventory import preview` | `master_data.manage` | Preview inventory CSV mapping and row impact without writing |
| Direct API | `wms evidence detail` | `master_data.manage` | Inspect one preview/confirm evidence record |
| Direct API | `wms evidence failed` | `master_data.manage` | Inspect failed agent evidence |
| Direct API | `wms evidence replay-preview` | `master_data.manage` | Replay stored preview evidence for review only |
| Direct API | `wms wcs config --warehouse-id ID` | tenant admin or operator | Read redacted WCS config and point mappings |
| Direct API | `wms wcs bindings` | tenant admin or operator | Read WCS task bindings for dispatch/callback diagnosis |
| Direct API preview | `wms wcs gate-check --dry-run --task-id ID` | tenant admin or operator | Validate WCS dispatch gate without calling WCS |
| Direct API preview | `wms wcs dispatch --dry-run --task-id ID` | tenant admin or operator | Build planned WCS transport payload without calling WCS |
| Direct API preview | `wms wcs callback replay --dry-run --tenant-id ID --payload JSON` | tenant admin or operator | Replay WCS callback mapping without mutating task or inventory state |
| Direct API preview | `wms wcs ready-config --dry-run --warehouse-id ID --ready-sign SIGN --api-sign 1 --api-num 3` | tenant admin or operator | Preview WCS ready-vehicle configuration without calling WCS |
| Direct API preview | `wms wcs quality-complete --dry-run --warehouse-id ID --wtaskinfo-psn PSN` | tenant admin or operator | Preview WCS quality-complete payload without calling WCS |
| Direct API preview/write | `wms wcs config update --dry-run|--confirm-config --warehouse-id ID` | tenant admin | Preview or apply WCS sandbox connection config while preserving omitted secrets |
| Direct API preview/write | `wms wcs certification task --dry-run|--confirm-create --warehouse-id ID --source-location-id SRC --destination-location-id DST --sku-id SKU` | tenant admin | Preview or create sandbox-only WCS certification move tasks; create requires explicit confirm and never dispatches WCS |
| Direct API | `wms wcs point-mappings list/export/validate/import` | tenant admin | Maintain WMS-to-WCS point codes; actual import requires `--confirm-import` after operator approval |
| `inventory.explain` | API only | `master_data.manage` | Explain visible inventory state |
| `clients.list` | `wms client list` | `master_data.manage` | List visible clients |
| `clients.get` | API only | `master_data.manage` | Read one client profile |
| `skus.list` | `wms sku list` | `master_data.manage` | List SKU master data |
| `warehouses.list` | `wms warehouse list` | `master_data.manage` | List warehouse contexts |
| `orders.inbound.list` | `wms inbound list` | `inbound_orders.manage` | List inbound work |
| `orders.outbound.list` | `wms outbound list` | `outbound_orders.manage` | List outbound work |
| `setup.progress` | `wms setup progress` | `users.manage` or admin role | Read setup blockers |
| `billing.rate_cards.list` | `wms billing rate-cards list` | `billing.manage` | Read active billing rules |

## Settings Preview Capabilities

Settings previews do not write business data. The enabled medium-risk Settings
previews return confirmation cards with current values, proposed values,
changed fields, affected workflows, permission required, `planned_request`,
persisted evidence, and `confirmation_required_for_write: true`. The local
agent must call the matching `/agent` endpoint with the confirmation token
before any setting is updated. Billing rate-card preview remains preview-only.

| Tool | CLI command | Permission gate | Result use |
| --- | --- | --- | --- |
| `settings.receiving_codes.preview` | `wms settings receiving-codes preview --settings JSON` | `users.manage` | Preview receiving code rule changes with a sample code |
| `settings.receiving_labels.preview` | `wms settings receiving-labels preview --settings JSON` | `users.manage` | Preview label field/template changes |
| `settings.client_profile.preview` | `wms settings client-profile preview --client-id ID --changes JSON` | `master_data.manage` | Preview client profile scalar-field changes; nested settings are not writable |
| `settings.sku.preview` | `wms settings sku preview --sku-id ID --changes JSON` | `master_data.manage` | Preview SKU scalar-field changes; attributes are not writable |
| `settings.warehouse_location.preview` | `wms settings warehouse-location preview --location-id ID --changes JSON` | `master_data.manage` | Preview location/bin policy changes |
| `settings.billing_rate_card.preview` | `wms settings billing-rate-card preview --rate-card-id ID --changes JSON` | `billing.manage` | Preview rate-card rule changes |

Confirmed settings writes currently enabled:

| Confirm endpoint | Permission gate | Effect |
| --- | --- | --- |
| `POST /api/v1/agent/settings/receiving-codes/agent` | `users.manage` | Apply a previously previewed receiving code rule change |
| `POST /api/v1/agent/settings/receiving-labels/agent` | `users.manage` | Apply a previously previewed receiving label template change |
| `POST /api/v1/agent/settings/client-profile/agent` | `master_data.manage` | Apply a previously previewed client profile scalar-field change |
| `POST /api/v1/agent/settings/sku/agent` | `master_data.manage` | Apply a previously previewed SKU scalar-field change |
| `POST /api/v1/agent/settings/warehouse-location/agent` | `master_data.manage` | Apply a previously previewed warehouse location operational-field change |

## Guided Import And Mapping Capabilities

Preview commands are read-only from a business-state perspective. Inventory
preview is also exposed as CLI commands with row-level impact and recovery
output. Import commands are writes and are not enabled through direct
local-agent `/api/tools/run`; they must use a preview plus an evidence-backed
`/agent` confirmation path.

| Tool | Risk | Permission gate | Confirmation | Status |
| --- | --- | --- | --- | --- |
| `receiving.inbound.preview_import` | Low | `inbound_orders.import` | No | Available through Agent Console API |
| `receiving.inbound.import_with_mapping` | Medium | `inbound_orders.import` | Yes | Enabled through evidence-backed `/agent/imports/inbound/agent` |
| `orders.outbound.preview_import` | Low | `outbound_orders.import` | No | Available through Agent Console API |
| `orders.outbound.import_with_mapping` | Medium | `outbound_orders.import` | Yes | Enabled through evidence-backed `/agent/imports/outbound/agent` |
| `migration.inventory.preview` | Low | `master_data.manage` | No | Available through Agent Console API and CLI preview |
| `migration.inventory.import` | Medium | `master_data.manage` | Yes | Enabled through evidence-backed `/agent/imports/inventory/agent` |

## Controlled Write Capabilities

These product-contract writes remain disabled through the CLI until their own
preview, evidence, and confirmation gates are implemented.

| Tool | Risk | Required guard |
| --- | --- | --- |
| `clients.create` | Medium | Reviewed fields and confirmation |
| `skus.create` | Medium | Reviewed fields and confirmation |
| `receiving.inbound.create` | Medium | Inbound preview and confirmation |

## Receiving CLI Dry-Run Capabilities

Step 4 starts with Receiving because it is the operator workflow template. The
CLI exposes dry-run planners, authenticated live previews, and selected
agent-only write gates:

| CLI command | Risk | Backend write endpoint planned | Current behavior |
| --- | --- | --- | --- |
| `wms receiving scan --dry-run` | Medium | `POST /api/v1/receiving/inbound/{order_id}/scan-label/preview` | Validates order/code flags and prints planned request |
| `wms receiving scan --dry-run --live-preview` | Medium | `POST /api/v1/receiving/inbound/{order_id}/scan-label/preview` | Backend resolves the scanned package and rolls back observed-code capture |
| `wms receiving choose-dock --dry-run` | Medium | `POST /api/v1/receiving/inbound/{order_id}/packages/{package_id}/choose-dock/preview` | Validates dock/package flags and prints planned request |
| `wms receiving choose-dock --dry-run --live-preview` | Medium | `POST /api/v1/receiving/inbound/{order_id}/packages/{package_id}/choose-dock/preview` | Backend validates package, order state, and dock/staging location |
| `wms receiving confirm --dry-run` | Medium | `POST /api/v1/receiving/inbound/{order_id}/packages/{package_id}/receive/preview` | Validates quantity/package flags and prints planned request |
| `wms receiving confirm --dry-run --live-preview` | Medium | `POST /api/v1/receiving/inbound/{order_id}/packages/{package_id}/receive/preview` | Backend validates package, order state, quantity, and staging location, then returns confirmation payload |
| `wms receiving recover --dry-run` | Low | `POST /api/v1/receiving/recovery/preview` | Prints structured recovery guidance |
| `wms receiving recover --dry-run --live-preview` | Low | `POST /api/v1/receiving/recovery/preview` | Backend returns structured recovery guidance |

Only Receiving confirmation has an enabled Receiving write path. Scan, dock
selection, and recovery remain preview-only.

Receiving confirmation now has the first agent-only write gate:

| CLI command | Risk | Backend endpoint | Guards |
| --- | --- | --- | --- |
| `wms receiving confirm --confirm TOKEN --production-confirm --idempotency-key KEY` | Medium | `POST /api/v1/receiving/inbound/{order_id}/packages/{package_id}/receive/confirm` | Server recomputes preview hash, verifies the persisted evidence token, and requires `X-Idempotency-Key` |

## Putaway CLI Dry-Run Capabilities

| CLI command | Risk | Backend endpoint planned | Current behavior |
| --- | --- | --- | --- |
| `wms putaway next --dry-run` | Low | `GET /api/v1/tasks?status=pending&task_type=putaway` | Prints the read plan |
| `wms putaway next --dry-run --live-preview` | Low | `GET /api/v1/tasks?status=pending&task_type=putaway` | Reads pending putaway tasks without mutation |
| `wms putaway confirm --dry-run` | Medium | `POST /api/v1/fulfillment/putaway/confirm/preview` | Prints planned request only |
| `wms putaway confirm --dry-run --live-preview` | Medium | `POST /api/v1/fulfillment/putaway/confirm/preview` | Backend validates task, source stock, destination, allocation, then returns confirmation payload |
| `wms putaway block --dry-run` | Low | None | Prints structured block/recovery guidance |
| `wms putaway recover --dry-run` | Low | None | Prints structured recovery guidance |

Putaway confirmation now has an agent-only write gate:

| CLI command | Risk | Backend endpoint | Guards |
| --- | --- | --- | --- |
| `wms putaway confirm --confirm TOKEN --production-confirm --idempotency-key KEY` | Medium | `POST /api/v1/fulfillment/putaway/confirm/agent` | Server recomputes preview hash, verifies the persisted evidence token, and requires `X-Idempotency-Key` |

## Picking CLI Dry-Run Capabilities

| CLI command | Risk | Backend endpoint planned | Current behavior |
| --- | --- | --- | --- |
| `wms picking next --dry-run` | Low | `GET /api/v1/tasks?status=pending&task_type=pick` | Prints the read plan |
| `wms picking next --dry-run --live-preview` | Low | `GET /api/v1/tasks?status=pending&task_type=pick` | Reads pending pick tasks without mutation |
| `wms picking confirm --dry-run` | Medium | `POST /api/v1/fulfillment/pick/confirm/preview` | Prints planned request only |
| `wms picking confirm --dry-run --live-preview` | Medium | `POST /api/v1/fulfillment/pick/confirm/preview` | Backend validates task, quantity, source stock, assignment, then returns confirmation payload |
| `wms picking short --dry-run` | Medium | `POST /api/v1/fulfillment/pick/short/preview` | Prints structured shortage/recovery guidance |
| `wms picking short --dry-run --live-preview` | Medium | `POST /api/v1/fulfillment/pick/short/preview` | Backend validates the short-pick quantity and reason, then returns confirmation payload |
| `wms picking recover --dry-run` | Low | None | Prints structured recovery guidance |

Picking confirmation and short-pick confirmation have agent-only write gates:

| CLI command | Risk | Backend endpoint | Guards |
| --- | --- | --- | --- |
| `wms picking confirm --confirm TOKEN --production-confirm --idempotency-key KEY` | Medium | `POST /api/v1/fulfillment/pick/confirm/agent` | Server recomputes preview hash, verifies the persisted evidence token, and requires `X-Idempotency-Key` |
| `wms picking short --confirm TOKEN --production-confirm --idempotency-key KEY` | Medium | `POST /api/v1/fulfillment/pick/short/agent` | Server recomputes preview hash, verifies the persisted evidence token, and requires `X-Idempotency-Key` |

## Shipping CLI Dry-Run Capabilities

| CLI command | Risk | Backend endpoint planned | Current behavior |
| --- | --- | --- | --- |
| `wms shipping next --dry-run` | Low | `POST /api/v1/agent/tools/run orders.outbound.list` | Prints outbound review plan |
| `wms shipping pack --dry-run` | Medium | `POST /api/v1/fulfillment/pack/verify/preview` | Prints planned pack verification request |
| `wms shipping pack --dry-run --live-preview` | Medium | `POST /api/v1/fulfillment/pack/verify/preview` | Backend validates scanned packed items and returns confirmation payload |
| `wms shipping ship --dry-run` | Medium | `POST /api/v1/fulfillment/ship/confirm/preview` | Prints planned ship confirmation request |
| `wms shipping ship --dry-run --live-preview` | Medium | `POST /api/v1/fulfillment/ship/confirm/preview` | Backend validates packed order state and returns confirmation payload |
| `wms shipping recover --dry-run` | Low | None | Prints structured recovery guidance |

Shipping pack verification and ship confirmation have agent-only write gates:

| CLI command | Risk | Backend endpoint | Guards |
| --- | --- | --- | --- |
| `wms shipping pack --confirm TOKEN --production-confirm --idempotency-key KEY` | Medium | `POST /api/v1/fulfillment/pack/verify/agent` | Server recomputes preview hash, verifies the persisted evidence token, and requires `X-Idempotency-Key` |
| `wms shipping ship --confirm TOKEN --production-confirm --idempotency-key KEY` | Medium | `POST /api/v1/fulfillment/ship/confirm/agent` | Server recomputes preview hash, verifies the persisted evidence token, and requires `X-Idempotency-Key` |

## Inventory CLI Dry-Run Capabilities

| CLI command | Risk | Backend endpoint planned | Current behavior |
| --- | --- | --- | --- |
| `wms inventory count --dry-run` | Medium | `POST /api/v1/cycle-count/record/preview` | Prints planned cycle-count request |
| `wms inventory count --dry-run --live-preview` | Medium | `POST /api/v1/cycle-count/record/preview` | Backend validates location/SKU counts and returns confirmation payload |
| `wms inventory adjust --dry-run` | Medium | `POST /api/v1/inventory/ops/adjust/preview` | Prints planned adjustment request only |
| `wms inventory adjust --dry-run --live-preview` | Medium | `POST /api/v1/inventory/ops/adjust/preview` | Backend validates inventory row and adjustment reason, then returns confirmation payload |
| `wms inventory hold --dry-run` | Medium | `POST /api/v1/inventory/rules/freeze/preview` | Prints planned hold request only |
| `wms inventory hold --dry-run --live-preview` | Medium | `POST /api/v1/inventory/rules/freeze/preview` | Backend validates the inventory row, available quantity, and reason |
| `wms inventory release --dry-run` | Medium | `POST /api/v1/inventory/rules/unfreeze/preview` | Prints planned hold release request only |
| `wms inventory release --dry-run --live-preview` | Medium | `POST /api/v1/inventory/rules/unfreeze/preview` | Backend validates held quantity, release quantity, and reason |
| `wms inventory recover --dry-run` | Low | None | Prints structured recovery guidance |

Inventory count, adjustment, hold, and release now have agent-only write gates:

| CLI command | Risk | Backend endpoint | Guards |
| --- | --- | --- | --- |
| `wms inventory count --confirm TOKEN --production-confirm --idempotency-key KEY` | Medium | `POST /api/v1/cycle-count/record/agent` | Server recomputes preview hash, verifies the persisted evidence token, and requires `X-Idempotency-Key` |
| `wms inventory adjust --confirm TOKEN --production-confirm --idempotency-key KEY` | Medium | `POST /api/v1/inventory/ops/adjust/agent` | Server recomputes preview hash, verifies the persisted evidence token, and requires `X-Idempotency-Key` |
| `wms inventory hold --confirm TOKEN --production-confirm --idempotency-key KEY` | Medium | `POST /api/v1/inventory/rules/freeze/agent` | Server recomputes preview hash, verifies the persisted evidence token, and requires `X-Idempotency-Key` |
| `wms inventory release --confirm TOKEN --production-confirm --idempotency-key KEY` | Medium | `POST /api/v1/inventory/rules/unfreeze/agent` | Server recomputes preview hash, verifies the persisted evidence token, and requires `X-Idempotency-Key` |

Capability discovery includes `agent_write_gate` metadata for enabled write
commands. Agents should read this metadata before attempting any production
write.

## Agent Completion Standard

An agent may call a task complete only when it has:

- checked `ok === true`
- recorded `action`
- identified the entity or collection
- captured `evidence_id` when present
- followed `next_action`
- stopped or escalated when an error includes no safe command matching the task
