# WMS Agent Feature Map

This document organizes WMS QuickStart capabilities by product area so the Local
WMS Agent can be built from a complete functional map instead of isolated
commands. Settings and administration are intentionally expanded because they
are the first priority for agent support.

## Priority Legend

- `P0`: first Local Agent coverage
- `P1`: next coverage after stable reads/previews
- `P2`: later, after stronger confirmation and audit flows
- `Read`: safe lookup or explanation
- `Preview`: no business mutation; returns impact or confirmation evidence
- `Write`: mutates WMS state and must require confirmation where applicable

## Settings And Administration

Settings are the highest-priority agent domain because they define how every
warehouse workflow behaves.

| Area | Feature | Agent Mode | Priority | Notes |
| --- | --- | --- | --- | --- |
| Setup Wizard | Read setup progress and blockers | Read | P0 | Existing `setup.progress` agent tool |
| Setup Wizard | Explain missing setup steps | Read | P0 | Agent should link blockers to settings pages |
| Tenant profile | Read tenant/company context | Read | P1 | Useful for environment confirmation |
| User management | List users and roles | Read | P0 | Implemented: `settings.users.list` |
| User management | Read one user detail | Read | P0 | Implemented: `settings.users.get`; no password/reset tokens |
| User management | Explain effective permissions | Read | P0 | Must never expose tokens |
| User management | Create user | Preview/Write | P2 | Strong confirmation required |
| User management | Update permissions/roles | Preview/Write | P2 | High risk; before/after diff required |
| Agent Settings | Read provider, model, validation, enabled state | Read | P0 | Local Agent should show model governance |
| Agent Settings | Read allowed tool catalog | Read | P0 | Required before every plan |
| Agent Settings | Explain disabled or blocked tools | Read | P0 | Converts API 403/400 into admin guidance |
| Agent Settings | Update provider/model/key | Preview/Write | P2 | Secret handling and validation required |
| Agent Settings | Update allowed tools | Preview/Write | P2 | Strong confirmation; governance action |
| Receiving Code Settings | Read code matching rules | Read | P0 | Important for dock/label troubleshooting |
| Receiving Code Settings | Explain code detection behavior | Read | P0 | Should use receiving skill |
| Receiving Code Settings | Update matching rules | Preview/Write | P1 | Preview implemented: `settings.receiving_codes.preview` |
| Receiving Label Settings | Read label template and fields | Read | P0 | Important for receiving operations |
| Receiving Label Settings | Preview label layout | Preview | P1 | Implemented: `settings.receiving_labels.preview`; no business mutation |
| Receiving Label Settings | Update label template | Preview/Write | P1 | Confirmation with field diff |
| Warehouse settings | List warehouses | Read | P0 | Existing `warehouses.list` agent tool |
| Warehouse settings | Read warehouse details | Read | P1 | Implemented: `settings.warehouse.get` |
| Warehouse settings | Create/update warehouse | Preview/Write | P1 | Medium risk |
| Warehouse Planner | Read zones, locations, bins | Read | P0 | Needed for receiving/putaway |
| Warehouse Planner | Validate location choice | Preview | P0 | Useful before putaway |
| Warehouse Planner | Create/update locations | Preview/Write | P1 | Preview implemented: `settings.warehouse_location.preview` |
| Client settings | List clients | Read | P0 | Existing `clients.list` agent tool |
| Client settings | Read client details | Read | P0 | Existing `clients.get` intended |
| Client settings | Explain selected client edit state | Read | P0 | Important because workbench is selection-gated |
| Client settings | Create/update client | Preview/Write | P1 | Preview implemented: `settings.client_profile.preview` |
| Billing settings | Read active rate cards | Read | P0 | Existing `billing.rate_cards.list` |
| Billing settings | Explain client billing setup | Read | P0 | High-value settings agent task |
| Billing settings | Read rate-card detail | Read | P0 | Implemented: `settings.rate_card.get` |
| Billing settings | Preview rate-card changes | Preview | P1 | Implemented: `settings.billing_rate_card.preview` |
| Billing settings | Apply rate-card changes | Write | P2 | Billing write; strong confirmation |
| SKU settings | List SKUs | Read | P0 | Existing `skus.list` |
| SKU settings | Read SKU details | Read | P0 | Needed for inventory and receiving |
| SKU settings | Create/update SKU | Preview/Write | P1 | Preview implemented: `settings.sku.preview` |
| Subscription | Read plan/subscription status | Read | P1 | Admin visibility |
| Pricing | Read pricing plan/catalog | Read | P1 | Admin visibility |
| Integrations | Read integration status | Read | P1 | Shopify/carrier/model integrations |
| Integrations | Update external credentials | Preview/Write | P2 | Secret handling required |
| Migration settings | Preview import mapping | Preview | P0 | Existing import preview tools |
| Migration settings | Run import | Write | P2 | Confirmation and evidence required |

## Operations

| Area | Feature | Agent Mode | Priority | Notes |
| --- | --- | --- | --- | --- |
| Dashboard | Read operating summary | Read | P1 | High-level workflow orientation |
| Receiving | List inbound orders | Read | P0 | Existing `orders.inbound.list` |
| Receiving | Read inbound order detail | Read | P0 | Needed for preview workflows |
| Receiving | Scan package/code preview | Preview | P1 | Agent should not mutate observed codes silently |
| Receiving | Choose dock/staging preview | Preview | P1 | Validate package/location |
| Receiving | Receive confirmation preview | Preview | P1 | Produces confirmation token |
| Receiving | Confirm receiving | Write | P2 | Only with evidence token and idempotency |
| Putaway | List pending putaway tasks | Read | P1 | CLI/API capability exists |
| Putaway | Explain putaway blockers | Read | P1 | Uses fulfillment skill |
| Putaway | Confirm putaway preview | Preview | P1 | Must validate task/destination |
| Putaway | Confirm putaway | Write | P2 | Agent write gate exists |
| Inventory | Search inventory | Read | P0 | Existing `inventory.search` |
| Inventory | Explain inventory state | Read | P0 | Existing `inventory.explain` |
| Inventory | Read transactions/history | Read | P1 | Useful for troubleshooting |
| Inventory | Count preview | Preview | P1 | Confirmation token required for write |
| Inventory | Adjust preview | Preview | P1 | High-value next step |
| Inventory | Hold/release preview | Preview | P1 | High-value next step |
| Inventory | Count/adjust/hold/release | Write | P2 | Agent write gates exist |
| Picking | List pick tasks | Read | P1 | Fulfillment context |
| Picking | Confirm pick preview | Preview | P1 | Confirmation token |
| Picking | Short-pick preview | Preview | P1 | Exception handling |
| Picking | Confirm/short pick | Write | P2 | Agent write gate exists |
| Shipping | List outbound orders | Read | P0 | Existing `orders.outbound.list` |
| Shipping | Pack verification preview | Preview | P1 | Confirmation token |
| Shipping | Ship confirmation preview | Preview | P1 | Confirmation token |
| Shipping | Pack/ship confirmation | Write | P2 | Agent write gate exists |
| Returns | Read return work/analytics | Read | P2 | Endpoint exists; later coverage |
| Waves | Read wave status | Read | P2 | Later planning coverage |
| AGV | Read AGV units/tasks | Read | P2 | Later automation coverage |
| AGV | Dispatch/control | Write | P2 | High operational risk |

## Client Portal

| Area | Feature | Agent Mode | Priority | Notes |
| --- | --- | --- | --- | --- |
| Portal Dashboard | Explain client-facing status | Read | P1 | Useful for support |
| Portal Inventory | Read portal-visible inventory | Read | P1 | Must respect client scope |
| Portal Orders | Read portal-visible orders | Read | P1 | Must respect client scope |
| Portal Invoices | Read invoice summaries | Read | P1 | Billing-sensitive |

## Reporting And Analytics

| Area | Feature | Agent Mode | Priority | Notes |
| --- | --- | --- | --- | --- |
| Reports | Generate operational summaries | Read | P1 | Receiving, shipping, inventory |
| Billing reports | Explain invoice inputs | Read | P1 | Billing-sensitive |
| Return analytics | Read return metrics | Read | P2 | Endpoint exists |
| Workbench summaries | Read workbench summaries | Read | P2 | Useful once stable |

## Agent Capability Roadmap

### Phase A: Settings-First Reads

Add Local Agent read support for:

- setup progress
- agent settings and tool catalog
- users/roles/permissions read
- receiving code settings
- receiving label settings
- warehouse/location settings
- clients and client details
- SKU details
- billing setup and rate-card explanation

### Phase B: Settings Previews

Add preview support for:

- receiving code settings changes - implemented
- receiving label template changes - implemented
- client profile changes - implemented
- SKU changes - implemented
- warehouse/location changes - implemented
- billing rate-card changes - implemented

Every preview should produce:

- changed fields
- current value
- proposed value
- affected workflows
- permission required
- whether confirmation is standard or strong

### Phase C: Controlled Writes

Enable writes only after preview and explicit confirmation:

- medium risk: client/SKU/warehouse/receiving settings
- high risk: users, permissions, billing, provider secrets, allowed tools

### Phase D: Operations Preview And Execution

After settings are covered, expand into:

- inventory hold/release/adjust preview
- receiving confirmation preview
- putaway/picking/shipping preview
- agent write gates with evidence token and idempotency key

## Local Agent Skill Mapping

| Intent | Preferred Skill |
| --- | --- |
| Settings/admin/model/provider/tool governance | `wms-agent-operator` plus future `wms-settings-operator` |
| Receiving settings or receiving workflow | `wms-receiving-operator` |
| Inventory settings or inventory operations | `wms-inventory-operator` |
| Putaway, picking, shipping | `wms-fulfillment-operator` |
| Error recovery or failed operation | `wms-recovery-debugger` |
| Release readiness or smoke verification | `wms-release-gate-verifier` |
| Product or workflow design decision | `wms-roundtable` |

## Immediate Next Implementation

Because settings are the current priority, the next Local Agent implementation
should add these read tools first:

1. `settings.agent.get` — implemented through `wms agent settings`
2. `settings.receiving_codes.get` — implemented through `wms settings receiving-codes`
3. `settings.receiving_labels.get` — implemented through `wms settings receiving-labels`
4. `settings.users.list` — implemented through `wms settings users`
5. `settings.permissions.explain` — implemented through `wms settings permissions`
6. `settings.client_profile.get` — implemented through `wms settings client-profile`
7. `settings.billing.explain` — implemented through `wms settings billing`
8. `settings.warehouse_locations.list` — implemented through `wms settings warehouse-locations`

These should be read-only and should reuse existing authenticated WMS APIs
where possible.

The next settings closure batch is now controlled writes behind preview and
confirmation gates. Start with medium-risk client, SKU, warehouse/location, and
receiving settings writes; keep user/permission, billing, provider secret, and
allowed-tool writes in the high-risk lane.
