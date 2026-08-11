# Inbound Advice and Arrival Workflow

## Business Rule

The customer's Pack List is a pre-arrival notice. It identifies the expected goods, package quantities, customer references, and optional serial numbers, but it does not necessarily provide a reliable arrival date or time.

Receiving a Pack List must therefore be treated as an inbound pre-advice event, not as physical arrival. The purpose of the pre-advice is to prepare data and reserve warehouse capacity without increasing on-hand inventory or occupying staging locations before the truck arrives.

## Approved Workflow

### 1. Receive the Pack List

- Find or create one ASN using the inbound order number, customer, and container/tracking reference.
- Import the Pack List and map customer SKU values to internal SKUs.
- Confirm quantities and expected serial numbers when the document is ready for use.
- Keep the ASN in `Pre Arrival`.
- Leave `ETA` as `Not Provided` when the customer has not supplied an arrival time.
- Do not increase received or on-hand inventory.
- Do not mark staging slots as occupied.

Pack List confirmation means that the receiving reference data is ready. It does not mean that the goods have arrived.

### 2. Reserve Capacity

If capacity must be held before arrival:

- Reserve the required Stage-left or Stage-right positions with status `Reserved`.
- A reserved position is held for the ASN but is not physically occupied.
- Use package, pallet, or load-unit quantity for staging allocation, not raw SKU quantity.
- For permanent storage, reserve a compatible zone or capacity first. Assign the exact storage bin after physical receipt, weight/dimension verification, and QC.

For example, eight crates should reserve eight staging positions even if each crate contains multiple product units. One SKU quantity of eight packed into one crate should reserve one position, not eight.

### 3. Receive a Customer Arrival-Time Update

When the customer later provides an arrival date or time, the operator should:

1. Locate the existing ASN by inbound order number, container/tracking number, and customer.
2. Verify that the update belongs to the existing ASN. Do not create another ASN or Pack List.
3. Update the ASN `expected_arrival_at` value in the warehouse local timezone.
4. Keep the ASN in `Pre Arrival` and keep any reserved staging positions in `Reserved`.
5. Confirm that the planned staging capacity is still available and adjust the reservation if the load quantity changed.
6. Use the updated ETA to schedule the forklift/AGV and prepare the unloading instruction.

Updating ETA is a planning action only. It must not create inventory, change received quantity, occupy staging positions, or start the receiving workflow.

The dashboard should change from `ETA: Not Provided` to the supplied ETA while the work status remains `Pending` until the vehicle actually arrives.

### 4. Confirm Physical Arrival

Physical arrival is a separate operator action:

- Confirm the vehicle, container, and ASN at the dock.
- Record the actual arrival time.
- Confirm or adjust the reserved Stage-left/Stage-right positions.
- Record the actual arrival first. The ASN remains `Pre Arrival` until the operator starts the unloading step.
- When unloading starts, change the ASN to `Unloading` and keep the reserved positions reserved until goods are physically placed there.
- Change the relevant staging assignments from `Reserved` to `Occupied` only when goods are physically placed there.

If the vehicle arrives without a prior ETA, the operator may still start this step. The ETA remains unknown unless the customer provides one; actual arrival time is recorded separately.

### 5. Receive and Inspect

- Scan the goods and serial numbers when available.
- Compare actual SKU and quantity against the confirmed Pack List.
- Record shortage, overage, wrong SKU, damage, and SN exceptions.
- Attach photo/video references to the receiving or QC record.
- Keep goods in the active staging positions until QC and putaway are complete.

### 6. Put Away

- Assign final storage zones and bins after the received quantity and physical dimensions are verified.
- Move the ASN to `Putaway`.
- Release the staging assignments only after the goods leave the staging area.
- Complete the ASN after all accepted goods have been put away or exceptions have been resolved.

## Current System Fit

The current system already supports Pack List documents, optional ETA, the `Pre Arrival` state, and `Reserved / Occupied / Released` staging assignment states. The current dashboard correctly shows `Not Provided` when ETA is absent.

The workflow is implemented in the current system:

- `Update ETA` records the new ETA, source, operator, and receipt time without changing inventory or ASN status.
- `Reserve` holds Stage-left/Stage-right capacity as `Reserved`; it does not occupy the locations.
- `Mark Arrived` records the actual arrival timestamp separately from ETA.
- `Start Unloading` is blocked until physical arrival is confirmed and uses package/load-unit quantity for staging allocation.
- ASN lists and the operations dashboard show `Reserved` versus `Occupied` staging counts.
- Container/tracking references prevent a second active ASN from being created for the same load.
- ETA, arrival, and staging reservation events are available through the ASN event history endpoint.
