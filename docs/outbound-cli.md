# Outbound CLI Workflow

The outbound CLI uses the same governed Agent preview and confirmation flow as
the inbound CLI. It calls GreaterWMS API endpoints and never writes directly to
the database.

## Create the delivery note

Create the pre-order delivery note first. The server generates `dn_code` and
the barcode when they are omitted.

```bash
node tools/greaterwms.mjs outbound create \
  --data '{"customer":"Delta Electronics (USA) Inc.","creater":"warehouse"}' \
  --dry-run --json
```

Review the preview, then repeat with the returned token and a stable key:

```bash
node tools/greaterwms.mjs outbound create \
  --data '{"customer":"Delta Electronics (USA) Inc.","creater":"warehouse"}' \
  --confirm \
  --confirmation-token TOKEN_FROM_PREVIEW \
  --idempotency-key outbound-create-20260814-01 \
  --json
```

## Add SKU quantities

The detail endpoint accepts parallel arrays. A scalar `goods_code` or
`goods_qty`, or arrays with different lengths, is rejected as a client error
before the legacy indexing logic runs.

```json
{
  "dn_code": "DN2026081401",
  "customer": "Delta Electronics (USA) Inc.",
  "goods_code": ["SKU-01", "SKU-02"],
  "goods_qty": [2, 1]
}
```

```bash
node tools/greaterwms.mjs outbound-detail create \
  --data-file outbound-detail.json \
  --dry-run --json
```

## Execute the outbound steps

The server validates the current delivery-note status before every transition:

| Command | Required current status | Result |
| --- | ---: | --- |
| `outbound release` | 1 | Release order |
| `outbound order-release` | 2 | Generate the picking work |
| `outbound pick` | 3 | Mark picking complete |
| `outbound dispatch` | 4 | Dispatch to staging/driver |
| `outbound pod` | 5 | Record proof of delivery and close |
| `outbound cancel-intransit` | 5 | Cancel in transit and release staging |

Example preview:

```bash
node tools/greaterwms.mjs outbound release \
  --id 123 --data '{}' --dry-run --json
```

Each command must be reviewed and then repeated with `--confirm`,
`--confirmation-token`, and `--idempotency-key`. Repeating the same confirmed
request is idempotent; a different payload or status is rejected.

`outbound cancel-intransit` is administrator-only. It clears in-transit
quantities and releases the outbound staging assignment. It does not add stock
back automatically; if the goods physically return, create an
`OUTBOUND_RETURN` receiving record and run QC/Putaway.
