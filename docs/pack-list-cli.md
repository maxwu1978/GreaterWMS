# Pack List CLI / AI Agent Ingestion

The Pack List page is read-only. Pack List and QC results are written through
the governed CLI/AI Agent ingestion path, which uses GreaterWMS APIs and does
not write to the database directly. Each ASN has one current customer Pack
List; older revisions remain as history. A Pack List received after physical
receiving must be imported as a late reference and never overwrites the prior
receiving or QC history.

The CLI is the current execution adapter for the AI Agent. The Agent is
responsible for reading the customer email or workbook, mapping customer SKUs
to internal SKUs, and passing the normalized result to this CLI/API flow. The
web page only displays the saved Pack List, reconciliation, and QC results.

## Authentication

Use the CLI login flow to obtain the same `openid` token used by the web client.
The password is prompted without echo and is never saved. The local session file
contains only the token, operator id, login name, and selected URL.

```bash
node tools/greaterwms.mjs login --env production --name ADMIN
node tools/greaterwms.mjs auth status --json
```

Use `--env test` for the Render test service. The session is stored at
`~/.config/greaterwms/session.json` with local-only permissions. For automation,
`GREATERWMS_TOKEN` and `GREATERWMS_OPERATOR` can still override the local
session without writing credentials to disk.

## Workflow

Preview the Excel file first. This reads the same headers and validates the
same ASN/SKU/quantity/SN rules as the ingestion API, without saving a record.

```bash
node tools/greaterwms.mjs packlist import \
  --asn-code IB260807-11 \
  --file ./pack-list.xlsx \
  --dry-run \
  --json
```

After reviewing the preview, reuse its short-lived `confirmation_token` and
provide a stable idempotency key to import it as `PENDING`:

```bash
node tools/greaterwms.mjs packlist import \
  --asn-code IB260807-11 \
  --file ./pack-list.xlsx \
  --confirm \
  --confirmation-token TOKEN_FROM_PREVIEW \
  --idempotency-key inbound-IB260807-11-packlist-1 \
  --json
```

List documents or confirm a pending document through the CLI/Agent path:

```bash
node tools/greaterwms.mjs packlist list --asn-code IB260807-11 --json
node tools/greaterwms.mjs packlist confirm --id 123 --dry-run --json
node tools/greaterwms.mjs packlist confirm --id 123 --confirm \
  --confirmation-token TOKEN_FROM_PREVIEW \
  --idempotency-key packlist-confirm-123-1 --json
```

Importing the same content again for the same ASN is idempotent. A different
file must be previewed and explicitly replaced:

```bash
node tools/greaterwms.mjs packlist import \
  --asn-code ASN202608123 \
  --file ./replacement-pack-list.xlsx \
  --replace \
  --confirm \
  --confirmation-token TOKEN_FROM_PREVIEW \
  --idempotency-key replacement-packlist-1 \
  --json
```

After physical receiving starts, a different file must use the late-reference
flow. The uploaded workbook is parsed and discarded; only normalized Pack List
rows and serial records are stored. Confirmation remains a separate step because
a confirmed Pack List becomes the receiving verification baseline; it does not
mean that the goods have arrived.

```bash
node tools/greaterwms.mjs packlist import \
  --asn-code ASN202608123 --file ./late-pack-list.xlsx \
  --replace --late-reference --dry-run
node tools/greaterwms.mjs packlist import \
  --asn-code ASN202608123 --file ./late-pack-list.xlsx \
  --replace --late-reference --confirm \
  --confirmation-token TOKEN_FROM_PREVIEW \
  --idempotency-key late-packlist-1
```

## Receiving acceptance scan

Customer acceptance workbooks can use the operational headers `PART NUMBER`,
`SERIAL NUMBER`, and `DATE`. The receiving importer records physical scans and
does not create a Pack List document. Use `inspection import` for a QC result
file. Each import is a separate QC round; re-importing a later round does not
count the same SN as a duplicate physical scan. If the workbook is tied to an
ASN but has no inbound PO or shipout reference, `--allow-all` records that
explicit scope choice.

Preview the workbook through the GreaterWMS API. The server reads the file,
checks the ASN scope, and returns a confirmation token; no scan or QC record is
written:

```bash
node tools/greaterwms.mjs inspection import \
  --asn-code ASN202608123 \
  --file ./acceptance-scan.xlsx \
  --mode receive \
  --allow-all \
  --dry-run \
  --json
```

After review, submit the scan rows:

```bash
node tools/greaterwms.mjs inspection import \
  --asn-code ASN202608123 \
  --file ./acceptance-scan.xlsx \
  --mode receive \
  --allow-all \
  --confirm \
  --confirmation-token TOKEN_FROM_PREVIEW \
  --idempotency-key qc-acceptance-1 \
  --json
```

The result reports matched, created, updated, skipped, and exception rows.
This import records QC/serial evidence only. It does not replace the separate
ASN receiving quantity confirmation and does not confirm a pending customer
Pack List. The system stores import batch metadata, not the uploaded workbook name
or file contents. In `receive` mode, standard damage/QC result columns are
converted to a `DAMAGED` exception and the row note is retained for QC review.
The Pack List page displays each QC round but does not provide an import
control.

### Exception review and putaway

List open serial and quantity exceptions before putaway:

\`\`\`bash
node tools/greaterwms.mjs serial exceptions \
  --asn-code ASN202608123 \
  --json
\`\`\`

If the scan shows a wrong SKU, duplicate SN, damage, unexpected SN, or missing
SN, the record is an open exception. QC must record a resolution action and
note before putaway. A note is required for an approval. A damaged unit that
needs repair must be moved to a repair or quarantine location and kept out of
putaway until reinspection:

\`\`\`bash
node tools/greaterwms.mjs serial resolve \
  --id 456 \
  --data '{"action":"REPAIR_REWORK","note":"Needs repair and reinspection","resolution_location":"REPAIR-01"}' \
  --dry-run \
  --json
node tools/greaterwms.mjs serial resolve \
  --id 456 \
  --data '{"action":"REPAIR_REWORK","note":"Needs repair and reinspection","resolution_location":"REPAIR-01"}' \
  --confirm \
  --confirmation-token TOKEN_FROM_PREVIEW \
  --idempotency-key serial-resolve-456-1 \
  --json
\`\`\`

After repair, reopen the same SN for reinspection, then accept it only if QC
passes:

\`\`\`bash
node tools/greaterwms.mjs serial resolve \
  --id 456 \
  --data '{"action":"REOPEN","note":"Ready for reinspection"}' \
  --confirm \
  --confirmation-token TOKEN_FROM_PREVIEW \
  --idempotency-key serial-reopen-456-1 \
  --json
node tools/greaterwms.mjs serial resolve \
  --id 456 \
  --data '{"action":"ACCEPT_FOR_PUTAWAY","note":"Passed reinspection"}' \
  --confirm \
  --confirmation-token TOKEN_FROM_PREVIEW \
  --idempotency-key serial-accept-456-1 \
  --json
\`\`\`

Use WAIVE_MISSING only when an expected SN was not received but the
quantity variance has been approved. Quantity shortage, overage, and damage
exceptions use the same explicit approval flow:

\`\`\`bash
node tools/greaterwms.mjs serial resolve-quantity \
  --data '{"asn_code":"ASN202608123","goods_code":"702-S","action":"ACCEPT_EXCEPTION","note":"Customer approved shortage"}' \
  --confirm \
  --confirmation-token TOKEN_FROM_PREVIEW \
  --idempotency-key quantity-resolve-1 \
  --json
\`\`\`

Resolving an exception records the QC decision; it does not move physical
inventory. For a received unit marked hold, repair, or reject, execute the
second physical movement after choosing a valid non-staging exception bin:

```bash
node tools/greaterwms.mjs serial exception-move \
  --id 456 --asn-code ASN202608123 \
  --data '{"bin_name":"QC-HOLD-01"}' --dry-run --json
node tools/greaterwms.mjs serial exception-move \
  --id 456 --asn-code ASN202608123 \
  --data '{"bin_name":"QC-HOLD-01"}' --confirm \
  --confirmation-token TOKEN_FROM_PREVIEW \
  --idempotency-key exception-move-456-1 --json
```

For a physical quantity exception, use `serial exception-move-quantity` with
`asn_code`, `goods_code`, `action`, `qty`, and `bin_name`. A shortage with no
physical units cannot be moved; it can only be approved or reopened.

Putaway requires a valid Driver master-data record. The first successful
putaway assigns the driver to the ASN; later putaway moves for the same ASN
must use the same driver:

\`\`\`bash
node tools/greaterwms.mjs asn putaway \
  --id 789 \
  --data '{"asn_code":"ASN202608123","goods_code":"702-S","qty":1,"bin_name":"A1-01","putaway_driver":"Tom"}' \
  --dry-run \
  --json
\`\`\`

## Physical inbound commands

ETA, arrival, staging reservation, unloading, receiving, and putaway use the
same server preview/confirmation boundary:

```bash
node tools/greaterwms.mjs asn arrival --id 123 --data '{}' --dry-run --json
node tools/greaterwms.mjs asn arrival --id 123 --data '{}' --confirm \
  --confirmation-token TOKEN_FROM_PREVIEW \
  --idempotency-key arrival-123-1 --json
node tools/greaterwms.mjs asn unload-start --id 123 --asn-code ASN202608123 \
  --data '{"unload_driver":"Tom","staging_bins":["STAGE-LEFT-01"]}' --dry-run --json
node tools/greaterwms.mjs asn receive --id 123 --asn-code ASN202608123 \
  --data '{"supplier":"Delta Electronics","asn_code":"ASN202608123","goodsData":[{"goods_code":"702-S","goods_actual_qty":8}]}' \
  --dry-run --json
node tools/greaterwms.mjs asn putaway-bulk --asn-code ASN202608123 \
  --data '{"asn_code":"ASN202608123","bin_name":"A1-01","putaway_driver":"Tom","res_data":[{"goods_code":"702-S","qty":8}]}' \
  --dry-run --json
```
