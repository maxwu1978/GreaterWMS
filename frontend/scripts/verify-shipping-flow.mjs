import { chromium } from "playwright";
import { registerOrBootstrapAuditTenant } from "./audit-tenant-bootstrap.mjs";

const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const appUrl = process.env.WMS_AUDIT_APP_URL ?? "https://app.maxsmartwms.online";
const language = process.env.WMS_AUDIT_LANGUAGE ?? "en";
const password = process.env.WMS_AUDIT_PASSWORD ?? "Aaa200058";
const platformEmail = process.env.WMS_AUDIT_PLATFORM_EMAIL;
const platformPassword = process.env.WMS_AUDIT_PLATFORM_PASSWORD;
const stamp = `ship${Date.now().toString().slice(-6)}`;
const companyCode = `SH${stamp}`.slice(0, 12);
const email = `${stamp}@example.com`;
const skuCode = `SHIP-SKU-${stamp}`;
const clientCode = `SCL${stamp.slice(-6)}`;
const orderNumber = `OUT-SHIP-${stamp}`;
const nextStepPattern = /Next:|下一步：|Siguiente:|Következő:|Nächster Schritt:/i;

function items(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.items)) return payload.items;
  return [];
}

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

async function pollShipmentState(orderId, orderNumber, headers, expectedTracking) {
  let latestOrder = null;
  let latestSummary = null;
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const orders = await callApi("/orders/outbound", { headers });
    latestOrder = (orders || []).find((item) => item.order_number === orderNumber) || null;
    latestSummary = await callApi(`/fulfillment/ship/${orderId}/summary`, { headers });
    if (
      latestOrder?.status === "shipped" &&
      latestOrder?.tracking_number === expectedTracking &&
      latestSummary?.status === "shipped" &&
      latestSummary?.tracking_number === expectedTracking
    ) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return { shippedOrder: latestOrder, shippedSummary: latestSummary };
}

async function installBrowserApiProxy(page) {
  const appApiPrefix = `${appUrl.replace(/\/+$/, "")}/api/v1`;
  const remoteApiPrefix = apiUrl.replace(/\/+$/, "");
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = request.url();
    const proxiedPath = url.startsWith(appApiPrefix)
      ? url.slice(appApiPrefix.length)
      : url.startsWith(remoteApiPrefix)
        ? url.slice(remoteApiPrefix.length)
        : null;
    if (proxiedPath === null) {
      await route.continue();
      return;
    }

    const allowHeaders = {
      "access-control-allow-origin": appUrl.replace(/\/+$/, ""),
      "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
      "access-control-allow-headers": "authorization,content-type,x-idempotency-key",
    };
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: allowHeaders, body: "" });
      return;
    }

    const headers = { ...request.headers() };
    delete headers.host;
    const response = await fetch(`${remoteApiPrefix}${proxiedPath}`, {
      method: request.method(),
      headers,
      body: request.postDataBuffer(),
    });
    const body = Buffer.from(await response.arrayBuffer());
    await route.fulfill({
      status: response.status,
      headers: {
        ...Object.fromEntries(response.headers.entries()),
        ...allowHeaders,
      },
      body,
    });
  });
}

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

async function registerOrBootstrapTenant() {
  return registerOrBootstrapAuditTenant({
    apiUrl,
    platformEmail,
    platformPassword,
    email,
    password,
    companyName: `Shipping Audit ${stamp}`,
    companyCode,
    adminName: "Audit User",
  });
}

async function ensureWarehouseContext(jsonHeaders, authHeaders) {
  let warehouse;
  try {
    warehouse = await callApi("/warehouses/", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        name: `Shipping WH ${stamp}`,
        code: `SWH${stamp.slice(-4)}`,
        timezone: "Europe/Budapest",
      }),
    });
  } catch (error) {
    if (!String(error).includes("plan_limit_exceeded")) throw error;
    warehouse = items(await callApi("/warehouses/", { headers: authHeaders }))[0];
    if (!warehouse) throw error;
  }

  let zone;
  try {
    zone = await callApi(`/warehouses/${warehouse.id}/zones`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ name: `Shipping Zone ${stamp}`, code: `SZ${stamp.slice(-4)}`, sequence: 1 }),
    });
  } catch {
    zone = items(await callApi(`/warehouses/${warehouse.id}/zones`, { headers: authHeaders }))[0];
  }
  if (!zone) throw new Error("No warehouse zone available for shipping audit");

  let location;
  const storageBarcode = `SHIP-STOR-${stamp}`;
  try {
    location = await callApi(`/warehouses/${warehouse.id}/locations`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        zone_id: zone.id,
        barcode: storageBarcode,
        aisle: "SH",
        rack: stamp.slice(-2),
        level: "01",
        position: "01",
        location_type: "storage",
      }),
    });
  } catch {
    location = items(await callApi(`/warehouses/${warehouse.id}/locations`, { headers: authHeaders })).find(
      (item) => item.location_type === "storage",
    );
  }
  if (!location) throw new Error("No storage location available for shipping audit");
  return { warehouse, location };
}

const tenantAuth = await registerOrBootstrapTenant();
const token = tenantAuth.access_token;
const user = tenantAuth.user ?? {
  role: tenantAuth.role,
  tenant_id: tenantAuth.tenant_id,
  permissions: tenantAuth.permissions ?? [],
};
const authHeaders = { Authorization: `Bearer ${token}` };

const { warehouse, location } = await ensureWarehouseContext(
  { ...authHeaders, "Content-Type": "application/json" },
  authHeaders,
);

const client = await callApi("/clients/", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    name: "Shipping Client",
    code: clientCode,
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
    sku_code: skuCode,
    name: "Shipping Audit SKU",
    weight_kg: 1,
    requires_lot: false,
    requires_expiry: false,
  }),
});

await callApi("/data/inventory/manual", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    warehouse_id: warehouse.id,
    location_barcode: location.barcode,
    sku_code: skuCode,
    client_id: client.id,
    quantity: 3,
    lot_number: `LOT-SHIP-${stamp}`,
  }),
});

const order = await callApi("/orders/outbound", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({
    client_id: client.id,
    warehouse_id: warehouse.id,
    order_number: orderNumber,
    reference_number: `REF-SHIP-${stamp}`,
    carrier: "DHL",
    lines: [{ sku_id: sku.id, quantity: 3 }],
  }),
});

await callApi("/fulfillment/pick/allocate", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({ order_id: order.id }),
});
await callApi("/fulfillment/pick/create-tasks", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({ order_id: order.id }),
});

const taskList = await callApi("/tasks/?status=pending&task_type=pick", {
  headers: authHeaders,
});
const pickTask = taskList.find((task) => task.reference_id === order.id);
expect(pickTask, "Pick task not created");

await callApi("/fulfillment/pick/confirm", {
  method: "POST",
  headers: { ...authHeaders, "Content-Type": "application/json" },
  body: JSON.stringify({ task_id: pickTask.id, quantity_picked: 3 }),
});

const pickedOrdersAfterPick = await callApi("/orders/outbound", { headers: authHeaders });
const pickedOrderAfterPick = (pickedOrdersAfterPick || []).find((item) => item.order_number === orderNumber);
expect(
  pickedOrderAfterPick?.status === "picked",
  `Order was not ready for shipping after pick confirmation: ${pickedOrderAfterPick?.status ?? "missing"}`,
);

const browser = await chromium.launch({ headless: true });

const mobilePage = await browser.newPage({
  viewport: { width: 390, height: 844 },
  isMobile: true,
});
await installBrowserApiProxy(mobilePage);
await mobilePage.goto(`${appUrl}/login`, { waitUntil: "domcontentloaded" });
await mobilePage.evaluate(
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
await mobilePage.goto(`${appUrl}/shipping`, { waitUntil: "networkidle" });
const shippingMobileQueuePath = await mobilePage.getByTestId("shipping-mobile-next-action").first().getAttribute("data-shipping-path");
await mobilePage.getByText(orderNumber).first().waitFor({ state: "visible", timeout: 10000 });
await mobilePage.getByText(orderNumber).first().click();
await mobilePage.locator("#shipping-flow").waitFor({ state: "visible", timeout: 10000 });
const shippingMobileActivePath = await mobilePage.getByTestId("shipping-mobile-active-task").first().getAttribute("data-shipping-path");
await mobilePage.getByTestId("shipping-mobile-current-object").first().waitFor({ state: "visible", timeout: 10000 });
await mobilePage.locator("#shipping-pack-scanner-mobile input").first().waitFor({ state: "visible", timeout: 10000 });

const mobileConfirmPackBeforeScan = await mobilePage.locator('[data-testid="shipping-mobile-confirm-pack"]').count();
const mobileScannerBeforeRecovery = await mobilePage.locator("#shipping-pack-scanner-mobile").count();
await mobilePage.locator("#shipping-pack-scanner-mobile input").first().fill(`WRONG-${stamp}`);
await mobilePage.locator("#shipping-pack-scanner-mobile input").first().press("Enter");
const mobileRecoveryPanel = mobilePage.getByTestId("shipping-recovery-panel").first();
await mobileRecoveryPanel.waitFor({ state: "visible", timeout: 10000 });
for (const testId of [
  "shipping-recovery-what-happened",
  "shipping-recovery-why-blocked",
  "shipping-recovery-recommended-action",
  "shipping-recovery-return-entry",
]) {
  await mobilePage.getByTestId(testId).first().waitFor({ state: "visible", timeout: 10000 });
}
await mobilePage.getByTestId("shipping-recovery-safe-exit").first().waitFor({ state: "visible", timeout: 10000 });
const shippingRecoveryStructure = {
  code: await mobileRecoveryPanel.getAttribute("data-recovery-code"),
  action: await mobileRecoveryPanel.getAttribute("data-recovery-action"),
  whatHappened: true,
  whyBlocked: true,
  recommendedAction: true,
  returnEntry: true,
  safeExit: true,
};
const mobileRecoveryActionVisible = await mobilePage.getByTestId("shipping-recovery-action-resetPackCheck").count();
const mobileScannerHiddenDuringRecovery = (await mobilePage.locator("#shipping-pack-scanner-mobile").count()) === 0;
const mobilePackActionHiddenDuringRecovery =
  (await mobilePage.locator('[data-testid="shipping-mobile-confirm-pack"]').count()) === 0;
await mobilePage.getByTestId("shipping-recovery-action-resetPackCheck").first().click();
await mobilePage.locator("#shipping-pack-scanner-mobile").waitFor({ state: "visible", timeout: 10000 });
const mobileScannerRestoredAfterRecovery = (await mobilePage.locator("#shipping-pack-scanner-mobile").count()) > 0;
await mobilePage.close();

const page = await browser.newPage({ viewport: { width: 1440, height: 1400 } });
await installBrowserApiProxy(page);
const outboundOrderResponses = [];
page.on("response", async (response) => {
  if (!response.url().includes("/orders/outbound")) return;
  let body = "";
  try {
    body = (await response.text()).replace(/\s+/g, " ").slice(0, 500);
  } catch {
    body = "<unreadable>";
  }
  outboundOrderResponses.push({
    status: response.status(),
    url: response.url(),
    body,
  });
});

await page.goto(`${appUrl}/login`, { waitUntil: "domcontentloaded" });
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

await page.goto(`${appUrl}/shipping`, { waitUntil: "networkidle" });
const shippingRow = page.locator("tbody tr", { hasText: orderNumber }).first();
try {
  await shippingRow.waitFor({ state: "visible", timeout: 10000 });
} catch {
  const bodySample = (await page.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 700);
  throw new Error(
    `Shipping row for ${orderNumber} was not visible. UI outbound responses: ${JSON.stringify(outboundOrderResponses)} Page body: ${bodySample}`,
  );
}
await shippingRow.click();
await page.waitForTimeout(1000);

const beforePackText = await page.locator("body").innerText();
const hasSuggestedSkuAction = (await page.getByRole("button", { name: new RegExp(skuCode) }).first().count()) > 0;
const hasPackAction =
  hasSuggestedSkuAction || /確認包裝|Confirm packing|Check \d+ more SKU|Scan each SKU once|SKU check/.test(beforePackText);
const hasShipAction = /確認出貨|Confirm shipment/.test(beforePackText);
const layoutDiagnostics = await page.evaluate(() => ({
  overflowX: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
  selectedOrderVisible: /current shipping order|pack and ship one outbound order|selected outbound order|dispatch handoff|出貨交接/i.test(document.body.innerText || ""),
  orderDetailVisible: document.querySelectorAll("table tbody tr").length > 0 || document.body.innerText.includes("OUT-SHIP-"),
}));

await page.getByRole("button", { name: new RegExp(skuCode) }).first().click();
await page.waitForTimeout(250);
const firstScanText = await page.locator("body").innerText();
const singleSkuScanCompletesPackCheck = /Pack check complete|Confirm packing|Checked|Packed 3\/3/.test(firstScanText);

await page.getByRole("button", { name: /確認包裝|Confirm packing/ }).click();
await page.waitForTimeout(1200);
await page.getByTestId("shipping-success-next-step").waitFor({ state: "visible", timeout: 10000 });
const packNextStepText = await page.getByTestId("shipping-success-next-step").innerText();
await page.waitForTimeout(1800);
const packNextStepStillVisible = await page.getByTestId("shipping-success-next-step").isVisible();

await page.locator('[data-testid="shipping-carrier-input"]:visible').fill("DHL");
const trackingScannerInput = page.locator('[data-testid="shipping-tracking-scanner"] input:visible').first();
await trackingScannerInput.waitFor({ state: "visible", timeout: 10000 });
await trackingScannerInput.fill(`TRACK-${stamp}`);
await trackingScannerInput.press("Enter");
await page.waitForTimeout(250);
const trackingScanFilledField =
  (await page.locator('[data-testid="shipping-tracking-input"]:visible').inputValue()) === `TRACK-${stamp}`;
await page.getByRole("button", { name: /確認出貨|Confirm shipment/ }).click();
await page.waitForTimeout(1500);
await page.getByTestId("shipping-success-next-step").waitFor({ state: "visible", timeout: 10000 });
const shipNextStepText = await page.getByTestId("shipping-success-next-step").innerText();
await page.waitForTimeout(1800);
const shipNextStepStillVisible = await page.getByTestId("shipping-success-next-step").isVisible();

const { shippedOrder, shippedSummary } = await pollShipmentState(order.id, orderNumber, authHeaders, `TRACK-${stamp}`);

const result = {
  hasPackAction,
  hasShipAction,
  singleSkuScanCompletesPackCheck,
  packNextStepVisible: nextStepPattern.test(packNextStepText),
  packNextStepStillVisible,
  shipNextStepVisible: nextStepPattern.test(shipNextStepText),
  shipNextStepStillVisible,
  trackingScanFilledField,
  mobileActionSurface: {
    confirmPackBeforeScan: mobileConfirmPackBeforeScan,
    scannerBeforeRecovery: mobileScannerBeforeRecovery,
    recoveryActionVisible: mobileRecoveryActionVisible,
    scannerHiddenDuringRecovery: mobileScannerHiddenDuringRecovery,
    packActionHiddenDuringRecovery: mobilePackActionHiddenDuringRecovery,
    scannerRestoredAfterRecovery: mobileScannerRestoredAfterRecovery,
    recoveryStructure: shippingRecoveryStructure,
    queuePath: shippingMobileQueuePath,
    activePath: shippingMobileActivePath,
  },
  layoutDiagnostics,
  shippedStatus: shippedOrder?.status ?? null,
  trackingNumber: shippedOrder?.tracking_number ?? null,
  summaryStatus: shippedSummary?.status ?? null,
  summaryTracking: shippedSummary?.tracking_number ?? null,
  summaryCarrier: shippedSummary?.carrier ?? null,
};

await browser.close();

console.log(JSON.stringify(result, null, 2));

expect(result.hasPackAction, "Pack action not visible on shipping page");
expect(result.hasShipAction, "Ship action not visible on shipping page");
expect(result.singleSkuScanCompletesPackCheck, "A single SKU scan did not complete the pack check for one SKU line");
expect(result.packNextStepVisible, "Pack success did not show a next-step instruction");
expect(result.packNextStepStillVisible, "Pack success next-step was hidden by refresh/loading state");
expect(result.shipNextStepVisible, "Ship success did not show a next-step instruction");
expect(result.shipNextStepStillVisible, "Ship success next-step was hidden by refresh/loading state");
expect(result.trackingScanFilledField, "Tracking barcode scan did not fill the tracking number field");
expect(result.mobileActionSurface.confirmPackBeforeScan === 0, "Mobile pack confirm action was visible before SKU check completion");
expect(result.mobileActionSurface.scannerBeforeRecovery > 0, "Mobile pack scanner was not visible before recovery");
expect(result.mobileActionSurface.recoveryActionVisible > 0, "Mobile recovery action was not visible after a wrong SKU scan");
expect(result.mobileActionSurface.recoveryStructure.code === "shipping.resetPackCheck", "Shipping recovery did not expose the expected recovery code");
expect(result.mobileActionSurface.recoveryStructure.action === "resetPackCheck", "Shipping recovery did not expose the expected recommended action");
expect(result.mobileActionSurface.recoveryStructure.whatHappened, "Shipping recovery is missing what-happened section");
expect(result.mobileActionSurface.recoveryStructure.whyBlocked, "Shipping recovery is missing why-blocked section");
expect(result.mobileActionSurface.recoveryStructure.recommendedAction, "Shipping recovery is missing recommended-action section");
expect(result.mobileActionSurface.recoveryStructure.returnEntry, "Shipping recovery is missing return-entry section");
expect(result.mobileActionSurface.recoveryStructure.safeExit, "Shipping recovery is missing safe exit");
expect(result.mobileActionSurface.scannerHiddenDuringRecovery, "Mobile scanner stayed visible during active recovery");
expect(result.mobileActionSurface.packActionHiddenDuringRecovery, "Mobile pack action stayed visible during active recovery");
expect(result.mobileActionSurface.scannerRestoredAfterRecovery, "Mobile scanner did not return after recovery reset");
expect(result.mobileActionSurface.queuePath === "pack", `Shipping mobile queue path was not pack: ${result.mobileActionSurface.queuePath}`);
expect(result.mobileActionSurface.activePath === "pack", `Shipping mobile active path was not pack: ${result.mobileActionSurface.activePath}`);
expect(result.layoutDiagnostics.overflowX <= 12, `Shipping page has horizontal overflow: ${result.layoutDiagnostics.overflowX}px`);
expect(result.layoutDiagnostics.selectedOrderVisible, "Selected shipping order panel was not visible");
expect(result.layoutDiagnostics.orderDetailVisible, "Shipping order detail was not visible");
expect(result.shippedStatus === "shipped", "Order did not move to shipped");
expect(result.summaryStatus === "shipped", "Shipment summary did not move to shipped");
expect(result.summaryTracking === `TRACK-${stamp}`, "Tracking number did not persist");
