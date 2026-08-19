# Warehouse Email Document Mapping

Use this reference when an email has several attachments or filenames are not
reliable. Keep the original value and evidence pointer for every row.

## Evidence Pointers

- `email:<message-id>/body`
- `email:<message-id>/subject`
- `attachment:<file>/page-1/region-top`
- `attachment:<file>/sheet:<sheet>/cell:<cell>`

For a workbook, record sheet name, header row, data range, and hidden or
formula-derived values that affect the result.

## Inbound

### Inbound Notice / Inbound List

Extract inbound/ASN reference, client/owner, container/tracking number, package
count, listed SKU/quantity rows, and ETA only when explicitly stated. Do not
infer ETA from sent date, requested delivery date, or file creation time.

### Pack List

Look for `Pack List`, `Package Type`, `SKU`, `Item Qty`, `Total`, `S-SKU`, and
`Item Name`. Extract every package row: package ID/type, customer SKU, internal
SKU candidate, quantity, S-SKU/customer reference, item name, SN/lot,
dimensions, weight, and unit when present.

Keep package count, expected quantity, and later scanned quantity separate. If
there are eight package rows, do not report nine received items because a header
total, barcode, or QR code is also visible.

For a late/replacement Pack List, match ASN/container, customer, SKU set, and
package IDs. If it is the same load, use the late-Pack-List path and preserve
prior history. If it differs, stop and show both versions.

## Outbound

### Pick Ticket / Delivery Request

Look for `Pick Ticket`, `Outbound No.`, `Order No.`, `Ship To`, `Client ID`, and
`Items to pick`. Extract outbound/DN and customer order references, customer,
ship-to, requested date, transport information, item name, SKU, quantity,
location, lot, and SN requirement. SN rows require exact SN picking; SKU/qty
rows use quantity picking without inventing SNs.

A PO inside a Pick Ticket is supporting reference data. It does not create an
inbound record.

## QC / Inspection

### Scan Sheet / QC Workbook

The first sheet commonly contains scanned SNs or physical count results; later
dated sheets may contain customer validation. Extract scanned, duplicate, and
missing SNs; actual SKU/quantity; accepted/rejected/repair/damage/shortage/
overage; inspector/date/notes; evidence URLs; and explicitly linked ASN/DN
references.

Do not import this workbook as an inbound order. Use the receiving/QC import
path and keep warehouse scan rows separate from customer validation rows.

## Logistics

Extract requested date, ETA, actual arrival, carrier, truck, driver, appointment,
dock, transport requirement, ship-to address, and warehouse delivery address.
If two addresses or docks appear, show the conflict and stop; never choose a
default based on the last line or a familiar customer.

## Reconciliation Table

Before a CLI write, produce one row per fact:

| Fact | Source | Normalized | WMS match | Evidence | Confidence | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| ETA | Not stated | Not Provided | ASN ETA empty | email/body | high | do not infer |
| Customer SKU | source code | same | exact/near/unresolved | sheet/row | medium | ask if not exact |
| Package count | 8 | 8 packages | ASN package count | header/rows | high | compare scan count |

Keep `Not Provided` distinct from `Unknown`: the former means the source did
not supply the fact; the latter means extraction failed or the source is
ambiguous.

