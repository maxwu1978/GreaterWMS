---
name: wms-email-intake-operator
description: Use when a warehouse operator receives customer instructions by email or phone follow-up and needs to read the message and attachments, classify inbound or outbound documents, extract SKU/quantity/SN/ETA/customer/transport facts, reconcile them with GreaterWMS, and receive a safe next-step plan. Trigger for pack lists, inbound notices, delivery requests, pick tickets, scan sheets, QC workbooks, appointment emails, PDF/image/XLSX/CSV attachments, or conflicting shipment instructions.
---

# WMS Email Intake Operator

Turn customer email into an evidence-backed GreaterWMS workflow decision. The
customer does not log in; the warehouse operator owns intake, review, and the
decision to create or continue work. Use this Skill before any inbound or
outbound write that originates from email.

## Operating Contract

- Read the complete thread and every relevant attachment before deciding what
  the message means.
- Preserve original files. Do not send, reply, archive, delete, or label email
  unless the user explicitly requests that separate action.
- Start read-only. Never create, update, import, dispatch, receive, put away,
  pick, or cancel a WMS record from extraction alone.
- Never use direct SQL, undocumented endpoints, guessed IDs, or model-only
  approval. Use `tools/greaterwms.mjs` and its preview/confirmation gates.
- Never expose passwords, bearer tokens, confirmation tokens, or unnecessary
  attachment contents.
- If facts conflict or a required fact is missing, stop and state exactly what
  the warehouse must confirm.

## Workflow

### 1. Establish scope

Confirm or discover the connected Gmail, Outlook, or macOS Mail account, target
thread, GreaterWMS tenant, warehouse, customer/owner scope, and authenticated
role. Determine whether the user wants analysis only, a dry-run, or a confirmed
write. If mailbox access is unavailable, ask the user to connect it or provide
the message and attachments; never guess mailbox access.

### 2. Read the source package

1. Search by sender, subject, container/tracking number, inbound/outbound code,
   customer reference, and recent date.
2. Read the active thread, not only the newest message. Record message ID,
   sender, recipients, sent time, subject, and quoted/forwarded sections.
3. Open every relevant PDF, image, XLSX, CSV, and text attachment. For
   workbooks, inspect all sheets, hidden rows/columns when available, and the
   actual data range.
4. Keep file names and page/sheet/cell or image-region evidence for every
   extracted fact. Mark OCR uncertainty instead of silently correcting it.

Use [document-mapping.md](references/document-mapping.md) when filenames are
misleading or multiple attachments are present.

### 3. Classify before suggesting a WMS action

| Source | WMS meaning | Possible result |
| --- | --- | --- |
| Inbound Notice / Inbound List | planned inbound reference and expected load | ASN metadata/details |
| Customer Pack List | package/SKU/quantity/SN reference for receiving | Pack List linked to ASN |
| Pick Ticket / Delivery Request | customer outbound instruction | outbound order/detail |
| Scan Sheet / QC workbook | warehouse inspection after physical arrival | receiving/QC result and exception |
| Appointment / delivery email | ETA, arrival, or transport information | ETA/arrival/transport planning |
| PO, invoice, quote, generic packing document | supporting evidence only | no automatic WMS order |

Hard rules:

- A Pick Ticket is outbound. Never import it as an inbound Pack List.
- A Scan Sheet or QC workbook is an inspection result, not an inbound order
  because it contains a PO, ASN, or date.
- A Pack List can arrive before ETA. If no ETA is explicitly stated, keep it as
  `Not Provided`; never infer it from sent time or file creation time.
- A late Pack List updates the same load only after matching ASN/container,
  customer, SKU set, and package IDs. Do not create a duplicate ASN or silently
  overwrite the prior source.

### 4. Extract and normalize with evidence

Extract, when present:

- document/reference, customer/owner, supplier, container/tracking number
- ETA, requested date, actual arrival, appointment, and timezone
- ship-to/delivery address, dock, carrier, driver, and transport requirement
- SKU, customer SKU, internal SKU candidate, item name, quantity, package type
- package count, lot/batch, serial number, dimensions, weight, and unit
- scan/inspection result, damage, shortage, overage, exception note, evidence URL

For SKU matching use exact code, safe normalized code, then a clearly labelled
near-match candidate. Never silently map a near match, convert a customer SKU,
or create master data from an email.

### 5. Reconcile with GreaterWMS

Use read-only lookups first and keep the authenticated tenant scope:

```bash
GREATERWMS_TOKEN=... node tools/greaterwms.mjs asn list --json
GREATERWMS_TOKEN=... node tools/greaterwms.mjs outbound list --json
GREATERWMS_TOKEN=... node tools/greaterwms.mjs sku list --query '{"goods_code__icontains":"CODE"}' --json
GREATERWMS_TOKEN=... node tools/greaterwms.mjs packlist list --asn-code ASN --json
GREATERWMS_TOKEN=... node tools/greaterwms.mjs staging-slots list --json
GREATERWMS_TOKEN=... node tools/greaterwms.mjs asn events --query '{"asn_code":"ASN"}' --json
```

Find existing records by ASN/DN code, customer reference, container/tracking
number, then customer + SKU set + quantity + date. If a likely match exists,
propose an update or attachment to that record instead of a new record.

Report customer/owner, SKU, quantity, Pack List/QC, address/dock, status, ETA,
and actual-arrival mismatches separately.

### 6. Decide the next business step

#### Inbound

- Notice/Pack List only: keep ETA `Not Provided` when absent; do not mark
  arrived or received. Reserve Stage-left/Stage-right capacity only when asked.
- ETA/appointment supplied: preview an ETA update on the existing ASN. ETA is
  planning data, not actual arrival.
- Vehicle physically present: record actual arrival, validate staging capacity,
  assign the driver when required, and start unloading. Staging remains occupied
  until receiving/QC and putaway finish.
- Cargo in staging: import the fixed-format QC/scan file and compare actual
  SKU/SN/quantity/damage with the Pack List. Record exceptions explicitly.
- QC clean or exceptions resolved: assign putaway driver and final bin,
  complete putaway, then reconcile the warehouse receipt to the customer
  instruction.

#### Outbound

- Pick Ticket/Delivery Request: find or create the outbound record only after
  confirming customer, ship-to, reference, and requested date.
- If SNs are supplied, pick those exact SNs. If no SN is supplied, pick by SKU
  and quantity; never invent SNs.
- Short, over, damaged, or blocked: keep the exception and reason explicit;
  do not silently substitute inventory.
- If a short-haul truck is needed, plan transport and assign the driver/logistics
  person before dispatch. Conflicting addresses or docks are a hard stop.
- Use POD for normal completion. Use cancel-in-transit only with a clear reason
  and confirmed disposition for returned goods.

### 7. Return a reviewable result

Before any write, return:

1. Source scope: mailbox/thread, date, attachments, and scan coverage.
2. Document classification and why each file is or is not an order.
3. Extracted facts with source evidence and confidence.
4. WMS matches, duplicates, current status, and unresolved SKU mapping.
5. Actionable exceptions and missing confirmations.
6. One recommended next action, owner, and expected result.
7. Read-only lookups and the exact dry-run command when appropriate.

Use `Not Provided` when the source did not supply ETA, driver, SN, address, or
dock. Use `Unknown` only when extraction failed or the source is ambiguous.

### 8. Execute only after explicit confirmation

1. Re-read current state; email data may be stale.
2. Run the exact command with `--dry-run --json`.
3. Check `ok`, entity, state before/after, validation messages, confirmation
   token, evidence ID, and tenant scope.
4. Get confirmation of the reviewed dry-run before changing WMS state. In AI
   mode, confirmation must be the structured approval action in the AI
   conversation; do not treat a free-text "confirm" as authorization.
5. Execute only with the server-issued confirmation token and stable idempotency
   key when supported.
6. Re-read the record, events, dashboard queue, staging assignment, and
   inspection/exception state.
7. Report the change and the next role-owned task. Never claim success from a
   process exit code alone.

## Safe CLI Routing

### AI source-backed intake

Before an AI-originated ASN or outbound write, capture the source metadata and
extracted fields first. The endpoint returns a source evidence ID; keep it
server-side and bind it to the AI preview. Do not put passwords, bearer tokens,
or confirmation tokens in the evidence payload.

```bash
node tools/greaterwms.mjs source capture --data-file source-evidence.json --json
GREATERWMS_AGENT_SURFACE=ai node tools/greaterwms.mjs asn create \
  --data-file asn.json --source-evidence-id SOURCE_ID --dry-run --json
```

The AI preview response includes the source summary and payload hash. The AI
approval action calls the structured AI approval endpoint with the AI surface;
the server keeps the preview state and executes the write without returning a
CLI confirmation token. The browser Web flow does not use this token flow:
its Preview button creates a `WEB_FORM` source record automatically, and its
Approve button executes the write in the same Web workflow. The legacy CLI
token flow remains available on the default CLI surface during the
compatibility period.

Examples below are preview-only planning commands, not permission to skip the
confirmation gate:

```bash
node tools/greaterwms.mjs asn eta --id ASN_ID --data '{"expected_arrival_at":"..."}' --dry-run --json
node tools/greaterwms.mjs asn arrival --id ASN_ID --data '{}' --dry-run --json
node tools/greaterwms.mjs asn reserve-staging --id ASN_ID --asn-code ASN --data '{"staging_bins":["STAGE-LEFT-01"]}' --dry-run --json
node tools/greaterwms.mjs asn unload-start --id ASN_ID --asn-code ASN --data '{}' --dry-run --json
node tools/greaterwms.mjs packlist import --asn-code ASN --file FILE --dry-run --json
node tools/greaterwms.mjs inspection import --asn-code ASN --file FILE --allow-all --dry-run --json
node tools/greaterwms.mjs receiving qc --data JSON --dry-run --json
node tools/greaterwms.mjs receiving reconcile --data JSON --dry-run --json
node tools/greaterwms.mjs asn putaway --id ASN_DETAIL_ID --data JSON --dry-run --json
node tools/greaterwms.mjs outbound create --data JSON --dry-run --json
node tools/greaterwms.mjs outbound-detail create --data JSON --dry-run --json
node tools/greaterwms.mjs outbound pick --id DN_ID --data JSON --dry-run --json
node tools/greaterwms.mjs outbound dispatch --id DN_ID --data JSON --dry-run --json
node tools/greaterwms.mjs transport create --data JSON --dry-run --json
```

For structured errors, stop and use `error_code`, `why_blocked`,
`recommended_action`, and `safe_commands`. Do not retry a stale confirmation
token or bypass a stage/permission error.

## Hard Stops

Stop for human confirmation when customer/owner, address/dock, container/order
reference, Pack List load, SKU/SN, or quantities conflict; the attachment is
unreadable or incomplete; ETA is absent but urgency is requested; a write would
delete, bulk-clean, overwrite history, or send email; the WMS status disallows
the requested step; or authentication/scope/preview evidence is unavailable.

## Completion Standard

The task is complete only after the source inventory is classified, facts are
tied to evidence, WMS matches and exceptions are explicit, one next action and
responsible role are identified, and any proposed write has a reviewed dry-run.
After execution, verify WMS state and the dashboard next step.
