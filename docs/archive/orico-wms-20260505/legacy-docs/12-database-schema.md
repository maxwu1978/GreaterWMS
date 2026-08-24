# Database Schema & ERD

Complete data model documentation for WMS QuickStart.

## Base Patterns

All models follow these conventions:
- **Primary Key**: UUID string (36 chars) via `generate_uuid()`
- **Timestamps**: `created_at`, `updated_at` (datetime with timezone) from `TimestampMixin`
- **Multi-Tenancy**: `tenant_id` column (indexed) from `TenantMixin`
- **JSON Fields**: Dialect-aware `JsonType` (JSONB on PostgreSQL, JSON on SQLite)

---

## Entity Relationship Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         TENANT                                    │
│  (id, name, code, subdomain, plan_tier, is_active)               │
└───────┬──────────┬──────────┬───────────────┬────────────────────┘
        │          │          │               │
        ▼          ▼          ▼               ▼
┌───────���──┐ ┌─────────┐ ┌──────────┐ ┌──────────────┐
│   USER   │ │  CLIENT │ │WAREHOUSE │ │ SUBSCRIPTION │
└──────────┘ └────┬────┘ └────┬─────┘ └──────────────┘
                   │           │
                   ▼           ▼
              ┌────────┐  ┌────────┐
              │  SKU   │  │  ZONE  │
              └───┬────┘  ��───┬────┘
                  │           │
                  │           ▼
                  │      ┌──────────┐
                  │      │ LOCATION │
                  │      └────┬─────┘
                  │           │
                  ▼           ▼
             ┌─────────────────────┐
             │     INVENTORY       │
             │ (sku_id, location_id)│
             └──────────┬──────────┘
                        │
                        ▼
             ┌──────────��──────────┐
             │INVENTORY_TRANSACTION │
             │   (audit ledger)     │
             └─────────────────────┘

┌───────────────────────────────────────────────────┐
│                  ORDER FLOW                         │
│                                                    │
│  INBOUND_ORDER ──▶ INBOUND_ORDER_LINE             │
│       │                    │                       │
│       └──────▶ RECEIVING_LABEL                     │
��                                                    │
│  OUTBOUND_ORDER ──▶ OUTBOUND_ORDER_LINE           │
│                                                    │
│  RETURN_ORDER ──▶ RETURN_ORDER_LINE               │
└───────────────────────────────────���───────────────┘

┌���──────────────────────────────────────────────────┐
│                   TASK SYSTEM                       │
│                                                    │
│  TASK (unified: RECEIVING/PUTAWAY/PICKING/...)    │
│       │                                            │
│       └──▶ PUTAWAY_ALLOCATION                     │
└───────────────────────────────────────────────────┘

���───────────────────────────────────────────────────┐
│                   BILLING                           │
│                                                    │
│  RATE_CARD ──▶ BILLING_PERIOD ──▶ BILLING_LINE   │
│                       │                            │
│                       └──▶ INVOICE                 │
└──��────────────────────────────────────────────────┘
```

---

## Model Details

### Tenant Management

#### `tenants`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| name | String(200) | NOT NULL | Company name |
| code | String(50) | UNIQUE, NOT NULL | URL-safe identifier |
| subdomain | String(63) | UNIQUE | tenant.wmsquickstart.com |
| contact_email | String(254) | NOT NULL | Primary contact |
| contact_phone | String(20) | | |
| address | JSON | | Structured address |
| plan_tier | String(20) | default: "starter" | starter/growth/enterprise |
| is_active | Boolean | default: true | |
| settings | JSON | | Tenant-specific config |
| created_at | DateTime | | |
| updated_at | DateTime | | |

**Relationships:** → users (1:N), → clients (1:N), → warehouses (1:N)

#### `users`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| tenant_id | UUID | FK(tenants), indexed | |
| email | String(254) | NOT NULL | |
| hashed_password | Text | NOT NULL | bcrypt hash |
| full_name | String(200) | NOT NULL | |
| role | String(20) | NOT NULL | UserRole enum value |
| job_title | String(120) | | |
| permissions | JSON | | Array of permission strings |
| client_id | String(36) | | For client_viewer role only |
| is_active | Boolean | default: true | |
| is_email_verified | Boolean | default: true | |
| email_verification_token | String(128) | | |
| password_reset_token | String(128) | | |
| created_at | DateTime | | |
| updated_at | DateTime | | |

**Roles:** `platform_admin`, `tenant_admin`, `operator`, `client_viewer`

---

### Warehouse Infrastructure

#### `warehouses`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| tenant_id | UUID | FK(tenants), indexed | |
| name | String(200) | NOT NULL | |
| code | String(20) | NOT NULL | |
| address | JSON | | |
| timezone | String(50) | default: "America/Chicago" | |
| is_active | Boolean | default: true | |

**Relationships:** → zones (1:N)

#### `zones`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| warehouse_id | UUID | FK(warehouses) | |
| tenant_id | UUID | indexed | |
| name | String(100) | NOT NULL | |
| code | String(20) | NOT NULL | |
| is_agv_zone | Boolean | default: false | AGV-accessible zone |
| sequence | Integer | default: 0 | Pick path ordering |

**Relationships:** → locations (1:N)

#### `locations`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| warehouse_id | UUID | FK(warehouses) | |
| zone_id | UUID | FK(zones) | |
| tenant_id | UUID | indexed | |
| barcode | String(50) | NOT NULL | Scannable unique code |
| aisle | String(10) | NOT NULL | |
| rack | String(10) | NOT NULL | |
| level | String(10) | NOT NULL | |
| position | String(10) | NOT NULL | |
| coordinate_x | Numeric(10,3) | | AGV navigation |
| coordinate_y | Numeric(10,3) | | AGV navigation |
| coordinate_z | Numeric(10,3) | | AGV navigation |
| is_agv_accessible | Boolean | default: false | |
| location_type | String(20) | | STORAGE/STAGING/DOCK/RETURN/PACKING |
| current_status | String(20) | | AVAILABLE/OCCUPIED/RESERVED/BLOCKED |
| max_weight_kg | Numeric(10,2) | | |
| max_volume_m3 | Numeric(10,4) | | |
| pick_sequence | Integer | default: 0 | |

---

### Inventory

#### `skus`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| client_id | UUID | FK(clients), indexed | |
| tenant_id | UUID | indexed | |
| sku_code | String(100) | NOT NULL | Client product code |
| barcode | String(100) | | UPC/EAN |
| name | String(300) | NOT NULL | |
| description | Text | | |
| weight_kg | Numeric(10,3) | | |
| length_cm | Numeric(10,2) | | |
| width_cm | Numeric(10,2) | | |
| height_cm | Numeric(10,2) | | |
| requires_lot | Boolean | default: false | |
| requires_expiry | Boolean | default: false | FEFO tracking |
| is_hazmat | Boolean | default: false | |
| units_per_case | Integer | | |
| cases_per_pallet | Integer | | |
| attributes | JSON | | Custom fields |

#### `inventory`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| location_id | UUID | FK(locations), indexed | |
| sku_id | UUID | FK(skus), indexed | |
| tenant_id | UUID | indexed | |
| client_id | UUID | indexed | |
| warehouse_id | UUID | indexed | |
| lpn | String(50) | | License Plate Number |
| lot_number | String(100) | | |
| expiry_date | DateTime | | |
| received_at | DateTime | | |
| quantity_on_hand | Integer | default: 0 | |
| quantity_allocated | Integer | default: 0 | Reserved for orders |
| quantity_damaged | Integer | default: 0 | |

**Computed:** `quantity_available = on_hand - allocated - damaged`
**Index:** `(tenant_id, sku_id, location_id)` — primary lookup path

#### `inventory_transactions`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| tenant_id | UUID | indexed | |
| client_id | UUID | indexed | |
| transaction_type | String(20) | NOT NULL | See TransactionType enum |
| sku_id | String(36) | | |
| location_id | String(36) | | |
| quantity_change | Integer | NOT NULL | +in / -out |
| from_location_id | String(36) | | For moves |
| to_location_id | String(36) | | For moves |
| reference_type | String(50) | | 'inbound_order', 'outbound_order', etc. |
| reference_id | String(36) | | |
| performed_by | String(36) | | user_id or 'agv:{id}' |
| performed_at | DateTime | NOT NULL | |
| lot_number | String(100) | | |
| notes | Text | | |

**TransactionType enum:** `RECEIVE`, `PUTAWAY`, `PICK`, `PACK`, `SHIP`, `RETURN`, `ADJUST`, `DAMAGE`, `REPAIR`

**Note:** Immutable audit ledger — no updates/deletes, no TimestampMixin.

---

### Orders - Inbound

#### `inbound_orders`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| client_id | UUID | FK(clients), indexed | |
| warehouse_id | UUID | FK(warehouses) | |
| tenant_id | UUID | indexed | |
| order_number | String(50) | NOT NULL | |
| reference_number | String(100) | | Client's PO number |
| status | String(20) | | InboundStatus enum |
| expected_date | DateTime | | |
| received_date | DateTime | | |
| supplier_name | String(200) | | |
| notes | Text | | |
| extra_data | JSON | | |

**InboundStatus:** `DRAFT` → `EXPECTED` → `ARRIVED` → `RECEIVING` → `COMPLETED` / `CANCELLED`

#### `inbound_order_lines`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| order_id | UUID | FK(inbound_orders) | |
| sku_id | UUID | FK(skus) | |
| tenant_id | UUID | indexed | |
| quantity_expected | Integer | NOT NULL | |
| quantity_received | Integer | default: 0 | |
| quantity_damaged | Integer | default: 0 | |
| staging_location_id | String(36) | | |
| package_count | Integer | | |
| measured_weight_kg | Numeric(10,3) | | |
| measured_length_cm | Numeric(10,2) | | |
| measured_width_cm | Numeric(10,2) | | |
| measured_height_cm | Numeric(10,2) | | |
| receiving_note | Text | | |
| lot_number | String(100) | | |
| expiry_date | DateTime | | |

#### `receiving_labels`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| order_id | UUID | FK(inbound_orders), indexed | |
| order_line_id | UUID | FK(inbound_order_lines), indexed | |
| sku_id | UUID | FK(skus), indexed | |
| tenant_id | UUID | indexed | |
| label_code | String(120) | NOT NULL, indexed | Scannable barcode |
| label_type | String(20) | default: "line" | |
| expected_qty | Integer | NOT NULL | |
| received_qty | Integer | default: 0 | |
| status | String(20) | default: "pending" | |
| lot_number | String(100) | | |
| expiry_date | DateTime | | |
| printed_at | DateTime | | |
| received_at | DateTime | | |
| extra_data | JSON | | |

---

### Orders - Outbound

#### `outbound_orders`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| client_id | UUID | FK(clients), indexed | |
| warehouse_id | UUID | FK(warehouses) | |
| tenant_id | UUID | indexed | |
| order_number | String(50) | NOT NULL | |
| reference_number | String(100) | | |
| status | String(20) | | OutboundStatus enum |
| priority | Integer | default: 0 | |
| ship_by_date | DateTime | | |
| carrier | String(100) | | |
| tracking_number | String(200) | | |
| shipping_address | JSON | | |
| notes | Text | | |

**OutboundStatus:** `CREATED` → `ALLOCATED` → `PICKED` → `PACKED` → `SHIPPED` / `CANCELLED`

#### `outbound_order_lines`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| order_id | UUID | FK(outbound_orders) | |
| sku_id | UUID | FK(skus) | |
| tenant_id | UUID | indexed | |
| quantity_ordered | Integer | NOT NULL | |
| quantity_allocated | Integer | default: 0 | |
| quantity_picked | Integer | default: 0 | |
| quantity_shipped | Integer | default: 0 | |

---

### Task System

#### `tasks`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| tenant_id | UUID | indexed | |
| warehouse_id | UUID | | |
| task_type | String(20) | NOT NULL | TaskType enum |
| status | String(20) | NOT NULL | TaskStatus enum |
| priority | Integer | default: 0 | |
| assigned_type | String(10) | | USER/AGV/WAVE |
| assigned_to | String(36) | | user_id or agv_unit_id |
| order_id | String(36) | | Reference to inbound/outbound order |
| order_line_id | String(36) | | |
| sku_id | String(36) | | |
| from_location_id | String(36) | | |
| to_location_id | String(36) | | |
| quantity | Integer | | |
| started_at | DateTime | | |
| completed_at | DateTime | | |
| notes | Text | | |

**Index:** `(status, assigned_to)` — task queue queries
**TaskType:** `RECEIVING`, `PUTAWAY`, `PICKING`, `PACKING`, `SHIPPING`, `CYCLE_COUNT`, `REPLENISHMENT`
**TaskStatus:** `OPEN` → `ASSIGNED` → `IN_PROGRESS` → `COMPLETED` / `FAILED` / `CANCELLED`
**AssignedType:** `USER`, `AGV`, `WAVE`

#### `putaway_allocations`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| tenant_id | UUID | indexed | |
| task_id | UUID | FK(tasks) | |
| sku_id | UUID | | |
| from_location_id | UUID | | Staging source |
| to_location_id | UUID | | Destination |
| quantity | Integer | NOT NULL | |
| status | String(20) | | |

---

### Returns

#### `return_orders`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| tenant_id | UUID | indexed | |
| client_id | UUID | FK(clients) | |
| original_order_id | UUID | | Link to outbound order |
| return_number | String(50) | NOT NULL | |
| status | String(20) | | |
| reason | Text | | |
| notes | Text | | |

#### `return_order_lines`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| return_id | UUID | FK(return_orders) | |
| sku_id | UUID | FK(skus) | |
| tenant_id | UUID | indexed | |
| quantity_expected | Integer | NOT NULL | |
| quantity_received | Integer | default: 0 | |
| condition | String(20) | | good/damaged/defective |
| disposition | String(20) | | restock/quarantine/dispose |

---

### Kits

#### `kits`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| tenant_id | UUID | indexed | |
| client_id | UUID | FK(clients) | |
| sku_id | UUID | FK(skus) | The kit SKU itself |
| name | String(200) | NOT NULL | |
| is_active | Boolean | default: true | |

#### `kit_components`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| kit_id | UUID | FK(kits) | |
| component_sku_id | UUID | FK(skus) | |
| tenant_id | UUID | indexed | |
| quantity | Integer | NOT NULL | Per kit |

---

### Billing

#### `subscriptions`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| tenant_id | UUID | FK(tenants), indexed | |
| plan_tier | String(20) | NOT NULL | starter/growth/enterprise |
| status | String(20) | | trial/active/past_due/cancelled |
| trial_end_date | DateTime | | |
| current_period_start | DateTime | | |
| current_period_end | DateTime | | |
| stripe_customer_id | String(100) | | |
| stripe_subscription_id | String(100) | | |

#### `rate_cards`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| tenant_id | UUID | indexed | |
| client_id | UUID | FK(clients) | |
| name | String(200) | | |
| rates | JSON | | Structured pricing rules |
| is_active | Boolean | default: true | |

#### `billing_periods`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| tenant_id | UUID | indexed | |
| client_id | UUID | FK(clients) | |
| start_date | DateTime | NOT NULL | |
| end_date | DateTime | NOT NULL | |
| status | String(20) | | open/closed/invoiced |

#### `billing_line_items`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| billing_period_id | UUID | FK(billing_periods) | |
| tenant_id | UUID | indexed | |
| description | String(500) | | |
| quantity | Numeric | | |
| unit_price | Numeric | | |
| total | Numeric | | |
| category | String(50) | | storage/handling/shipping |

#### `invoices`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| tenant_id | UUID | indexed | |
| client_id | UUID | FK(clients) | |
| billing_period_id | UUID | FK(billing_periods) | |
| invoice_number | String(50) | NOT NULL | |
| total_amount | Numeric | | |
| status | String(20) | | draft/sent/paid/overdue |
| due_date | DateTime | | |
| paid_at | DateTime | | |

---

## Indexes Summary

| Table | Index | Columns |
|-------|-------|---------|
| inventory | lookup | (tenant_id, sku_id, location_id) |
| tasks | queue | (status, assigned_to) |
| All tenant tables | tenant | (tenant_id) |
| receiving_labels | scan | (label_code) |
| locations | barcode | (barcode) |

---

## Enums Reference

```python
class UserRole(str, Enum):
    PLATFORM_ADMIN = "platform_admin"
    TENANT_ADMIN = "tenant_admin"
    OPERATOR = "operator"
    CLIENT_VIEWER = "client_viewer"

class TaskType(str, Enum):
    RECEIVING = "receiving"
    PUTAWAY = "putaway"
    PICKING = "picking"
    PACKING = "packing"
    SHIPPING = "shipping"
    CYCLE_COUNT = "cycle_count"
    REPLENISHMENT = "replenishment"

class TaskStatus(str, Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TransactionType(str, Enum):
    RECEIVE = "receive"
    PUTAWAY = "putaway"
    PICK = "pick"
    PACK = "pack"
    SHIP = "ship"
    RETURN = "return"
    ADJUST = "adjust"
    DAMAGE = "damage"
    REPAIR = "repair"

class LocationType(str, Enum):
    STORAGE = "storage"
    STAGING = "staging"
    DOCK = "dock"
    RETURN = "return"
    PACKING = "packing"

class LocationStatus(str, Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    BLOCKED = "blocked"

class InboundStatus(str, Enum):
    DRAFT = "draft"
    EXPECTED = "expected"
    ARRIVED = "arrived"
    RECEIVING = "receiving"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class OutboundStatus(str, Enum):
    CREATED = "created"
    ALLOCATED = "allocated"
    PICKED = "picked"
    PACKED = "packed"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"
```
