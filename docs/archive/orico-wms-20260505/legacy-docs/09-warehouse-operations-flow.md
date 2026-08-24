# Warehouse Operations Flow

End-to-end business process documentation for WMS QuickStart.

## Overview

```
ASN/PO ──▶ RECEIVING ──▶ PUTAWAY ──▶ STORAGE
                                        │
CUSTOMER ORDER ──▶ ALLOCATION ──▶ PICKING ──▶ PACKING ──▶ SHIPPING
                                        │
                              CYCLE COUNT (periodic)
                                        │
RETURN REQUEST ──▶ RETURNS ──▶ INSPECTION ──▶ PUTAWAY/DISPOSE
```

## 1. Receiving (收货)

### Trigger
- Inbound Order (ASN/PO) created via API, CSV import, or Shopify webhook

### Flow
```
1. InboundOrder created (status: CREATED)
2. Goods arrive → operator scans/confirms arrival (status: ARRIVED)
3. System generates ReceivingLabels (one per line item or handling unit)
4. Operator scans label → records:
   - Actual quantity received
   - Measurements (weight, dimensions) [optional]
   - Condition/notes
   - Discrepancy flag (if qty mismatch)
5. Good units → inventory accepted into STAGING location
6. Damaged units → flagged, separate handling
7. All lines processed → order status: COMPLETED
```

### Key Models
- `InboundOrder` → `InboundOrderLine` → `ReceivingLabel`
- `InventoryTransaction` (type: RECEIVE) created per acceptance
- `Task` (type: RECEIVING) assigned to operator or AGV

### State Machine
```
InboundOrder: CREATED → ARRIVED → IN_PROGRESS → COMPLETED
```

---

## 2. Putaway (上架)

### Trigger
- Receiving completed → goods in STAGING location need permanent storage

### Flow
```
1. Task (type: PUTAWAY) created automatically after receiving
2. System suggests destination location(s) via PutawayService:
   - Zone affinity rules (e.g., flammable → hazmat zone)
   - Aisle mode preference
   - Available capacity
   - SKU velocity / pick frequency
3. Operator reviews suggestion:
   - Accept suggested location
   - Split to multiple destinations (partial quantities)
   - Override with manual location
4. Operator moves goods and scans destination barcode
5. Inventory transferred: STAGING → destination location
6. Task completed
```

### Location Suggestion Logic
- Rule-based: `InventoryRulesService` defines zone/location type preferences per SKU
- Capacity-aware: checks location current fill vs max capacity
- Consolidation: prefers locations that already hold the same SKU

### Split-Destination Planning
- Large receipts can be split across multiple locations
- Operator allocates quantities per destination
- Each split creates a separate inventory movement

---

## 3. Picking (拣货)

### Trigger
- Outbound Order allocated → pick tasks generated

### Flow
```
1. OutboundOrder created (status: CREATED)
2. Allocation runs (manual or wave-based):
   - FIFO inventory selection (oldest stock first)
   - Checks available quantity per location
   - Creates pick tasks with source location + qty
3. Tasks assigned to operator or AGV (status: ASSIGNED)
4. Operator navigates to source location
5. Scans location barcode → confirms pick
6. Picks quantity → scans item barcode
7. Places in cart/tote → moves to packing station
8. Task completed → inventory decremented
```

### Wave Management
- Multiple orders grouped into a wave for efficiency
- Wave tasks assigned together (batch picking)
- `TaskType.PICKING` with `AssignedType.WAVE`

### Allocation Strategy
- FIFO by default (earliest received inventory first)
- Respects lot/batch boundaries
- Skips locations with insufficient quantity
- Creates multiple pick tasks if order spans locations

---

## 4. Packing (打包)

### Trigger
- All pick tasks for an order completed

### Flow
```
1. Order arrives at packing station
2. Operator scans order/tote barcode
3. Verifies items against order lines:
   - Scan each item barcode
   - System confirms match / flags mismatch
4. Selects packaging type
5. Records package weight/dimensions
6. System generates shipping label
7. Order status: PACKED
```

---

## 5. Shipping (发货)

### Trigger
- Order packed and shipping label generated

### Flow
```
1. Shipping label printed (via ShippingLabelService)
2. Package placed in carrier staging area
3. Carrier pickup confirmed
4. Tracking number recorded
5. Order status: SHIPPED
6. Customer notification triggered
```

### State Machine
```
OutboundOrder: CREATED → ALLOCATED → PICKED → PACKED → SHIPPED
```

---

## 6. Cycle Count (盘点)

### Trigger
- Scheduled (periodic) or triggered by discrepancy

### Flow
```
1. CycleCount created for target locations/SKUs
2. Tasks (type: CYCLE_COUNT) assigned to operators
3. Operator physically counts items at location
4. Records counted quantity in system
5. System compares: counted vs expected
6. If match → confirmed, no action
7. If mismatch → adjustment transaction created:
   - InventoryTransaction (type: ADJUSTMENT)
   - Supervisor approval may be required
8. Count task completed
```

---

## 7. Returns (退货)

### Trigger
- Return Request created (customer-initiated or CS-created)

### Flow
```
1. ReturnOrder created (linked to original OutboundOrder)
2. Return arrives → operator scans return label
3. Inspection:
   - Good condition → return to inventory (PUTAWAY flow)
   - Damaged → quarantine / dispose
4. Inventory adjusted accordingly
5. Refund/credit triggered (external system)
6. ReturnOrder completed
```

---

## 8. AGV Integration

### How AGV fits into flows
- AGV can execute PUTAWAY and PICKING tasks (instead of human)
- Task assigned with `assigned_type = AGV`
- AGV receives task via WebSocket dispatch
- Reports progress: navigating → arrived → executing → completed
- Location coordinates used for path planning

### Task Assignment Decision
```
TaskAssignmentService evaluates:
1. Is location AGV-accessible? (location.agv_accessible flag)
2. Is AGV available? (check current AGV task queue)
3. Weight/dimensions within AGV capacity?
→ If yes to all: assign to AGV
→ Otherwise: assign to human operator
```

---

## Key Business Rules

1. **FIFO enforcement**: Oldest inventory picked first (regulatory compliance)
2. **Location capacity**: Cannot putaway beyond location max capacity
3. **Tenant isolation**: All operations scoped to tenant_id via RLS
4. **Discrepancy handling**: Receiving mismatches flagged, not auto-resolved
5. **Task atomicity**: Each task = one movement; complex flows decompose into task chains
6. **Audit trail**: Every inventory change creates an `InventoryTransaction` record
