# GreaterWMS Master-Data Fields

Use this reference when building the confirmation preview or validating a
write. The CLI/session supplies the tenant context; do not ask the user for or
write `openid` manually.

## Warehouse

Required fields:

- `warehouse_name`
- `warehouse_city`
- `warehouse_address`
- `warehouse_contact`
- `warehouse_manager`
- `creater`

Peak receiving context currently used by the business:

- Name: `Peak Smart Logistics`
- Address: `1991 Lakepointe Dr, Dock #24, Lewisville, TX`

Treat the customer/final-consignee address, such as Delta's Plano address, as
customer data, not as a second warehouse.

## Customer

Required fields:

- `customer_name`
- `customer_city`
- `customer_address`
- `customer_contact`
- `customer_manager`
- `customer_level`
- `creater`

The business owner/customer currently referenced in source documents is Delta
Electronics (USA) Inc. Do not create a second customer for a legal-name
variant without showing the existing match and receiving confirmation.

## Supplier

Required fields:

- `supplier_name`
- `supplier_city`
- `supplier_address`
- `supplier_contact`
- `supplier_manager`
- `supplier_level`
- `creater`

Optional field:

- `supplier_short_name`

The shipper on an arrival notice is a supplier candidate, not automatically the
customer or owner.

## SKU / Goods

Required fields for a normal web create:

- `goods_code`
- `goods_desc`
- `goods_supplier`
- `goods_weight`
- `goods_w`, `goods_d`, `goods_h`
- `unit_volume`
- `goods_unit`
- `goods_class`, `goods_brand`, `goods_color`, `goods_shape`
- `goods_specs`, `goods_origin`
- `goods_cost`, `goods_price`
- `creater`
- `bar_code`

The source may not provide all of these fields. The Skill must list the missing
fields and ask the user instead of using zero, `N/A`, or a guessed value.

For an explicitly approved source-traced SKU import, the minimum fields are
`goods_code`, the approved raw supplier name, `source_evidence_id`, and the
source-derived physical measurements. Optional description, class, brand,
color, shape, specification, origin, cost, price, and barcode fields may stay
blank. The import stores normalized US customary dimensions/weight and keeps
the original metric values and units in `source_note`.

Use net weight as the product-weight candidate and retain gross weight as
shipment/packaging evidence unless the user directs otherwise. Preserve source
units and show conversions separately:

- `1 in = 2.54 cm`
- `1 in = 25.4 mm`
- `1 kg = 2.20462262185 lb`
- `1 m³ = 35.3146667 ft³`

If the source contains customer SKU, supplier SKU, S-SKU, and barcode values,
show each identifier separately. Only one may become `goods_code` unless the
current WMS model has an alias field; never silently collapse them.
