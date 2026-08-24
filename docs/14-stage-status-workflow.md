# Stage Status Workflow Rules

_Last updated: 2026-04-29_

This document defines which order statuses belong to each operational page and
which API actions are allowed to move work into the next stage.

## Inbound Flow

| Status | Meaning | Primary Surface | Allowed Next Action |
| --- | --- | --- | --- |
| `draft` | Inbound order is still being prepared or imported | Import / order detail | Publish as expected |
| `expected` | ASN exists and is waiting to be opened for receiving | Receiving | Start receiving |
| `arrived` | Freight is at dock but not yet actively scanned | Receiving | Start receiving |
| `receiving` | Packages or SKU quantities are being checked into staging | Live Receiving | Complete receiving after staging is valid |
| `putaway` | Receiving is closed and stock must move from staging to storage | Putaway | Confirm putaway tasks |
| `completed` | Inbound stock is fully stored | History / completed filter | No warehouse execution action |
| `cancelled` | Inbound order was voided before completion | Voided / archived filter | No warehouse execution action |

Receiving pages should treat only `expected`, `arrived`, and `receiving` as
active receiving work. `putaway` can appear as a handoff signal, but the user
must finish that work from Putaway rather than reopening live receiving.

## Outbound Flow

| Status | Meaning | Primary Surface | Allowed Next Action |
| --- | --- | --- | --- |
| `draft` | Outbound order is still being prepared or imported | Import / order detail | Publish as pending |
| `pending` | Order is waiting for inventory allocation | Picking | Allocate inventory |
| `allocated` | Inventory is reserved and ready to release to tasks | Picking | Create pick tasks |
| `picking` | Pick tasks are open for operators | Picking | Confirm pick tasks |
| `picked` | Pick tasks are complete and stock is ready for packing | Shipping | Verify pack |
| `packing` | Packing is in progress | Shipping | Verify pack |
| `packed` | Pack verification is complete | Shipping | Confirm shipment |
| `shipped` | Order has left the warehouse | History / completed filter | No warehouse execution action |
| `cancelled` | Order was cancelled before shipping | Voided / archived filter | No warehouse execution action |

Picking should not show already picked, packed, or shipped orders as actionable
work. Shipping should not show pending, allocated, or picking orders because
those still belong upstream.

## API Stage Guards

The backend should reject out-of-stage actions with `409 Conflict` so the UI and
API cannot drift apart:

| Action | Allowed Status |
| --- | --- |
| `ReceivingService.start_receiving` | `expected`, `arrived`; idempotent for `receiving` |
| `ReceivingService.complete_receiving` | `receiving` |
| `PutawayService.confirm_putaway` for an inbound task | referenced inbound order must be `putaway` |
| `PickingService.allocate_order` | `pending` |
| `PickingService.create_pick_tasks` | `allocated` and no active duplicate pick tasks |
| `ShippingService.verify_pack` | `picked`, `packing` |
| `ShippingService.ship_confirm` | `packed` |

## Page Ownership Rules

- Receiving owns opening inbound work and confirming dock receipt into staging.
- Putaway owns stock that has already left receiving and is waiting in staging.
- Picking owns outbound allocation and picking tasks.
- Shipping owns orders after picking is complete.
- Completed, cancelled, archived, and voided records are reference records, not
  active execution records.

When a page needs to show downstream work, label it as a handoff rather than as
active work on the current page. For example, receiving uses `Putaway handoff`
instead of `Putaway pending`.

## Regression Coverage

The stage rules are covered by backend regression tests:

- receiving start/complete guards reject wrong inbound statuses
- picking allocation and task release reject wrong outbound statuses
- shipping pack/ship confirms reject premature actions
- putaway refuses to confirm tasks whose inbound order has not been released to
  `putaway`
- the full receive-to-ship closed-loop test still passes with these guards
