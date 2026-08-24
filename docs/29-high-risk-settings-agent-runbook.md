# High-Risk Settings Agent Runbook

This runbook keeps high-risk Settings work in design and preview mode until a
separate release explicitly enables a write gate.

## Scope

High-risk Settings are:

- billing rate-card apply and billing profile changes
- users, roles, permissions, invites, resets, and deactivation
- provider secrets, model roster settings, and allowed-tool governance
- nested client settings, SKU attributes, destructive deletes, and bulk mutation

## Current Boundary

Agents may read these settings when the authenticated user has the required
permission. Agents may also produce a preview or design note when a preview
endpoint exists.

Agents must not execute high-risk Settings writes through CLI, local-agent
confirmation, direct API calls, database access, or generated scripts.

## Required Design Before Any Write Gate

Before enabling one high-risk write gate, create a design note that answers:

- What object is being changed?
- Which permission is required?
- Which fields are allowed, rejected, or redacted?
- What preview evidence is stored before confirmation?
- What exact endpoint performs the confirmed write?
- What idempotency key shape is recommended?
- What audit record proves who changed what?
- What rollback or recovery path exists if the setting blocks operations?

## Minimum Write-Gate Contract

Every future high-risk Settings write must use:

- a read-only preview endpoint
- persisted evidence with redacted secrets
- a confirmation token that matches the latest preview payload
- `X-Idempotency-Key`
- structured recovery detail on failure
- unit tests for missing idempotency, token mismatch, payload mismatch, replay,
  and forbidden fields
- a production smoke that defaults to preview-only

## Current Safe Commands

Agents may run:

```bash
WMS_TOKEN=... node tools/wms.mjs settings billing
WMS_TOKEN=... node tools/wms.mjs settings rate-card --rate-card-id RATE-CARD-ID
WMS_TOKEN=... node tools/wms.mjs settings users --limit 20
WMS_TOKEN=... node tools/wms.mjs settings user --user-id USER-ID
WMS_TOKEN=... node tools/wms.mjs settings permissions
WMS_TOKEN=... node tools/wms.mjs agent settings
```

Preview-only:

```bash
WMS_TOKEN=... node tools/wms.mjs settings billing-rate-card preview --rate-card-id RATE-CARD-ID --changes '{"rules":{"storage_per_pallet_day":1.5}}'
```

Blocked until a later runbook enables them:

```bash
node tools/wms.mjs settings billing-rate-card preview --confirm ...
node tools/wms.mjs settings users preview --confirm ...
node tools/wms.mjs agent settings --confirm ...
```

## Human Review Checklist

- Can the operator understand the changed setting from the preview alone?
- Are secrets and tokens absent from preview, evidence, logs, and prompts?
- Does the write have one clear recovery path?
- Does replay return the same result for the same idempotency key?
- Does a changed body with the same idempotency key fail?
