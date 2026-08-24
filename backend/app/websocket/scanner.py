"""
WebSocket endpoint for real-time barcode scanning feedback.

Mobile devices connect via WebSocket to get instant confirmation
when scanning barcodes during receiving, putaway, and picking.

Protocol:
  Client sends: {"action": "scan", "barcode": "A-01-03-02-01", "context": "putaway"}
  Server responds: {"status": "ok", "type": "location", "data": {...}} or {"status": "error", ...}
"""

import json

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.database import apply_session_context, async_session_factory
from app.core.security import verify_token
from app.models.inventory import SKU, Inventory
from app.models.warehouse import Location


async def scanner_websocket(websocket: WebSocket):
    """
    WebSocket handler for barcode scanner devices.

    Authentication: first message must be {"token": "jwt..."}
    Then: {"action": "scan", "barcode": "...", "context": "receiving|putaway|picking"}
    """
    await websocket.accept()

    # Authenticate
    try:
        auth_msg = await websocket.receive_text()
        auth_data = json.loads(auth_msg)
        token_data = verify_token(auth_data.get("token", ""))
        if not token_data:
            await websocket.send_json({"status": "error", "message": "Invalid token"})
            await websocket.close(code=4001)
            return
        tenant_id = token_data.tenant_id
        if not tenant_id:
            await websocket.send_json({"status": "error", "message": "Tenant context required"})
            await websocket.close(code=4001)
            return
    except (json.JSONDecodeError, KeyError):
        await websocket.send_json({"status": "error", "message": 'Send {"token": "..."} first'})
        await websocket.close(code=4001)
        return

    await websocket.send_json({"status": "authenticated", "user": token_data.sub})

    # Main scan loop
    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            action = data.get("action")

            if action == "scan":
                barcode = data.get("barcode", "").strip()
                context = data.get("context", "")
                result = await _process_scan(tenant_id, barcode, context)
                await websocket.send_json(result)

            elif action == "ping":
                await websocket.send_json({"status": "pong"})

            else:
                await websocket.send_json(
                    {"status": "error", "message": f"Unknown action: {action}"}
                )

    except WebSocketDisconnect:
        pass
    except json.JSONDecodeError:
        await websocket.send_json({"status": "error", "message": "Invalid JSON"})


async def _process_scan(tenant_id: str, barcode: str, context: str) -> dict:
    """Look up a barcode and return relevant info based on scan context."""
    async with async_session_factory() as db:
        await apply_session_context(db, tenant_id=tenant_id)
        # Try as location barcode
        loc_result = await db.execute(
            select(Location).where(
                Location.tenant_id == tenant_id,
                Location.barcode == barcode,
            )
        )
        location = loc_result.scalar_one_or_none()
        if location:
            return {
                "status": "ok",
                "type": "location",
                "data": {
                    "id": location.id,
                    "barcode": location.barcode,
                    "address": f"{location.aisle}-{location.rack}-{location.level}-{location.position}",
                    "status": location.current_status,
                    "type": location.location_type,
                    "agv_accessible": location.is_agv_accessible,
                },
            }

        # Try as SKU barcode
        sku_result = await db.execute(
            select(SKU).where(
                SKU.tenant_id == tenant_id,
                SKU.barcode == barcode,
            )
        )
        sku = sku_result.scalar_one_or_none()
        if not sku:
            # Also try sku_code
            sku_result = await db.execute(
                select(SKU).where(
                    SKU.tenant_id == tenant_id,
                    SKU.sku_code == barcode,
                )
            )
            sku = sku_result.scalar_one_or_none()

        if sku:
            # Get inventory summary for this SKU
            inv_result = await db.execute(
                select(Inventory).where(
                    Inventory.tenant_id == tenant_id,
                    Inventory.sku_id == sku.id,
                    Inventory.quantity_on_hand > 0,
                )
            )
            inventories = inv_result.scalars().all()
            total_qty = sum(inv.quantity_on_hand for inv in inventories)

            return {
                "status": "ok",
                "type": "sku",
                "data": {
                    "id": sku.id,
                    "sku_code": sku.sku_code,
                    "name": sku.name,
                    "barcode": sku.barcode,
                    "total_on_hand": total_qty,
                    "locations": len(inventories),
                },
            }

        return {"status": "not_found", "barcode": barcode, "message": "Barcode not recognized"}
