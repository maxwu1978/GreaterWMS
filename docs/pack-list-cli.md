# Pack List CLI

The CLI uses the same GreaterWMS Pack List endpoints as the web page. It does
not write to the database directly. Each ASN has one current Pack List; an
import never creates a second current Pack List record.

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
same ASN/SKU/quantity/SN rules as the Pack List page, without saving a record.

```bash
node tools/greaterwms.mjs packlist import \
  --asn-code IB260807-11 \
  --file ./pack-list.xlsx \
  --dry-run \
  --json
```

After reviewing the preview, import it as `PENDING`:

```bash
node tools/greaterwms.mjs packlist import \
  --asn-code IB260807-11 \
  --file ./pack-list.xlsx \
  --confirm \
  --json
```

List documents or confirm a pending document through the same API used by the
web page:

```bash
node tools/greaterwms.mjs packlist list --asn-code IB260807-11 --json
node tools/greaterwms.mjs packlist confirm --id 123 --confirm --json
```

Importing the same content again for the same ASN is idempotent. A different
file must be previewed and explicitly replaced:

```bash
node tools/greaterwms.mjs packlist import \
  --asn-code ASN202608123 \
  --file ./replacement-pack-list.xlsx \
  --replace \
  --confirm \
  --json
```

Replacement is blocked after physical receiving scans have started. The
uploaded workbook is parsed and discarded; only normalized Pack List rows and
serial records are stored. Confirmation remains a separate step because a
confirmed Pack List becomes the receiving verification baseline; it does not
mean that the goods have arrived.

## Receiving acceptance scan

Customer acceptance workbooks can use the operational headers `PART NUMBER`,
`SERIAL NUMBER`, and `DATE`. The receiving importer records physical scans and
does not create a Pack List document. Use `receive` mode for an acceptance
file. If the workbook is tied to an ASN but has no inbound PO or shipout
reference, `--allow-all` records that explicit scope choice.

Preview the write plan locally:

```bash
node tools/greaterwms.mjs serial import \
  --asn-code ASN202608123 \
  --file ./acceptance-scan.xlsx \
  --mode receive \
  --allow-all \
  --dry-run \
  --json
```

After review, submit the scan rows:

```bash
node tools/greaterwms.mjs serial import \
  --asn-code ASN202608123 \
  --file ./acceptance-scan.xlsx \
  --mode receive \
  --allow-all \
  --confirm \
  --json
```

The result reports matched, created, updated, skipped, and exception rows.
This import records receipt; it does not confirm a pending customer Pack
List. The system stores import batch metadata, not the uploaded workbook name
or file contents. In `receive` mode, standard damage/QC result columns are
converted to a `DAMAGED` exception and the row note is retained for QC review.

### Exception review and putaway

List open serial and quantity exceptions before putaway:

\`\`\`bash
node tools/greaterwms.mjs serial exceptions \
  --asn-code ASN202608123 \
  --json
\`\`\`

If the scan shows a wrong SKU, duplicate SN, damage, unexpected SN, or missing
SN, the record is an open exception. QC must record a resolution action and
note before putaway. A note is required for an approval:

\`\`\`bash
node tools/greaterwms.mjs serial resolve \
  --id 456 \
  --data '{"action":"ACCEPT_EXCEPTION","note":"QC approved after photo review"}' \
  --dry-run \
  --json
node tools/greaterwms.mjs serial resolve \
  --id 456 \
  --data '{"action":"ACCEPT_EXCEPTION","note":"QC approved after photo review"}' \
  --confirm \
  --json
\`\`\`

Use WAIVE_MISSING only when an expected SN was not received but the
quantity variance has been approved. Quantity shortage, overage, and damage
exceptions use the same explicit approval flow:

\`\`\`bash
node tools/greaterwms.mjs serial resolve-quantity \
  --data '{"asn_code":"ASN202608123","goods_code":"702-S","action":"ACCEPT_EXCEPTION","note":"Customer approved shortage"}' \
  --confirm \
  --json
\`\`\`

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
