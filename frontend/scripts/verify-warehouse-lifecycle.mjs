import { chromium } from "playwright";
import { registerOrBootstrapAuditTenant } from "./audit-tenant-bootstrap.mjs";

const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const appUrl = process.env.WMS_AUDIT_APP_URL ?? "https://app.maxsmartwms.online";
const language = process.env.WMS_AUDIT_LANGUAGE ?? "en";
const password = process.env.WMS_AUDIT_PASSWORD ?? "Aaa200058";
const platformEmail = process.env.WMS_AUDIT_PLATFORM_EMAIL;
const platformPassword = process.env.WMS_AUDIT_PLATFORM_PASSWORD;

const stamp = `life${Date.now().toString().slice(-6)}`;
const companyCode = `LF${stamp}`.slice(0, 12);
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
  if (!condition) throw new Error(message);
}

function sumQuantityByLocation(items, locationId) {
  return (items || [])
    .filter((item) => item.location_id === locationId)
    .reduce((total, item) => total + (item.quantity_on_hand || 0), 0);
}

async function setSession(page, auth) {
  await page.goto(`${appUrl}/dashboard`, { waitUntil: "domcontentloaded" });
  await page.evaluate(
    ({ nextLanguage, token, role, tenantId, permissions }) => {
      localStorage.setItem("wms.language", nextLanguage);
      localStorage.setItem("wms_token", token);
      localStorage.setItem("wms_role", role ?? "tenant_admin");
      localStorage.setItem("wms_tenant_id", tenantId ?? "");
      localStorage.setItem("wms_permissions", JSON.stringify(permissions ?? []));
    },
    {
      nextLanguage: language,
      token: auth.access_token,
      role: auth.user?.role ?? "tenant_admin",
      tenantId: auth.user?.tenant_id ?? "",
      permissions: auth.user?.permissions ?? [],
    },
  );
}

async function pageContains(page, path, phrases) {
  await page.goto(`${appUrl}${path}`, { waitUntil: "networkidle" });
  const text = await page.locator("body").innerText();
  return phrases.every((phrase) => text.includes(phrase));
}

async function inventoryShowsLocation(page, barcode, qtyText) {
  await page.goto(`${appUrl}/inventory`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "依庫位" }).click();
  await page.waitForTimeout(800);
  const text = await page.locator("body").innerText();
  return text.includes(barcode) && text.includes(qtyText);
}

async function pickingShowsTask(page, orderNumber, skuCode) {
  await page.goto(`${appUrl}/picking`, { waitUntil: "networkidle" });
  const taskTab = page
    .getByRole("button", {
      name: /任務|Tasks|Pick tasks|Picking work|揀貨工作|工作/,
    })
    .first();
  if ((await taskTab.count()) > 0) {
    await taskTab.click();
  }
  await page.waitForTimeout(800);
  const text = await page.locator("body").innerText();
  return text.includes(orderNumber) || text.includes(skuCode);
}

const registration = await registerOrBootstrapAuditTenant({
  apiUrl,
  platformEmail,
  platformPassword,
  email,
  password,
  companyName: `Lifecycle Audit ${stamp}`,
  companyCode,
  adminName: "Lifecycle User",
});

const token = registration.access_token;
const authHeaders = { Authorization: `Bearer ${token}` };

const warehouse = await callApi("/warehouses/", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    name: "Lifecycle Warehouse",
    code: "LIFEWH",
    timezone: "Europe/Budapest",
  }),
});

const zone = await callApi(`/warehouses/${warehouse.id}/zones`, {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({ name: "A Zone", code: "A", sequence: 1 }),
});

const dockLocation = await callApi(`/warehouses/${warehouse.id}/locations`, {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    zone_id: zone.id,
    barcode: "DOCK-01",
    aisle: "DOCK",
    rack: "01",
    level: "00",
    position: "00",
    location_type: "dock",
  }),
});

const storageLocation = await callApi(`/warehouses/${warehouse.id}/locations`, {
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
    name: "Lifecycle Client",
    code: "LIFECL",
    contact_email: email,
    billing_enabled: true,
    portal_access: true,
  }),
});

const sku = await callApi("/skus/", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    client_id: client.id,
    sku_code: "LIFE-SKU-001",
    name: "Lifecycle Demo SKU",
    weight_kg: 1,
    requires_lot: false,
    requires_expiry: false,
  }),
});

const inboundCsv = [
  "order_number,client_code,warehouse_code,sku_code,quantity,reference_number,supplier_name",
  "INB-LIFE-001,LIFECL,LIFEWH,LIFE-SKU-001,5,REF-INB-001,Demo Supplier",
].join("\n");
const inboundForm = new FormData();
inboundForm.append("file", new Blob([inboundCsv], { type: "text/csv" }), "inbound.csv");
await callApi("/receiving/inbound/import-csv", {
  method: "POST",
  headers: authHeaders,
  body: inboundForm,
});

const inboundOrdersImported = await callApi("/orders/inbound", { headers: authHeaders });
const inboundOrder = (inboundOrdersImported || []).find((item) => item.order_number === "INB-LIFE-001");
expect(inboundOrder, "Inbound order not found after import");

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1400 } });
await setSession(page, registration);

const receivingPageVisible = await pageContains(page, "/receiving", ["INB-LIFE-001", "待入庫"]);

await callApi(`/receiving/inbound/${inboundOrder.id}/start-receiving`, {
  method: "POST",
  headers: authHeaders,
});

const inboundReceiving = await callApi(`/order-details/inbound/${inboundOrder.id}`, { headers: authHeaders });
expect(inboundReceiving.status === "receiving", "Inbound order did not move to receiving");
const inboundLine = inboundReceiving.lines[0];
expect(inboundLine, "Inbound line not found");

await callApi(`/receiving/inbound/${inboundOrder.id}/receive-line`, {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    line_id: inboundLine.line_id,
    quantity_received: 5,
    quantity_damaged: 0,
    staging_location_id: dockLocation.id,
  }),
});

const inventoryAfterReceive = await callApi("/inventory?page_size=200", { headers: authHeaders });
const dockQtyBeforePutaway = sumQuantityByLocation(inventoryAfterReceive.items, dockLocation.id);

await callApi(`/receiving/inbound/${inboundOrder.id}/complete`, {
  method: "POST",
  headers: authHeaders,
});

const inboundPutaway = await callApi(`/order-details/inbound/${inboundOrder.id}`, { headers: authHeaders });
expect(inboundPutaway.status === "putaway", "Inbound order did not move to putaway");

const putawayTasks = await callApi("/tasks/?status=pending&task_type=putaway", { headers: authHeaders });
const putawayTask = (putawayTasks || []).find((task) => task.reference_id === inboundOrder.id);
expect(putawayTask, "Putaway task not created");

const putawayPageVisible = await pageContains(page, "/putaway", ["LIFE-SKU-001", "5"]);

await callApi("/fulfillment/putaway/confirm", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    task_id: putawayTask.id,
    destination_location_id: storageLocation.id,
  }),
});

const inboundCompleted = await callApi(`/order-details/inbound/${inboundOrder.id}`, { headers: authHeaders });
expect(inboundCompleted.status === "completed", "Inbound order did not complete after putaway");

const inventoryAfterPutaway = await callApi("/inventory?page_size=200", { headers: authHeaders });
const dockQtyAfterPutaway = sumQuantityByLocation(inventoryAfterPutaway.items, dockLocation.id);
const storageQtyAfterPutaway = sumQuantityByLocation(inventoryAfterPutaway.items, storageLocation.id);

const inventoryPageVisible = await inventoryShowsLocation(page, "A-01-01-01-01", "5");

const outboundCsv = [
  "order_number,client_code,warehouse_code,sku_code,quantity,reference_number,carrier",
  "OUT-LIFE-001,LIFECL,LIFEWH,LIFE-SKU-001,2,REF-OUT-001,DHL",
].join("\n");
const outboundForm = new FormData();
outboundForm.append("file", new Blob([outboundCsv], { type: "text/csv" }), "outbound.csv");
await callApi("/orders/outbound/import-csv", {
  method: "POST",
  headers: authHeaders,
  body: outboundForm,
});

const outboundOrdersImported = await callApi("/orders/outbound", { headers: authHeaders });
const outboundOrder = (outboundOrdersImported || []).find((item) => item.order_number === "OUT-LIFE-001");
expect(outboundOrder, "Outbound order not found after import");

await callApi("/fulfillment/pick/allocate", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({ order_id: outboundOrder.id }),
});

await callApi("/fulfillment/pick/create-tasks", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({ order_id: outboundOrder.id }),
});

const outboundPicking = await callApi(`/order-details/outbound/${outboundOrder.id}`, { headers: authHeaders });
expect(outboundPicking.fully_allocated === true, "Outbound order did not fully allocate");

const pickTasks = await callApi("/tasks/?status=pending&task_type=pick", { headers: authHeaders });
const pickTask = (pickTasks || []).find((task) => task.reference_id === outboundOrder.id);
expect(pickTask, "Pick task not created");

const pickingPageVisible = await pickingShowsTask(page, "OUT-LIFE-001", "LIFE-SKU-001");

await callApi("/fulfillment/pick/confirm", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    task_id: pickTask.id,
    quantity_picked: 2,
  }),
});

const outboundPicked = await callApi(`/order-details/outbound/${outboundOrder.id}`, { headers: authHeaders });
expect(outboundPicked.status === "picked", "Outbound order did not move to picked");

const inventoryAfterPick = await callApi("/inventory?page_size=200", { headers: authHeaders });
const storageQtyAfterPick = sumQuantityByLocation(inventoryAfterPick.items, storageLocation.id);

const shippingPageVisible = await pageContains(page, "/shipping", ["OUT-LIFE-001", "已揀貨"]);

await callApi("/fulfillment/pack/verify", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    order_id: outboundOrder.id,
    scanned_items: [{ sku_id: sku.id, quantity: 2 }],
  }),
});

const outboundPacked = await callApi(`/order-details/outbound/${outboundOrder.id}`, { headers: authHeaders });
expect(outboundPacked.status === "packed", "Outbound order did not move to packed");

await callApi("/fulfillment/ship/confirm", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    order_id: outboundOrder.id,
    carrier: "DHL",
    tracking_number: `TRACK-${stamp}`,
  }),
});

const outboundShipped = await callApi(`/order-details/outbound/${outboundOrder.id}`, { headers: authHeaders });
const shipmentSummary = await callApi(`/fulfillment/ship/${outboundOrder.id}/summary`, { headers: authHeaders });

await browser.close();

const result = {
  receivingPageVisible,
  putawayPageVisible,
  inventoryPageVisible,
  pickingPageVisible,
  shippingPageVisible,
  inboundStatuses: {
    imported: inboundOrder.status,
    afterStartReceiving: inboundReceiving.status,
    afterCompleteReceiving: inboundPutaway.status,
    afterPutaway: inboundCompleted.status,
  },
  outboundStatuses: {
    imported: outboundOrder.status,
    afterAllocation: outboundPicking.status,
    afterPick: outboundPicked.status,
    afterPack: outboundPacked.status,
    afterShip: outboundShipped.status,
  },
  inventory: {
    dockQtyBeforePutaway,
    dockQtyAfterPutaway,
    storageQtyAfterPutaway,
    storageQtyAfterPick,
  },
  shipment: {
    trackingNumber: outboundShipped.tracking_number ?? null,
    carrier: shipmentSummary.carrier ?? null,
    summaryStatus: shipmentSummary.status ?? null,
  },
};

console.log(JSON.stringify(result, null, 2));

expect(receivingPageVisible, "Receiving page did not show the imported inbound order");
expect(putawayPageVisible, "Putaway page did not show the pending putaway task");
expect(inventoryPageVisible, "Inventory page did not show the final storage location");
expect(pickingPageVisible, "Picking page did not show the created pick task");
expect(shippingPageVisible, "Shipping page did not show the picked order");
expect(dockQtyBeforePutaway === 5, "Dock quantity before putaway was not 5");
expect(dockQtyAfterPutaway === 0, "Dock quantity after putaway was not cleared");
expect(storageQtyAfterPutaway === 5, "Storage quantity after putaway was not 5");
expect(storageQtyAfterPick === 3, "Storage quantity after pick was not 3");
expect(outboundShipped.status === "shipped", "Outbound order did not move to shipped");
expect(shipmentSummary.status === "shipped", "Shipment summary did not move to shipped");
expect(shipmentSummary.tracking_number === `TRACK-${stamp}`, "Tracking number did not persist");
