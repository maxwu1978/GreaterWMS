# CAD Layout Export Standard

This standard defines how WMS/AGV warehouse planning drawings must be exported
to CAD/DXF so operators, customers, and AGV vendors can review the same plan
without label overlap, hidden capacity changes, or ambiguous route semantics.

Use this standard together with `docs/36-agv-planning-standard.md`.

## Scope

Use this standard for:

- CAD/DXF exports generated from WMS warehouse planning data;
- AGV route, lane, station, charger, dock, and safety-zone drawings;
- customer-facing warehouse layout review files;
- CAD exports used as source material for WCS point mapping.

## Required Inputs

Before exporting CAD, the planner must have:

- source drawing name/version or source image name;
- original building or area dimensions;
- every storage-zone width/depth and slot width/depth/height;
- cargo dimensions used to size slots;
- rack bay count, bay width, level count, level clear height, and pallet
  depth/width basis when rack storage is present;
- route lane widths, directions, and station roles;
- unresolved assumptions, especially missing field measurements, AGV envelope,
  turning radius, dock constraints, floor conditions, and safety clearances.

If these inputs are incomplete, mark the CAD as draft and show the missing
assumptions in the drawing notes or handoff text.

## Units And Coordinates

- CAD unit must be millimeters.
- Source dimensions may be stored in feet, but DXF geometry must convert using
  `1 ft = 304.8 mm`.
- Use model space for geometry.
- Keep a consistent drawing orientation with the reviewed WMS map. If the CAD
  Y-axis orientation differs from the source image, note it in the export
  script or title block.
- Do not distort physical dimensions to make the drawing look balanced.

## Required Layers

| Layer | Required content |
| --- | --- |
| `WALL` | Warehouse shell, walls, columns, fixed building boundaries |
| `EQUIP` | Racks, fixed equipment, office boundary, workstation outlines |
| `STORAGE` | WMS storage zones and generated storage slots |
| `AGV-CORRIDOR` | AGV lanes, drive aisles, connector lanes, lower return lanes |
| `AGV-PATH` | AGV route centerlines and arrows |
| `STATION` | Wait points, chargers, maintenance points, pickup/dropoff stations |
| `SAFE` | Safety boundaries, slow/sensing/no-go areas |
| `DOCK` | Dock doors and external transport interfaces |
| `DIMENSION` | Dimension lines and dimension ledger items |
| `TEXT` | Short object labels and note panel content |

Do not put everything on a default layer. Reviewers must be able to hide routes,
dimensions, storage, dock, and safety objects independently.

## Drawing Layout

Use a clear two-part drawing structure:

1. Main plan area.
   Show warehouse shell, storage slots, lanes, route centerlines, dock doors,
   stations, and safety boundaries.
2. Annotation panel.
   Place dimension ledger, cargo assumptions, slot counts, WCS point-count
   summary, and non-storage notes in a dedicated panel outside the main plan.
3. Detail sheets when needed.
   If rack, conveyor, charger, or station details would crowd the main plan,
   create a separate detail DXF for the equipment and keep only a short
   summary label on the main plan.

Avoid placing long horizontal dimension ledgers above the main plan when they
make the drawing extents much taller or shrink the main drawing in CAD viewers.
Prefer a right-side annotation panel for wide warehouse plans and a bottom
annotation panel only when it does not reduce plan readability.

## Text And Label Rules

- Main-plan labels must be short. Use object names, lane width, and direction
  only.
- Long explanations belong in the annotation panel, not on top of lanes,
  storage slots, routes, or dock doors.
- Labels must not overlap:
  - storage slot boundaries;
  - route centerlines or arrows;
  - dock-door labels;
  - dimension lines;
  - station markers.
- Keep at least one text-height of clear space between a label and the nearest
  line it could be mistaken for.
- Prefer horizontal labels. Use vertical labels only when they sit outside the
  functional geometry and remain readable at full extents.
- Do not duplicate the same explanation in multiple places on the main plan.

## Dimension Rules

Every CAD export must include a dimension ledger that answers:

- which original dimensions were preserved;
- how total width/depth was allocated;
- whether a lane or connector consumed storage capacity;
- whether an external lane sits outside the storage boundary and does not
  reduce storage capacity.

For the Dallas A/B/C pattern, the ledger must preserve this style of statement:

```text
Width: 120ft = A-CONN 12 + A 28 + B 40 + C 40
Depth: rack-to-ABC 34ft = upper aisle 12 + storage 22
Lower lane: 12ft outside ABC storage, not deducted
```

Local object dimensions may appear near the object, but full allocation
statements must stay in the annotation panel.

## Storage Rules

- Storage zones create WMS locations.
- AGV corridors, connector lanes, lower return lanes, wait points, chargers,
  maintenance points, and dock doors do not create WMS storage locations.
- Dock doors are unload/ship interfaces, not inventory locations.
- If a corridor consumes space previously counted as storage, split it into a
  non-storage AGV zone and reduce storage width/depth, area, slot count, and
  capacity notes.
- If a clear lane is outside the original storage boundary, model it as an
  external AGV lane and do not subtract it from storage capacity.
- Slot dimensions must come from cargo footprint plus operational clearance
  when customer cargo exceeds a standard pallet footprint.

## AGV Route Rules

- AGV route centerlines must stay outside `floor_storage` zones unless an
  approved internal aisle is split out as a separate non-storage zone.
- Route arrows must show direction on every major path segment.
- Lane labels must include width and direction.
- Main aisle, branch/connector lane, return lane, dock corridor, wait point,
  charger, and safety boundary must be visually distinct by layer.
- Chargers and wait points must not block the main route.
- Slow/sensing or safe-boundary zones should be shown around dock approaches,
  intersections, blind corners, and route/storage interfaces.

## Export Naming

Use stable, descriptive names:

```text
exports/{warehouse-code}-agv-layout-v{version}-cad.dxf
```

For temporary review variants, append the purpose:

```text
exports/dallas-agv-layout-v2-cad.dxf
exports/dallas-rack-detail-v1-cad.dxf
exports/dallas-agv-layout-v2-map-only.pdf
exports/dallas-agv-layout-v2-cad-label-fix.dxf
```

## Closure Standard

A CAD export is not ready for customer/vendor review until all items below pass:

- DXF opens in a CAD viewer without parse errors.
- Drawing units are millimeters.
- Required layers are present and objects are separated into the correct
  layers.
- Main plan is readable at full extents; storage slots, routes, and dock doors
  are not visually crushed by off-plan dimensions.
- No main-plan label overlaps storage slots, route centerlines, arrows,
  dimension lines, dock labels, or station markers.
- Dimension ledger reconciles original dimensions and final allocation.
- Storage location count matches backend/simulator/generated WMS locations.
- WCS point-count summary separates storage, dock, wait, charger, and station
  points.
- Dock doors are labeled as external transport interfaces, not storage.
- AGV route centerlines do not cross `floor_storage`.
- Lane widths, route direction arrows, station roles, and safety boundaries are
  visible.
- Rack detail sheet is generated when rack level height, bay count, pallet
  depth, or elevation data would make the main plan crowded.
- Export script is repeatable from source layout data.
- The matching PNG/PDF preview is generated or visually checked when the CAD
  layout changes materially.

## Verification Commands

For the Dallas simulator export, run:

```bash
cd agv-simulator
npm run check
npm run cad:dallas
npm run cad:dallas:rack
npm run review:dallas
npm run smoke:dallas
```

If backend blueprint data changed, also run the focused backend blueprint
regression:

```bash
cd backend
uv run pytest tests/test_regressions.py::test_agent_warehouse_blueprint_preview_and_confirm_create_dallas_layout -q
```

If the local agent blueprint prompt, parser, generated layout, or WCS mapping
draft changed, run:

```bash
node wms-agent/scripts/verify-dallas-blueprint-flow.mjs
```

Before any Dallas WCS mapping import or warehouse blueprint confirm, run the
validate-only backend/WCS comparison:

```bash
cd backend
uv run python scripts/verify_dallas_blueprint_validate_only.py
```

After operator approval and after production health reports the deployed build
that contains the Dallas blueprint/WCS changes, use the guarded live apply
script. It requires explicit confirmation environment variables and writes only
redacted summaries to `tmp/`:

```bash
cd backend
WMS_DALLAS_APPLY_CONFIRM=ALLOW_DALLAS_BLUEPRINT_WRITE \
WMS_DALLAS_IMPORT_CONFIRM=ALLOW_DALLAS_WCS_MAPPING_IMPORT \
uv run python scripts/apply_dallas_blueprint_live.py
```

For a tenant that already has the reviewed `DAL` warehouse, add:

```bash
WMS_DALLAS_ALLOW_EXISTING_WAREHOUSE=true
```

If the existing Dallas warehouse still contains the known layout-v2 legacy
A-zone racks consumed by the A-area connector lane, cleanup is also guarded by:

```bash
WMS_DALLAS_EXISTING_CLEANUP_CONFIRM=ALLOW_DALLAS_EXISTING_LAYOUT_CLEANUP
```
