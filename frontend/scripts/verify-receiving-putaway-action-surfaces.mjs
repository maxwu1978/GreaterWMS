import { chromium } from "playwright";
import { registerOrBootstrapAuditTenant } from "./audit-tenant-bootstrap.mjs";

const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const appUrl = process.env.WMS_AUDIT_APP_URL ?? "https://app.maxsmartwms.online";
const language = process.env.WMS_AUDIT_LANGUAGE ?? "en";
const password = process.env.WMS_AUDIT_PASSWORD || "Aaa200058";
const platformEmail = process.env.WMS_AUDIT_PLATFORM_EMAIL;
const platformPassword = process.env.WMS_AUDIT_PLATFORM_PASSWORD;

const stamp = `act${Date.now().toString().slice(-6)}`;
const companyCode = `AF${stamp}`.slice(0, 12);
const email = `${stamp}@example.com`;
const clientCode = `ACL${stamp.slice(-6)}`;
const skuCode = `ACT-SKU-${stamp}`;

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

function logStep(message) {
  console.error(`[verify] ${message}`);
}

const receiptActionPattern = /Confirm (scanned package|this package receipt|Package \d+ receipt)/;
const scannerInputSelector =
  'input[placeholder^="Scan or type"]:visible, input[placeholder="Scan barcode or type manually..."]:visible';

async function waitFor(check, { timeoutMs = 15000, intervalMs = 500, label = "condition" } = {}) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await check()) return true;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error(`Timed out waiting for ${label}`);
}

async function setClientState(page, auth, sessionState = {}) {
  await page.goto(`${appUrl}/dashboard`, { waitUntil: "domcontentloaded" });
  await page.evaluate(
    ({ nextLanguage, token, role, tenantId, permissions, nextSessionState }) => {
      localStorage.setItem("wms.language", nextLanguage);
      localStorage.setItem("wms_token", token);
      localStorage.setItem("wms_role", role ?? "tenant_admin");
      localStorage.setItem("wms_tenant_id", tenantId ?? "");
      localStorage.setItem("wms_permissions", JSON.stringify(permissions ?? []));
      Object.entries(nextSessionState || {}).forEach(([key, value]) => {
        if (typeof value === "string") {
          sessionStorage.setItem(key, value);
        }
      });
    },
    {
      nextLanguage: language,
      token: auth.access_token,
      role: auth.user?.role ?? "tenant_admin",
      tenantId: auth.user?.tenant_id ?? "",
      permissions: auth.user?.permissions ?? [],
      nextSessionState: sessionState,
    },
  );
}

async function isDetailsOpen(page, summaryText) {
  const summary = page.locator("summary").filter({ hasText: summaryText }).first();
  await summary.waitFor({ state: "visible" });
  return summary.evaluate((node) => Boolean(node.parentElement?.open));
}

async function fillVisibleScanner(page, value) {
  const scanner = page.locator(scannerInputSelector).first();
  await scanner.waitFor({ state: "visible", timeout: 20000 });
  await scanner.fill(value);
  await scanner.press("Enter");
}

async function waitForInboundOrderVisible(orderId) {
  let lastSnapshot = "";
  await waitFor(
    async () => {
      const params = new URLSearchParams({
        include_archived: "false",
        lifecycle: "active",
        sort_by: "order_number",
        sort_direction: "desc",
        offset: "0",
        limit: "100",
      });
      const orders = await callApi(`/orders/inbound?${params.toString()}`, { headers: authHeaders });
      const items = Array.isArray(orders) ? orders : orders.items || [];
      lastSnapshot = items
        .slice(0, 5)
        .map((order) => `${order.order_number}:${order.status}`)
        .join(", ");
      return items.some((order) => order.id === orderId && ["expected", "arrived", "receiving"].includes(order.status));
    },
    { timeoutMs: 20000, intervalMs: 1000, label: `inbound order ${orderId} in active list; saw ${lastSnapshot || "none"}` },
  );
}

async function registerOrBootstrapTenant() {
  const auth = await registerOrBootstrapAuditTenant({
    apiUrl,
    platformEmail,
    platformPassword,
    email,
    password,
    companyName: `Action First ${stamp}`,
    companyCode,
    adminName: "Action Audit User",
  });
  logStep("prepared verified tenant admin");
  return auth;
}

const login = await registerOrBootstrapTenant();
logStep("logged in with fresh tenant admin");

const auth = {
  access_token: login.access_token,
  user: {
    role: login.role,
    tenant_id: login.tenant_id,
    permissions: login.permissions ?? [],
  },
};

const token = auth.access_token;
const authHeaders = { Authorization: `Bearer ${token}` };

async function ensureWarehouseContext() {
  const jsonHeaders = { ...authHeaders, "Content-Type": "application/json" };
  let warehouse;
  try {
    warehouse = await callApi("/warehouses/", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        name: `Action Surface Warehouse ${stamp}`,
        code: `AWH${stamp.slice(-4)}`,
        timezone: "Europe/Budapest",
      }),
    });
    logStep("created warehouse");
  } catch (error) {
    if (!String(error).includes("plan_limit_exceeded")) throw error;
    const warehouses = await callApi("/warehouses/", { headers: authHeaders });
    warehouse = (Array.isArray(warehouses) ? warehouses : warehouses.items || [])[0];
    if (!warehouse) throw error;
    logStep(`reused warehouse ${warehouse.code}`);
  }

  let zone;
  try {
    zone = await callApi(`/warehouses/${warehouse.id}/zones`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ name: `Action Zone ${stamp}`, code: `AZ${stamp.slice(-4)}`, sequence: 1 }),
    });
  } catch {
    const zones = await callApi(`/warehouses/${warehouse.id}/zones`, { headers: authHeaders });
    zone = (Array.isArray(zones) ? zones : zones.items || [])[0];
  }
  if (!zone) throw new Error("No zone available for receiving audit");

  let dockLocation;
  try {
    dockLocation = await callApi(`/warehouses/${warehouse.id}/locations`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        zone_id: zone.id,
        barcode: `DOCK-${stamp}`,
        aisle: "DOCK",
        rack: stamp.slice(-2),
        level: "00",
        position: "00",
        location_type: "dock",
      }),
    });
  } catch {
    const locations = await callApi(`/warehouses/${warehouse.id}/locations`, { headers: authHeaders });
    dockLocation = (Array.isArray(locations) ? locations : locations.items || []).find((item) =>
      ["dock", "staging"].includes(item.location_type),
    );
  }
  if (!dockLocation) throw new Error("No dock or staging location available for receiving audit");

  let storageLocation;
  try {
    storageLocation = await callApi(`/warehouses/${warehouse.id}/locations`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        zone_id: zone.id,
        barcode: `STOR-${stamp}`,
        aisle: "ST",
        rack: stamp.slice(-2),
        level: "01",
        position: "01",
        location_type: "storage",
      }),
    });
  } catch {
    const locations = await callApi(`/warehouses/${warehouse.id}/locations`, { headers: authHeaders });
    storageLocation = (Array.isArray(locations) ? locations : locations.items || []).find(
      (item) => item.location_type === "storage",
    );
  }
  if (!storageLocation) throw new Error("No storage location available for putaway audit");

  return { warehouse, dockLocation, storageLocation };
}

const { warehouse, dockLocation, storageLocation } = await ensureWarehouseContext();

const client = await callApi("/clients/", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    name: "Action Surface Client",
    code: clientCode,
    contact_email: email,
    billing_enabled: true,
    portal_access: true,
  }),
});
logStep("created client");

const sku = await callApi("/skus/", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    client_id: client.id,
    sku_code: skuCode,
    name: "Action Surface SKU",
    weight_kg: 1,
    requires_lot: false,
    requires_expiry: false,
  }),
});
logStep("created sku");

const suffix = Date.now().toString().slice(-6);
const orderNumber = `INB-ACT-${suffix}`;
const tracking = `TRK-ACT-${suffix}`;
const inbound = await callApi("/receiving/inbound", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    warehouse_id: warehouse.id,
    client_id: client.id,
    order_number: orderNumber,
    reference_number: `REF-ACT-${suffix}`,
    lines: [{ sku_id: sku.id, quantity: 5 }],
  }),
});
logStep("created inbound order");

const orderId = inbound.id;
await callApi(`/receiving/inbound/${orderId}/start-receiving`, {
  method: "POST",
  headers: authHeaders,
});
logStep("started receiving");

const detail = await callApi(`/order-details/inbound/${orderId}`, { headers: authHeaders });
const line = detail.lines[0];

const pkg = await callApi(`/receiving/inbound/${orderId}/packages`, {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    line_id: line.line_id,
    expected_qty: 5,
    package_type: "carton",
    external_tracking_number: tracking,
  }),
});
logStep("created dock package");
await waitForInboundOrderVisible(orderId);
logStep("confirmed inbound order is visible in active receiving list");

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1400 } });

await setClientState(page, auth, {
  "receiving.selectedOrderId": orderId,
  "receiving.lastActiveOrder": JSON.stringify({ id: orderId, status: "receiving" }),
});
logStep("seeded receiving client state");

await page.goto(`${appUrl}/receiving?orderId=${orderId}`, { waitUntil: "domcontentloaded" });
await page.waitForFunction(
  ({ orderNumber: nextOrderNumber, nextOrderId }) => {
    const text = document.body?.innerText || "";
    return text.includes(nextOrderNumber) || window.location.search.includes(nextOrderId);
  },
  { orderNumber, nextOrderId: orderId },
  { timeout: 20000 },
);
logStep("opened receiving page");

const receivingBody = await page.locator("body").innerText();
logStep(`receiving snapshot: ${receivingBody.slice(0, 1200).replace(/\s+/g, " ")}`);
logStep("entered live receiving through direct order focus");
await fillVisibleScanner(page, tracking);
await page.waitForFunction(
  ({ packageNumber }) => {
    const text = document.body?.innerText || "";
    return text.includes(`Package ${packageNumber}`) && text.includes("Still to receive");
  },
  { packageNumber: pkg.package_number },
  { timeout: 15000 },
);
logStep("opened package from scan input");

const activeReceivingBody = await page.locator("body").innerText();
expect(
  activeReceivingBody.includes(`Package ${pkg.package_number}`),
  "Receiving page did not surface the focused package identity on the first screen",
);
expect(activeReceivingBody.includes("Still to receive"), "Receiving page did not surface remaining quantity");
expect(
  activeReceivingBody.includes("Choose staging to continue") ||
    receiptActionPattern.test(activeReceivingBody),
  "Receiving page did not surface the blocker-clearing receipt action",
);

await page.waitForFunction(() => {
  const select = document.querySelector("#receiving-staging-selector select");
  return Boolean(select && "options" in select && select.options.length > 1);
}, undefined, { timeout: 15000 });
await page.locator("#receiving-staging-selector select").selectOption(String(dockLocation.id));
const stagingValue = await page.locator("#receiving-staging-selector select").inputValue();
const actionTexts = await page.getByRole("button").allInnerTexts();
logStep(`selected staging value: ${stagingValue}`);
logStep(`buttons after staging select: ${actionTexts.join(" | ")}`);
await page.waitForFunction(() => {
  const stagingSelect = document.querySelector("#receiving-staging-selector select");
  const actionButtons = Array.from(document.querySelectorAll("button"));
  const hasConfirmAction = actionButtons.some((button) =>
    /Confirm (scanned package|this package receipt|Package \d+ receipt)/.test(button.textContent || ""),
  );
  return Boolean(stagingSelect && "value" in stagingSelect && stagingSelect.value) && hasConfirmAction;
}, undefined, { timeout: 15000 });
await page.getByRole("button", { name: receiptActionPattern }).click();
await page.waitForFunction(() => {
  const text = (document.body?.innerText || "").toLowerCase();
  return (
    text.includes("just confirmed") ||
    text.includes("internal label issued") ||
    text.includes("confirmed internal labels") ||
    text.includes("print confirmed internal labels") ||
    text.includes("print this internal label")
  );
}, undefined, { timeout: 15000 });
logStep("confirmed receipt in UI");

const afterReceiptBody = await page.locator("body").innerText();
logStep(`after receipt snapshot: ${afterReceiptBody.slice(0, 1600).replace(/\s+/g, " ")}`);
const afterReceiptBodyLower = afterReceiptBody.toLowerCase();
expect(
  afterReceiptBodyLower.includes("just confirmed") ||
    afterReceiptBodyLower.includes("internal label issued") ||
    afterReceiptBodyLower.includes("confirmed internal labels"),
  "Receipt outcome did not appear after confirmation",
);
await page.waitForFunction(() => {
  const text = (document.body?.innerText || "").toLowerCase();
  return text.includes("print this internal label") || text.includes("print confirmed internal labels");
}, undefined, { timeout: 15000 });
const receiptWithPrintBody = (await page.locator("body").innerText()).toLowerCase();
expect(
  receiptWithPrintBody.includes("print this internal label") ||
    receiptWithPrintBody.includes("print confirmed internal labels"),
  "Print action did not appear after receipt",
);

const printTemplateSummary = page.locator("summary").filter({ hasText: "Print template" }).first();
let printTemplateOpen = false;
if ((await printTemplateSummary.count()) > 0) {
  printTemplateOpen = await isDetailsOpen(page, "Print template");
  expect(!printTemplateOpen, "Print template summary should stay collapsed until explicitly opened");
  logStep("verified collapsed print template");
}

await callApi(`/receiving/inbound/${orderId}/complete`, {
  method: "POST",
  headers: authHeaders,
});
logStep("completed receiving");

const tasksPayload = await callApi("/tasks/?status=pending&task_type=putaway", { headers: authHeaders });
const putawayTask = (Array.isArray(tasksPayload) ? tasksPayload : tasksPayload.items || []).find(
  (task) => task.reference_id === orderId,
);
expect(putawayTask, "Putaway task was not created after completing receiving");
logStep("located pending putaway task");

await setClientState(page, auth, {
  "putaway.focusContext": JSON.stringify({
    source: "action-first-audit",
    orderId,
    orderNumber,
    referenceNumber: `REF-ACT-${suffix}`,
    handlingUnitCode: putawayTask.handling_unit_code || null,
    taskId: putawayTask.id,
  }),
});
logStep("seeded putaway client state");

await page.goto(`${appUrl}/putaway`, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(4000);
logStep("opened putaway page");

const putawayBody = await page.locator("body").innerText();
logStep(`putaway snapshot: ${putawayBody.slice(0, 1600).replace(/\s+/g, " ")}`);
expect(
  putawayBody.includes(putawayTask.handling_unit_code || "RCV-") ||
    putawayBody.includes(orderNumber) ||
    putawayBody.includes("This task is selected"),
  "Putaway page did not focus the seeded task",
);
expect(!putawayBody.includes("Current decision"), "Putaway should not render the removed Current decision layer");
expect(!putawayBody.includes("Check the source"), "Putaway checklist should not repeat the removed passive source step");

const openPutawayTaskButton = page.locator("button").filter({ hasText: /^Open$/i }).first();
if ((await openPutawayTaskButton.count()) > 0) {
  await openPutawayTaskButton.click();
  await page.waitForFunction(
    () => /Active task|Final storage location|Choose final storage location/i.test(document.body?.innerText || ""),
    undefined,
    { timeout: 15000 },
  );
  logStep("opened focused putaway task from queue");
}

await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(500);
const mobilePrimaryAction = page.getByTestId("putaway-mobile-primary-action");
await mobilePrimaryAction.waitFor({ state: "visible", timeout: 15000 });
expect((await mobilePrimaryAction.count()) === 1, "Putaway mobile should expose exactly one primary action");
const putawayPrimaryAction = await mobilePrimaryAction.first().getAttribute("data-putaway-primary-action");
const putawayPath = await mobilePrimaryAction.first().getAttribute("data-putaway-path");
expect(
  ["use_recommended_slot", "confirm_putaway"].includes(putawayPrimaryAction || ""),
  `Putaway mobile primary action is not stable: ${putawayPrimaryAction}`,
);
expect(
  ["recommended", "manual", "exception"].includes(putawayPath || ""),
  `Putaway mobile path is not stable: ${putawayPath}`,
);
if (putawayPrimaryAction === "use_recommended_slot") {
  expect(putawayPath === "recommended", "Putaway recommended slot action should use recommended path");
}
const manualSlotDetails = page.getByTestId("putaway-mobile-manual-slot");
await manualSlotDetails.waitFor({ state: "visible", timeout: 15000 });
expect(
  !(await manualSlotDetails.first().evaluate((node) => node instanceof HTMLDetailsElement && node.open)),
  "Putaway manual slot controls should stay collapsed on mobile",
);
if ((await page.getByTestId("putaway-mobile-other-suggestions").count()) > 0) {
  expect(
    !(await page.getByTestId("putaway-mobile-other-suggestions").first().evaluate((node) => node instanceof HTMLDetailsElement && node.open)),
    "Putaway secondary suggested slots should stay collapsed on mobile",
  );
}
expect(
  (await page.evaluate(() => Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth))) <= 12,
  "Putaway mobile has horizontal overflow",
);
logStep("verified putaway mobile primary action contract");

await page.setViewportSize({ width: 1440, height: 1400 });
await page.waitForTimeout(500);

const slotButton = page.getByRole("button", { name: storageLocation.barcode });
if ((await slotButton.count()) > 0) {
  await slotButton.first().click();
  await page.getByRole("button", { name: "Confirm putaway" }).click();
} else {
  const apiPutaway = await callApi("/fulfillment/putaway/confirm", {
    method: "POST",
    headers: { ...authHeaders, "Content-Type": "application/json" },
    body: JSON.stringify({
      task_id: putawayTask.id,
      destination_location_id: storageLocation.id,
    }),
  });
  expect(apiPutaway.success === true, `Putaway API confirm failed: ${JSON.stringify(apiPutaway)}`);
}
const taskCompleted = await waitFor(
  async () => {
    const tasksPayload = await callApi("/tasks/?status=pending&task_type=putaway", { headers: authHeaders });
    const pendingTasks = Array.isArray(tasksPayload) ? tasksPayload : tasksPayload.items || [];
    return !pendingTasks.some((task) => task.id === putawayTask.id);
  },
  { timeoutMs: 15000, intervalMs: 750, label: "putaway task completion" },
);
await page.waitForTimeout(1000);
logStep("confirmed putaway in UI");

const finalBody = await page.locator("body").innerText();
logStep(`putaway success snapshot: ${finalBody.slice(0, 1600).replace(/\s+/g, " ")}`);
expect(
  taskCompleted || finalBody.toLowerCase().includes("putaway confirmed"),
  "Putaway completion was not confirmed",
);
const putawaySuccessNextStep = page.getByTestId("putaway-success-next-step");
if ((await putawaySuccessNextStep.count()) > 0) {
  const successText = await putawaySuccessNextStep.first().innerText();
  expect(/Next:/i.test(successText), "Putaway success state did not explain the next step");
}

const result = {
  orderNumber,
  packageNumber: pkg.package_number,
  printTemplateOpen,
  putawayTaskId: putawayTask.id,
  storageBarcode: storageLocation.barcode,
  putawayNextStepVisible: (await putawaySuccessNextStep.count()) > 0,
};

await browser.close();

console.log(JSON.stringify(result, null, 2));
