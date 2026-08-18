---
name: wms-master-data-configurator
description: Analyze warehouse emails and attachments to propose, verify, and—only after explicit chat confirmation—configure GreaterWMS master data such as warehouses, customers, suppliers, and SKUs. Use when source documents must be converted into safe master-data changes; do not use for ASN execution, receiving, QC, putaway, or inventory operations.
---

# WMS Master Data Configurator

Configure GreaterWMS master data from customer emails, PDFs, Excel files, and
images without inventing missing values or creating duplicates.

## Operating Rules

- Start in read-only mode. Parse the supplied email and attachments, then query
  the current GreaterWMS tenant before proposing any write.
- Never create, update, merge, or delete master data without an explicit
  confirmation that names the displayed batch ID and the exact entities or
  fields approved. A bare “confirm” is insufficient when more than one batch
  or entity is pending.
- Treat an exact existing match as `REUSE`, a clear new record as `CREATE`, a
  changed existing record as `UPDATE_REVIEW`, and a fuzzy or conflicting match
  as `AMBIGUOUS`. Do not silently merge customer SKU, supplier SKU, S-SKU,
  barcode, or internal SKU values.
- Do not use placeholder values for required fields. Ask the user for missing
  address, contact, manager, level, dimensions, unit, description, cost,
  price, class, brand, color, shape, specification, origin, or barcode data.
- Do not create a supplier, customer, warehouse, or SKU merely because it is
  mentioned in an email. The email is evidence, not authorization.
- Access GreaterWMS with the administrator username and password. Before any
  read or write, verify the local CLI session is `login_mode=admin` and
  `role=Admin`; never use a Warehouse or other staff session for this Skill.
- Passwords are login input only. Never place them in source evidence, audit
  payloads, temporary JSON, shell history, chat output, or Skill files. Keep
  only the resulting session token in the protected local CLI session store.
- Respect the logged-in WMS role. If the current operator cannot write a
  master-data module, stop and tell the user which manager/admin role is
  required. Never bypass the permission model.
- Keep all source values, normalized values, conversions, confidence, and
  unresolved questions in the preview. Preserve the original source units;
  show any converted US/metric values side by side and do not overwrite a
  source value with a conversion.
- For an explicitly approved source-SKU import, missing optional master-data
  fields remain blank. Do not invent lookup records or zero-valued business
  fields just to satisfy the normal web form. The import must still include a
  real tenant-scoped `source_evidence_id`, an internal `goods_code`, and the
  approved supplier name (`Delta` or `PZ`).
- Normalize physical measurements to US customary values before writing to the
  US warehouse: dimensions to `in`, weight to `lb`, and set
  `measurement_unit=in/lb`. Preserve the source values and source unit in
  `source_note`; preserve the customer S-SKU in `customer_sku`.
- Do not perform ASN, Outbound, Receiving, QC, Putaway, staging, inventory, or
  serial-number actions. This Skill ends after verified master-data changes.

## Source Intake

Accept email files or attachments supplied in the conversation. When the user
asks to read the configured macOS mailbox, use the local Mail CLI and keep the
mail read separate from WMS writes:

```bash
python3 /Users/wuqingxin/LocalProjects/texas-ranch-growth-ops/agent-runtime/scripts/mac_mail_local_triage.py \
  scan --account "$WMS_MAIL_ACCOUNT" --days 7 --json-out /tmp/wms-master-data-mail.json
```

For nested `.eml`, PDF, XLSX, CSV, and image attachments, extract the relevant
fields and record the source location (message body, attachment name, PDF
page, Excel sheet/cell, or image region). Use the existing email-intake
attachment guidance when needed:

- [attachment-processing.md](../wms-scheduled-email-intake/references/attachment-processing.md)
- [document-mapping.md](../wms-scheduled-email-intake/references/document-mapping.md)

If the source came from email, capture a tenant-scoped source record before
configuration when the current WMS CLI supports it. Use operation
`master_data.configure`, keep the Message-ID/content hash, and treat a
duplicate source as a readback/review rather than a new configuration run.

## Analyze and Match

Read [master-data-fields.md](references/master-data-fields.md) before building
the payload or deciding that an email contains enough information to create a
record.

1. Identify the tenant, the configured warehouse, the owner/customer, the
   shipper/supplier, and every product identifier.
2. Normalize whitespace, case, punctuation, legal suffixes, and common unit
   spellings for comparison only. Preserve the exact source text for audit.
3. Query the tenant-scoped lists for `warehouse`, `customer`, `supplier`, and
   `sku`/`goods`. Query exact codes first, then exact names, then fuzzy matches.
4. For each candidate, show the existing record ID, exact fields that match,
   fields that differ, and the proposed action. A fuzzy match never becomes an
   automatic update.
5. For products, distinguish customer part number, supplier part number,
   S-SKU, barcode, and internal `goods_code`. If the system has no alias field,
   do not pretend that an alias was stored; ask which code should be the
   internal `goods_code` and preserve the other identifiers in the source
   evidence/provenance.
6. Treat net weight as the product weight candidate. Treat gross weight as
   packaging/shipment evidence unless the user explicitly says otherwise.
7. Only map dimensions to SKU fields when the source clearly identifies the
   package/product dimension. Display `W x D x H`, original unit, and converted
   value; do not infer orientation or unit.

## Confirmation Card

Before any write, show a compact card with a generated batch ID such as
`MDM-20260818-01`:

```text
Batch: MDM-...
Source: email / sender / subject / received time / Message-ID
Tenant: ...

Entity | Action | Existing ID | Proposed fields | Source location | Confidence
...

Blocked or unresolved:
- ...
Required user decision:
- ...
```

Ask for confirmation in the conversation. Accept only a confirmation that
clearly identifies the batch and scope, for example:

`Confirm MDM-20260818-01: create the supplier and the four approved SKUs; reuse the existing customer; do not update warehouse.`

If the user approves only part of the batch, write only that subset and create
a new preview for changed fields. If a required field or match remains
uncertain, stop and ask one focused question instead of writing.

## Safe WMS Write

Use the installed GreaterWMS CLI and the authenticated local session. Do not
put tokens, passwords, or confirmation tokens into the source record or chat.
If an administrator session is not already available, log in interactively or
through protected environment input, then verify it before querying:

```bash
node tools/greaterwms.mjs login --env production --name "$GREATERWMS_ADMIN_NAME"
node tools/greaterwms.mjs auth status --json
```

The status must report `login_mode: admin` and `role: Admin`. Do not put the
password directly in a command copied into chat.

```bash
node tools/greaterwms.mjs <resource> list --query '<JSON>' --json
node tools/greaterwms.mjs <resource> create --data-file /tmp/mdm-<batch>.json --dry-run --json
node tools/greaterwms.mjs <resource> create --data-file /tmp/mdm-<batch>.json \
  --idempotency-key "$IDEMPOTENCY_KEY" \
  --confirmation-token "$PREVIEW_CONFIRMATION_TOKEN" --confirm --json
```

For source-traced SKU batches, use the dedicated import path after review:

```bash
node tools/greaterwms.mjs sku import --data-file /tmp/mdm-<batch>.json --dry-run --json
node tools/greaterwms.mjs sku import --data-file /tmp/mdm-<batch>.json --confirm --json
```

The source import endpoint permits blank optional fields and does not require
the separate class/brand/color/shape/specification lookup rows. It does not
permit cross-tenant evidence, duplicate active `goods_code` values, or a
missing source evidence record.

Use resources `warehouse`, `customer`, `supplier`, and `sku` (or `goods`).
Use a deterministic key such as
`mdm:<source-evidence-id>:<entity>:<normalized-primary-key>` for each create
or update. Keep the server-issued token inside the Skill process. For updates,
show a before/after diff and require a separate explicit approval; never turn a
new email into a silent overwrite.

Write in dependency order when approved: warehouse/company context if
explicitly approved, customer and supplier, then SKU records. If one write
fails, stop, report the exact entity and error, and read back all previous
results. Do not retry with a new idempotency key until the previous result has
been checked.

## Verification and Result

After each successful write, query by ID and by primary key. Verify:

- the record belongs to the current tenant;
- the exact name/code and required fields match the approved preview;
- no duplicate active record was created;
- source/provenance and audit references are present when the endpoint supports
  them;
- no ASN, outbound, receiving, putaway, inventory, or serial data changed.

Report `CREATED`, `REUSED`, `UPDATED`, `BLOCKED`, or `FAILED` for every entity,
plus the next missing input. Never report “configured” based only on a CLI
exit code; use the readback result.
