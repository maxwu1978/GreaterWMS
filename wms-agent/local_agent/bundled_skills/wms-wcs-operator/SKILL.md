---
name: wms-wcs-operator
description: Use when an agent needs WCS/AGV warehouse layout planning, WCS dispatch dry-run, dispatch gate checks, callback replay, or redacted WCS config/binding reads.
---

# WMS WCS Operator

Use this skill for WCS/AGV integration work that must stay in preview or
diagnostic mode. Do not call live WCS dispatch or live callback endpoints unless
a human operator explicitly asks for the production action outside this skill.

## Discovery

```bash
node tools/wms.mjs capabilities --json
```

Confirm that `wcs config`, `wcs bindings`, `wcs point-mappings list`,
`wcs point-mappings validate`, `wcs gate-check`, `wcs dispatch`, and
`wcs callback replay`, `wcs ready-config`, `wcs quality-complete`, and
`wcs certification task` are present before planning WCS actions.

## AGV Planning Standard

For warehouse layout, route, station, or WCS point-mapping work, first reference
`docs/36-agv-planning-standard.md`. Keep any generated layout in draft status
when field measurements, AGV vehicle profile, aisle widths, safety clearances,
station center points, or one-way/two-way route directions are missing.
For CAD/DXF generation or review, also reference
`docs/37-cad-layout-export-standard.md`.

Agents must preserve physical metadata when asking the platform to generate or
save layouts: dimensions, drawing coordinates, aisle widths, docking direction,
route role, safety assumptions, AGV accessibility, and source drawing status.
Dock doors are external transport interfaces unless the operator explicitly
creates WMS location records for them; do not model dock doors as storage
locations.
If a customer drawing shows clear space below A/B/C floor-storage areas, model
that space as a non-storage AGV lane when it has confirmed width, direction,
clearance, and safety separation.
For the default A/B/C floor-storage pattern, keep AGV route centerlines outside
the storage blocks and use external edge handoff points unless the operator
explicitly approves internal AGV aisles and the resulting capacity change.

## Warehouse Layout Drawing Rules

Before generating or revising a warehouse drawing, make a dimension ledger
first. Preserve the original drawing boundaries and show how each segment is
allocated. Example: if A/B/C are originally 40 ft + 40 ft + 40 ft, the final
layout must still reconcile to 120 ft unless the operator explicitly changes
the building or storage boundary.

Separate area types before drawing routes:

- storage zones create WMS locations;
- AGV corridors, connector lanes, lower return lanes, wait points, chargers,
  and dock doors do not create storage locations;
- dock doors are unload/ship interfaces, not inventory locations;
- if a corridor consumes space previously counted as storage, split it into a
  non-storage zone and reduce the affected storage width/depth, area, slot
  count, and capacity notes;
- if a clear lane is outside the original storage boundary, record it as an
  external AGV lane and do not subtract it from storage capacity.

Size locations from the cargo footprint plus operational clearance. Record
zone width/depth, slot width/depth/height, slot rows/columns, slot count,
occupied footprint, residual clear bands, and cargo dimensions. Do not keep
GMA-sized slots when the customer cargo is larger than GMA.

Drawing output must support field review:

- show aisle widths, storage dimensions, slot dimensions, route direction
  arrows, and station roles;
- keep labels and callouts outside busy route/slot areas where possible;
- show WCS/AGV route centerlines outside storage blocks unless an approved
  internal aisle is modeled as a separate non-storage zone;
- explain the dimension split directly on the drawing when a route or connector
  changes the usable storage area.

Validation before handoff:

- route centerlines must not cross `floor_storage` zones;
- WMS storage point count must equal generated storage/rack locations only;
- WCS draft count must separately account for storage, dock, and station
  points;
- CAD exports must use millimeter units, required layers, a readable main plan,
  a separate dimension ledger/notes panel, and no main-plan label overlap;
- simulator fixture, backend tests, local-agent prompts, and project docs must
  use the same dimensions and counts.

## AGV Driving Guardrails

When planning AGV travel, keep this concise field-standard summary in context:

- prefer controlled one-way loops; avoid head-to-head travel, dead ends, sharp
  turns, and unnecessary crossings;
- keep main aisles straight/wide and branch aisles controlled;
- place wait/avoidance points before narrow lanes, blind corners, dock
  corridors, pedestrian crossings, and other conflict areas;
- add slow/sensing zones at dock approaches, intersections, pedestrian
  crossings, and blind corners;
- place chargers and maintenance points at route ends, corners, or side spurs
  so they do not block the main aisle;
- AGV should dock square/perpendicular to pickup/dropoff faces; record station
  center point and docking direction;
- baseline SLAM turning radius is at least 800 mm unless the vendor requires
  more;
- preserve baseline clearances: AGV to wall/column 150 mm, AGV to
  rack/equipment 200 mm, floor-storage to wall/column 100 mm, fork tip to
  pallet recognition/alignment feature 500 mm unless vendor data overrides;
- record aisle width and lane policy. Typical minimums: underride one-way
  1200 mm, underride two-way 1600 mm, forklift AGV aisle 2200 mm, rack main
  aisle preferred one-way 2800 mm, two-way rack main aisle 3200-3500 mm,
  pallet-jack/forklift main aisle one-way 2800 mm, two-way passing 3600 mm.

## Safe Reads

Read redacted WCS config and point mappings:

```bash
WMS_TOKEN=... node tools/wms.mjs wcs config --warehouse-id WH-ID
```

Preview a sandbox connection update before writing it:

```bash
WMS_WCS_TOKEN=... WMS_TOKEN=... node tools/wms.mjs wcs config update --dry-run --warehouse-id WH-ID --base-url https://wcs-sandbox.example.com --callback-url CALLBACK-URL --access-token-env WMS_WCS_TOKEN
```

Apply the reviewed sandbox connection update only after explicit operator
approval. Omitted secrets are preserved; new secrets must be passed through
environment variables so they are not printed in CLI output:

```bash
WMS_WCS_TOKEN=... WMS_TOKEN=... node tools/wms.mjs wcs config update --confirm-config --warehouse-id WH-ID --base-url https://wcs-sandbox.example.com --callback-url CALLBACK-URL --access-token-env WMS_WCS_TOKEN
```

Read WCS task bindings:

```bash
WMS_TOKEN=... node tools/wms.mjs wcs bindings --warehouse-id WH-ID --limit 20
WMS_TOKEN=... node tools/wms.mjs wcs bindings --task-id TASK-ID
```

Config output redacts passwords and access tokens. Treat callback URLs, WCS
base URLs, point codes, task IDs, and payloads as operationally sensitive.

## Certification Task Factory

Preview a fresh sandbox certification task before any write:

```bash
WMS_TOKEN=... node tools/wms.mjs wcs certification task --dry-run --warehouse-id WH-ID --source-location-id SRC-LOCATION-ID --destination-location-id DST-LOCATION-ID --sku-id SKU-ID --quantity 1
```

Tenant admins may create the reviewed internal WMS task with an explicit
confirm flag:

```bash
WMS_TOKEN=... node tools/wms.mjs wcs certification task --confirm-create --warehouse-id WH-ID --source-location-id SRC-LOCATION-ID --destination-location-id DST-LOCATION-ID --sku-id SKU-ID --quantity 1
```

This factory exists only for sandbox certification. It creates a pending
`move` task with `reference_type=wcs_sandbox_cert`, `assigned_type=unassigned`,
and `execution_mode=agv`. It does not dispatch to WCS. Run `wcs gate-check` or
`wcs dispatch --dry-run` on the created task before any live sandbox dispatch.

## Point Mapping Maintenance

Review WMS locations and WCS point codes before a dispatch gate:

```bash
WMS_TOKEN=... node tools/wms.mjs wcs point-mappings list --warehouse-id WH-ID --include-unmapped
WMS_TOKEN=... node tools/wms.mjs wcs point-mappings export --warehouse-id WH-ID --format csv --file mappings.csv
```

Validate edited or generated mappings without applying changes:

```bash
WMS_TOKEN=... node tools/wms.mjs wcs point-mappings validate --warehouse-id WH-ID --file mappings.csv
WMS_TOKEN=... node tools/wms.mjs wcs point-mappings import --warehouse-id WH-ID --file mappings.csv --validate-only
```

Only import after validation returns no blocking issues and the operator
explicitly approves the configuration change. The CLI requires
`--confirm-import` for an actual mapping write:

```bash
WMS_TOKEN=... node tools/wms.mjs wcs point-mappings import --warehouse-id WH-ID --file mappings.csv --confirm-import
```

Dock doors are external WCS points unless the warehouse intentionally has WMS
location records for them. Do not turn dock doors into storage locations.

## Dispatch Dry-Run

Use gate-check or dispatch dry-run before any live WCS call:

```bash
WMS_TOKEN=... node tools/wms.mjs wcs gate-check --dry-run --task-id TASK-ID
WMS_TOKEN=... node tools/wms.mjs wcs dispatch --dry-run --task-id TASK-ID --callback-url CALLBACK-URL
```

Both commands call `POST
/api/v1/integrations/wcs/tasks/{task_id}/dispatch/preview`. The preview does
not call WCS. It validates:

- WCS base URL.
- Static token or username/password.
- Callback URL.
- source and destination WCS point mappings.
- AGV reachability.
- blocked storage rules such as putaway/move/replenish to a dock door.

If `gate.ok` is false, fix the listed issues or hand off to warehouse/integration
configuration. Do not try to bypass the gate.

## Ready Vehicle and Quality Preview

Preview ready-vehicle changes without calling WCS:

```bash
WMS_TOKEN=... node tools/wms.mjs wcs ready-config --dry-run --warehouse-id WH-ID --ready-sign OUTBOUND-DOCK-A --api-sign 1 --api-num 3
```

Preview quality-complete payloads without calling WCS:

```bash
WMS_TOKEN=... node tools/wms.mjs wcs quality-complete --dry-run --warehouse-id WH-ID --wtaskinfo-psn PALLET-QC-001 --quality-status 合格
```

These commands call `/preview` endpoints only. They return `planned_request`
with the WCS endpoint and redacted config. A human operator must approve any
live `editReadyConfig` or `/QualityComplete` call.

## Callback Replay

Replay a callback payload without mutating WMS task or inventory state:

```bash
WMS_TOKEN=... node tools/wms.mjs wcs callback replay --dry-run --tenant-id TENANT-ID --payload '{"taskTid":4093,"taskPsn":"PALLET-1","stepStatus":30,"stepStatusName":"completed"}'
```

Use replay to verify binding match, WCS status mapping, task status prediction,
and whether completion would create inventory movement. Replay is diagnostic
only; it is not proof that a live WCS callback has been accepted.

## Hard Stops

- Do not call `POST /api/v1/integrations/wcs/tasks/{task_id}/dispatch` from
  autonomous agent flow.
- Do not call `POST /api/v1/integrations/wcs/webhook/{tenant_id}/taskfinish`
  for testing; use replay.
- Do not call live `ready-config` or `quality-complete` endpoints from
  autonomous flow; use the `--dry-run` preview commands.
- Do not run `wcs config update --confirm-config` without explicit operator
  approval after the dry-run validation and redacted diff are reviewed.
- Do not run `wcs certification task --confirm-create` without explicit tenant
  admin approval after the dry-run task plan is reviewed.
- Do not run `wcs point-mappings import --confirm-import` without explicit
  operator approval after validation evidence is reviewed.
- Do not edit AGV simulator or core adapter behavior from this skill. If the
  preview contract is missing data, request a small read/preview API extension.
