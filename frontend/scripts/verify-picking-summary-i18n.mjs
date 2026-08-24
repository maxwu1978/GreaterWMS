import { chromium } from "playwright";
import { registerOrBootstrapAuditTenant } from "./audit-tenant-bootstrap.mjs";

const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const appUrl = process.env.WMS_AUDIT_APP_URL ?? "https://app.maxsmartwms.online";
const language = process.env.WMS_AUDIT_LANGUAGE ?? "en";
const password = process.env.WMS_AUDIT_PASSWORD ?? "Aaa200058";
const platformEmail = process.env.WMS_AUDIT_PLATFORM_EMAIL;
const platformPassword = process.env.WMS_AUDIT_PLATFORM_PASSWORD;
const stamp = `pick${Date.now().toString().slice(-6)}`;
const companyCode = `PK${stamp}`.slice(0, 12);
const email = `${stamp}@example.com`;

async function callApi(path, options = {}) {
  const response = await fetch(`${apiUrl}${path}`, options);
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }

  if (!response.ok) {
    throw new Error(`${path} -> ${response.status} ${JSON.stringify(data)}`);
  }

  return data;
}

function expect(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const registration = await registerOrBootstrapAuditTenant({
  apiUrl,
  platformEmail,
  platformPassword,
  email,
  password,
  companyName: `Picking Audit ${stamp}`,
  companyCode,
  adminName: "Audit User",
});

const token = registration.access_token;
const user = registration.user ?? {};
const authHeaders = { Authorization: `Bearer ${token}` };

const warehouse = await callApi("/warehouses/", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    name: "Audit WH",
    code: "AUDWH",
    timezone: "Europe/Budapest",
  }),
});

const zone = await callApi(`/warehouses/${warehouse.id}/zones`, {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    name: "A Zone",
    code: "A",
    sequence: 1,
  }),
});

await callApi(`/warehouses/${warehouse.id}/locations`, {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    zone_id: zone.id,
    barcode: "A-01-01-01-01",
    aisle: "01",
    rack: "01",
    level: "01",
    position: "01",
    location_type: "storage",
  }),
});

const client = await callApi("/clients/", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    name: "Audit Client",
    code: "AUDCL",
    contact_email: email,
    billing_enabled: true,
    portal_access: true,
  }),
});

await callApi("/skus/", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    client_id: client.id,
    sku_code: "TAB-SKU-001",
    name: "Task Audit SKU",
    weight_kg: 1,
    requires_lot: false,
    requires_expiry: false,
  }),
});

const inventoryCsv = [
  "client_code,warehouse_code,sku_code,location_barcode,quantity,lot,expiry_date",
  "AUDCL,AUDWH,TAB-SKU-001,A-01-01-01-01,2,LOT-01,",
].join("\n");
const inventoryForm = new FormData();
inventoryForm.append("file", new Blob([inventoryCsv], { type: "text/csv" }), "inventory.csv");
await callApi("/data/inventory/csv", {
  method: "POST",
  headers: authHeaders,
  body: inventoryForm,
});
const inventoryList = await callApi("/inventory", {
  headers: authHeaders,
});

const outboundCsv = [
  "order_number,client_code,warehouse_code,sku_code,quantity,reference_number,carrier",
  "OUT-TAB-001,AUDCL,AUDWH,TAB-SKU-001,2,REF-TAB-001,DHL",
].join("\n");
const outboundForm = new FormData();
outboundForm.append("file", new Blob([outboundCsv], { type: "text/csv" }), "outbound.csv");
await callApi("/orders/outbound/import-csv", {
  method: "POST",
  headers: authHeaders,
  body: outboundForm,
});

const outboundOrders = await callApi("/orders/outbound", { headers: authHeaders });
const seededOrder = (outboundOrders.items ?? outboundOrders).find(
  (item) => item.order_number === "OUT-TAB-001",
);
expect(seededOrder, "Seeded outbound order not found");

const allocationResult = await callApi("/fulfillment/pick/allocate", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({ order_id: seededOrder.id }),
});

const createTasksResult = await callApi("/fulfillment/pick/create-tasks", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({ order_id: seededOrder.id }),
});
const taskList = await callApi("/tasks/?status=pending&task_type=pick", {
  headers: authHeaders,
});

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });

await page.goto(`${appUrl}/picking`, { waitUntil: "domcontentloaded" });
await page.evaluate(
  ({ nextLanguage, nextToken, nextRole, nextTenantId, nextPermissions }) => {
    localStorage.setItem("wms.language", nextLanguage);
    localStorage.setItem("wms_token", nextToken);
    localStorage.setItem("wms_role", nextRole ?? "tenant_admin");
    localStorage.setItem("wms_tenant_id", nextTenantId ?? "");
    localStorage.setItem("wms_permissions", JSON.stringify(nextPermissions ?? []));
  },
  {
    nextLanguage: language,
    nextToken: token,
    nextRole: user.role ?? "tenant_admin",
    nextTenantId: user.tenant_id ?? "",
    nextPermissions: user.permissions ?? [],
  },
);

await page.goto(`${appUrl}/picking`, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(1500);
const tasksTab = page.getByRole("button", { name: /任務/ }).first();
try {
  await tasksTab.click({ timeout: 10000 });
} catch (error) {
  const beforeClickText = await page.locator("body").innerText();
  console.error("Failed to find task tab. Page text snapshot:");
  console.error(beforeClickText.slice(0, 4000));
  throw error;
}
await page.waitForTimeout(1200);

const bodyText = await page.locator("body").innerText();
const result = {
  hasChineseSnapshot: bodyText.includes("任務隊列摘要"),
  hasChineseSnapshotTitle: bodyText.includes("進入掃描流程前，先看清下一批待揀任務"),
  hasEnglishSnapshot: bodyText.includes("Task queue snapshot"),
  hasEnglishSnapshotTitle: bodyText.includes("See the next pick jobs before you enter scan flow"),
  hasOrder: bodyText.includes("OUT-TAB-001"),
  hasSku: bodyText.includes("TAB-SKU-001"),
  hasLocation: bodyText.includes("A-01-01-01-01"),
  allocationSucceeded: allocationResult.fully_allocated === true,
  createdTaskCount: Array.isArray(createTasksResult.task_ids) ? createTasksResult.task_ids.length : 0,
  listedTaskCount: Array.isArray(taskList) ? taskList.length : 0,
  importedWarehouseId: inventoryList?.items?.[0]?.warehouse_id ?? null,
};

await browser.close();

console.log(JSON.stringify(result, null, 2));

expect(result.hasChineseSnapshot, "Chinese snapshot eyebrow not found");
expect(result.hasChineseSnapshotTitle, "Chinese snapshot title not found");
expect(!result.hasEnglishSnapshot, "English snapshot eyebrow still visible");
expect(!result.hasEnglishSnapshotTitle, "English snapshot title still visible");
expect(result.hasOrder && result.hasSku && result.hasLocation, "Task summary data is incomplete");
