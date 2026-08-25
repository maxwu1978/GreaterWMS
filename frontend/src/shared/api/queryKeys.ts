/**
 * Central query-key factory.
 *
 * Every react-query cache key used across the app is produced here so that
 * `useQuery` keys and `invalidateQueries` calls can never drift apart.
 *
 * IMPORTANT: the arrays produced here intentionally keep the exact same
 * shapes/spellings that pages historically used inline, so existing caches
 * and prefix-based invalidation keep working.
 *
 * One deliberate reconciliation: the inbound order detail endpoint
 * (`/order-details/inbound/{id}`) was previously cached under TWO different
 * spellings — `["receiving-order-detail", id]` (ReceivingFlow) and
 * `["inbound-order-detail", id]` (ReceivingPage / InboundOrderDetailPage).
 * The factory converges on the majority spelling `"receiving-order-detail"`,
 * so invalidating after a receiving mutation now refreshes *all* detail
 * views (that is a fix — previously each page only refreshed its own copy).
 */

export const queryKeys = {
  operationsBoard: () => ["operations-board"] as const,
  inboundOrders: {
    /** `list()` → ["inbound-orders"]; extra filter parts are appended (prefix-invalidation still matches). */
    list: (...filters: readonly unknown[]) => ["inbound-orders", ...filters] as const,
    /** Orders in "expected"/"receiving" status shown in the receiving flow. */
    receivable: () => ["inbound-receivable"] as const,
    /** Detail summary from /order-details/inbound/{id} (converged spelling, see file header). */
    detail: (orderId: unknown) => ["receiving-order-detail", orderId] as const,
  },
  outboundOrders: {
    list: (...filters: readonly unknown[]) => ["outbound-orders", ...filters] as const,
    detail: (orderId: unknown) => ["outbound-order-detail", orderId] as const,
  },
  shipping: {
    orders: (...filters: readonly unknown[]) => ["shipping-orders", ...filters] as const,
    orderDetail: (orderId: unknown) => ["shipping-order-detail", orderId] as const,
  },
  receiving: {
    packages: (orderId: unknown) => ["receiving-packages", orderId] as const,
    labels: (orderId: unknown) => ["receiving-labels", orderId] as const,
    labelTemplate: () => ["receiving-label-template"] as const,
    observedCodes: (orderId: unknown, packageRef: unknown) =>
      ["receiving-observed-codes", orderId, packageRef] as const,
    stagingLocations: (warehouseId: unknown) => ["receiving-staging-locations", warehouseId] as const,
    codeRules: () => ["receiving-code-rules"] as const,
    supervisorExceptions: (orderIds: readonly unknown[]) =>
      ["receiving-supervisor-exceptions", orderIds] as const,
  },
  tasks: {
    all: () => ["tasks"] as const,
    pick: () => ["pick-tasks"] as const,
    myPick: (...parts: readonly unknown[]) => ["my-pick-tasks", ...parts] as const,
    putaway: (...filters: readonly unknown[]) => ["putaway-tasks", ...filters] as const,
    inventoryPending: () => ["inventory-tasks-pending"] as const,
  },
  mailTasks: {
    list: (...filters: readonly unknown[]) => ["mail-tasks", ...filters] as const,
    detail: (taskKey: unknown) => ["mail-task-detail", taskKey] as const,
  },
  putaway: {
    warehouses: () => ["putaway-warehouses"] as const,
    locations: (warehouseIdsKey: unknown) => ["putaway-locations", warehouseIdsKey] as const,
    inboundOrders: () => ["putaway-inbound-orders"] as const,
    skus: () => ["putaway-skus"] as const,
    suggestions: (...parts: readonly unknown[]) => ["putaway-suggestions", ...parts] as const,
    batchSuggestions: (...parts: readonly unknown[]) => ["putaway-batch-suggestions", ...parts] as const,
    inventoryContext: (...parts: readonly unknown[]) => ["putaway-inventory-context", ...parts] as const,
    plannerRules: (warehouseId: unknown) => ["putaway-planner-rules", warehouseId] as const,
  },
  planner: {
    warehouses: () => ["planner-warehouses"] as const,
    zones: (warehouseId: unknown) => ["planner-zones", warehouseId] as const,
    locations: (warehouseId: unknown, zoneId: unknown) =>
      ["planner-locations", warehouseId, zoneId] as const,
    allLocations: (warehouseId: unknown) => ["planner-all-locations", warehouseId] as const,
    rules: (warehouseId: unknown) => ["planner-rules", warehouseId] as const,
    heatInventory: (warehouseId: unknown) => ["planner-heat-inventory", warehouseId] as const,
    wcsPointMappings: (warehouseId: unknown) => ["planner-wcs-point-mappings", warehouseId] as const,
  },
  warehouses: {
    masterData: () => ["warehouses-master-data"] as const,
    zoneCounts: (warehouseIdsKey: unknown) => ["warehouses-zone-counts", warehouseIdsKey] as const,
  },
  inventory: {
    list: (...filters: readonly unknown[]) => ["inventory", ...filters] as const,
    summary: () => ["inventory-summary"] as const,
    activity: () => ["inventory-activity"] as const,
    warehouses: () => ["inventory-warehouses"] as const,
    skuDirectory: () => ["inventory-sku-directory"] as const,
    clientDirectory: () => ["inventory-client-directory"] as const,
    locationDirectory: (warehouseIdsKey: unknown) =>
      ["inventory-location-directory", warehouseIdsKey] as const,
    inboundOrders: () => ["inventory-inbound-orders"] as const,
  },
  skus: {
    masterList: () => ["sku-master-list"] as const,
    masterClients: () => ["sku-master-clients"] as const,
  },
  clients: {
    /** Page-scoped clients list, e.g. list("shipping") → ["clients-list", "shipping"]. */
    list: (scope: unknown) => ["clients-list", scope] as const,
    billing: () => ["billing-clients"] as const,
  },
  billing: {
    rateCards: () => ["billing-rate-cards"] as const,
    invoices: (...filters: readonly unknown[]) => ["billing-invoices", ...filters] as const,
    tenantProfile: () => ["tenant-current-profile"] as const,
  },
  adminUsers: {
    list: () => ["admin-users"] as const,
    clients: () => ["admin-users-clients"] as const,
    tenants: () => ["admin-users-tenants"] as const,
  },
  platform: {
    workspaces: () => ["platform-workspaces"] as const,
    workspaceUsers: () => ["platform-workspaces-users"] as const,
    tenantApprovals: () => ["platform-tenant-approvals"] as const,
  },
  subscriptions: {
    current: () => ["subscription-current"] as const,
    usage: () => ["subscription-usage"] as const,
    plans: () => ["plans"] as const,
    status: () => ["sub-status"] as const,
  },
  agent: {
    settings: () => ["agent-settings"] as const,
  },
  agv: {
    warehouses: () => ["agv-warehouses"] as const,
    pendingTasksPreview: (warehouseId: unknown) => ["agv-pending-tasks-preview", warehouseId] as const,
    validation: (warehouseId: unknown) => ["agv-validation", warehouseId] as const,
    wcsBindings: (warehouseId: unknown) => ["agv-wcs-bindings", warehouseId] as const,
  },
  setup: {
    progress: () => ["setup-progress"] as const,
    /** Per-page copies of the setup progress query, e.g. progressFor("receiving") → ["setup-progress-receiving"]. */
    progressFor: (scope: string) => [`setup-progress-${scope}`] as const,
  },
  migration: {
    clients: () => ["migration-clients"] as const,
    warehouses: () => ["migration-warehouses"] as const,
    warehouseLocations: (warehouseId: unknown) => ["migration-warehouse-locations", warehouseId] as const,
    inboundSkus: (clientId: unknown) => ["migration-inbound-skus", clientId] as const,
    outboundSkus: (clientId: unknown) => ["migration-outbound-skus", clientId] as const,
  },
  portal: {
    dashboard: () => ["portal-dashboard"] as const,
    outbound: () => ["portal-outbound"] as const,
    orders: () => ["portal-orders"] as const,
    invoices: () => ["portal-invoices"] as const,
    inventory: () => ["portal-inventory"] as const,
  },
  dashboard: {
    kpi: () => ["kpi-dashboard"] as const,
    activityLog: () => ["activity-log"] as const,
  },
} as const;

export default queryKeys;
