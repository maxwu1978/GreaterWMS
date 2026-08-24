# WebSocket Protocol Documentation

Real-time communication protocols for the WMS scanner and AGV dispatch subsystems.

## Endpoints

| Endpoint | Path | Purpose |
|----------|------|---------|
| Scanner | `/ws/scanner` | Barcode scanning feedback for receiving/putaway/picking |
| AGV Dispatch | `/ws/agv` | AGV fleet coordination, task dispatch, position tracking |

---

## 1. Scanner WebSocket (`/ws/scanner`)

**File:** `backend/app/websocket/scanner.py`
**Client:** `frontend/src/shared/hooks/useWebSocket.ts` → `useScannerSocket()`

### Connection Lifecycle

```
Client                                Server
  │                                      │
  │──── Connect /ws/scanner ────────────▶│
  │                                      │
  │──── {"token": "<JWT>"} ──────���─────▶│  (first message = auth)
  │                                      │
  │◀─── {"status":"authenticated",  ────│
  │       "user":"<user_id>"}            │
  │                                      │
  │──── {"action":"scan",...} ──────────▶│  (operational messages)
  │◀─── {"status":"ok","type":...} ─────│
  │                                      │
  │───��� {"action":"ping"} ─────────────▶│  (keep-alive)
  │◀─── {"status":"pong"} ─────────────│
  │                                      │
  │──── [disconnect] ──────────────────▶│
```

### Authentication

- **Method:** JWT token sent as first message (not header/query param)
- **Request:** `{"token": "<JWT_TOKEN>"}`
- **Success:** `{"status": "authenticated", "user": "<user_id>"}`
- **Failure:** `{"status": "error", "message": "Invalid token"}` + close code `4001`

### Client → Server Messages

#### Scan Request
```json
{
  "action": "scan",
  "barcode": "<barcode_string>",
  "context": "receiving|putaway|picking"
}
```

#### Keep-Alive
```json
{
  "action": "ping"
}
```

### Server → Client Messages

#### Scan Result - Location Match
```json
{
  "status": "ok",
  "type": "location",
  "data": {
    "id": "<location_uuid>",
    "barcode": "<location_barcode>",
    "address": "<aisle>-<rack>-<level>-<position>",
    "status": "<location_current_status>",
    "type": "<location_type>",
    "agv_accessible": true
  }
}
```

#### Scan Result - SKU Match
```json
{
  "status": "ok",
  "type": "sku",
  "data": {
    "id": "<sku_uuid>",
    "sku_code": "<sku_code>",
    "name": "<sku_name>",
    "barcode": "<sku_barcode>",
    "total_on_hand": 150,
    "locations": 3
  }
}
```

#### Scan Result - Not Found
```json
{
  "status": "not_found",
  "barcode": "<scanned_barcode>",
  "message": "Barcode not recognized"
}
```

#### Pong
```json
{"status": "pong"}
```

#### Error
```json
{"status": "error", "message": "<error_message>"}
```

### Barcode Lookup Logic

1. Match against `Location.barcode` (warehouse addresses)
2. If no match → try `SKU.barcode` (UPC/EAN)
3. If no match → try `SKU.sku_code` (alternative identifier)
4. If still no match → return `not_found`
5. For SKU matches: includes inventory summary (total qty + location count)

### Client-Side Implementation

```typescript
// frontend/src/shared/hooks/useWebSocket.ts
const { connected, lastResult, sendScan } = useScannerSocket();

// Send a scan
sendScan("LOC-A01-R02-L3-P1", "putaway");

// React to results
useEffect(() => {
  if (lastResult?.type === "location") {
    // Handle location scan
  }
}, [lastResult]);
```

**Notes:**
- Auto-detects ws:// vs wss:// based on page protocol
- URL: `${protocol}//${window.location.host}/ws/scanner`
- No auto-reconnect (reconnects on page reload)
- Used by: `ReceivingFlow.tsx`, `PickingFlow.tsx`

---

## 2. AGV Dispatch WebSocket (`/ws/agv`)

**File:** `backend/app/websocket/agv_dispatch.py`

### Connection Lifecycle

```
AGV Unit                              Server
  │                                      │
  │──── Connect /ws/agv ──────────────���▶│
  │                                      │
  │──── {"token":"<JWT>",  ───────���────▶│  (auth + register)
  │       "unit_id":"agv-001"}           │
  │                                      │
  │◀─── {"type":"connected",  ──────────│
  │       "unit_id":"agv-001"}           │
  │                                      │
  │◀─── {"type":"fleet_status",...} ────│  (broadcast to all units)
  │                                      │
  │──── {"type":"position",...} ────────▶│  (position updates)
  │──── {"type":"status",...} ──────────▶│  (status changes)
  │──── {"type":"heartbeat"} ──────────▶│  (keep-alive)
  │◀─── {"type":"heartbeat_ack"} ──────│
  │                                      │
  │◀─── {"type":"new_task",...} ────────│  (task dispatch)
  │                                      │
  │──── [disconnect] ────────────���─────▶│
  │                                      │  (broadcasts updated fleet_status)
```

### Authentication

- **Method:** JWT token + unit_id in first message
- **Request:** `{"token": "<JWT_TOKEN>", "unit_id": "<agv_unit_identifier>"}`
- **Success:** `{"type": "connected", "unit_id": "<unit_id>"}`
- **Failure:** `{"type": "error", "message": "Invalid token"}` + close code `4001`
- **Tenant extraction:** `tenant_id` from JWT claims

### AGV → Server Messages

#### Position Update
```json
{
  "type": "position",
  "x": 10.5,
  "y": 8.2,
  "z": 0.0
}
```

#### Status Change
```json
{
  "type": "status",
  "status": "idle|moving|loading|charging|error"
}
```

#### Heartbeat
```json
{
  "type": "heartbeat"
}
```

### Server → AGV Messages

#### Connection Confirmation
```json
{
  "type": "connected",
  "unit_id": "agv-001"
}
```

#### Heartbeat Acknowledgement
```json
{"type": "heartbeat_ack"}
```

#### Fleet Status Broadcast
Sent to ALL connected AGVs of the same tenant when any unit connects/disconnects:
```json
{
  "type": "fleet_status",
  "units": [
    {
      "unit_id": "agv-001",
      "position": {"x": 10.5, "y": 8.2, "z": 0.0},
      "status": "idle",
      "connected_at": "2026-05-05T07:51:00Z",
      "last_heartbeat": "2026-05-05T07:51:30Z"
    },
    {
      "unit_id": "agv-002",
      "position": {"x": 5.0, "y": 12.1, "z": 0.0},
      "status": "moving",
      "connected_at": "2026-05-05T07:45:00Z",
      "last_heartbeat": "2026-05-05T07:51:28Z"
    }
  ]
}
```

#### New Task Assignment
```json
{
  "type": "new_task",
  "task": {
    "id": "<task_uuid>",
    "type": "PUTAWAY|PICKING",
    "from_location": {"x": 1.0, "y": 2.0, "barcode": "LOC-A01"},
    "to_location": {"x": 5.0, "y": 8.0, "barcode": "LOC-B03"},
    "sku_code": "SKU-12345",
    "quantity": 10
  }
}
```

### Fleet Manager (Server-Side)

`AGVFleetManager` maintains connection state per tenant:

```python
{
  tenant_id: {
    unit_id: {
      "websocket": WebSocket,
      "position": {"x": 0, "y": 0, "z": 0},
      "status": "idle",
      "connected_at": "ISO8601",
      "last_heartbeat": "ISO8601"
    }
  }
}
```

**Methods:**
- `connect(ws, tenant_id, unit_id)` — register new AGV connection
- `disconnect(tenant_id, unit_id)` — unregister on disconnect
- `broadcast_to_tenant(tenant_id, message)` — send to all tenant AGVs
- `send_to_unit(tenant_id, unit_id, message)` — target specific AGV

### Multi-Tenancy

- Each AGV connection is scoped to a tenant via JWT `tenant_id` claim
- Fleet status broadcasts only go to AGVs of the same tenant
- No cross-tenant visibility

---

## Protocol Notes

### Keep-Alive Strategy
- **Recommended interval:** 30 seconds (Render proxy timeout is 60s for idle)
- Scanner: `{"action": "ping"}` → `{"status": "pong"}`
- AGV: `{"type": "heartbeat"}` → `{"type": "heartbeat_ack"}`

### Error Codes
| Close Code | Meaning |
|-----------|---------|
| `4001` | Authentication failure |
| `1000` | Normal close |
| `1001` | Going away (server shutdown) |

### Reconnection
- Scanner client: no auto-reconnect (page reload required)
- AGV client: should implement exponential backoff reconnection
