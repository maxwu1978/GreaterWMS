# AGV-Ready Receiving Roadmap

## Purpose

This roadmap defines how receiving should evolve to support future AGV execution
without breaking the current WMS architecture.

The goal is not to replace the current receiving flow. The goal is to preserve
the existing internal-label-driven workflow while adding the right compatibility
layer for current customer habits and the right task structure for future AGV use.

## Current System Baseline

The current codebase already has a strong backbone that should remain intact:

- `InboundOrder` and `InboundOrderLine` manage inbound business documents.
- `ReceivingLabel` is the internal system label used during receiving.
- `ReceivingService` supports:
  - order creation
  - label generation
  - label scan
  - label confirmation
  - putaway task generation
- `Task` is already the shared work unit for both human and AGV execution.
- `PutawayService` already moves stock from staging to storage and completes
  putaway tasks.
- `AGVService` already consumes `Task` as the universal execution object.
- `Location` already contains AGV-ready fields such as coordinates and
  `is_agv_accessible`.

Because of this, future work should extend the current flow instead of replacing it.

## Design Principle

Use a dual-layer model:

1. Human-facing entry can match current customer habits.
2. System-facing execution must stay standardized for AGV and traceability.

That means:

- operators may scan external identifiers such as tracking number or carton mark
- the system should still normalize every receipt into internal labels,
  internal handling units, and internal tasks

## What Should Not Change

The following current foundations should remain:

- `ReceivingLabel` remains the internal receiving identifier
- `Task` remains the single work model for human and AGV execution
- `PutawayService` remains the canonical source-to-destination inventory move flow
- AGV does not consume customer-facing external codes directly

## Evolution Strategy

### Phase 1: External Code Compatibility Layer

#### Goal

Match the current customer receiving habit without changing the internal flow.

#### Scope

Add support for identifying inbound work through:

- system receiving label
- tracking number
- carton mark
- customer barcode

#### Implementation Approach

Do not replace `scan-label`.

Instead, add a compatibility resolver that:

1. checks internal label first
2. checks mapped external identifiers second
3. resolves to the same internal label or line context

#### Data Shape

Extend receiving identification with optional mapped fields:

- `external_tracking_number`
- `external_carton_mark`
- `external_customer_barcode`

These fields should be additive and not become the primary internal key.

#### Why This Is Compatible

- current receiving APIs remain valid
- current review and completion flow remains valid
- current putaway task generation remains valid

### Phase 2: Handling Unit Layer

#### Goal

Introduce a true warehouse movement object without breaking the current model.

#### New Object

Add `HandlingUnit` as an attached layer, not a replacement layer.

Suggested fields:

- `id`
- `tenant_id`
- `order_id`
- `order_line_id`
- `receiving_label_id`
- `unit_type` (`carton`, `pallet`, `tote`)
- `external_tracking_number`
- `external_carton_mark`
- `expected_qty`
- `received_qty`
- `damaged_qty`
- `measured_weight_kg`
- `measured_length_cm`
- `measured_width_cm`
- `measured_height_cm`
- `staging_location_id`
- `status`

#### Suggested Statuses

- `expected`
- `received`
- `staged`
- `putaway_pending`
- `putaway_in_progress`
- `stored`

#### Why This Is Compatible

- `InboundOrderLine` still exists
- `ReceivingLabel` still exists
- current line-based receiving can still aggregate from handling units
- no rewrite of the putaway service is required yet

### Phase 3: Task Enrichment for AGV

#### Goal

Make putaway tasks AGV-ready without creating a second task system.

#### Implementation Approach

Extend the existing `Task` model instead of introducing a new AGV task model.

Suggested additions:

- `handling_unit_id`
- `execution_mode` (`human`, `agv`, `hybrid`)

#### Why This Is Compatible

Current services already depend on `Task`:

- putaway
- picking
- AGV polling

Keeping a single task model avoids fragmentation and regression risk.

### Phase 4: AGV Execution Integration

#### Goal

Allow AGV systems to consume standardized internal work only.

#### Implementation Approach

Keep AGV polling through the current `AGVService`, but enrich the payload with:

- `handling_unit_id`
- unit weight
- unit dimensions
- internal label code
- execution constraints

AGV should continue to rely on:

- `Task`
- source location
- destination location
- location coordinates
- internal identifiers

AGV should not rely on:

- customer carton marks
- carrier tracking numbers
- customer-defined ad hoc labels

## UX Direction

### Receiving Page

The receiving page should remain simple for operators:

1. scan a code
2. see the resolved receiving target
3. confirm receipt
4. stage goods
5. hand off to putaway

The page should not expose AGV-specific concepts at the receiving step.

### Putaway Page

The putaway page becomes the transition point between:

- human execution
- AGV execution

At that stage, the system can decide whether a task is:

- human-only
- AGV-capable
- hybrid

## Recommended Rollout Order

1. External code compatibility
2. HandlingUnit as an attached layer
3. Task enrichment with `handling_unit_id`
4. AGV payload enrichment
5. Full carton/pallet operational views

## What To Avoid

Do not:

- replace `ReceivingLabel` with external codes
- create a second AGV-specific task model
- rewrite `PutawayService` early
- expose too many AGV concepts in the human receiving UI
- make external codes the long-term system primary key

## Final Recommendation

The best AGV-ready receiving design for this codebase is:

- keep the current label-driven internal flow
- let operators enter through their current external-code habit
- normalize everything into internal labels and handling units
- keep `Task` as the single execution model for both humans and AGVs

This path fits the current customer reality and the future AGV direction at the same time.
