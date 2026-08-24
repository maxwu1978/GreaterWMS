# Agent CLI And Skill Coverage Roadmap

> **Legacy notice:** This roadmap belongs to the retired MaxSmart CLI and is
> not an operational command source. Current integration work is maintained
> across the platform Agent API, `wms-agent/`, and `mcp-server/`. See
> `docs/25-greaterwms-cli-reference.md` for current entry points.

This roadmap tracks platform-owned CLI and skill work after the local-agent
responsibility split.

## Current Coverage Snapshot

Current local capability metadata reports:

- 72 commands
- 54 authenticated commands
- 18 planned write commands with governed write-gate metadata

Covered families:

- health, capabilities, glossary, workflow discovery
- agent/settings reads, narrow governance reads, and medium-risk Settings previews
- desktop-first admin reads for subscription, setup, billing readiness,
  integrations, and audit summary
- inbound, outbound, and inventory import previews and confirms
- evidence list/detail/failed/replay-preview
- receiving scan, choose-dock, confirm, and recover planning
- putaway next, confirm, block, and recover planning
- picking next, confirm, shortage, and recover planning
- shipping next, pack, ship, and recover planning
- inventory lookup, transactions, count, adjust, hold, release, and recover planning

## Platform-Owned Next CLI Work

### P1: Authenticated Import Smoke Enablement

Goal:

- run authenticated `smoke:agent-import-production` preview against a disposable
  test tenant.

Status:

- completed for preview-only smoke with the online test account.
- the smoke returned `dry_run=true`, `writes=false`, and no confirm.

Rule:

- confirm mode remains disabled unless the user explicitly approves a write in
  a test tenant.

### P1: Billing Preview-Only Smoke

Goal:

- add a preview-only smoke for high-risk billing rate-card apply design.

Allowed:

- read billing settings
- read rate-card list/detail
- call preview-only billing rate-card design path if backend preview supports it

Blocked:

- no `/agent` confirmed billing write
- no production billing mutation

Status:

- implemented as `npm run smoke:agent-billing-production`.
- without `WMS_TOKEN`, it checks production health and capability metadata.
- with `WMS_TOKEN`, it reads billing settings, lists rate cards, and exercises
  `settings billing-rate-card preview` without returning or using a confirmable
  write card.
- authenticated read/list passed for the online test account, but preview is
  currently blocked by tenant allowed-tools: production returned `403` for
  `settings.billing_rate_card.preview`.

Next:

- decide whether the online test tenant should enable
  `settings.billing_rate_card.preview` for preview-only smoke.
- do not enable billing apply or any billing `/agent` write gate as part of
  this smoke.

### P2: Settings Governance Read Coverage

Goal:

- ensure local agents can explain provider roster, allowed tools, confirmation
  policy, model validation state, and missing configuration without seeing
  secrets.

Implemented commands:

```bash
node tools/wms.mjs agent provider-health
node tools/wms.mjs agent allowed-tools
node tools/wms.mjs agent confirmation-policy
node tools/wms.mjs agent model-roster
```

Notes:

- the commands consume the existing `/api/v1/agent/settings` platform endpoint.
- no backend endpoint or local-agent product shell change is required.
- raw provider secrets are not exposed; only `has_api_key` and validation state
  are returned.

### P2: Recovery Matrix CLI Convenience

Goal:

- make recovery review easier for agents without opening the app UI.

Implemented commands:

```bash
node tools/wms.mjs receiving recover --dry-run --error-code ERROR
node tools/wms.mjs putaway recover --dry-run --error-code ERROR
node tools/wms.mjs picking recover --dry-run --error-code ERROR
node tools/wms.mjs shipping recover --dry-run --error-code ERROR
node tools/wms.mjs inventory recover --dry-run --error-code ERROR
node tools/wms.mjs evidence failed --limit 20
node tools/wms.mjs evidence replay-preview --id EVIDENCE-ID
```

Notes:

- Putaway, Picking, Shipping, and Inventory now have explicit `recover
  --dry-run` aliases like Receiving.
- recovery aliases are static, preview-only guidance and do not call backend
  write endpoints.

### P3: Desktop-First Admin Reads

Goal:

- expose enough read-only admin state for agents to answer questions without
  navigating the UI.

Candidate reads:

- `node tools/wms.mjs admin subscription-status`
- `node tools/wms.mjs admin warehouse-setup`
- `node tools/wms.mjs admin billing-readiness`
- `node tools/wms.mjs admin integration-status --client-id CLIENT`
- `node tools/wms.mjs admin audit-summary`

Rule:

- keep these read-only until a dedicated preview/write gate exists.

Status:

- implemented as authenticated, read-only CLI commands.
- all five commands expose `agent_write_gate.enabled=false` in capability
  metadata.

## Write Gates That Stay Blocked

Do not add write gates yet for:

- high-risk Settings writes
- billing apply
- provider secrets and model roster updates
- allowed-tool governance changes
- destructive deletes
- carrier voids and label-completion exceptions
- inventory bulk mutation

Each future write gate must follow
[32-high-risk-settings-write-design.md](32-high-risk-settings-write-design.md)
or a domain-specific equivalent.

User-management writes are the exception: `wms users create`, `wms users
update`, and `wms users reset-password` now use the dedicated
`/api/v1/users/management/{preview|agent}` evidence gate. The critical
`wms users cleanup` command uses the separate
`/api/v1/users/cleanup/{preview|agent}` gate and can only retain one named
active platform admin. These commands are not available as free-form
local-agent chat writes.

`wms users deactivate-except` is the preferred reversible production cleanup
for test accounts. It changes only `is_active` after a live preview and keeps
all user rows available for later review or authorized archival.

Current confirmation:

- `smoke:agent-production` asserts high-risk Settings/admin governance
  commands remain without enabled agent write gates.
- `smoke:agent-admin-production` asserts admin reads are authenticated and
  `agent_write_gate.enabled=false`.
- no allowed-tools governance mutation was made while testing authenticated
  billing preview.

## Skill Updates

Platform-owned skills should continue to document:

- safe read commands
- preview-first write flow
- evidence inspection
- idempotency and retry rules
- high-risk blocked areas

The local-agent process owns runtime prompt assembly, provider selection, and
chat behavior. Platform skills should not prescribe product-shell UI behavior
beyond required safety boundaries.

## Acceptance Gate

Every platform CLI/skill coverage change should pass:

```bash
node --check tools/wms.mjs
cd frontend && npm run check:agent-contract
cd frontend && npm run check:agent-readiness
cd frontend && npm run smoke:agent-production
cd frontend && npm run smoke:agent-import-production
cd frontend && npm run smoke:agent-billing-production
cd frontend && npm run smoke:agent-admin-production
cd frontend && npm run smoke:agent-settings-confirm-production
git diff --check
```
