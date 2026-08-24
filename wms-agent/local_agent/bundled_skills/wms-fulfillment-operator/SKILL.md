---
name: wms-fulfillment-operator
description: Use when an agent needs to operate WMS Putaway, Picking, or Shipping through governed CLI/API guardrails with preview, evidence token, idempotency, and recovery checks.
---

# WMS Fulfillment Operator

Use this for Putaway, Picking, and Shipping. Never bypass live preview,
evidence tokens, or idempotency keys for enabled writes.

## Discover Work

```bash
WMS_TOKEN=... node tools/wms.mjs task list --status pending --type putaway --limit 20
WMS_TOKEN=... node tools/wms.mjs task list --status pending --type pick --limit 20
WMS_TOKEN=... node tools/wms.mjs outbound list --limit 20
WMS_TOKEN=... node tools/wms.mjs outbound detail --order-id OUT-ID
```

## Preview

```bash
WMS_TOKEN=... node tools/wms.mjs putaway confirm --dry-run --live-preview --task-id TASK-ID --destination-location-id LOC-ID --quantity QTY
WMS_TOKEN=... node tools/wms.mjs picking confirm --dry-run --live-preview --task-id TASK-ID --quantity QTY
WMS_TOKEN=... node tools/wms.mjs picking short --dry-run --live-preview --task-id TASK-ID --quantity AVAILABLE --reason REASON
WMS_TOKEN=... node tools/wms.mjs shipping pack --dry-run --live-preview --order-id OUT-ID --sku-id SKU-ID --quantity QTY
WMS_TOKEN=... node tools/wms.mjs shipping ship --dry-run --live-preview --order-id OUT-ID --carrier CARRIER --tracking-number TRACKING
```

## Recover

Use recovery planners to explain a blocked flow before retrying or escalating.
They do not write state and do not replace live preview for enabled writes.

```bash
WMS_TOKEN=... node tools/wms.mjs putaway recover --dry-run --error-code ERROR
WMS_TOKEN=... node tools/wms.mjs picking recover --dry-run --error-code ERROR
WMS_TOKEN=... node tools/wms.mjs shipping recover --dry-run --error-code ERROR
```

## Execute

Execute only after preview returns `ok: true`, `confirmation_token`, and
`evidence_id`.

```bash
WMS_TOKEN=... node tools/wms.mjs putaway confirm --confirm TOKEN --production-confirm --idempotency-key KEY --task-id TASK-ID --destination-location-id LOC-ID --quantity QTY
WMS_TOKEN=... node tools/wms.mjs picking confirm --confirm TOKEN --production-confirm --idempotency-key KEY --task-id TASK-ID --quantity QTY
WMS_TOKEN=... node tools/wms.mjs picking short --confirm TOKEN --production-confirm --idempotency-key KEY --task-id TASK-ID --quantity AVAILABLE --reason REASON
WMS_TOKEN=... node tools/wms.mjs shipping pack --confirm TOKEN --production-confirm --idempotency-key KEY --order-id OUT-ID --sku-id SKU-ID --quantity QTY
WMS_TOKEN=... node tools/wms.mjs shipping ship --confirm TOKEN --production-confirm --idempotency-key KEY --order-id OUT-ID --carrier CARRIER --tracking-number TRACKING
```

Void, label completion, carrier exceptions, and pick substitution remain
outside this skill.
