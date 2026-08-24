"""
Inventory ledger gateway — the single door for stock movements.

Every change to Inventory quantities must go through ``post_movement`` so the
quantity mutation and its matching ``InventoryTransaction`` ledger row are
created together. This makes "stock change ⇒ ledger row" a structural
guarantee instead of a convention each service has to remember.

The gateway is deliberately mechanical: it applies exactly the deltas the
caller computed and writes exactly the transaction fields the caller supplies.
Business validation (negative-stock checks, allocation caps, …) stays at the
call sites, which own their own rules.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory, InventoryTransaction


@dataclass(frozen=True)
class StockDelta:
    """A quantity adjustment to apply to one Inventory row."""

    inventory: Inventory
    on_hand: int = 0
    allocated: int = 0
    damaged: int = 0


def ensure_inventory(
    db: AsyncSession,
    existing: Inventory | None,
    *,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    location_id: str,
    sku_id: str,
    lpn: str | None = None,
    lot_number: str | None = None,
    expiry_date: datetime | None = None,
    received_at: datetime | None = None,
) -> Inventory:
    """
    Return ``existing`` if present, otherwise create an empty Inventory row.

    The new row starts at zero quantity; the caller applies the actual
    quantity through ``post_movement`` so the ledger row is guaranteed.
    """
    if existing is not None:
        return existing
    inventory = Inventory(
        tenant_id=tenant_id,
        client_id=client_id,
        warehouse_id=warehouse_id,
        location_id=location_id,
        sku_id=sku_id,
        lpn=lpn,
        lot_number=lot_number,
        expiry_date=expiry_date,
        received_at=received_at,
        quantity_on_hand=0,
    )
    db.add(inventory)
    return inventory


def _apply(inventory: Inventory, on_hand: int, allocated: int, damaged: int) -> None:
    if on_hand:
        inventory.quantity_on_hand += on_hand
    if allocated:
        inventory.quantity_allocated += allocated
    if damaged:
        inventory.quantity_damaged += damaged


async def post_movement(
    db: AsyncSession,
    *,
    tenant_id: str,
    client_id: str,
    transaction_type: str,
    sku_id: str,
    location_id: str,
    quantity_change: int,
    inventory: Inventory | None = None,
    delta_on_hand: int = 0,
    delta_allocated: int = 0,
    delta_damaged: int = 0,
    extra_deltas: Sequence[StockDelta] = (),
    from_location_id: str | None = None,
    to_location_id: str | None = None,
    reference_type: str | None = None,
    reference_id: str | None = None,
    performed_by: str | None = None,
    performed_at: datetime | None = None,
    lot_number: str | None = None,
    notes: str | None = None,
    flush: bool = True,
) -> InventoryTransaction:
    """
    Apply quantity deltas to Inventory row(s) and append the ledger row.

    - ``inventory`` + ``delta_*`` adjust the primary row the movement is
      about. Ledger-only movements (e.g. AGV completion reports, ship
      confirmations whose stock was already deducted at pick) pass no
      inventory and no deltas.
    - ``extra_deltas`` covers movements that touch more than one Inventory
      row under a single transaction (moves, multi-row cycle counts).
    - ``performed_at`` defaults to now (UTC).
    - ``flush=False`` lets call sites that batch several movements keep
      their single flush at the end of the unit of work.
    """
    if inventory is not None:
        _apply(inventory, delta_on_hand, delta_allocated, delta_damaged)
    elif delta_on_hand or delta_allocated or delta_damaged:
        raise ValueError("post_movement received quantity deltas without an inventory row")

    for delta in extra_deltas:
        _apply(delta.inventory, delta.on_hand, delta.allocated, delta.damaged)

    txn = InventoryTransaction(
        tenant_id=tenant_id,
        client_id=client_id,
        transaction_type=transaction_type,
        sku_id=sku_id,
        location_id=location_id,
        quantity_change=quantity_change,
        from_location_id=from_location_id,
        to_location_id=to_location_id,
        reference_type=reference_type,
        reference_id=reference_id,
        performed_by=performed_by,
        performed_at=performed_at or datetime.now(UTC),
        lot_number=lot_number,
        notes=notes,
    )
    db.add(txn)
    if flush:
        await db.flush()
    return txn
