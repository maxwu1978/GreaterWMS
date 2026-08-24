"""
AGV Fleet WebSocket — real-time bidirectional communication with AGV units.

Provides:
- Live task dispatch (push new tasks to AGVs instead of polling)
- Real-time position reporting from AGVs
- Fleet status dashboard feed
- Emergency stop broadcast

Protocol:
  AGV → Server: {"type": "position", "unit_id": "agv-003", "x": 12.5, "y": 8.3}
  AGV → Server: {"type": "task_update", "task_id": "...", "status": "completed"}
  Server → AGV: {"type": "new_task", "task": {...}}
  Server → All: {"type": "fleet_status", "units": [...]}
"""

import contextlib
import json
from datetime import UTC, datetime

from fastapi import WebSocket, WebSocketDisconnect

from app.core.security import verify_token


class AGVFleetManager:
    """Manages WebSocket connections from AGV units."""

    def __init__(self):
        # {tenant_id: {unit_id: {"websocket": ws, "position": {}, "status": "..."}}}
        self.connections: dict[str, dict[str, dict]] = {}

    async def connect(self, websocket: WebSocket, tenant_id: str, unit_id: str):
        await websocket.accept()
        if tenant_id not in self.connections:
            self.connections[tenant_id] = {}
        self.connections[tenant_id][unit_id] = {
            "websocket": websocket,
            "position": {"x": 0, "y": 0, "z": 0},
            "status": "idle",
            "connected_at": datetime.now(UTC).isoformat(),
            "last_heartbeat": datetime.now(UTC).isoformat(),
        }

    def disconnect(self, tenant_id: str, unit_id: str):
        if tenant_id in self.connections:
            self.connections[tenant_id].pop(unit_id, None)

    async def broadcast_to_tenant(self, tenant_id: str, message: dict):
        """Send a message to all AGV units of a tenant."""
        if tenant_id not in self.connections:
            return
        for _unit_id, conn in self.connections[tenant_id].items():
            with contextlib.suppress(Exception):
                await conn["websocket"].send_json(message)

    async def send_to_unit(self, tenant_id: str, unit_id: str, message: dict):
        """Send a message to a specific AGV unit."""
        conn = self.connections.get(tenant_id, {}).get(unit_id)
        if conn:
            await conn["websocket"].send_json(message)

    def get_fleet_status(self, tenant_id: str) -> list[dict]:
        """Get current status of all connected AGV units."""
        if tenant_id not in self.connections:
            return []
        return [
            {
                "unit_id": uid,
                "position": conn["position"],
                "status": conn["status"],
                "connected_at": conn["connected_at"],
                "last_heartbeat": conn["last_heartbeat"],
            }
            for uid, conn in self.connections[tenant_id].items()
        ]


# Global fleet manager instance
fleet_manager = AGVFleetManager()


async def agv_websocket(websocket: WebSocket):
    """
    WebSocket handler for AGV units.

    Auth: first message {"token": "jwt...", "unit_id": "agv-003"}
    Then: bidirectional JSON messages
    """
    await websocket.accept()

    # Authenticate
    try:
        auth_msg = await websocket.receive_text()
        auth_data = json.loads(auth_msg)
        token_data = verify_token(auth_data.get("token", ""))
        if not token_data:
            await websocket.send_json({"type": "error", "message": "Invalid token"})
            await websocket.close(code=4001)
            return
        tenant_id = token_data.tenant_id
        unit_id = auth_data.get("unit_id", "unknown")
    except (json.JSONDecodeError, KeyError):
        await websocket.close(code=4001)
        return

    # Register connection
    await fleet_manager.connect(websocket, tenant_id, unit_id)
    await websocket.send_json({"type": "connected", "unit_id": unit_id})

    # Broadcast updated fleet status
    await fleet_manager.broadcast_to_tenant(
        tenant_id,
        {
            "type": "fleet_status",
            "units": fleet_manager.get_fleet_status(tenant_id),
        },
    )

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "position":
                # AGV reporting its position
                conn = fleet_manager.connections.get(tenant_id, {}).get(unit_id)
                if conn:
                    conn["position"] = {
                        "x": data.get("x", 0),
                        "y": data.get("y", 0),
                        "z": data.get("z", 0),
                    }
                    conn["last_heartbeat"] = datetime.now(UTC).isoformat()

            elif msg_type == "status":
                # AGV reporting status change (idle, moving, loading, charging, error)
                conn = fleet_manager.connections.get(tenant_id, {}).get(unit_id)
                if conn:
                    conn["status"] = data.get("status", "unknown")

            elif msg_type == "heartbeat":
                conn = fleet_manager.connections.get(tenant_id, {}).get(unit_id)
                if conn:
                    conn["last_heartbeat"] = datetime.now(UTC).isoformat()
                await websocket.send_json({"type": "heartbeat_ack"})

    except WebSocketDisconnect:
        fleet_manager.disconnect(tenant_id, unit_id)
        # Broadcast disconnect
        await fleet_manager.broadcast_to_tenant(
            tenant_id,
            {
                "type": "fleet_status",
                "units": fleet_manager.get_fleet_status(tenant_id),
            },
        )
