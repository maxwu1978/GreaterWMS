---
name: wms-recovery-debugger
description: Use when a WMS CLI/API/agent operation fails and the agent needs to inspect structured recovery fields, rerun safe commands, check evidence, and avoid unsafe retries.
---

# WMS Recovery Debugger

Use structured JSON. Do not infer success from prose.

## First Checks

- Read `ok`, `error_code`, `what_happened`, `why_blocked`,
  `recommended_action`, and `safe_commands`.
- Run only safe commands that match the same tenant, workflow, and object.
- If token mismatch occurs, rerun the matching `--dry-run --live-preview`.

## Useful Commands

```bash
node tools/wms.mjs capabilities --json
WMS_TOKEN=... node tools/wms.mjs auth whoami
WMS_TOKEN=... node tools/wms.mjs evidence list --entity-id OBJECT-ID --limit 20
WMS_TOKEN=... node tools/wms.mjs evidence detail --id EVIDENCE-ID
WMS_TOKEN=... node tools/wms.mjs evidence failed --limit 20
WMS_TOKEN=... node tools/wms.mjs evidence replay-preview --id EVIDENCE-ID
WMS_TOKEN=... node tools/wms.mjs inventory transactions --sku-id SKU-ID --limit 20
WMS_TOKEN=... node tools/wms.mjs inbound detail --order-id INB-ID
WMS_TOKEN=... node tools/wms.mjs outbound detail --order-id OUT-ID
WMS_TOKEN=... node tools/wms.mjs receiving recover --dry-run --error-code ERROR
WMS_TOKEN=... node tools/wms.mjs putaway recover --dry-run --error-code ERROR
WMS_TOKEN=... node tools/wms.mjs picking recover --dry-run --error-code ERROR
WMS_TOKEN=... node tools/wms.mjs shipping recover --dry-run --error-code ERROR
WMS_TOKEN=... node tools/wms.mjs inventory recover --dry-run --error-code ERROR
```

Never retry a production write with a stale confirmation token. Refresh preview,
record the new `evidence_id`, then retry with a new idempotency key.
