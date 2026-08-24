import { chromium } from "playwright";

const appUrl = process.env.WMS_AUDIT_APP_URL ?? "http://127.0.0.1:4173";

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

function json(route, data, status = 200, headers = {}) {
  return route.fulfill({
    status,
    contentType: "application/json",
    headers,
    body: JSON.stringify(data),
  });
}

function fakeJwt(subject) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ sub: subject, exp: 4102444800 })}.`;
}

const tenantId = "tenant-recovery-clicks";
const userId = "operator-recovery-clicks";
const warehouse = { id: "wh-recovery", name: "Recovery Warehouse", code: "RCV" };
const zone = { id: "zone-recovery", warehouse_id: warehouse.id, name: "Zone A", code: "A" };
const sourceLocation = {
  id: "loc-source",
  warehouse_id: warehouse.id,
  zone_id: zone.id,
  barcode: "MOCK-STAGE-01",
  aisle: "STAGE",
  rack: "01",
  level: "00",
  position: "01",
  location_type: "staging",
  current_status: "occupied",
};
const storageLocation = {
  id: "loc-storage",
  warehouse_id: warehouse.id,
  zone_id: zone.id,
  barcode: "MOCK-STOR-01",
  aisle: "A",
  rack: "01",
  level: "01",
  position: "01",
  location_type: "storage",
  current_status: "available",
};
const client = { id: "client-recovery", name: "Recovery Client", code: "RC" };
const sku = {
  id: "sku-recovery",
  client_id: client.id,
  sku_code: "REC-SKU-01",
  barcode: "REC-SKU-01",
  name: "Recovery SKU",
};
const putawayTask = {
  id: "task-putaway-recovery",
  tenant_id: tenantId,
  warehouse_id: warehouse.id,
  task_type: "putaway",
  status: "pending",
  priority: 5,
  sku_id: sku.id,
  sku_code: sku.sku_code,
  quantity: 4,
  source_location_id: sourceLocation.id,
  source_barcode: sourceLocation.barcode,
  reference_type: "inbound_order",
  reference_id: "inbound-recovery",
  inbound_order_number: "INB-RECOVERY",
  handling_unit_code: "HU-RECOVERY-01",
  assigned_type: "unassigned",
};
const pickTask = {
  id: "task-pick-recovery",
  warehouse_id: warehouse.id,
  task_type: "pick",
  status: "pending",
  assigned_type: "unassigned",
  assigned_to: null,
  sku_id: sku.id,
  sku_code: sku.sku_code,
  sku_barcode: sku.sku_code,
  quantity: 2,
  source_location_id: storageLocation.id,
  source_location_barcode: storageLocation.barcode,
  reference_type: "outbound_order",
  reference_id: "outbound-recovery",
};
const missingScanPickTask = {
  ...pickTask,
  id: "task-pick-missing-scan",
  source_location_id: null,
  source_location_barcode: null,
  sku_barcode: null,
  sku_code: "",
};
let useMissingScanTask = false;
let putawayConfirmMode = "destination_blocked";
let pickingConfirmMode = "quantity_rejected";

async function installApiMocks(page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^.*\/api\/v1/, "") || "/";
    const taskType = url.searchParams.get("task_type");
    const status = url.searchParams.get("status");

    if (path === "/setup/progress") {
      return json(route, {
        steps: ["warehouse", "locations", "client", "skus", "billing", "team"].map((name) => ({
          name,
          done: true,
        })),
      });
    }
    if (path === "/clients/") return json(route, { items: [client] });
    if (path === "/skus/") return json(route, [sku]);
    if (path === "/warehouses/") return json(route, [warehouse]);
    if (path === `/warehouses/${warehouse.id}/zones`) return json(route, [zone]);
    if (path === `/warehouses/${warehouse.id}/locations`) {
      return json(route, [sourceLocation, storageLocation]);
    }
    if (path === `/warehouses/${warehouse.id}/planner-rules`) return json(route, {});
    if (path === "/inventory/") {
      return json(route, [
        {
          id: "inv-recovery",
          warehouse_id: warehouse.id,
          location_id: sourceLocation.id,
          sku_id: sku.id,
          quantity_on_hand: 4,
          quantity_allocated: 0,
        },
      ]);
    }
    if (path === "/orders/inbound") return json(route, []);
    if (path === "/orders/outbound") {
      return json(
        route,
        [{ id: "outbound-recovery", order_number: "OUT-RECOVERY", status: "picking" }],
        200,
        { "X-Has-More": "false", "X-Offset": "0", "X-Limit": "50", "X-Returned-Count": "1" },
      );
    }
    if (path === "/workbench-summaries/putaway") {
      return json(route, {
        pending_tasks: 1,
        pending_units: 4,
        by_assigned_type: { unassigned: 1, human: 0, agv: 0 },
      });
    }
    if (path === "/workbench-summaries/picking") {
      return json(route, {
        by_status: { pending: 0, allocated: 0, picking: 1 },
        active_pick_tasks: 1,
      });
    }
    if (path === "/fulfillment/putaway/suggest-location") {
      return json(route, [
        {
          location_id: storageLocation.id,
          barcode: storageLocation.barcode,
          reason: "empty_available",
          rank: 1,
        },
      ]);
    }
    if (path === "/fulfillment/putaway/confirm") {
      if (putawayConfirmMode === "task_not_ready") {
        return json(route, {
          success: false,
          detail: {
            error_code: "putaway_task_not_pending",
            message: "Putaway task is completed; only pending tasks can be confirmed",
          },
        });
      }
      return json(route, {
        success: false,
        error_code: "putaway_destination_blocked",
        detail: {
          error_code: "putaway_destination_blocked",
          message: "Selected destination is blocked and cannot receive putaway stock",
        },
        error: "Selected destination is blocked and cannot receive putaway stock",
      });
    }
    if (path === "/fulfillment/pick/confirm") {
      if (pickingConfirmMode === "task_not_available") {
        return json(route, {
          success: false,
          detail: {
            error_code: "pick_task_not_found",
            message: "Pick task was not found",
          },
          task_id: pickTask.id,
        });
      }
      return json(route, {
        success: false,
        error_code: "pick_quantity_exceeds_reserved",
        detail: {
          error_code: "pick_quantity_exceeds_reserved",
          message: "quantity_picked (2) exceeds reserved quantity (1)",
        },
        error: "quantity_picked (2) exceeds reserved quantity (1)",
        task_id: pickTask.id,
      });
    }
    if (path === "/tasks/") {
      if (taskType === "putaway") return json(route, [putawayTask]);
      if (taskType === "pick" && status === "pending") return json(route, [useMissingScanTask ? missingScanPickTask : pickTask]);
      if (taskType === "pick") return json(route, []);
      return json(route, []);
    }

    return json(route, {});
  });
}

async function setSession(page) {
  await page.goto(`${appUrl}/dashboard`, { waitUntil: "domcontentloaded" });
  await page.evaluate(
    ({ token, tenantId }) => {
      localStorage.setItem("wms.language", "en");
      localStorage.setItem("wms_token", token);
      localStorage.setItem("wms_role", "tenant_admin");
      localStorage.setItem("wms_tenant_id", tenantId);
      localStorage.setItem("wms_permissions", JSON.stringify(["*"]));
    },
    { token: fakeJwt(userId), tenantId },
  );
}

async function verifyPutawayRecovery(page) {
  putawayConfirmMode = "destination_blocked";
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${appUrl}/putaway`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Putaway Work/i }).click();
  await page.getByTestId("putaway-mobile-primary-action").waitFor({ state: "visible" });
  expect(
    (await page.getByTestId("putaway-mobile-primary-action").count()) === 1,
    "Putaway mobile should expose exactly one primary action",
  );
  const primaryAction = await page.getByTestId("putaway-mobile-primary-action").getAttribute("data-putaway-primary-action");
  const primaryPath = await page.getByTestId("putaway-mobile-primary-action").getAttribute("data-putaway-path");
  expect(primaryAction === "use_recommended_slot", `Unexpected putaway mobile primary action: ${primaryAction}`);
  expect(primaryPath === "recommended", `Unexpected putaway mobile path: ${primaryPath}`);
  await page.getByTestId("putaway-mobile-manual-slot").waitFor({ state: "visible" });
  expect(
    !(await page.getByTestId("putaway-mobile-manual-slot").evaluate((node) => node instanceof HTMLDetailsElement && node.open)),
    "Putaway mobile manual slot controls should be collapsed by default",
  );

  await page.setViewportSize({ width: 1440, height: 1200 });
  await page.goto(`${appUrl}/putaway`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Putaway Work/i }).click();
  await page.getByRole("button", { name: /MOCK-STOR-01/ }).first().click();
  await page.getByRole("button", { name: /Confirm putaway/i }).click();
  await page.getByTestId("putaway-recovery-panel").waitFor({ state: "visible" });
  const firstRecovery = await page.getByTestId("putaway-recovery-panel").evaluate((node) => ({
    code: node.getAttribute("data-recovery-code"),
    action: node.getAttribute("data-recovery-action"),
    safeExit: node.getAttribute("data-recovery-safe-exit"),
  }));
  expect(firstRecovery.code === "putaway.putaway_destination_blocked", `Unexpected putaway recovery code: ${firstRecovery.code}`);
  expect(firstRecovery.action === "choose_slot", `Unexpected putaway recovery action: ${firstRecovery.action}`);
  expect(Boolean(firstRecovery.safeExit), "Putaway recovery did not expose a safe exit");
  for (const testId of [
    "putaway-recovery-what-happened",
    "putaway-recovery-why-blocked",
    "putaway-recovery-recommended-action",
    "putaway-recovery-return-entry",
  ]) {
    await page.getByTestId(testId).waitFor({ state: "visible" });
  }
  await page.getByTestId("putaway-recovery-action-choose_slot").click();
  await page.getByTestId("putaway-recovery-panel").waitFor({ state: "detached" });

  await page.getByRole("button", { name: /Putaway Work/i }).click();
  await page.getByRole("button", { name: /MOCK-STOR-01/ }).first().click();
  await page.getByRole("button", { name: /Confirm putaway/i }).click();
  await page.getByTestId("putaway-recovery-panel").waitFor({ state: "visible" });
  await page.getByTestId("putaway-recovery-action-back_to_list").click();
  await page.getByText(/Putaway priority|Pending putaway tasks/i).first().waitFor({ state: "visible" });

  putawayConfirmMode = "task_not_ready";
  await page.getByRole("button", { name: /Putaway Work/i }).click();
  await page.getByRole("button", { name: /MOCK-STOR-01/ }).first().click();
  await page.getByRole("button", { name: /Confirm putaway/i }).click();
  await page.getByTestId("putaway-recovery-panel").waitFor({ state: "visible" });
  const refreshRecovery = await page.getByTestId("putaway-recovery-panel").evaluate((node) => ({
    code: node.getAttribute("data-recovery-code"),
    action: node.getAttribute("data-recovery-action"),
    safeExit: node.getAttribute("data-recovery-safe-exit"),
  }));
  expect(refreshRecovery.code === "putaway.putaway_task_not_pending", `Unexpected putaway refresh recovery code: ${refreshRecovery.code}`);
  expect(refreshRecovery.action === "refresh_task", `Unexpected putaway refresh action: ${refreshRecovery.action}`);
  expect(refreshRecovery.safeExit === "refresh_task", `Unexpected putaway refresh safe exit: ${refreshRecovery.safeExit}`);
  await page.getByTestId("putaway-recovery-action-refresh_task").click();
  await page.getByTestId("putaway-recovery-panel").waitFor({ state: "detached" });
}

async function verifyPickingRecovery(page) {
  useMissingScanTask = false;
  pickingConfirmMode = "quantity_rejected";
  await page.goto(`${appUrl}/picking`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Picking Work/i }).first().click();
  await page.getByRole("button", { name: /Open pick task/i }).click();
  await page.getByRole("button", { name: /Confirm source location/i }).click();
  await page.getByRole("button", { name: /Confirm SKU/i }).click();
  await page.getByRole("button", { name: /Confirm pick/i }).click();
  await page.getByTestId("picking-recovery-panel").waitFor({ state: "visible" });
  const firstRecovery = await page.getByTestId("picking-recovery-panel").evaluate((node) => ({
    code: node.getAttribute("data-recovery-code"),
    action: node.getAttribute("data-recovery-action"),
    safeExit: node.getAttribute("data-recovery-safe-exit"),
  }));
  expect(firstRecovery.code === "picking.pick_quantity_exceeds_reserved", `Unexpected picking recovery code: ${firstRecovery.code}`);
  expect(firstRecovery.action === "adjust_quantity", `Unexpected picking recovery action: ${firstRecovery.action}`);
  expect(Boolean(firstRecovery.safeExit), "Picking recovery did not expose a safe exit");
  for (const testId of [
    "picking-recovery-what-happened",
    "picking-recovery-why-blocked",
    "picking-recovery-recommended-action",
    "picking-recovery-return-entry",
  ]) {
    await page.getByTestId(testId).waitFor({ state: "visible" });
  }
  await page.getByTestId("picking-recovery-action-adjust_quantity").click();
  await page.getByTestId("picking-recovery-panel").waitFor({ state: "detached" });

  await page.getByRole("button", { name: /Confirm pick/i }).click();
  await page.getByTestId("picking-recovery-panel").waitFor({ state: "visible" });
  await page.getByTestId("picking-recovery-action-back_to_list").click();
  await page.getByRole("button", { name: /Open pick task/i }).waitFor({ state: "visible" });

  pickingConfirmMode = "task_not_available";
  await page.getByRole("button", { name: /Open pick task/i }).click();
  await page.getByRole("button", { name: /Confirm source location/i }).click();
  await page.getByRole("button", { name: /Confirm SKU/i }).click();
  await page.getByRole("button", { name: /Confirm pick/i }).click();
  await page.getByTestId("picking-recovery-panel").waitFor({ state: "visible" });
  const refreshRecovery = await page.getByTestId("picking-recovery-panel").evaluate((node) => ({
    code: node.getAttribute("data-recovery-code"),
    action: node.getAttribute("data-recovery-action"),
    safeExit: node.getAttribute("data-recovery-safe-exit"),
  }));
  expect(refreshRecovery.code === "picking.pick_task_not_found", `Unexpected picking refresh recovery code: ${refreshRecovery.code}`);
  expect(refreshRecovery.action === "refresh_tasks", `Unexpected picking refresh action: ${refreshRecovery.action}`);
  expect(refreshRecovery.safeExit === "refresh_tasks", `Unexpected picking refresh safe exit: ${refreshRecovery.safeExit}`);
  await page.getByTestId("picking-recovery-action-refresh_tasks").click();
  await page.getByTestId("picking-recovery-panel").waitFor({ state: "detached" });
}

async function verifyPickingMissingScanRecovery(page) {
  useMissingScanTask = true;
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${appUrl}/picking`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Picking Work/i }).first().click();
  await page.getByRole("button", { name: /Open pick task/i }).click();
  const activeTask = page.getByTestId("picking-mobile-active-task");
  await activeTask.waitFor({ state: "visible" });
  await page.getByTestId("picking-mobile-current-object").waitFor({ state: "visible" });
  expect(
    (await activeTask.getAttribute("data-picking-path")) === "exception",
    `Unexpected picking active path: ${await activeTask.getAttribute("data-picking-path")}`,
  );
  await page.getByTestId("picking-recovery-panel").waitFor({ state: "visible" });
  const recovery = await page.getByTestId("picking-recovery-panel").evaluate((node) => ({
    code: node.getAttribute("data-recovery-code"),
    action: node.getAttribute("data-recovery-action"),
    safeExit: node.getAttribute("data-recovery-safe-exit"),
  }));
  expect(recovery.code === "picking.missing_scan_code", `Unexpected missing-scan recovery code: ${recovery.code}`);
  expect(recovery.action === "back_to_list", `Unexpected missing-scan recovery action: ${recovery.action}`);
  expect(Boolean(recovery.safeExit), "Picking missing-scan recovery did not expose a safe exit");
  for (const testId of [
    "picking-recovery-what-happened",
    "picking-recovery-why-blocked",
    "picking-recovery-recommended-action",
    "picking-recovery-return-entry",
  ]) {
    await page.getByTestId(testId).waitFor({ state: "visible" });
  }
  useMissingScanTask = false;
  await page.setViewportSize({ width: 1440, height: 1200 });
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
const consoleErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => consoleErrors.push(error.message));

try {
  await installApiMocks(page);
  await setSession(page);
  await verifyPutawayRecovery(page);
  await verifyPickingRecovery(page);
  await verifyPickingMissingScanRecovery(page);
  expect(consoleErrors.length === 0, `Console errors found: ${consoleErrors.join("\n")}`);
  console.error("[verify] recovery action clicks passed");
} finally {
  await browser.close();
}
