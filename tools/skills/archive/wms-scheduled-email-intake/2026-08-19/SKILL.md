---
name: wms-scheduled-email-intake
description: Use when a warehouse operator receives customer instructions by email or phone follow-up and needs to read the message and attachments, classify inbound or outbound documents, extract SKU/quantity/SN/ETA/customer/transport facts, reconcile them with GreaterWMS, and receive a safe next-step plan. Trigger for pack lists, inbound notices, delivery requests, pick tickets, scan sheets, QC workbooks, appointment emails, PDF/image/XLSX/CSV attachments, or conflicting shipment instructions.
---

# Scheduled WMS Email Intake

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
- Use the configured warehouse/customer mapping below. Do not treat a customer
  or final-consignee address as a warehouse-address conflict.
- If a required business fact is still unresolved, create only a pre-arrival
  review record when the minimum identity is known, then show the unresolved
  items for confirmation. Do not mark cargo arrived, received, or put away.

## Current Warehouse and Customer Mapping

For this tenant, the operational receiving site is fixed:

```text
Warehouse: Peak Smart Logistics
Receiving address: 1991 Lakepointe Dr, Dock #24, Lewisville, TX
Customer/owner: Delta Electronics (USA) Inc.
Customer/final-consignee address: 601 Data Dr, Plano, TX
```

Use Peak Smart Logistics and Dock #24 as the WMS receiving location unless the
operator explicitly changes the warehouse configuration. When an email or
attachment shows Delta Electronics Plano, store it as the customer/owner or
final-consignee address. It is not, by itself, a conflict with the Peak
receiving address. Keep both roles visible in the evidence and ASN preview.

## Workflow

### macOS Mail local CLI (required on this Mac)

When the source mailbox is the macOS Mail app, read mail through the local,
read-only adapter before using any GreaterWMS command. The local adapter is
the mailbox reader; `tools/greaterwms.mjs` only submits evidence and operates
on WMS records after review.

Configure the adapter path and the exact mailbox account explicitly:

```bash
export WMS_MAC_MAIL_CLI="${WMS_MAC_MAIL_CLI:-/Users/wuqingxin/LocalProjects/texas-ranch-growth-ops/agent-runtime/scripts/mac_mail_local_triage.py}"
export WMS_MAIL_ACCOUNT="${WMS_MAIL_ACCOUNT:-admin@vestwoodshft.com}"

python3 "$WMS_MAC_MAIL_CLI" accounts
python3 "$WMS_MAC_MAIL_CLI" scan \
  --account "$WMS_MAIL_ACCOUNT" \
  --days 1 \
  --cursor "${CURSOR_BEFORE:-}" \
  --json-out /tmp/wms-mail-scan.json
```

`CURSOR_BEFORE` comes from the WMS `source sync-start` response. Leave it
empty on the first run. The CLI re-scans a five-minute overlap by default so
messages arriving around the boundary are not missed; Message-ID and content
hash deduplication make the overlap safe.

Before scanning, confirm that `WMS_MAIL_ACCOUNT` appears in the `accounts`
output. If it does not, stop and ask the operator to connect or authorize the
account in Mail.app. Do not put the mailbox password into GreaterWMS, the WMS
CLI, or evidence payloads; Mail.app's logged-in account and macOS Automation
permission provide local access.

For a structured local-only classification pass, use:

```bash
python3 "$WMS_MAC_MAIL_CLI" triage \
  --account "$WMS_MAIL_ACCOUNT" \
  --days 1 \
  --no-model \
  --json-out /tmp/wms-mail-triage.json
```

Use the scan/triage JSON to select the thread, then read the complete thread
and attachments locally as required. Preserve the returned Message-ID,
thread ID, sender, recipients, timestamps, attachment names, and hashes when
building the source evidence. Never send, reply, archive, delete, or label
mail from this workflow.

To read the selected message body and export its actual attachment bytes, run
the local CLI `read` command after the Message-ID duplicate preflight:

```bash
python3 "$WMS_MAC_MAIL_CLI" read \
  --account "$WMS_MAIL_ACCOUNT" \
  --message-id "MESSAGE_ID" \
  --output-dir "/tmp/wms-mail-read-MESSAGE_ID" \
  --json-out "/tmp/wms-mail-read-MESSAGE_ID.json"
```

The command is read-only. It writes `message-body.txt` and numbered attachment
files to the local temporary directory and returns each file's original name,
detected content type, byte size, and SHA-256. Use the returned file paths to
read the attachment contents, not the filename alone. Do not pass `--include-body`
unless the full body is needed in a local test result; the body remains in the
local `message-body.txt` by default.

When building `source-evidence.json`, preserve the source timeline and content
explicitly. If the message is forwarded or contains a nested `.eml`, the
nested customer message is the business source and the outer message is
forwarding context. Never use the outer forwarder's sender, subject, or sent
time as the customer source. Use this shape:

```json
{
  "metadata": {
    "mailbox_account": "admin@example.com",
    "message_id": "outer-message-id",
    "thread_id": "outer-thread-id",
    "sender_name": "Forwarder",
    "sender_email": "forwarder@example.com",
    "subject": "Fwd: customer instruction",
    "received_at": "2026-08-18T13:22:17-05:00",
    "forwarded_email": {
      "sender_name": "Forwarder",
      "sender_email": "forwarder@example.com",
      "subject": "Fwd: customer instruction"
    },
    "original_email": {
      "sender_name": "Customer contact",
      "sender_email": "customer@example.com",
      "from_raw": "customer@example.com On Behalf Of Customer Team",
      "sent_at": "2026-08-14T09:20:00",
      "to": ["Receiving <receiving@example.com>"],
      "cc": [],
      "subject": "Delivery Request TRHU4217950",
      "message_id": "nested-message-id",
      "thread_id": "nested-thread-id",
      "body": "Complete original email body",
      "source_location": "nested .eml, original headers and body"
    }
  }
}
```

The WMS uses `original_email` first for sender, subject, sent time, body, and
business references, while retaining the outer headers for traceability. Put
the customer's sent timestamp in `original_email.sent_at`, the mailbox arrival
timestamp in root `metadata.received_at`, and the plain-text body in
`original_email.body`. Keep Message-ID, thread ID, recipients, attachment
names, hashes, and source locations. If the body is not captured, omit it
rather than copying a summary into the body field; Source Intake will show the
structured fields and attachments and mark the original body as not captured.

Process every exported attachment according to
[attachment-processing.md](references/attachment-processing.md). A nested
`.eml` must be parsed as a new source package, including its own body and
attachments. A PDF, workbook, CSV, text file, or image must be inspected for
actual fields and evidence locations. If any relevant attachment is encrypted,
corrupt, unreadable, or only partially parsed, mark the source `BLOCKED` and do
not create an ASN or outbound record.

### Codex Automation scheduled mode

When this Skill is invoked by a scheduled Codex Automation, treat the run as
an intake scan, not as permission to write an ASN or outbound order:

1. Start a mailbox sync run and keep its returned ID and `cursor_before` in
   memory.
2. For macOS Mail, run the local CLI `accounts` check followed by `scan` or
   `triage --no-model` with the returned `cursor_before`. Do not use
   `tools/greaterwms.mjs` to search or read the mailbox; that CLI does not
   access Mail.app.
3. Before opening a full thread, use the Message-ID from the local scan as a
   lightweight WMS preflight:

   ```bash
   node tools/greaterwms.mjs source list \
     --mailbox-account "$WMS_MAIL_ACCOUNT" \
     --message-id "MESSAGE_ID" --json
   ```

   If a source already exists, count it as duplicate and do not download its
   attachments, call AI classification, or create another preview. Otherwise,
   capture the message and its attachment metadata with `source capture`,
   passing the sync run ID, Message-ID, thread ID, sender, subject, timestamps,
   attachment hashes, and storage references.
   If `source capture` returns `duplicate: true`, increment the duplicate
   counter and do not reopen the full thread, call AI classification, or build
   another preview for that item.
4. Use `source intake` and `source intake-get` to reconcile the captured item
   and update its classification, conflicts, match, owner, and next action.
5. Leave external instructions in `READY_FOR_PREVIEW` or
   `APPROVAL_REQUIRED` until the user approves the structured AI action.
6. Finish the sync run with counters and the scan's `cursor_after`, including
   partial failures. Only a `SUCCEEDED` run advances the mailbox cursor;
   `PARTIAL` and `FAILED` runs remain retryable. Never mark a run successful
   when a message was skipped without a recorded reason.

The scheduled runner may automatically capture, classify, deduplicate, and
prepare previews. It must not silently create ASN/Outbound records, mark cargo
arrived, receive goods, or change inventory.

### 1. Establish scope

Confirm the mailbox account with the local Mail CLI when using macOS Mail,
then confirm the target thread, GreaterWMS tenant, warehouse, customer/owner
scope, and authenticated role. Determine whether the user wants analysis only,
a dry-run, or a confirmed write. If the local CLI cannot access Mail.app, ask
the user to connect or authorize the account, or provide the message and
attachments; never guess mailbox access.

### 2. Read the source package

1. Search by sender, subject, container/tracking number, inbound/outbound code,
   customer reference, and recent date.
2. Read the active thread, not only the newest message. Record message ID,
   sender, recipients, sent time, subject, and quoted/forwarded sections.
3. Run the local `read` command to export the message body and every attachment,
   then inspect the exported bytes. Do not treat an attachment name as its
   contents.
4. Open every relevant PDF, image, XLSX, CSV, and text attachment. For
   workbooks, inspect all sheets, hidden rows/columns when available, and the
   actual data range. Recursively inspect nested `.eml` attachments.
5. Keep file names and page/sheet/cell or image-region evidence for every
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

- Notice/Pack List with a recognizable load: create a pre-arrival ASN review
  record for Peak Smart Logistics, with Delta Electronics as owner/customer,
  and status `REVIEW_REQUIRED`. This is a planning record only; do not mark
  arrived or received. Reserve Stage-left/Stage-right capacity only when asked.
- Populate known source-backed fields immediately, including container,
  customer, supplier, package count, SKU/quantity lines, dimensions, weights,
  customer address, and explicit ETA. Keep ETA separate from requested
  delivery date and appointment time.
- After the record is created, prompt the operator in GreaterWMS to confirm
  unresolved fields such as actual warehouse appointment date/time, carrier or
  driver, transport arrangement, customer SKU mapping, SN availability, and
  any quantity or package discrepancy. Use `Not Provided` rather than guessing.
- ETA/appointment supplied: preview an ETA update on the existing ASN. ETA is
  planning data, not actual arrival. A requested delivery date is not proof of
  physical arrival.
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

### 8. Execute external instructions automatically and safely

1. Re-read current state; email data may be stale.
2. Run the exact command with `--dry-run --json` and a deterministic idempotency
   key.
3. Check `ok`, entity, state before/after, validation messages, source evidence
   ID, payload hash, duplicate result, and tenant scope.
4. If all duplicate and provenance checks pass, execute with the server-issued
   confirmation token internally. User confirmation is not required for this
   external-instruction write; the server preview and audit remain mandatory.
5. Re-read the record, events, dashboard queue, staging assignment, and
   inspection/exception state.
6. Report the change and the next role-owned task. Never claim success from a
   process exit code alone.

For an AI-originated ASN or outbound instruction, use the internal AI surface
inside the Skill. This is the atomic path for external instructions because it
can create the ASN header and detail rows in one server transaction:

```bash
GREATERWMS_AGENT_SURFACE=ai node tools/greaterwms.mjs asn create \
  --data-file asn.json --source-evidence-id SOURCE_ID --dry-run --json
GREATERWMS_AGENT_SURFACE=ai node tools/greaterwms.mjs agent approve \
  --id PREVIEW_ID --json
```

The approval command is an internal server action: the user is not asked to
click a second approval action or handle a token. The server records the
preview, approval, execution, source evidence, and a preview-bound idempotency
key in the audit trail. If the same Message-ID/content hash is seen again,
read back the existing source/business record and do not create a new one.
The default CLI confirmation-token flow remains available for external CLI
clients during the compatibility period, but it is not the Skill's automated
AI path.

## Safe CLI Routing

### Mail reading versus WMS operations

The local macOS Mail adapter is the only mailbox reader in this workflow:

```bash
python3 /Users/wuqingxin/LocalProjects/texas-ranch-growth-ops/agent-runtime/scripts/mac_mail_local_triage.py \
  scan --account admin@vestwoodshft.com --days 1 \
  --json-out /tmp/wms-mail-scan.json
```

`tools/greaterwms.mjs source ...` does not query Mail.app. It accepts the
already-read message and attachment metadata, stores the tenant-scoped source
record, and reports source workflow state. Keep these steps separate:

```text
mac_mail_local_triage.py -> local JSON/evidence extraction ->
tools/greaterwms.mjs source capture -> AI-surface server dry-run -> internal approve -> readback
```

The adapter is read-only and uses the Mail.app account already configured on
this Mac. Set `WMS_MAC_MAIL_CLI` and `WMS_MAIL_ACCOUNT` when running the Skill
on another machine or mailbox.

### Source intake commands

Use these commands for the scheduled source log. They do not modify ASN,
Outbound, Receiving, Putaway, or Inventory records:

```bash
node tools/greaterwms.mjs source sync-start --mailbox-account sales@example.com --json
python3 "$WMS_MAC_MAIL_CLI" scan --account "$WMS_MAIL_ACCOUNT" --days 1 \
  --cursor "$CURSOR_BEFORE" --json-out /tmp/wms-mail-scan.json
node tools/greaterwms.mjs source capture --data-file source-evidence.json --json
node tools/greaterwms.mjs source intake --status REVIEW_REQUIRED --json
node tools/greaterwms.mjs source intake-get --id INTAKE_ID --json
node tools/greaterwms.mjs source intake-update --id INTAKE_ID --data-file intake-update.json --dry-run --json
node tools/greaterwms.mjs source intake-update --id INTAKE_ID --data-file intake-update.json --confirm --json
node tools/greaterwms.mjs source sync-finish --id RUN_ID --data-file sync-result.json --json
```

Use `source sync-state --mailbox-account EMAIL --json` to inspect the durable
cursor or confirm that another run currently holds the mailbox lease. Do not
advance the cursor manually after a failed run.

`source intake-update` changes only the source intake workflow state and is
still operator- and tenant-scoped. External WMS writes continue to use the
source evidence requirement and the Skill-managed automatic CLI write flow
below.

### Automated source-backed intake

Before an AI-originated ASN or outbound write, capture the source metadata and
extracted fields first. The endpoint returns a source evidence ID; bind it to
the server preview and final WMS audit. The user does not need to approve a
second structured action or handle a token. Do not put passwords, bearer
tokens, or confirmation tokens in the evidence payload.

```bash
node tools/greaterwms.mjs source capture --data-file source-evidence.json --json
GREATERWMS_AGENT_SURFACE=ai node tools/greaterwms.mjs asn create \
  --data-file asn.json --source-evidence-id SOURCE_ID --dry-run --json
GREATERWMS_AGENT_SURFACE=ai node tools/greaterwms.mjs agent approve \
  --id PREVIEW_ID --json
```

The Skill itself runs the dry-run, validates the server response, and invokes
the internal structured approval action. The user does not see or copy a
confirmation token. The browser Web flow remains independent and continues to
use its own preview and approval buttons. The default CLI confirmation-token
flow remains available to external CLI clients during the compatibility period.

The write is allowed only when all of these checks pass:

- `source list` finds no existing tenant/mailbox/Message-ID record;
- `source capture` returns a non-duplicate source evidence ID;
- the WMS lookup finds no existing ASN or outbound record for the same
  container/order reference and customer;
- the payload contains the same source evidence ID and content hash used in
  the preview;
- the server preview is bound to the source evidence and records a
  preview-scoped idempotency key;
- the post-write readback confirms the expected record and provenance.

If a retry sees the same idempotency key or an existing matching record, treat
it as an idempotent success after readback. Never generate a new ASN merely
because a previous process timed out. If any duplicate or payload-hash check
is uncertain, stop without writing.

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

Stop or keep the pre-arrival record in `REVIEW_REQUIRED` when the actual Peak
receiving address or Dock #24 is disputed, the customer/owner cannot be
identified, the container/order reference is missing, SKU/quantity mapping is
unsafe, the attachment is unreadable or incomplete, or ETA is absent while
urgency is requested. A Delta Plano customer/final-consignee address alongside
the configured Peak receiving address is expected and is not a hard stop.
Never proceed to arrival, receiving, putaway, inventory change, deletion,
bulk-clean, overwrite, or email sending from this automated external-instruction
path. Those operations require their own current-state workflow and role
authorization. ASN/Outbound writes still require current WMS state, source
evidence, server preview, deterministic idempotency, and post-write
verification.

## Completion Standard

The task is complete only after the source inventory is classified, facts are
tied to evidence, WMS matches and exceptions are explicit, one next action and
responsible role are identified, any external-instruction write has passed a
server dry-run and idempotency check, and the final record has been read back.
After execution, verify WMS state and the dashboard next step.
