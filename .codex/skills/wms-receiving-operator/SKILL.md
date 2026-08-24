---
name: wms-receiving-operator
description: Use when an agent needs to operate WMS Receiving through CLI/API guardrails: inbound lookup, package scan, dock choice, receive preview, confirmation token execution, and receiving recovery.
---

# WMS Receiving Operator

Use only documented CLI/API paths. Never write directly to the database or call
undocumented endpoints.

## Start

```bash
node tools/wms.mjs capabilities --json
WMS_TOKEN=... node tools/wms.mjs inbound list --limit 20
WMS_TOKEN=... node tools/wms.mjs inbound detail --order-id INB-ID
```

## Preview First

```bash
WMS_TOKEN=... node tools/wms.mjs receiving scan --dry-run --live-preview --order-id INB-ID --code CODE
WMS_TOKEN=... node tools/wms.mjs receiving choose-dock --dry-run --live-preview --order-id INB-ID --package-id PKG-ID --staging-location-id DOCK-ID
WMS_TOKEN=... node tools/wms.mjs receiving confirm --dry-run --live-preview --order-id INB-ID --package-id PKG-ID --quantity QTY --staging-location-id DOCK-ID
```

Only execute Receiving confirmation when preview returns `ok: true`,
`confirmation_payload.confirmation_token`, and `evidence_id`.

```bash
WMS_TOKEN=... node tools/wms.mjs receiving confirm --confirm TOKEN --production-confirm --idempotency-key KEY --order-id INB-ID --package-id PKG-ID --quantity QTY --staging-location-id DOCK-ID
```

## Recovery

If a command fails, follow `safe_commands` from the JSON error. For Receiving
exceptions:

```bash
WMS_TOKEN=... node tools/wms.mjs receiving recover --dry-run --live-preview --error-code CODE
```
