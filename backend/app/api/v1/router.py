"""API v1 router — aggregates all endpoint modules."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    agent,
    agv,
    auth,
    batch_operations,
    billing,
    clients,
    cycle_count,
    data_import,
    fulfillment_ops,
    integrations,
    inventory,
    inventory_rules,
    kits,
    maintenance,
    onboarding,
    operations,
    operations_board,
    order_details,
    orders,
    picking,
    portal,
    receiving,
    reports,
    return_analytics,
    returns,
    setup_wizard,
    shipping,
    skus,
    subscriptions,
    survey,
    task_assignment,
    tasks,
    tenants,
    users,
    warehouses,
    waves,
    workbench_summaries,
)
from app.core.config import settings

api_v1_router = APIRouter()

api_v1_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_v1_router.include_router(tenants.router, prefix="/tenants", tags=["Tenants"])
api_v1_router.include_router(users.router, prefix="/users", tags=["Users"])
api_v1_router.include_router(onboarding.router, prefix="/onboarding", tags=["Client Onboarding"])
api_v1_router.include_router(setup_wizard.router, prefix="/setup", tags=["Setup Wizard"])
api_v1_router.include_router(clients.router, prefix="/clients", tags=["Clients"])
api_v1_router.include_router(warehouses.router, prefix="/warehouses", tags=["Warehouses"])
api_v1_router.include_router(inventory.router, prefix="/inventory", tags=["Inventory"])
api_v1_router.include_router(skus.router, prefix="/skus", tags=["SKUs"])
api_v1_router.include_router(
    operations.router, prefix="/inventory/ops", tags=["Inventory Operations"]
)
api_v1_router.include_router(data_import.router, prefix="/data", tags=["Data Import/Export"])
api_v1_router.include_router(kits.router, prefix="/kits", tags=["Kits/Bundles"])
api_v1_router.include_router(
    inventory_rules.router, prefix="/inventory/rules", tags=["Inventory Rules"]
)
api_v1_router.include_router(orders.router, prefix="/orders", tags=["Orders"])
api_v1_router.include_router(
    operations_board.router, prefix="/operations", tags=["Operations Board"]
)
api_v1_router.include_router(order_details.router, prefix="/order-details", tags=["Order Details"])
api_v1_router.include_router(receiving.router, prefix="/receiving", tags=["Receiving"])
api_v1_router.include_router(picking.router, prefix="/fulfillment", tags=["Fulfillment"])
api_v1_router.include_router(
    fulfillment_ops.router, prefix="/fulfill", tags=["One-Click Fulfillment"]
)
api_v1_router.include_router(shipping.router, prefix="/shipping", tags=["Shipping Labels"])
api_v1_router.include_router(returns.router, prefix="/returns", tags=["Returns/RMA"])
api_v1_router.include_router(return_analytics.router, prefix="/returns", tags=["Return Analytics"])
api_v1_router.include_router(cycle_count.router, prefix="/cycle-count", tags=["Cycle Count"])
api_v1_router.include_router(waves.router, prefix="/waves", tags=["Wave Picking"])
api_v1_router.include_router(
    task_assignment.router, prefix="/task-assignment", tags=["Task Assignment"]
)
api_v1_router.include_router(batch_operations.router, prefix="/batch", tags=["Batch Operations"])
api_v1_router.include_router(reports.router, prefix="/reports", tags=["Reports & Analytics"])
api_v1_router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
api_v1_router.include_router(
    workbench_summaries.router, prefix="/workbench-summaries", tags=["Workbench Summaries"]
)
api_v1_router.include_router(billing.router, prefix="/billing", tags=["Billing"])
api_v1_router.include_router(portal.router, prefix="/portal", tags=["Client Portal"])
api_v1_router.include_router(integrations.router, prefix="/integrations", tags=["Integrations"])
api_v1_router.include_router(survey.router, prefix="/survey", tags=["Survey"])
api_v1_router.include_router(agv.router, prefix="/agv", tags=["AGV"])
api_v1_router.include_router(agent.router, prefix="/agent", tags=["Agent"])
api_v1_router.include_router(subscriptions.router, prefix="/subscriptions", tags=["Subscriptions"])
# Destructive ops/seed toolkit — dev-only by default. Production must opt in
# explicitly (MAINTENANCE_API_ENABLED=true) for UAT bootstrap/cleanup windows.
_maintenance_enabled = settings.MAINTENANCE_API_ENABLED
if _maintenance_enabled is None:
    _maintenance_enabled = settings.DEBUG
if _maintenance_enabled:
    api_v1_router.include_router(
        maintenance.router, prefix="/maintenance", tags=["Maintenance"]
    )
