# Source Intake Automation

## Scope

The mailbox schedule belongs to the Codex client. GreaterWMS does not poll a
mailbox or run a background scheduler. A scheduled Skill invocation uses the
local mailbox adapter to read only new messages, uses the GreaterWMS CLI to
create a `MailboxSyncRun` and capture source metadata, classifies each
message, and closes the run with counters and a cursor.

For the current macOS setup, the mailbox reader is:

```shell
export WMS_MAC_MAIL_CLI="${WMS_MAC_MAIL_CLI:-/Users/wuqingxin/LocalProjects/texas-ranch-growth-ops/agent-runtime/scripts/mac_mail_local_triage.py}"
export WMS_MAIL_ACCOUNT="${WMS_MAIL_ACCOUNT:-admin@vestwoodshft.com}"

python3 "$WMS_MAC_MAIL_CLI" accounts
python3 "$WMS_MAC_MAIL_CLI" scan \
  --account "$WMS_MAIL_ACCOUNT" \
  --days 1 \
  --cursor "${CURSOR_BEFORE:-}" \
  --json-out /tmp/wms-mail-scan.json
```

`CURSOR_BEFORE` is returned by `source sync-start`; it is empty on the first
run. The local adapter scans a five-minute overlap by default and returns
`cursor_after`. The overlap catches boundary-delayed messages, while the WMS
Message-ID/content-hash constraint prevents duplicate source records.

The local adapter reads Mail.app through macOS automation and is read-only.
It must confirm the configured account before scanning. Mailbox passwords are
never sent to GreaterWMS. On another Mac, set `WMS_MAC_MAIL_CLI` and
`WMS_MAIL_ACCOUNT` to the local adapter and account used there.

After the Message-ID duplicate preflight, the Skill reads the complete message
and exports its actual attachments with the local adapter:

```shell
python3 "$WMS_MAC_MAIL_CLI" read \
  --account "$WMS_MAIL_ACCOUNT" \
  --message-id MESSAGE_ID \
  --output-dir "/tmp/wms-mail-read-MESSAGE_ID" \
  --json-out "/tmp/wms-mail-read-MESSAGE_ID.json"
```

The result contains `message-body.txt` and numbered attachment files. Each
attachment includes its original name, detected content type, byte size, and
SHA-256. The Skill must parse the exported bytes: nested `.eml` recursively,
all PDF pages, all visible and hidden workbook sheets/ranges, complete CSV/TXT
rows, and image contents with visual inspection/OCR where necessary. Every
field is recorded with source file and page/sheet/cell/row/image region. An
unreadable or partially parsed relevant attachment blocks WMS production
writes. The detailed parsing rules are in the Skill reference
`tools/skills/wms-scheduled-email-intake/references/attachment-processing.md`.

The source board is separate from the operations dashboard. It answers:

- Which mailbox message or attachment was received?
- What document type and business operation were detected?
- Which fields were extracted and where did they come from?
- Is a human review or customer clarification required?
- Is the item ready for a preview, awaiting approval, completed, or blocked?

For the current tenant, use this fixed operational mapping when interpreting
email addresses:

```text
Warehouse: Peak Smart Logistics
Receiving address: 1991 Lakepointe Dr, Dock #24, Lewisville, TX
Customer/owner: Delta Electronics (USA) Inc.
Customer/final-consignee address: 601 Data Dr, Plano, TX
```

The Plano address in a customer document is not a warehouse-address conflict.
It is stored as the owner or final-consignee address while Peak remains the
receiving location in GreaterWMS.

## Two Entry Surfaces

### AI conversation

The Skill captures the email and attachment evidence, runs the server-side
preview, checks duplicates and provenance, and executes the external ASN or
Outbound write through the internal AI surface. The server-side structured
approval is invoked by the Skill; the confirmation token is not exposed. The
user does not need to click a second approval action or switch to the WMS
website. ASN header and detail creation is atomic on this path.
Physical arrival, receiving, QC, putaway, and inventory changes remain separate
role-owned workflows.

### WMS web page

The web workflow creates a `WEB_FORM` source record automatically when the
operator opens a preview. The page approves the same server-side workflow.
The operator does not create a second evidence record or switch to AI.

The server stores `execution_surface` on the preview and rejects approval from
the other surface.

## Source States

`CAPTURED -> ANALYZING -> REVIEW_REQUIRED -> READY_FOR_PREVIEW ->
APPROVAL_REQUIRED -> EXECUTING -> COMPLETED`

`BLOCKED`, `FAILED`, and `DUPLICATE` are explicit outcomes. A duplicate email
is deduplicated by tenant, mailbox account, Message-ID, and content hash. The
canonical source remains usable; the API source-capture view records a repeat
read as `DUPLICATE` and appends an event.

## CLI scan sequence

```shell
node tools/greaterwms.mjs source sync-start \
  --mailbox-account "$WMS_MAIL_ACCOUNT" --json

python3 "$WMS_MAC_MAIL_CLI" triage \
  --account "$WMS_MAIL_ACCOUNT" \
  --days 1 \
  --cursor "${CURSOR_BEFORE:-}" \
  --no-model \
  --json-out /tmp/wms-mail-triage.json

node tools/greaterwms.mjs source capture \
  --data-file source-evidence.json --json

node tools/greaterwms.mjs source intake --status REVIEW_REQUIRED --json
node tools/greaterwms.mjs source intake-get --id INTAKE_ID --json

node tools/greaterwms.mjs source intake-update \
  --id INTAKE_ID --data-file intake-update.json --dry-run --json
node tools/greaterwms.mjs source intake-update \
  --id INTAKE_ID --data-file intake-update.json --confirm --json

node tools/greaterwms.mjs source sync-finish \
  --id RUN_ID --data-file sync-result.json --json
```

The `sync-result.json` file must contain the local scan's `cursor_after`.
Only `SUCCEEDED` advances the durable cursor. A `PARTIAL` or `FAILED` run
releases the lease but keeps the previous cursor so the next scheduled run
retries the affected window. Check the state with:

```shell
node tools/greaterwms.mjs source sync-state \
  --mailbox-account "$WMS_MAIL_ACCOUNT" --json
```

Source intake commands only change evidence processing state. They do not
create ASN, Outbound, Receiving, Putaway, or Inventory records.

When an external notice or Pack List contains enough identity to recognize the
load, the AI workflow may create a source-backed pre-arrival ASN review record
for the configured Peak warehouse, with Delta as owner/customer and
`REVIEW_REQUIRED` status. The Skill performs the server dry-run and invokes the
internal AI approval action; the user does not provide a second approval. ASN
header and detail rows are created atomically. It must not mark arrival,
receiving, putaway, or inventory.
Before execution it must verify the Message-ID/content-hash source duplicate,
the existing ASN/Outbound business-key duplicate, a deterministic idempotency
key, and the source evidence ID. After creation, the operator is prompted in
GreaterWMS to confirm unresolved ETA/appointment, carrier/driver, SKU mapping,
SN availability, and quantity or package issues. Missing values remain `Not
Provided` rather than being inferred.

The scheduled runner should first use the scanned Message-ID as a lightweight
preflight before opening the full thread:

```shell
node tools/greaterwms.mjs source list \
  --mailbox-account "$WMS_MAIL_ACCOUNT" \
  --message-id MESSAGE_ID --json
```

If a source already exists, count it as duplicate and skip attachment
download, AI classification, preview, and business write. For a new message,
capture the complete source package; the `duplicate: true` response from
`source capture` remains the final race-safe duplicate gate.

`tools/greaterwms.mjs` does not read Mail.app. The intended handoff is:

```text
mac_mail_local_triage.py -> local JSON/evidence extraction ->
GreaterWMS source capture -> AI-surface server dry-run -> internal approve -> readback
```

## Evidence and audit

The database stores tenant-scoped source metadata, extracted fields,
attachments metadata, field provenance, operation audits, and append-only
source intake events. Sensitive values such as passwords, tokens, bearer
headers, and raw email bodies are scrubbed from metadata responses and audit
payloads.

`storage_uri` and `content_hash` identify the original email or attachment.
The current phase does not upload file bytes or provide durable object storage.
Before production mailbox use, configure encrypted object storage and a
backup/retention policy; otherwise the board is an evidence index, not a
long-term archive.

## Production guardrails

- The scheduled Skill must finish a sync run as `PARTIAL` when any message is
  skipped or fails.
- No ASN or Outbound external instruction may be written from AI without a
  tenant-scoped source evidence ID, server dry-run, deterministic idempotency
  key, duplicate checks, and post-write readback.
- The Skill consumes the compatibility confirmation token internally; the
  token is never shown to the user or written to audit evidence.
- CLI token approval remains available during the compatibility period.
- The website Source Intake page is read-only in this phase; business writes
  remain in the existing inbound/outbound workflows.
