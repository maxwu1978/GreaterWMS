# WCS / AGV Integration Plan

## Goal

Support WCS systems that accept transport tasks from WMS and send task lifecycle callbacks. This complements the existing pull-based `/api/v1/agv` API instead of replacing it.

## Source Documents

- `AGV/WCS对接手册.pdf`
- `AGV/WCS接口API.html`
- `AGV现场绘图指导V1.0.docx`, summarized as
  `docs/36-agv-planning-standard.md`

## AGV Planning Standard

Warehouse layout generation, WCS point-code draft generation, and AGV route
planning must follow `docs/36-agv-planning-standard.md`.

The standard now defines the minimum field-survey inputs, CAD layer rules,
aisle widths, safety clearances, one-way/two-way route principles, pickup and
dropoff station rules, rack-storage dimensions, floor-storage lane rules, and
batch-isolation requirements. It also defines the WMS layout metadata that must
be preserved when an agent converts customer drawings into zones, locations,
station points, and WCS mapping drafts.

If a layout cannot satisfy those thresholds, the blueprint output must remain a
draft and the agent must surface the missing field measurements or physical
constraint before asking for operator approval.

## Protocol Surface

WMS calls WCS:

- `POST /loginToken` to obtain an access token when a static token is not configured.
- `POST /task/wlTaskInfo/addTransportTask` to create a transport task.
- `POST /task/wlReadyAgvRobot/editReadyConfig` to update ready-vehicle control.
- `POST /QualityComplete` to notify WCS that a QC step is complete.

WCS calls WMS:

- `POST /api/v1/integrations/wcs/webhook/{tenant_id}/taskfinish` for lifecycle callbacks.

## Field Mapping

| WMS | WCS |
| --- | --- |
| `Task.source_location.barcode` | `startPos` |
| `Task.destination_location.barcode` | `endPos` |
| `Task.priority` | `wtaskinfoOrder` |
| `Task.lpn / handling_unit_id / reference_id` | `wtaskinfoPsn` |
| `Warehouse.code` or WCS config `scode` | `wtaskinfoScode` |
| WCS callback URL | `wtaskinfoReturnurl` |
| `Task.id` | `wtaskinfoTabletid` |

## Status Mapping

| WCS `stepStatus` | Meaning | WMS task status |
| --- | --- | --- |
| `-10` | Cancelled | `cancelled` |
| `0` | Waiting | `assigned` |
| `5` | Waiting assignment | `assigned` |
| `10` | Waiting execution | `assigned` |
| `20` | Running | `in_progress` |
| `25` | Paused | `in_progress` with recovery note |
| `30` | Completed | `completed` and inventory transaction |
| `40` | Exception | `failed` |

## Implemented Foundation

- `WcsTaskBinding` model stores the WMS task to WCS task relationship.
- Alembic migration `014_add_wcs_task_bindings.py`.
- `WcsAdapterService` for:
  - building WCS transport payloads,
  - dispatching tasks to WCS,
  - applying callbacks idempotently,
  - mapping WCS statuses into the existing WMS `Task` state machine.
- Integration endpoints:
  - `GET /api/v1/integrations/wcs/config/{warehouse_id}`
  - `GET /api/v1/integrations/wcs/bindings`
  - `POST /api/v1/integrations/wcs/configure`
  - `GET /api/v1/integrations/wcs/point-mappings?warehouse_id=...&include_unmapped=true&format=json|csv`
  - `POST /api/v1/integrations/wcs/point-mappings`
  - `POST /api/v1/integrations/wcs/point-mappings/validate`
  - `POST /api/v1/integrations/wcs/point-mappings/import`
  - `POST /api/v1/integrations/wcs/tasks/{task_id}/dispatch/preview`
  - `POST /api/v1/integrations/wcs/tasks/{task_id}/dispatch`
  - `POST /api/v1/integrations/wcs/ready-config`
  - `POST /api/v1/integrations/wcs/ready-config/preview`
  - `POST /api/v1/integrations/wcs/quality-complete`
  - `POST /api/v1/integrations/wcs/quality-complete/preview`
  - `POST /api/v1/integrations/wcs/webhook/{tenant_id}/taskfinish/replay`
  - `POST /api/v1/integrations/wcs/webhook/{tenant_id}/taskfinish`
- WCS dispatch gate:
  - requires WCS `base_url`,
  - requires static token or username/password,
  - requires callback URL,
  - requires source and destination WCS `point_code`,
  - requires source and destination AGV reachability,
  - returns both compatibility `issues` strings and structured `issue_details` / `recovery_actions`,
  - reports source and destination point summaries including `point_code`, `point_type`, WCS reachability, and WMS AGV accessibility,
  - blocks putaway/move/replenish tasks whose destination point is a dock door,
  - treats buffers and AGV stations as valid WCS execution points when their mapping marks them AGV reachable.
- WCS point-code mapping maintenance:
  - maps WMS `Location.id` / `Location.barcode` to WCS `point_code`,
  - accepts storage locations plus external point roles such as dock doors, buffers, aisle groups, and AGV stations,
  - preserves optional `point_type`, `point_role`, `point_name`, `station_role`, and `wcs_metadata`,
  - stores canonical rows indexed by both location id and barcode for dispatch lookup,
  - validates unknown locations, duplicate locations, duplicate point codes, and missing point codes,
  - reports unmapped AGV-accessible locations for rollout readiness,
  - supports JSON/CSV export and JSON/CSV import through `tools/wms.mjs`.
- Warehouse layout metadata:
  - `zones` now carry `zone_type`, drawing coordinates, `dimensions`, `layout_metadata`, and `drawing_source`,
  - `locations` now carry physical `dimensions`, `layout_metadata`, `drawing_source`, and `wcs_point_metadata`,
  - `Warehouse.address._blueprint_layout` remains as a compatibility snapshot for existing map/agent readers.
- Dallas blueprint preview:
  - accepts local-agent copied JSON with nested `metadata` / `dimensions`,
  - returns `abc_floor_areas`, `rack_areas`, `dock_doors`, `area_dimensions`, and `wcs_point_mapping_draft`,
  - stores WCS point codes from blueprint generation as draft metadata until mappings are explicitly validated/imported.
- AGV simulator Dallas interop path:
  - `agv-simulator/fixtures/dallas-layout-wcs-point-mapping-draft.json` stores Dallas AGV standard layout v2,
  - `GET /api/layouts/dallas` exposes the layout plus a dynamically generated WCS point mapping draft,
  - the generated draft contains 108 storage points, 8 external dock-door points, and AGV wait/charge station points,
  - A/B/C are floor-storage locations sized to the customer cargo footprints. A cargo is 68 x 58 x 100 in and uses 6 ft x 5 ft x 9 ft slots; because the west side is enclosed, A uses a 12 ft non-storage `A-CONN` connector carved from the original A area and now has 16 visible oversize slots. B/C cargo is 104 x 55 x 98 in and each area uses 9 ft x 5 ft x 9 ft slots, 16 visible slots per area. ABC keeps the original 120 ft total width, and the lower AGV lane is outside the 34 ft rack-to-ABC storage depth. AGV routes stay outside the green storage slots, only the top row near the office is 4-level rack storage, and dock doors are transport interfaces rather than storage locations,
  - the layout includes route nodes, one-way/controlled AGV paths, wait/charge stations, slow zones, and safety boundaries,
  - `GET /api/exchanges` and `POST /api/exchanges/{id}/replay` retain and replay saved local WMS/WCS exchanges,
  - `npm run smoke:dallas` starts the simulator and verifies health, task creation, Dallas route/state generation, pause/resume/reset, WCS-compatible callbacks for `stepStatus=20` / `25` / `30` / `40`, and local exchange replay.
- Agent/CLI WCS diagnostics:
  - `node tools/wms.mjs wcs config --warehouse-id WH-ID`
  - `node tools/wms.mjs wcs bindings --warehouse-id WH-ID`
  - `node tools/wms.mjs wcs certification task --dry-run --warehouse-id WH-ID --source-location-id SRC --destination-location-id DST --sku-id SKU`
  - `node tools/wms.mjs wcs certification task --confirm-create --warehouse-id WH-ID --source-location-id SRC --destination-location-id DST --sku-id SKU`
  - `node tools/wms.mjs wcs gate-check --dry-run --task-id TASK-ID`
  - `node tools/wms.mjs wcs dispatch --dry-run --task-id TASK-ID`
  - `node tools/wms.mjs wcs ready-config --dry-run --warehouse-id WH-ID --ready-sign SIGN --api-sign 1 --api-num 3`
  - `node tools/wms.mjs wcs quality-complete --dry-run --warehouse-id WH-ID --wtaskinfo-psn PSN`
  - `node tools/wms.mjs wcs point-mappings list --warehouse-id WH-ID --include-unmapped`
  - `node tools/wms.mjs wcs point-mappings export --warehouse-id WH-ID --format csv --file mappings.csv`
  - `node tools/wms.mjs wcs point-mappings validate --warehouse-id WH-ID --file mappings.csv`
  - `node tools/wms.mjs wcs point-mappings import --warehouse-id WH-ID --file mappings.csv --validate-only`
  - `node tools/wms.mjs wcs point-mappings import --warehouse-id WH-ID --file mappings.csv --confirm-import`
  - `node tools/wms.mjs wcs callback replay --dry-run --tenant-id TENANT-ID --payload JSON`
  - `wms-agent/skills/wms-wcs-operator/SKILL.md` documents the safe agent workflow.

## 2026-05-08 Certification Snapshot

Latest safe gate evidence for Dallas test data:

- CI: GitHub Actions run `25558178544` passed on `main`.
- Render deploy: run `25558178546` passed and deployed commit `f74a911f14dca8b9df7feba3c5866108837dd5a6`.
- Production health: `https://api.maxsmartwms.online/health` returned `status=ok`, build `f74a911f14dca8b9df7feba3c5866108837dd5a6`.
- Warehouse: `db096932-cbae-4cbe-8a24-28e05dda6c6c`, tenant `221274c6-a6cf-49b2-92b8-06d422bbb421`.
- Point mappings: 128 rows, 120 mapped WMS locations, 0 unmapped AGV-accessible locations, 8 external dock-door points, 0 validation issues, 0 warnings.
- Dispatch preview task: `24d4420e-5110-4cf2-8f38-d63217166a89`; gate `ok=true`, dry-run only, source `DAL-STO-DAL-A-01-01-01-01`, destination `DAL-STO-DAL-B-01-01-01-01`, endpoint `POST /task/wlTaskInfo/addTransportTask`, callback URL present.
- Local simulator: Dallas smoke passed with route from `DAL-DOCK-DOCK-27` to `DAL-STO-DAL-A-01-01-01-01`, callback statuses `20` / `25` / `30`, saved exchange replay status `200`, and an explicit failed-task `40` path.
- Callback replay without a live WCS binding correctly returned “No WCS task binding matches callback”; this is expected until an operator approves a live sandbox dispatch.

Live WCS dispatch, production callback writes, mapping imports without
`--validate-only`, and production DDL remain approval-gated.

## 2026-05-08 Live Sandbox Certification Update

After explicit operator approval, the Dallas live sandbox path was certified
against the public AGV simulator:

- `wms-agv-sandbox` is live at `https://wms-agv-sandbox.onrender.com`.
- Dallas WCS config was updated through `wcs config update --dry-run` and the
  approved `--confirm-config` path.
- Commit `5486d341e5a18d142299553f99d401dee8e69222` fixed the production
  webhook tenant context issue that initially caused live simulator callbacks
  to return `404`.
- CI run `25582133151` and Render deploy gate `25582133140` passed; production
  `/health` reports build `5486d341e5a18d142299553f99d401dee8e69222`.
- Live dispatch created WCS task `1778278075237001` for WMS task
  `24d4420e-5110-4cf2-8f38-d63217166a89`.
- Production callbacks for `stepStatus=20` and `stepStatus=30` returned `200`
  and moved the binding through `in_progress` to `completed`.
- Duplicate `stepStatus=30` callback returned `200` and left exactly one AGV
  putaway transaction for the inbound reference.
- Live sandbox ready-config and quality-complete calls succeeded.

## 2026-05-09 Exception Callback Certification Update

The remaining WCS-specific exception path has now been certified against the
public AGV simulator sandbox:

- fresh WMS move task: `23d5d652-4ec0-4575-9f1d-dc6471a10ffe`;
- WCS task ID: `1778298018550001`;
- source: `DAL-STO-DAL-A-01-01-01-01`;
- destination: `DAL-STO-DAL-B-01-01-01-01`;
- simulator emitted `stepStatus=40`;
- WMS binding moved to `failed`, WMS task moved to `failed`, `retry_count=1`,
  and `failure_reason=simulated AGV error`;
- inventory movement for the exception reference remained at `0`.

WCS-specific certification is complete for simulator-compatible dispatch,
running, completion, duplicate completion, exception, ready-config, and
quality-complete flows. The provided `AGV/WCS接口API.html` contract has also
been reviewed for ready-config and quality-complete field names; no additional
field variant is required unless the live vendor sandbox differs from that
document. External infrastructure sign-off is complete for the current
release/test stage.

## 2026-05-13 Dallas AGV Standard Layout v2

The Dallas warehouse layout has been reorganized against
`docs/36-agv-planning-standard.md`:

- `DAL-A`, `DAL-B`, and `DAL-C` are floor-storage areas using customer cargo
  footprints instead of GMA slots: A uses 16 slots sized 6 ft x 5 ft x 9 ft
  for 68 x 58 x 100 in cargo; B/C each use 16 slots sized 9 ft x 5 ft x 9 ft
  for 104 x 55 x 98 in cargo. A was reduced horizontally because the west
  side is enclosed and the 12 ft internal AGV connector must occupy the left
  side of the original A footprint.
- ABC still keeps the original 120 ft total width:
  A-CONN 12 ft + A 28 ft + B 40 ft + C 40 ft. The 34 ft rack-to-ABC depth is
  now split into a 12 ft upper AGV aisle and 22 ft floor-storage depth.
- `ABC-LOWER` is a non-storage AGV lane below A/B/C. It is available for
  controlled eastbound return/travel back toward the dock corridor and sits
  outside the original ABC storage depth.
- AGV routes do not enter or cross A/B/C floor-storage slots. `A-CONN` connects
  the upper aisle to the lower lane through non-storage space carved from A;
  B/C use external edge handoff points on the upper aisle and lower lane.
- `DAL-RACK` is the only rack-storage zone, placed along the top row near the
  office, with 15 rack positions and 4 levels. Each level uses 65 in clear
  height, and rack depth is marked from the GMA pallet depth of 40 in / 3.33 ft.
- `DOCK` is an external dock-door interface (`DOCK-23` through `DOCK-30`), not
  a WMS storage-location zone.
- The vertical drive aisle and dock corridor are route/reference areas, not
  inventory storage.
- AGV metadata is stored with the blueprint preview/write path:
  `route_policy`, `route_nodes`, `agv_paths`, `stations`, `safety_zones`,
  zone route metadata, location route metadata, and WCS point metadata.
- The local agent blueprint draft now emits the same planning standard fields
  and adds station WCS points to the copied JSON.
- The simulator UI renders zones, dock doors, route paths, safety zones, and
  wait/charge stations on a scrollable/full-screen canvas.

Current local simulator Dallas smoke expectations:

- 108 storage WCS points;
- 8 external dock-door WCS points;
- 3 AGV station/buffer points;
- controlled one-way loop route from `DAL-DOCK-DOCK-27` to an A-zone edge
  handoff point, plus the lower ABC AGV lane and return lane back toward the
  dock;
- smoke validation samples every planned route and task route to make sure no
  centerline crosses a `floor_storage` zone.

## Closure Status

Completed in the platform lane:

1. Blueprint/WCS draft loop:
   - Agent Console and the local agent surface expose blueprint preview and WCS draft output.
   - Warehouse Planner validates and saves WCS point mappings after layout review.
   - Dock doors remain external WCS points unless a warehouse intentionally creates dock location records.

2. Ready-vehicle and QC preview:
   - `/wcs/ready-config/preview` and `/wcs/quality-complete/preview` build outbound WCS payloads without calling WCS.
   - `tools/wms.mjs` exposes `wcs ready-config --dry-run` and `wcs quality-complete --dry-run`.
   - Field review against `AGV/WCS接口API.html` is complete:
     ready-config uses `wrarSign`, `wrarApiSign`, `wrarApiNum`; quality-complete
     uses `wtaskstepTid`, `wtaskinfoPsn`, `qualityStatus`,
     `unqualifiedBuffer`, and `params`.

3. Operator recovery visibility:
   - The AGV page shows WCS bindings, WCS task ID, AGV unit, step state, last callback, and recovery paths.
   - Actual recovery writes such as retry, switch to human, and local cancel remain future explicit write gates.

4. Local AGV simulator:
   - It receives WCS-style transport tasks, displays route and state, emits `20` / `25` / `30` / `40` callbacks, supports pause/resume/reset/fail, and stores exchanges for replay.
   - Current local Dallas check: `cd agv-simulator && npm run smoke:dallas`.

Remaining follow-up:

1. Before loading irreplaceable customer data, confirm the existing logical
   export/PITR posture in `docs/38-real-customer-onboarding-runbook.md`. A
   downloadable export already exists from 2026-05-09; create or download a
   fresh one only if the operator wants a newer off-platform archive.

2. Repeat vendor-specific WCS field review only if the live vendor sandbox
   differs from the provided `AGV/WCS接口API.html` contract.

3. Revisit the backend service plan before sustained production traffic or SLA
   commitment; the current `free` one-instance backend plan is accepted for the
   release/test stage only.
