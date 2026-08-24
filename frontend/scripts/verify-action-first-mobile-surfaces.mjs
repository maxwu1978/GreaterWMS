import { chromium } from "playwright";
import { registerOrBootstrapAuditTenant } from "./audit-tenant-bootstrap.mjs";

const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const appUrl = process.env.WMS_AUDIT_APP_URL ?? "https://app.maxsmartwms.online";
const language = process.env.WMS_AUDIT_LANGUAGE ?? "en";
const password = process.env.WMS_AUDIT_PASSWORD || "Aaa200058";
const platformEmail = process.env.WMS_AUDIT_PLATFORM_EMAIL;
const platformPassword = process.env.WMS_AUDIT_PLATFORM_PASSWORD;
const stamp = `actmob${Date.now().toString().slice(-7)}`;

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

function logStep(message) {
  console.error(`[action-mobile] ${message}`);
}

async function prepareTenant() {
  return registerOrBootstrapAuditTenant({
    apiUrl,
    platformEmail,
    platformPassword,
    email: `${stamp}@example.com`,
    password,
    companyName: `Action Mobile ${stamp}`,
    companyCode: `AM${stamp}`.slice(0, 12).toUpperCase(),
    adminName: "Action Mobile Admin",
  });
}

async function seedClientState(page, auth) {
  await page.goto(`${appUrl}/login`, { waitUntil: "domcontentloaded" });
  await page.evaluate(
    ({ nextLanguage, token, role, tenantId, permissions }) => {
      localStorage.setItem("wms.language", nextLanguage);
      localStorage.setItem("wms_token", token);
      localStorage.setItem("wms_role", role ?? "tenant_admin");
      if (tenantId) localStorage.setItem("wms_tenant_id", tenantId);
      localStorage.setItem("wms_permissions", JSON.stringify(permissions ?? []));
    },
    {
      nextLanguage: language,
      token: auth.access_token,
      role: auth.user?.role ?? auth.role ?? "tenant_admin",
      tenantId: auth.user?.tenant_id ?? auth.tenant_id ?? "",
      permissions: auth.user?.permissions ?? auth.permissions ?? [],
    },
  );
}

async function assertVisibleTestId(page, testId, label) {
  const locator = page.getByTestId(testId).first();
  await locator.waitFor({ state: "visible", timeout: 20000 });
  const text = (await locator.innerText()).trim();
  expect(text.length > 0, `${label} rendered without readable text`);
  return text;
}

async function assertNoHorizontalOverflow(page, label) {
  const overflowX = await page.evaluate(() =>
    Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
  );
  expect(overflowX <= 8, `${label} has horizontal overflow: ${overflowX}px`);
}

async function assertDetailsClosed(page, testId, label) {
  const locator = page.getByTestId(testId).first();
  await locator.waitFor({ state: "visible", timeout: 20000 });
  const isOpen = await locator.evaluate((node) => node instanceof HTMLDetailsElement && node.open);
  expect(!isOpen, `${label} should be collapsed by default`);
}

const auth = await prepareTenant();
logStep("prepared tenant");

const browser = await chromium.launch({ headless: process.env.HEADLESS !== "0" });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true });
await seedClientState(page, auth);

await page.goto(`${appUrl}/dashboard`, { waitUntil: "domcontentloaded" });
const dashboardText = await assertVisibleTestId(page, "dashboard-mobile-next-work", "Dashboard next work");
const dashboardObjectText = await assertVisibleTestId(page, "dashboard-mobile-current-object", "Dashboard current object");
const dashboardQuestionText = await assertVisibleTestId(page, "dashboard-mobile-current-question", "Dashboard current question");
const whyNowText = await assertVisibleTestId(page, "dashboard-mobile-why-now", "Dashboard why now");
const dashboardPrimaryAction = page.getByTestId("dashboard-mobile-primary-action").first();
await dashboardPrimaryAction.waitFor({ state: "visible", timeout: 20000 });
const dashboardRecommendation = await page.getByTestId("dashboard-mobile-next-work").first().evaluate((node) => ({
  route: node.getAttribute("data-recommended-route"),
  key: node.getAttribute("data-recommended-key"),
  priority: node.getAttribute("data-recommended-priority"),
  contract: node.getAttribute("data-mobile-primary-contract"),
}));
expect(/start here|finish setup|no live work|receiving|putaway|picking|shipping/i.test(dashboardText), "Dashboard mobile next-work card is not action-oriented");
expect(dashboardObjectText.length >= 3, "Dashboard mobile current object is missing");
expect(/what should i do next|current question/i.test(dashboardQuestionText), "Dashboard mobile current question is missing");
expect(whyNowText.length >= 12, "Dashboard why-now text is too short to explain the action");
expect(
  ["/receiving", "/putaway", "/picking", "/inventory", "/setup"].some((route) => dashboardRecommendation.route?.startsWith(route)),
  `Dashboard mobile recommendation route is not a known execution route: ${dashboardRecommendation.route}`,
);
expect(Boolean(dashboardRecommendation.key), "Dashboard mobile recommendation did not expose a stable recommendation key");
expect(dashboardRecommendation.contract === "single-next-work", "Dashboard mobile did not expose the single-next-work contract");
expect(Number(dashboardRecommendation.priority || 0) > 0, "Dashboard mobile recommendation did not expose a positive priority");
expect((await page.getByTestId("dashboard-mobile-primary-action").count()) === 1, "Dashboard mobile should expose exactly one primary action");
expect(await dashboardPrimaryAction.isVisible(), "Dashboard mobile primary action is not visible");
await assertDetailsClosed(page, "dashboard-mobile-secondary-work", "Dashboard secondary work queues");
await assertNoHorizontalOverflow(page, "Dashboard mobile");
logStep("verified dashboard next-work surface");

await page.goto(`${appUrl}/inventory`, { waitUntil: "domcontentloaded" });
const inventoryText = await assertVisibleTestId(page, "inventory-mobile-primary-task", "Inventory mobile primary task");
const inventoryObject = await assertVisibleTestId(page, "inventory-mobile-current-object", "Inventory current object");
const inventoryQuestion = await assertVisibleTestId(page, "inventory-mobile-current-question", "Inventory current question");
const inventoryPrimaryAction = page.getByTestId("inventory-mobile-recommended-action").first();
await inventoryPrimaryAction.waitFor({ state: "visible", timeout: 20000 });
const inventoryAction = await inventoryPrimaryAction.getAttribute("data-recommended-action");
const inventoryPath = await inventoryPrimaryAction.getAttribute("data-inventory-path");
const inventoryContract = await page.getByTestId("inventory-mobile-primary-task").first().getAttribute("data-mobile-primary-contract");
expect(inventoryObject.length >= 3, "Inventory mobile current object is missing");
expect(/question:/i.test(inventoryQuestion), "Inventory mobile surface does not state the current question");
expect(/next:/i.test(inventoryQuestion), "Inventory mobile surface does not state the next action");
expect(/inventory lookup|find stock|setup needed|check one record|clear staging|blocked stock|allocated stock/i.test(inventoryText), "Inventory mobile surface is not lookup/count oriented");
expect(inventoryContract === "single-record-lookup", "Inventory mobile did not expose the single-record lookup contract");
expect(
  ["setup", "staging", "blocked", "allocated", "record", "available", "empty"].includes(inventoryAction || ""),
  `Inventory mobile recommended action is not stable: ${inventoryAction}`,
);
expect(
  ["lookup", "record", "exception"].includes(inventoryPath || ""),
  `Inventory mobile path is not stable: ${inventoryPath}`,
);
if (["staging", "blocked", "allocated"].includes(inventoryAction || "")) {
  expect(inventoryPath === "exception", `Inventory ${inventoryAction} action should use exception path`);
}
if (inventoryAction === "record") {
  expect(inventoryPath === "record", "Inventory record action should use record path");
}
if (["setup", "available", "empty"].includes(inventoryAction || "")) {
  expect(inventoryPath === "lookup", `Inventory ${inventoryAction} action should use lookup path`);
}
expect((await page.getByTestId("inventory-mobile-recommended-action").count()) === 1, "Inventory mobile should expose exactly one primary action");
await assertDetailsClosed(page, "inventory-mobile-secondary-controls", "Inventory secondary controls");
await assertDetailsClosed(page, "inventory-mobile-record-list", "Inventory alternate record list");
await assertNoHorizontalOverflow(page, "Inventory mobile");
logStep("verified inventory lookup surface");

await page.goto(`${appUrl}/putaway`, { waitUntil: "domcontentloaded" });
await assertDetailsClosed(page, "putaway-mobile-queue-options", "Putaway mobile queue options");
await assertNoHorizontalOverflow(page, "Putaway mobile");
logStep("verified putaway mobile queue surface");

await page.goto(`${appUrl}/picking`, { waitUntil: "domcontentloaded" });
const pickingMobileAction = await assertVisibleTestId(page, "picking-mobile-next-action", "Picking mobile next action");
const pickingPath = await page.getByTestId("picking-mobile-next-action").first().getAttribute("data-picking-path");
expect(/next action|picking work|no picking action|allocate|pick/i.test(pickingMobileAction), "Picking mobile next action is not action-oriented");
expect(["allocate", "scan", "exception"].includes(pickingPath || ""), `Picking mobile path is not stable: ${pickingPath}`);
await assertDetailsClosed(page, "picking-mobile-queue-counts", "Picking mobile queue counts");
await assertNoHorizontalOverflow(page, "Picking mobile");
logStep("verified picking mobile queue surface");

await page.goto(`${appUrl}/shipping`, { waitUntil: "domcontentloaded" });
const shippingMobileAction = await assertVisibleTestId(page, "shipping-mobile-next-action", "Shipping mobile next action");
const shippingPath = await page.getByTestId("shipping-mobile-next-action").first().getAttribute("data-shipping-path");
expect(/next action|pack|ship|handoff|no shipping action/i.test(shippingMobileAction), "Shipping mobile next action is not action-oriented");
expect(["pack", "handoff", "exception"].includes(shippingPath || ""), `Shipping mobile path is not stable: ${shippingPath}`);
await assertDetailsClosed(page, "shipping-mobile-queue-counts", "Shipping mobile queue counts");
await assertNoHorizontalOverflow(page, "Shipping mobile");
logStep("verified shipping mobile queue surface");

for (const route of ["/billing", "/clients", "/skus"]) {
  await page.goto(`${appUrl}${route}`, { waitUntil: "domcontentloaded" });
  const notice = await assertVisibleTestId(page, "desktop-first-mobile-notice", `${route} desktop-first notice`);
  expect(/management workspace|desktop|ipad/i.test(notice), `${route} notice does not steer complex work to desktop/iPad`);
  await assertNoHorizontalOverflow(page, `${route} mobile`);
  logStep(`verified desktop-first mobile notice on ${route}`);
}

await browser.close();

console.log(
  JSON.stringify(
    {
      pass: true,
      appUrl,
      tenant: auth.tenant_id ?? auth.user?.tenant_id ?? null,
      checked: ["dashboard", "inventory", "putaway", "picking", "shipping", "billing", "clients", "skus"],
    },
    null,
    2,
  ),
);
