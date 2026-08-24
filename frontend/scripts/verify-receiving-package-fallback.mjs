import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "..");
const appUrl = process.env.WMS_AUDIT_APP_URL ?? "http://127.0.0.1:4173";
const shouldStartServer = !process.env.WMS_AUDIT_APP_URL;

const orderId = "ord-fallback";
const warehouseId = "wh-fallback";
const lineId = "line-fallback";
const order = {
  id: orderId,
  warehouse_id: warehouseId,
  order_number: "INB-FALLBACK-001",
  reference_number: "REF-FALLBACK-001",
  status: "receiving",
  archived: false,
  packages_open: 2,
};
const detailPackages = [
  {
    id: "pkg-fallback-1",
    package_number: 1,
    package_type: "carton",
    package_origin: "prebooked",
    status: "expected",
    expected_qty: 3,
    received_qty: 0,
    damaged_qty: 0,
    external_tracking_number: "TRK-FALLBACK-1",
  },
  {
    id: "pkg-fallback-2",
    package_number: 2,
    package_type: "crate",
    package_origin: "prebooked",
    status: "expected",
    expected_qty: 5,
    received_qty: 0,
    damaged_qty: 0,
    external_tracking_number: "TRK-FALLBACK-2",
  },
];
const orderDetail = {
  id: orderId,
  order_number: order.order_number,
  status: "receiving",
  lines: [
    {
      line_id: lineId,
      line_number: 22,
      sku_id: "sku-fallback",
      sku_code: "DAN-FLOUR-020",
      sku_name: "Danube Flour",
      quantity_expected: 8,
      quantity_received: 0,
      packages: detailPackages,
    },
  ],
};

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

function logStep(message) {
  console.error(`[package-fallback] ${message}`);
}

async function waitForServer(url, timeoutMs = 20000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok || response.status < 500) return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function fulfillJson(route, body, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function firstVisibleInputByLabel(page, label) {
  const inputs = page.getByLabel(label);
  const count = await inputs.count();
  for (let index = 0; index < count; index += 1) {
    const input = inputs.nth(index);
    if (await input.isVisible()) return input;
  }
  throw new Error(`No visible input found for label: ${label}`);
}

async function visibleInputValuesByLabel(page, label) {
  const inputs = page.getByLabel(label);
  const values = [];
  const count = await inputs.count();
  for (let index = 0; index < count; index += 1) {
    const input = inputs.nth(index);
    if (await input.isVisible()) values.push(await input.inputValue());
  }
  return values;
}

async function clickOpenPackageForCode(page, code) {
  const button = page.locator(`button[data-receiving-open-package-code="${code}"]`).first();
  if (await button.count()) {
    await Promise.all([
      page.waitForResponse((response) => response.url().includes("/scan-label") && response.request().method() === "POST"),
      button.click(),
    ]);
    return;
  }
  throw new Error(`No visible Open package action found for ${code}`);
}

function selectedScannedPackage(labelCode) {
  const pkg = detailPackages.find(
    (candidate) =>
      candidate.external_tracking_number === labelCode ||
      candidate.external_carton_mark === labelCode ||
      candidate.external_customer_barcode === labelCode,
  );
  if (!pkg) return null;
  return {
    matched_by: "external_tracking_number",
    opened_directly: true,
    scanned_code: labelCode,
    label_code: `RCV-FALLBACK-${String(pkg.package_number).padStart(3, "0")}`,
    label_type: pkg.package_type,
    status: "expected",
    package_id: pkg.id,
    package_number: pkg.package_number,
    package_status: pkg.status,
    expected_qty: pkg.expected_qty,
    received_qty: pkg.received_qty,
    remaining_qty: pkg.expected_qty - pkg.received_qty,
    sku_id: "sku-fallback",
    line_id: lineId,
    lot_number: null,
    external_tracking_number: pkg.external_tracking_number,
    external_carton_mark: null,
    external_customer_barcode: null,
    captured_codes: [],
  };
}

async function installApiMocks(page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathName = url.pathname.replace(/^.*\/api\/v1/, "");
    const method = request.method();

    if (pathName === "/orders/inbound") {
      if (url.searchParams.get("status") === "expected") return fulfillJson(route, []);
      return fulfillJson(route, [order]);
    }
    if (pathName === "/setup/progress") {
      return fulfillJson(route, {
        steps: [
          { name: "warehouse", done: true },
          { name: "locations", done: true },
          { name: "client", done: true },
          { name: "skus", done: true },
        ],
      });
    }
    if (pathName === "/clients/") return fulfillJson(route, { items: [] });
    if (pathName === `/receiving/inbound/${orderId}/labels`) return fulfillJson(route, []);
    if (pathName === `/receiving/inbound/${orderId}/packages`) return fulfillJson(route, []);
    if (pathName === `/order-details/inbound/${orderId}`) return fulfillJson(route, orderDetail);
    if (pathName === "/tenants/current/receiving-label-template") {
      return fulfillJson(route, {
        fields: ["package_number", "sku_code", "expected_qty", "tracking_number"],
        show_field_labels: true,
      });
    }
    if (pathName === `/warehouses/${warehouseId}/locations`) return fulfillJson(route, []);
    if (pathName === `/receiving/inbound/${orderId}/captured-codes`) return fulfillJson(route, []);
    if (pathName === `/receiving/inbound/${orderId}/scan-label` && method === "POST") {
      const payload = request.postDataJSON();
      const scanned = selectedScannedPackage(payload?.label_code || "");
      if (scanned) return fulfillJson(route, scanned);
      return fulfillJson(route, { detail: "Receiving label not found for this inbound order" }, 404);
    }
    if (pathName === "/subscriptions/current") return fulfillJson(route, { plan_code: "starter", status: "active" });

    logStep(`unhandled mock ${method} ${pathName}${url.search}`);
    return fulfillJson(route, {});
  });
}

let serverProcess = null;
if (shouldStartServer) {
  serverProcess = spawn("npm", ["run", "preview", "--", "--host", "127.0.0.1", "--port", "4173"], {
    cwd: frontendDir,
    stdio: ["ignore", "pipe", "pipe"],
  });
  serverProcess.stdout.on("data", (chunk) => process.stderr.write(chunk));
  serverProcess.stderr.on("data", (chunk) => process.stderr.write(chunk));
  await waitForServer(appUrl);
  logStep(`started preview server at ${appUrl}`);
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
  await installApiMocks(page);
  await page.addInitScript(
    ({ nextOrderId }) => {
      localStorage.setItem("wms.language", "en");
      localStorage.setItem("wms_token", "package-fallback-token");
      localStorage.setItem("wms_role", "tenant_admin");
      localStorage.setItem("wms_tenant_id", "tenant-fallback");
      localStorage.setItem("wms_permissions", JSON.stringify(["receiving.execute", "inbound_orders.manage"]));
      sessionStorage.setItem("receiving.selectedOrderId", nextOrderId);
    },
    { nextOrderId: orderId },
  );

  await page.goto(`${appUrl}/receiving`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    () => {
      const text = document.body?.innerText || "";
      return (
        text.includes("Package 1") &&
        text.includes("Package 2") &&
        text.includes("TRK-FALLBACK-1") &&
        text.includes("2 open")
      );
    },
    undefined,
    { timeout: 20000 },
  );
  logStep("package queue rendered packages from order detail fallback");

  const fallbackBody = await page.locator("body").innerText();
  expect(fallbackBody.includes("Package 1"), "Package 1 was not visible");
  expect(fallbackBody.includes("Package 2"), "Package 2 was not visible");
  expect(fallbackBody.includes("DAN-FLOUR-020"), "SKU context from the inbound line was not attached");
  expect(!fallbackBody.includes("No package records exist yet"), "Fallback packages still showed an empty queue");
  expect(!fallbackBody.includes("Add a package before scanning external codes"), "Fallback packages still showed no-package scan guidance");

  await page.goto(`${appUrl}/receiving/orders/${orderId}`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    () => {
      const text = document.body?.innerText || "";
      return text.includes("INB-FALLBACK-001") && text.includes("8 SKU units still need receiving");
    },
    undefined,
    { timeout: 15000 },
  );
  const detailBody = await page.locator("body").innerText();
  expect(detailBody.includes("8 SKU units still need receiving"), "Inbound detail did not surface unreceived SKU units as a blocker");
  expect(!detailBody.includes("Receiving, printing, and putaway are all caught up"), "Inbound detail showed caught-up copy while units were still unreceived");
  logStep("inbound detail blocker summary included unreceived SKU units");

  await page.goto(`${appUrl}/receiving`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    () => {
      const text = document.body?.innerText || "";
      return text.includes("Package 1") && text.includes("TRK-FALLBACK-1");
    },
    undefined,
    { timeout: 15000 },
  );

  await page.getByRole("button", { name: "Add package" }).first().click();
  const optionTexts = await page.locator("select option").allInnerTexts();
  expect(
    optionTexts.some((text) => text.includes("8/8 assigned")),
    "Package editor capacity did not count fallback packages",
  );
  await page.getByRole("button", { name: "Cancel" }).first().click();
  logStep("package editor capacity counted detail fallback packages");

  await clickOpenPackageForCode(page, "TRK-FALLBACK-1");
  await page.waitForFunction(
    () => {
      const text = document.body?.innerText || "";
      return text.includes("RCV-FALLBACK-001") && text.includes("Still to receive");
    },
    undefined,
    { timeout: 15000 },
  );
  logStep("package card action opened the fallback package via its tracking code");

  const receivingFlowBody = await page.locator("body").innerText();
  expect(receivingFlowBody.toLowerCase().includes("suggested code"), "Scanner did not show suggested barcode guidance");
  expect(receivingFlowBody.includes("TRK-FALLBACK-1"), "Scanner did not suggest the first fallback package tracking code");
  const otherCodesButton = page.getByRole("button", { name: /Show other codes/i }).first();
  if (await otherCodesButton.count()) {
    await otherCodesButton.click();
  }
  expect((await page.locator("body").innerText()).includes("TRK-FALLBACK-2"), "Scanner did not suggest the second fallback package tracking code");
  const primaryScanner = page.locator('input[placeholder*="Scan or type"]').first();
  const scannerPlaceholder = await page.locator('input[placeholder*="Scan or type"]').count();
  expect(scannerPlaceholder > 0, "Scanner input did not prompt with the first suggested barcode");

  const receiveNowInput = await firstVisibleInputByLabel(page, "Receive now");
  expect(
    (await visibleInputValuesByLabel(page, "Receive now")).length > 0 ||
      (await visibleInputValuesByLabel(page, "Receive SKU qty")).length > 0,
    "Active package did not expose an editable receive quantity",
  );
  await receiveNowInput.fill("2");
  expect(
    (await visibleInputValuesByLabel(page, "Receive now")).includes("2") ||
      (await visibleInputValuesByLabel(page, "Receive SKU qty")).includes("2"),
    "Active package receive quantity did not update",
  );

  const damagedInput = await firstVisibleInputByLabel(page, "Damaged");
  await damagedInput.fill("1");
  expect(
    (await visibleInputValuesByLabel(page, "Damaged")).includes("1") ||
      (await visibleInputValuesByLabel(page, "Damaged SKU qty")).includes("1"),
    "Active package damaged quantity did not update",
  );
  logStep("active package card exposed editable receipt quantities");

  await primaryScanner.fill("NO-SUCH-FALLBACK");
  await primaryScanner.press("Enter");
  await page.waitForFunction(
    () => {
      const text = document.body?.innerText || "";
      return (
        text.includes("Scan did not match this inbound") &&
        text.includes("NO-SUCH-FALLBACK") &&
        text.includes("Receiving label not found for this inbound order")
      );
    },
    undefined,
    { timeout: 15000 },
  );
  logStep("scanner surfaced the rejected manual code and API error");

  console.log(
    JSON.stringify(
      {
        orderNumber: order.order_number,
        renderedPackageCount: detailPackages.length,
        openedTrackingCode: detailPackages[0].external_tracking_number,
      },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
  if (serverProcess) {
    serverProcess.kill("SIGTERM");
  }
}
