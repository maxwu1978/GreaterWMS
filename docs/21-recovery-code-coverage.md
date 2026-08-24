# Recovery Code Coverage Matrix

This matrix tracks the action-first recovery contract for the four mobile
execution workflows. Every listed recovery state must render the shared
`WorkflowRecoveryPanel` shell with:

- what happened
- why the workflow cannot continue
- recommended action
- return entry
- `data-recovery-code`
- `data-recovery-action`
- `data-recovery-safe-exit`

## Shared Selectors

| Flow | Panel | Sections | Action selector |
| --- | --- | --- | --- |
| Receiving | `receiving-recovery-panel` | `receiving-recovery-what-happened`, `receiving-recovery-why-blocked`, `receiving-recovery-recommended-action`, `receiving-recovery-return-entry` | `receiving-recovery-action-{action}` |
| Putaway | `putaway-recovery-panel` | `putaway-recovery-what-happened`, `putaway-recovery-why-blocked`, `putaway-recovery-recommended-action`, `putaway-recovery-return-entry` | `putaway-recovery-action-{action}` |
| Picking | `picking-recovery-panel` | `picking-recovery-what-happened`, `picking-recovery-why-blocked`, `picking-recovery-recommended-action`, `picking-recovery-return-entry` | `picking-recovery-action-{action}` |
| Shipping | `shipping-recovery-panel` | `shipping-recovery-what-happened`, `shipping-recovery-why-blocked`, `shipping-recovery-recommended-action`, `shipping-recovery-return-entry` | `shipping-recovery-action-{action}` |

## Receiving

| Recovery code | Scenario | Recommended action | Safe exit | Automated coverage |
| --- | --- | --- | --- | --- |
| `receiving.scan_already_received` | Scanned code already closed out | `continue_next` | `review_inbound` | Manual/UAT |
| `receiving.scan_order_not_open` | Inbound is not open for live receiving | `back_to_orders` | `back_to_orders` | Manual/UAT |
| `receiving.scan_no_package_match` | Scan cannot match because no package records exist | `add_package` | `back_to_orders` | Manual/UAT |
| `receiving.scan_no_match` | Unknown scan for current inbound | `clear_scan` | `back_to_orders` | `verify-mobile-receiving-flow.mjs` |
| `receiving.receipt_staging_required` | Receipt needs dock/staging before confirmation | `focus_staging` | `focus_staging` | Manual/UAT |
| `receiving.receipt_damaged_quantity` | Damaged units exceed received quantity | `scan_again` | `scan_again` | Mobile UAT quantity assertion |
| `receiving.receipt_empty_quantity` | No good or damaged units entered | `scan_again` | `scan_again` | Manual/UAT |
| `receiving.open_packages_remain` | Complete receiving blocked by open packages | `open_next_package` | `review_inbound` | Manual/UAT |
| `receiving.staging_location_required` | Complete receiving blocked by missing staging/source | `focus_staging` | `review_inbound` | Manual/UAT |
| `receiving.order_not_receiving` | Inbound status changed before completion | `refresh_order` | `refresh_order` | Manual/UAT |
| `receiving.complete_failed` | Generic complete-receiving failure | `review_inbound` | `review_inbound` | Manual/UAT |

## Putaway

| Recovery code | Scenario | Recommended action | Safe exit | Automated coverage |
| --- | --- | --- | --- | --- |
| `putaway.putaway_source_staging_missing` | Backend reports missing source staging | `open_receiving` | `open_receiving` | Manual/UAT |
| `putaway.putaway_source_staging_not_found` | Backend cannot find source staging | `open_receiving` | `open_receiving` | Manual/UAT |
| `putaway.source_staging_missing` | Text fallback for source staging issues | `open_receiving` | `open_receiving` | Manual/UAT |
| `putaway.putaway_source_stock_split` | Source stock is split across inventory records | `open_inventory` | `open_inventory` | Manual/UAT |
| `putaway.putaway_source_inventory_short` | Source staging inventory is short | `open_inventory` | `open_inventory` | Manual/UAT |
| `putaway.source_stock_mismatch` | Text fallback for source stock mismatch | `open_inventory` | `open_inventory` | Manual/UAT |
| `putaway.putaway_allocation_*` | Split allocation plan is invalid | `fix_quantity` | `back_to_list` | Manual/UAT |
| `putaway.allocation_invalid` | Text fallback for allocation failure | `fix_quantity` | `back_to_list` | Manual/UAT |
| `putaway.putaway_destination_not_found` | Destination cannot be found | `choose_slot` | `refresh_task` | Manual/UAT |
| `putaway.putaway_destination_not_storage_slot` | Destination is not a storage slot | `choose_slot` | `refresh_task` | Manual/UAT |
| `putaway.putaway_destination_blocked` | Destination is blocked | `choose_slot` | `refresh_task` | `verify-recovery-action-clicks.mjs` |
| `putaway.putaway_destination_different_sku` | Destination contains different SKU | `choose_slot` | `refresh_task` | Manual/UAT |
| `putaway.destination_blocked` | Text fallback for destination policy conflict | `choose_slot` | `refresh_task` | Manual/UAT |
| `putaway.putaway_destination_same_sku_disabled` | Same-SKU consolidation is disabled | `choose_slot` | `back_to_list` | Manual/UAT |
| `putaway.same_sku_policy_blocked` | Text fallback for same-SKU policy block | `choose_slot` | `back_to_list` | Manual/UAT |
| `putaway.putaway_destination_lot_expiry_mismatch` | Destination lot/expiry does not match | `choose_slot` | `back_to_list` | Manual/UAT |
| `putaway.lot_expiry_mismatch` | Text fallback for lot/expiry mismatch | `choose_slot` | `back_to_list` | Manual/UAT |
| `putaway.putaway_inbound_not_released` | Inbound is not released to putaway | `open_receiving` | `open_receiving` | Manual/UAT |
| `putaway.inbound_not_released` | Text fallback for inbound release block | `open_receiving` | `open_receiving` | Manual/UAT |
| `putaway.putaway_task_not_available` | Task disappeared or changed | `refresh_task` | `refresh_task` | Manual/UAT |
| `putaway.putaway_task_not_pending` | Task is no longer pending | `refresh_task` | `refresh_task` | `verify-recovery-action-clicks.mjs` |
| `putaway.putaway_task_invalid_quantity` | Task quantity is invalid | `refresh_task` | `refresh_task` | Manual/UAT |
| `putaway.task_not_ready` | Text fallback for stale task | `refresh_task` | `refresh_task` | Manual/UAT |
| `putaway.confirm_failed` | Generic putaway confirmation failure | `refresh_task` | `refresh_task` | Manual/UAT |

## Picking

| Recovery code | Scenario | Recommended action | Safe exit | Automated coverage |
| --- | --- | --- | --- | --- |
| `picking.no_open_task` | No open task is available | `refresh_tasks` | `refresh_tasks` | Manual/UAT |
| `picking.stale_task` | Open task no longer exists in queue | `refresh_tasks` | `back_to_list` | Manual/UAT |
| `picking.wrong_location` | Wrong source location scanned | `scan_again` | `back_to_list` | Manual/UAT |
| `picking.wrong_sku` | Wrong SKU scanned | `scan_again` | `back_to_list` | Manual/UAT |
| `picking.missing_scan_code` | Task lacks expected scan code | `back_to_list` | `back_to_list` | Manual/UAT |
| `picking.pick_task_not_found` | Backend cannot find task | `refresh_tasks` | `back_to_list` | `verify-recovery-action-clicks.mjs` |
| `picking.pick_task_already_completed` | Task already completed | `refresh_tasks` | `back_to_list` | Manual/UAT |
| `picking.pick_task_cancelled` | Task was cancelled | `refresh_tasks` | `back_to_list` | Manual/UAT |
| `picking.pick_task_assigned_to_agv` | Task assigned to AGV work | `refresh_tasks` | `back_to_list` | Manual/UAT |
| `picking.pick_task_assigned_to_other_operator` | Task assigned to another human | `refresh_tasks` | `back_to_list` | Manual/UAT |
| `picking.task_not_available` | Text fallback for unavailable task | `refresh_tasks` | `back_to_list` | Manual/UAT |
| `picking.pick_quantity_non_positive` | Picked quantity is zero or negative | `adjust_quantity` | `back_to_list` | Manual/UAT |
| `picking.pick_quantity_exceeds_task` | Picked quantity exceeds task quantity | `adjust_quantity` | `back_to_list` | Manual/UAT |
| `picking.pick_quantity_exceeds_reserved` | Picked quantity exceeds reserved quantity | `adjust_quantity` | `back_to_list` | `verify-recovery-action-clicks.mjs` |
| `picking.quantity_rejected` | Text fallback for rejected quantity | `adjust_quantity` | `back_to_list` | Manual/UAT |
| `picking.pick_insufficient_stock` | Stock changed before confirmation | `refresh_tasks` | `refresh_tasks` | Manual/UAT |
| `picking.pick_source_inventory_not_found` | Source inventory disappeared | `refresh_tasks` | `refresh_tasks` | Manual/UAT |
| `picking.stock_changed` | Text fallback for source stock changes | `refresh_tasks` | `refresh_tasks` | Manual/UAT |
| `picking.confirm_failed` | Generic pick confirmation failure | `scan_again` | `refresh_tasks` | Manual/UAT |

## Shipping

| Recovery code | Scenario | Recommended action | Safe exit | Automated coverage |
| --- | --- | --- | --- | --- |
| `shipping.enterTracking` | Carrier handoff missing carrier or tracking details | `enterTracking` | `backToShippingList` | Manual/UAT |
| `shipping.scanNextSku` | SKU line already confirmed; continue pack check | `scanNextSku` | `backToShippingList` | Manual/UAT |
| `shipping.resetPackCheck` | Wrong SKU, no picked quantity, quantity mismatch, or pack verify failure | `resetPackCheck` | `backToShippingList` | `verify-shipping-flow.mjs` |
| `shipping.finishPickingFirst` | Order still needs upstream picking | `finishPickingFirst` | `backToShippingList` | Manual/UAT |
| `shipping.backToShippingList` | Order already left shipping queue | `backToShippingList` | `backToShippingList` | Manual/UAT |
| `shipping.refreshOrder` | Order state changed or API action failed | `refreshOrder` | `backToShippingList` | Manual/UAT |

## Automation Expectations

Release gates should keep at least one scripted assertion per workflow:

- Receiving: unknown scan renders `receiving.scan_no_match`, clicks
  `receiving-recovery-action-clear_scan`, and confirms the panel clears.
- Putaway: blocked destination renders `putaway.putaway_destination_blocked`,
  clicks `putaway-recovery-action-choose_slot`, then verifies
  `putaway-recovery-action-back_to_list`. Stale task recovery renders
  `putaway.putaway_task_not_pending` and clicks
  `putaway-recovery-action-refresh_task`.
- Picking: rejected quantity renders `picking.pick_quantity_exceeds_reserved`,
  clicks `picking-recovery-action-adjust_quantity`, then verifies
  `picking-recovery-action-back_to_list`. Missing task recovery renders
  `picking.pick_task_not_found` and clicks
  `picking-recovery-action-refresh_tasks`.
- Shipping: wrong pack-check SKU renders `shipping.resetPackCheck` and clicks
  `shipping-recovery-action-resetPackCheck`.

Run `npm run smoke:recovery-matrix` from `frontend/` after editing this file or
any recovery-state code. The validator checks that documented codes still exist
in source, referenced automation scripts exist, automation rows assert the
documented code, and each flow keeps at least one automated coverage row.

Run `npm run uat:mobile-orchestrator` from `frontend/` for the mobile release
gate. It executes the stable mobile Receiving, Putaway/Picking recovery, and
Shipping mobile handoff checks, then runs production test-data cleanup.
