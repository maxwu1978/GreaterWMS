# Pack List CLI

The CLI uses the same GreaterWMS Pack List endpoints as the web page. It does
not write to the database directly and it does not create a second Pack List
recording model.

## Authentication

Use the authenticated `openid` token from the current GreaterWMS session. Do
not commit the token or place it in a script file.

```bash
export GREATERWMS_URL=https://greaterwms-v2-test3-sn.onrender.com
export GREATERWMS_TOKEN='session-openid-token'
export GREATERWMS_OPERATOR='staff-id'
```

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

Importing the same file again for the same ASN is idempotent. The existing
document is returned instead of creating another version. Confirmation remains
a separate step because a confirmed Pack List becomes the receiving
verification baseline; it does not mean that the goods have arrived.
