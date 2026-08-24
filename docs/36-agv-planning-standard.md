# AGV Planning Standard

This standard captures the field drawing and layout rules that WMS agents,
warehouse planners, and WCS/AGV route tooling must use when generating or
reviewing warehouse layouts, storage locations, station points, and travel
routes.

Source: AGV field drawing guide V1.0 provided by the operator.

## Scope

Use this standard for:

- warehouse blueprint interpretation and cleanup;
- area, rack, floor-storage, dock, station, charging, waiting, and maintenance
  planning;
- WMS location generation from customer drawings;
- WCS point-code mapping drafts;
- AGV path, direction, lane, and safety-zone planning.

This standard complements the WCS protocol contract. Protocol fields may prove
that WMS and WCS can exchange tasks, but this standard decides whether the
physical plan is suitable for AGV execution.

## Field Survey Inputs

Before generating a warehouse layout, collect or confirm:

- real site dimensions;
- walls, columns, doors, windows, fire hydrants, electrical cabinets, forklift
  aisles, pedestrian aisles, racks, workstations, and fixed equipment;
- floor flatness and thresholds, trench drains, raised sections, and ramps;
- the latest construction CAD or layout CAD when available, reconciled against
  site measurements;
- AGV vehicle profile: one-way or two-way operation, vehicle width, turning
  radius, minimum aisle width, payload, and required safety distance;
- operational points: transport routes, pickup points, dropoff points, charging
  stations, waiting areas, and maintenance areas.

If these inputs are incomplete, the layout must remain a draft and the agent
must call out the missing survey data before asking for approval.

## CAD Drawing Rules

Draw in millimeters at 1:1 scale.

Recommended drawing order:

1. Warehouse shell.
2. Columns and fixed obstacles.
3. Rack or floor-storage arrangement.
4. Location boundaries.
5. AGV aisles.
6. AGV path centerlines.
7. Functional area labels.
8. Dimensions and direction labels.

Required annotations:

- aisle widths;
- rack row counts;
- location dimensions;
- location codes;
- AGV travel direction arrows;
- one-way or two-way lane labels;
- pickup, dropoff, charge, wait, and maintenance station names;
- station docking direction and center point.

Required layers:

| Layer | Content |
| --- | --- |
| `WALL` | Walls and columns |
| `EQUIP` | Racks, fixed equipment, and workstations |
| `AGV-PATH` | AGV travel paths, drawn as red solid lines |
| `STATION` | Pickup points, dropoff points, charging stations, waiting areas, and maintenance points |
| `SAFE` | Safety boundaries, drawn as dashed lines |
| `OBSTACLE` | No-go and obstacle areas |

When a building CAD exists, remove redundant lines and normalize layers before
layout generation. When no CAD exists, convert field sketches and dimensions
into CAD first.

## Clearance and Aisle Thresholds

Baseline clearances:

- AGV to wall or column: at least 150 mm.
- AGV to rack or equipment: at least 200 mm.
- Floor-storage location to wall: at least 100 mm.
- Floor-storage location to column: at least 100 mm.
- Left/right gap between two pallet columns: at least 100 mm.
- Front/back gap within one pallet column: at least 50 mm.

Baseline AGV aisle thresholds:

| Scenario | Minimum |
| --- | ---: |
| Underride or latent AGV aisle, one-way | 1200 mm |
| Underride or latent AGV aisle, two-way | 1600 mm |
| Forklift AGV aisle | 2200 mm |
| Forklift AGV aisle with centerline left/right pickup | 2800 mm |
| Rack-storage main aisle, one-way | 2400 mm |
| Rack-storage main aisle, preferred one-way | 2800 mm |
| Rack-storage main aisle, two-way | 3200-3500 mm |
| Slim underride lift AGV rack branch aisle | 2800 mm |
| Counterbalance AGV rack branch aisle | 3500 mm |
| Narrow-aisle AGV branch aisle | 1850-2200 mm |
| Pallet-jack/forklift AGV pickup branch aisle, one-way | 2500 mm |
| Pallet-jack/forklift AGV main aisle, one-way | 2800 mm |
| Pallet-jack/forklift AGV main aisle, two-way passing | 3600 mm |
| Dead-end turnaround area | 2800 mm |

If a live AGV vendor requires a larger value, the vendor value overrides this
baseline.

## Path Design

Prefer one-way loop routes. They reduce intersections, dead ends, and
head-to-head conflicts.

Route rules:

- keep main aisles wide and straight where possible;
- use narrower branch aisles only for controlled pickup/dropoff access;
- minimize crossings and dead ends;
- design turns with large radii and avoid sharp turns;
- for SLAM AGV routes, use a turning radius of at least 800 mm unless the
  vendor requires more;
- provide passing space or explicit wait/avoidance areas for two-way lanes;
- separate pedestrian aisles from AGV aisles where possible;
- add slow zones or sensor zones at pedestrian crossings, intersections, and
  blind corners;
- place chargers at route ends or corners so they do not occupy the main aisle.

Pickup and dropoff rules:

- AGV must dock perpendicular to the pickup/dropoff face whenever possible;
- AGV should face the station directly, not dock at an angle;
- mark station center point and docking direction;
- for pallet pickup, maintain at least 500 mm between fork tips and pallet
  recognition/alignment features unless vendor data requires more;
- station metadata must state whether the point is pickup, dropoff, charger,
  waiting area, maintenance point, dock door, buffer, or AGV station.

## Rack Storage Planning

Preferred rack orientation:

- transverse racks perpendicular to the AGV main aisle are preferred for most
  warehouses because AGV vehicles can enter and leave locations with fewer
  turns;
- longitudinal racks parallel to the main aisle may suit narrow warehouses, but
  they create more turns and must be reviewed more carefully.

For standard 1200 x 1000 mm pallets:

- location internal clearance should be at least 1250 x 1050 mm;
- each rack level height should include product height, 100 mm top clearance,
  and 150 mm beam allowance.

Location code format:

```text
ZONE-ROW-COLUMN-LEVEL
```

Example:

```text
A-01-05-02
```

Allocation rules:

- fast movers should be near entrances, exits, AGV main aisles, and lower
  levels;
- slow movers should be deeper in the warehouse, in corners, or on higher
  levels;
- heavy goods should use lower levels;
- light goods may use higher levels;
- AGV-priority locations must open toward the AGV aisle;
- angled docking into a storage location is not allowed unless the physical
  vendor design explicitly certifies it.

## Floor-Storage Planning for Pallet-Jack or Forklift AGV

Use corridor-style, single-column deep lanes for batch-based floor storage.

Lane rules:

- each batch should have its own deep storage lane;
- for strict FIFO, AGV enters from one end and exits from the other end;
- if FIFO is not required for a single batch, same-end entry/exit may be used to
  reduce aisle count;
- lanes are parallel, with AGV pickup aisles between lanes;
- the clear area below an A/B/C floor-storage block may be modeled as an AGV
  travel or return lane when the drawing and field measurements provide the
  required width, clearance, direction, and safety separation;
- when a route must pass through space that was previously counted as
  floor-storage area, split that space into a separate non-storage AGV corridor
  zone and reduce the storage location count accordingly;
- WMS and map renderers must show floor-storage area size, pallet slot size,
  slot count, remaining clear bands, and any capacity removed for AGV lanes;
- if customer cargo dimensions exceed a standard pallet footprint, use the
  cargo footprint plus operational clearance as the storage slot size. Do not
  keep GMA-sized WMS slots for oversized cargo.
- each lane is one-way for one AGV at a time;
- two-way head-to-head travel inside a lane is not allowed.

Batch rules:

- different batches must not share the same lane;
- nearby batches may be grouped in the same warehouse area;
- keep at least one empty lane available after a batch lane is cleared so old
  and new batches do not overlap;
- loose, unaligned pallets, mixed batches in one lane, and multi-batch
  crowding are not acceptable AGV-ready layouts.

Recommended area grouping:

- Area A: near-term, high-frequency outbound batches close to the main aisle.
- Area B: mid-term batches.
- Area C: long-term batches deeper in the warehouse.

For CAD and WMS generation, every floor-storage lane must label:

- location boundaries;
- inbound end;
- outbound end;
- whether inbound and outbound use the same end;
- AGV one-way travel direction;
- pallet fork orientation toward the aisle;
- location codes bound to the physical position.
- physical slot dimensions and total area, so a reviewer can compare the WMS
  location distribution against the customer drawing without relying on a
  purely decorative grid.

## WMS Data Requirements

When WMS stores a generated or reviewed layout, preserve these fields where
known:

- zone type and storage type;
- physical dimensions in millimeters or meters with unit metadata;
- drawing coordinates and layout percentages;
- AGV accessibility;
- aisle width;
- one-way or two-way lane policy;
- docking direction;
- station center point;
- route role: main aisle, branch aisle, crossing, wait zone, charger, dock
  door, buffer, maintenance, or storage access;
- safety clearance assumptions;
- source drawing name, version, and review status;
- unresolved survey assumptions.

Dock doors are external transport interfaces unless the operator explicitly
creates WMS location records for them. Do not model dock doors as storage
locations.

## Review Gate

Before approving an AGV-ready warehouse layout or WCS point mapping, verify:

- all AGV-accessible points have coordinates;
- route widths meet the applicable baseline or vendor-specific threshold;
- the route has clear one-way or two-way direction;
- all pickup/dropoff points have station center point and docking direction;
- pedestrian crossings and blind corners have slow or sensing zones;
- chargers, wait areas, and maintenance areas do not block the main aisle;
- rack and floor-storage slot dimensions are recorded;
- batch lanes do not mix batches when FIFO or batch isolation is required;
- dock doors are treated as external points, not storage locations;
- unresolved assumptions are visible to the operator before confirmation.
