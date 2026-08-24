---
name: wms-inventory-operator
description: Use when an agent needs to inspect or operate WMS Inventory through governed CLI/API guardrails: lookup, list, transaction history, count, adjust, hold, release, evidence, and recovery.
---

# WMS Inventory Operator

Use tenant-scoped CLI/API commands only. Never run direct SQL.

## Inspect

```bash
WMS_TOKEN=... node tools/wms.mjs inventory lookup --query SKU --limit 20
WMS_TOKEN=... node tools/wms.mjs inventory list --search SKU --limit 20
WMS_TOKEN=... node tools/wms.mjs inventory transactions --sku-id SKU-ID --limit 20
WMS_TOKEN=... node tools/wms.mjs evidence list --action inventory.hold --limit 20
WMS_TOKEN=... node tools/wms.mjs evidence detail --id EVIDENCE-ID
```

## Preview

```bash
WMS_TOKEN=... node tools/wms.mjs inventory count --dry-run --live-preview --location-id LOC-ID --sku-id SKU-ID --counted-quantity QTY
WMS_TOKEN=... node tools/wms.mjs inventory adjust --dry-run --live-preview --inventory-id INV-ID --new-quantity QTY --reason REASON
WMS_TOKEN=... node tools/wms.mjs inventory hold --dry-run --live-preview --inventory-id INV-ID --reason REASON
WMS_TOKEN=... node tools/wms.mjs inventory release --dry-run --live-preview --inventory-id INV-ID --quantity QTY --reason REASON
WMS_TOKEN=... node tools/wms.mjs inventory import preview --file inventory.csv
```

Import preview is read-only and returns mapping, row impact, errors, and safe
next commands. It does not produce a confirmation token.

## Execute

Execute only after preview returns `ok: true`, `confirmation_token`, and
`evidence_id`.

```bash
WMS_TOKEN=... node tools/wms.mjs inventory count --confirm TOKEN --production-confirm --idempotency-key KEY --location-id LOC-ID --sku-id SKU-ID --counted-quantity QTY
WMS_TOKEN=... node tools/wms.mjs inventory adjust --confirm TOKEN --production-confirm --idempotency-key KEY --inventory-id INV-ID --new-quantity QTY --reason REASON
WMS_TOKEN=... node tools/wms.mjs inventory hold --confirm TOKEN --production-confirm --idempotency-key KEY --inventory-id INV-ID --reason REASON
WMS_TOKEN=... node tools/wms.mjs inventory release --confirm TOKEN --production-confirm --idempotency-key KEY --inventory-id INV-ID --quantity QTY --reason REASON
```

Import writes, delete, and bulk mutation remain outside this skill.
