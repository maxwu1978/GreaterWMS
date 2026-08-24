---
name: wms-agv-layout-planner
description: Use when generating or reviewing WMS warehouse drawings, AGV route plans, storage-location layouts, dock/charger/wait station maps, or WCS point-map drafts from a customer warehouse plan.
---

# WMS AGV Layout Planner

Use this skill before generating, revising, exporting, or reviewing warehouse
layout drawings for AGV-ready WMS/WCS work.

## Reference Standard

First read `docs/36-agv-planning-standard.md` when the task involves warehouse
layout, AGV routes, stations, dock doors, chargers, floor-storage zones, rack
storage, or WCS point mapping. For CAD/DXF generation or review, also read
`docs/37-cad-layout-export-standard.md`.

Keep the plan in draft status if field measurements, AGV vehicle profile,
turning radius, aisle widths, docking direction, or safety clearances are not
confirmed.

## Planning Sequence

1. Build the dimension ledger before drawing routes.
   Preserve the original building and storage boundaries. If A/B/C are drawn as
   40 ft + 40 ft + 40 ft, the final allocation must still reconcile to 120 ft
   unless the operator explicitly changes that boundary.
2. Classify every area before creating locations:
   storage, rack, floor-storage, AGV corridor, connector lane, lower return
   lane, dock door, wait point, charger, maintenance point, safety/no-go zone.
3. Generate storage slots from real cargo footprint plus clearance.
   Record zone width/depth, slot width/depth/height, rows, columns, slot count,
   occupied footprint, residual clear bands, and cargo dimensions.
4. Draw AGV routes after storage boundaries are fixed.
   Route centerlines must stay outside `floor_storage` zones unless an approved
   internal aisle is split out as a separate non-storage zone.
5. Add drawing labels only after geometry is settled.
   Aisle widths, storage dimensions, slot dimensions, route arrows, station
   roles, and dimension split notes must be visible without overlapping busy
   slots or route centerlines.

## Area Rules

- Storage zones create WMS locations.
- AGV corridors, connector lanes, lower return lanes, wait points, chargers,
  maintenance points, and dock doors do not create storage locations.
- Dock doors are unload/ship interfaces, not inventory locations.
- If a corridor consumes space previously counted as storage, split that area
  into a non-storage AGV zone and reduce storage width/depth, area, slot count,
  and capacity notes.
- If a clear lane is outside the original storage boundary, model it as an
  external AGV lane and do not subtract it from storage capacity.
- Do not keep GMA-sized WMS slots when customer cargo exceeds GMA. Use the
  cargo footprint and operational clearance instead.

## AGV Driving Rules

Use these driving rules as hard planning guardrails. If vendor requirements are
stricter, vendor requirements override these baselines.

- Prefer a controlled one-way loop. Avoid head-to-head travel, dead ends, sharp
  turns, and unnecessary crossings.
- Keep route centerlines outside storage slots. If AGV travel must pass through
  a storage boundary, split that path into a separate non-storage corridor and
  update storage capacity.
- Main aisles should be straight and wide where possible; branch aisles should
  be controlled pickup/dropoff access, not uncontrolled bidirectional traffic.
- Use wait/avoidance points before narrow lanes, blind corners, dock corridors,
  pedestrian crossings, and other conflict areas.
- Add slow or sensing zones at dock approaches, intersections, pedestrian
  crossings, and blind corners.
- Chargers and maintenance points must sit at route ends, corners, or side
  spurs so they do not block the main aisle.
- AGV should dock square/perpendicular to pickup and dropoff faces whenever
  possible. Record station center point and docking direction.
- Baseline SLAM AGV turning radius is at least 800 mm unless the vendor
  requires more.
- Preserve baseline clearances: AGV to wall/column at least 150 mm; AGV to
  rack/equipment at least 200 mm; floor-storage to wall/column at least 100 mm;
  fork tip to pallet recognition/alignment feature at least 500 mm unless
  vendor data overrides.
- Record aisle width and lane policy. Typical minimums from the AGV standard:
  underride one-way 1200 mm, underride two-way 1600 mm, forklift AGV aisle
  2200 mm, rack main aisle preferred one-way 2800 mm, two-way rack main aisle
  3200-3500 mm, pallet-jack/forklift main aisle one-way 2800 mm, two-way
  passing 3600 mm.

## Drawing Contract

Every generated drawing should answer:

- What original dimensions were preserved?
- Which areas are storage and which are travel/interface areas?
- How many WMS storage locations are generated per zone?
- What are the storage slot dimensions and cargo dimensions?
- Where does the AGV travel, in which direction, and at what lane width?
- Which route or connector changed usable storage capacity?

## Validation

Before handoff or export:

- route centerlines do not cross `floor_storage`;
- WMS storage point count equals generated storage/rack locations only;
- WCS draft count separates storage, dock, wait, charger, and station points;
- map labels do not obscure critical slots, lane widths, or route arrows;
- CAD exports follow `docs/37-cad-layout-export-standard.md`: required layers,
  millimeter units, a readable main plan, a separate dimension ledger/notes
  panel, and no main-plan label overlap;
- simulator fixture, backend tests, local-agent prompts, and docs use the same
  dimensions and counts.
