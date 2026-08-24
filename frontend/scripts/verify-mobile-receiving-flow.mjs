import { chromium, devices } from "playwright";
import { callAuditApi, registerOrBootstrapAuditTenant } from "./audit-tenant-bootstrap.mjs";

const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const appUrl = process.env.WMS_AUDIT_APP_URL ?? "https://app.maxsmartwms.online";
const language = process.env.WMS_AUDIT_LANGUAGE ?? "en";
const password = process.env.WMS_AUDIT_PASSWORD || "Aaa200058";
const platformEmail = process.env.WMS_AUDIT_PLATFORM_EMAIL;
const platformPassword = process.env.WMS_AUDIT_PLATFORM_PASSWORD;
const stamp = `mob${Date.now().toString().slice(-8)}`;
const tracking = `TRK-${stamp}`;

function logStep(message) {
  console.error(`[mobile-uat] ${message}`);
}

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

async function callApi(pathname, token, options = {}) {
  return callAuditApi(apiUrl, pathname, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.headers ?? {}),
    },
  });
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
        if (typeof value === "string") sessionStorage.setItem(key, value);
      });
    },
    {
      nextLanguage: language,
      token: auth.access_token,
      role: auth.user?.role ?? auth.role ?? "tenant_admin",
      tenantId: auth.user?.tenant_id ?? auth.tenant_id ?? "",
      permissions: auth.user?.permissions ?? auth.permissions ?? [],
      nextSessionState: sessionState,
    },
  );
}

async function installApiProxy(page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const apiPath = url.pathname.replace(/^.*\/api\/v1/, "");
    const targetUrl = `${apiUrl}${apiPath}${url.search}`;
    const headers = await request.allHeaders();
    delete headers.host;
    delete headers.origin;
    delete headers.referer;

    const response = await fetch(targetUrl, {
      method: request.method(),
      headers,
      body: request.postDataBuffer() ?? undefined,
    });
    const body = Buffer.from(await response.arrayBuffer());
    await route.fulfill({
      status: response.status,
      headers: Object.fromEntries(response.headers.entries()),
      body,
    });
  });
}

async function prepareTenant() {
  const email = `${stamp}@example.com`;
  return registerOrBootstrapAuditTenant({
    apiUrl,
    platformEmail,
    platformPassword,
    email,
    password,
    companyName: `Mobile UAT ${stamp}`,
    companyCode: `MU${stamp}`.slice(0, 12).toUpperCase(),
    adminName: "Mobile UAT Admin",
  });
}

async function seedReceivingWork(auth) {
  const token = auth.access_token;
  const jsonHeaders = { "Content-Type": "application/json" };

  const warehouse = await callApi("/warehouses/", token, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      name: `Mobile Warehouse ${stamp}`,
      code: `MWH${stamp.slice(-5)}`.slice(0, 12).toUpperCase(),
      timezone: "Europe/Budapest",
    }),
  });
  const zone = await callApi(`/warehouses/${warehouse.id}/zones`, token, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ name: `Mobile Zone ${stamp}`, code: `MZ${stamp.slice(-4)}`, sequence: 1 }),
  });
  const dockLocation = await callApi(`/warehouses/${warehouse.id}/locations`, token, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      zone_id: zone.id,
      barcode: `DOCK-${stamp}`,
      aisle: "DOCK",
      rack: "01",
      level: "00",
      position: "00",
      location_type: "dock",
    }),
  });
  const client = await callApi("/clients/", token, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      name: "Mobile UAT Client",
      code: `MCL${stamp.slice(-6)}`,
      contact_email: `${stamp}@example.com`,
      billing_enabled: true,
      portal_access: true,
    }),
  });
  const sku = await callApi("/skus/", token, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      client_id: client.id,
      sku_code: `MOB-SKU-${stamp}`,
      name: "Mobile UAT SKU",
      weight_kg: 1,
      requires_lot: false,
      requires_expiry: false,
    }),
  });
  const inbound = await callApi("/receiving/inbound", token, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      warehouse_id: warehouse.id,
      client_id: client.id,
      order_number: `INB-${stamp}`,
      reference_number: `REF-${stamp}`,
      lines: [{ sku_id: sku.id, quantity: 2 }],
    }),
  });
  await callApi(`/receiving/inbound/${inbound.id}/start-receiving`, token, { method: "POST" });
  const detail = await callApi(`/order-details/inbound/${inbound.id}`, token);
  const line = detail.lines[0];
  const createdPackage = await callApi(`/receiving/inbound/${inbound.id}/packages`, token, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      line_id: line.line_id,
      expected_qty: 2,
      package_type: "carton",
      external_tracking_number: tracking,
      external_carton_mark: `CTN-${stamp}`,
    }),
  });
  const packageList = await callApi(`/receiving/inbound/${inbound.id}/packages`, token);
  const pkg =
    (Array.isArray(packageList) ? packageList : packageList.items || []).find((item) => item.id === createdPackage.id) ||
    createdPackage;

  return { warehouse, dockLocation, inbound, pkg };
}

const auth = await prepareTenant();
logStep("prepared verified mobile tenant");
const seeded = await seedReceivingWork(auth);
logStep(`seeded inbound ${seeded.inbound.order_number}`);

const browser = await chromium.launch({ headless: process.env.HEADLESS !== "0" });
const context = await browser.newContext({
  ...devices["iPhone 14 Pro Max"],
  locale: "en-US",
});
const page = await context.newPage();
await installApiProxy(page);

await setClientState(page, auth, {
  "receiving.selectedOrderId": seeded.inbound.id,
  "receiving.lastActiveOrder": JSON.stringify({ id: seeded.inbound.id, status: "receiving" }),
});

await page.goto(`${appUrl}/receiving?orderId=${seeded.inbound.id}`, { waitUntil: "domcontentloaded" });
await page.waitForFunction(
  ({ orderNumber }) => (document.body?.innerText || "").includes(orderNumber),
  { orderNumber: seeded.inbound.order_number },
  { timeout: 20000 },
);
logStep("opened receiving on mobile viewport");

const initialLayout = await page.evaluate(() => ({
  overflowX: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
  text: document.body?.innerText || "",
}));
expect(initialLayout.overflowX <= 8, `Mobile receiving has horizontal overflow before scan: ${initialLayout.overflowX}px`);
expect(initialLayout.text.includes("Step 1") && initialLayout.text.includes("Scan"), "Mobile receiving did not show the first scan step.");

const scanInput = page.getByPlaceholder(/scan|type/i).first();
await scanInput.fill(`WRONG-${stamp}`);
await scanInput.press("Enter");
const receivingRecoveryPanel = page.getByTestId("receiving-recovery-panel").first();
await receivingRecoveryPanel.waitFor({ state: "visible", timeout: 10000 });
const receivingRecovery = await receivingRecoveryPanel.evaluate((node) => ({
  code: node.getAttribute("data-recovery-code"),
  action: node.getAttribute("data-recovery-action"),
  safeExit: node.getAttribute("data-recovery-safe-exit"),
}));
expect(receivingRecovery.code === "receiving.scan_no_match", `Unexpected receiving recovery code: ${receivingRecovery.code}`);
expect(receivingRecovery.action === "clear_scan", `Unexpected receiving recovery action: ${receivingRecovery.action}`);
expect(Boolean(receivingRecovery.safeExit), "Receiving recovery did not expose a safe exit");
for (const testId of [
  "receiving-recovery-what-happened",
  "receiving-recovery-why-blocked",
  "receiving-recovery-recommended-action",
  "receiving-recovery-return-entry",
]) {
  await page.getByTestId(testId).first().waitFor({ state: "visible", timeout: 10000 });
}
await page.getByTestId("receiving-recovery-action-clear_scan").first().click();
await receivingRecoveryPanel.waitFor({ state: "detached", timeout: 10000 });

await scanInput.fill(tracking);
await scanInput.press("Enter");
await page.waitForFunction(
  ({ packageNumber }) => {
    const text = document.body?.innerText || "";
    return text.includes(`Package ${packageNumber}`) && text.includes("Dock / staging");
  },
  { packageNumber: seeded.pkg.package_number ?? 1 },
  { timeout: 20000 },
);
logStep("matched package from manual tracking code");

await page.waitForFunction(
  ({ dockBarcode, dockLocationId }) => {
    const text = document.body?.innerText || "";
    const visibleSelect = Array.from(document.querySelectorAll("select")).some((select) => {
      const rect = select.getBoundingClientRect();
      return (
        rect.width > 0 &&
        rect.height > 0 &&
        Array.from(select.options).some(
          (option) => option.value === dockLocationId || option.textContent?.includes(dockBarcode),
        )
      );
    });
    return text.includes(dockBarcode) || visibleSelect;
  },
  { dockBarcode: seeded.dockLocation.barcode, dockLocationId: String(seeded.dockLocation.id) },
  { timeout: 15000 },
);

const dockAlreadySurfaced = (await page.locator("body").innerText()).includes(seeded.dockLocation.barcode);
if (!dockAlreadySurfaced) {
  const selectedDock = await page.evaluate((dockLocationId) => {
    const visibleSelects = Array.from(document.querySelectorAll("select")).filter((select) => {
      const rect = select.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    });
    const dockSelect = visibleSelects.find((select) =>
      Array.from(select.options).some((option) => option.value === dockLocationId),
    );
    if (!dockSelect) return false;
    dockSelect.value = dockLocationId;
    dockSelect.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }, String(seeded.dockLocation.id));
  expect(selectedDock, "Dock/staging selector was not visible or auto-selected on mobile.");
}

const afterScanLayout = await page.evaluate((dockBarcode) => {
  const text = document.body?.innerText || "";
  return {
    overflowX: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
    text,
    buttons: Array.from(document.querySelectorAll("button"))
      .filter((button) => {
        const rect = button.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      })
      .map((button) => button.textContent?.trim())
      .filter(Boolean),
    optionalDetailsVisible:
      text.includes("Optional packaging, dimensions, and note") ||
      text.includes("More fields"),
    receiptActionVisible:
      text.includes("Confirm receipt") ||
      Array.from(document.querySelectorAll("button")).some((button) =>
        /Step 4 · Confirm receipt|Confirm Package \d+ receipt|Confirm this package receipt/i.test(
          button.textContent || "",
        ),
      ),
    fullMeasurementHeadingVisible: Array.from(document.querySelectorAll("p")).some((node) => {
      const rect = node.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 && node.textContent?.includes("Physical measurements");
    }),
    dockMentioned: text.includes(dockBarcode),
  };
}, seeded.dockLocation.barcode);
expect(afterScanLayout.overflowX <= 8, `Mobile receiving has horizontal overflow after scan: ${afterScanLayout.overflowX}px`);
expect(
  afterScanLayout.text.toLowerCase().includes("current package"),
  `Mobile receiving did not keep current package identity visible. Snapshot: ${afterScanLayout.text.slice(0, 600)}`,
);
expect(
  afterScanLayout.text.toLowerCase().includes("still to receive"),
  `Mobile receiving did not keep remaining quantity visible. Snapshot: ${afterScanLayout.text.slice(0, 600)}`,
);
expect(
  afterScanLayout.optionalDetailsVisible || afterScanLayout.receiptActionVisible,
  "Mobile receiving did not show optional receipt details or the confirm action.",
);
expect(!afterScanLayout.fullMeasurementHeadingVisible, "Full measurement section is still visible by default on mobile.");
expect(afterScanLayout.dockMentioned, "Dock/staging location was not surfaced near the active mobile package.");

const checkQuantityButton = page.getByRole("button", { name: /Check quantity/i });
if (await checkQuantityButton.count()) {
  await checkQuantityButton.first().click();
  await page.waitForFunction(() => (document.body?.innerText || "").includes("Check received quantity"), undefined, {
    timeout: 10000,
  });
}

const damagedQuantityInput = page.locator('input[aria-label="Damaged SKU qty"]:visible').first();
if (await damagedQuantityInput.count()) {
  await damagedQuantityInput.fill("3");
  await page.locator("button:visible").filter({ hasText: /Continue to confirm/i }).first().click();
  await page.waitForFunction(
    () => (document.body?.innerText || "").includes("Damaged quantity cannot exceed the received quantity."),
    undefined,
    { timeout: 10000 },
  );
  await damagedQuantityInput.fill("0");
  logStep("validated mobile damaged quantity feedback");
}

const continueToConfirmButton = page.locator("button:visible").filter({ hasText: /Continue to confirm/i });
if (await continueToConfirmButton.count()) {
  await continueToConfirmButton.first().click();
  await page.waitForFunction(() => (document.body?.innerText || "").includes("Confirm this receipt"), undefined, {
    timeout: 10000,
  });
}

await page
  .getByRole("button", { name: /Step 4 · Confirm receipt|Confirm Package \d+ receipt|Confirm this package receipt/i })
  .click();
await page.waitForFunction(() => {
  const text = (document.body?.innerText || "").toLowerCase();
  return text.includes("just confirmed") || text.includes("confirmed internal labels") || text.includes("print this internal label");
}, undefined, { timeout: 20000 });
await page.waitForFunction(() => {
  const text = document.body?.innerText || "";
  return text.includes("Step 4 · Package confirmed");
}, undefined, { timeout: 20000 });
await page.waitForFunction(() => {
  const text = document.body?.innerText || "";
  const success = document.querySelector('[data-testid="receiving-mobile-success-next-step"]');
  return Boolean(success) && /Next:/i.test(text);
}, undefined, { timeout: 20000 });
logStep("confirmed receipt from mobile surface");

const afterConfirmLayout = await page.evaluate(() => {
  const text = document.body?.innerText || "";
  return {
    text,
    overflowX: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
    stepOneStillActive: text.includes("Step 1 · Scan or type the package code"),
    confirmedTitleVisible: text.includes("Step 4 · Package confirmed"),
    nextStepVisible: /Next:/i.test(text),
    scanPromptVisible: text.includes("Scan or type the package code"),
  };
});
expect(afterConfirmLayout.overflowX <= 8, `Mobile receiving has horizontal overflow after confirm: ${afterConfirmLayout.overflowX}px`);
expect(afterConfirmLayout.confirmedTitleVisible, "Mobile receiving did not show the package-confirmed Step 4 state.");
expect(afterConfirmLayout.nextStepVisible, "Mobile receiving success state did not show a next-step instruction.");
expect(!afterConfirmLayout.stepOneStillActive, "Mobile receiving returned to Step 1 immediately after confirming receipt.");

const result = {
  pass: true,
  appUrl,
  orderNumber: seeded.inbound.order_number,
  packageNumber: seeded.pkg.package_number ?? 1,
  tracking,
  dockBarcode: seeded.dockLocation.barcode,
  receivingRecovery,
  buttonsAfterScan: afterScanLayout.buttons,
  confirmedTitleVisible: afterConfirmLayout.confirmedTitleVisible,
  nextStepVisibleAfterConfirm: afterConfirmLayout.nextStepVisible,
  scanPromptVisibleAfterConfirm: afterConfirmLayout.scanPromptVisible,
};

await browser.close();
console.log(JSON.stringify(result, null, 2));
