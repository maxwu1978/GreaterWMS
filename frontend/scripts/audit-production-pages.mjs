import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";
import { registerOrBootstrapAuditTenant } from "./audit-tenant-bootstrap.mjs";

const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const appUrl = process.env.WMS_AUDIT_APP_URL ?? "https://app.maxsmartwms.online";
const language = process.env.WMS_AUDIT_LANGUAGE ?? "en";
const testPassword = process.env.WMS_AUDIT_TEST_PASSWORD ?? "Aaa200058";
const platformEmail = process.env.WMS_AUDIT_PLATFORM_EMAIL;
const platformPassword = process.env.WMS_AUDIT_PLATFORM_PASSWORD;
const screenshotDir =
  process.env.WMS_AUDIT_SCREENSHOT_DIR ?? `/tmp/wms-production-page-audit-${Date.now()}`;

const desktop = { width: 1440, height: 1000 };
const mobile = { width: 390, height: 844 };
const stamp = `layout${Date.now().toString().slice(-8)}`;

async function callApi(pathname, options = {}) {
  const response = await fetch(`${apiUrl}${pathname}`, options);
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!response.ok) {
    throw new Error(`${pathname} -> ${response.status} ${JSON.stringify(data)}`);
  }
  return data;
}

async function login(email, password) {
  const data = await callApi("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return {
    access_token: data.access_token,
    user: {
      email,
      role: data.role ?? data.user?.role,
      tenant_id: data.tenant_id ?? data.user?.tenant_id,
      permissions: data.permissions ?? data.user?.permissions ?? [],
      client_id: data.client_id ?? data.user?.client_id ?? null,
      job_title: data.job_title ?? data.user?.job_title ?? null,
    },
  };
}

async function registerTenant() {
  const email = `${stamp}@example.com`;
  const companyCode = `LY${stamp}`.slice(0, 12).toUpperCase();
  return registerOrBootstrapAuditTenant({
    apiUrl,
    platformEmail,
    platformPassword,
    email,
    password: testPassword,
    companyName: `Layout Audit ${stamp}`,
    companyCode,
    adminName: "Layout Audit Admin",
  });
}

function authHeaders(auth) {
  return { Authorization: `Bearer ${auth.access_token}` };
}

async function seedTenant(auth) {
  const headers = authHeaders(auth);
  const jsonHeaders = { ...headers, "Content-Type": "application/json" };

  let warehouse;
  try {
    warehouse = await callApi("/warehouses/", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        name: `Layout Audit Warehouse ${stamp}`,
        code: `LWH${stamp.slice(-4)}`,
        timezone: "Europe/Budapest",
      }),
    });
  } catch (error) {
    if (!/plan_limit|limit|allows up to/i.test(String(error))) throw error;
    const warehousePayload = await callApi("/warehouses/", { headers });
    const warehouseItems = Array.isArray(warehousePayload)
      ? warehousePayload
      : warehousePayload.items || [];
    warehouse = warehouseItems[0];
    if (!warehouse) throw new Error("No existing warehouse available for layout audit");
  }
  let zone;
  try {
    zone = await callApi(`/warehouses/${warehouse.id}/zones`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ name: `Layout Zone ${stamp}`, code: `LZ${stamp.slice(-4)}`, sequence: 1 }),
    });
  } catch {
    zone = (await callApi(`/warehouses/${warehouse.id}/zones`, { headers }))[0];
  }
  if (!zone) throw new Error("No zone available for layout audit");
  const locationPayloads = [
    {
      barcode: `STG-${stamp}`,
      aisle: "STG",
      rack: "01",
      level: "00",
      position: "00",
      location_type: "staging",
    },
    {
      barcode: `A-01-01-01-${stamp.slice(-2)}`,
      aisle: "01",
      rack: "01",
      level: "01",
      position: stamp.slice(-2),
      location_type: "storage",
    },
  ];
  const locations = [];
  for (const payload of locationPayloads) {
    try {
      locations.push(
        await callApi(`/warehouses/${warehouse.id}/locations`, {
          method: "POST",
          headers: jsonHeaders,
          body: JSON.stringify({ zone_id: zone.id, ...payload }),
        }),
      );
    } catch {
      const existingLocations = await callApi(`/warehouses/${warehouse.id}/locations`, { headers });
      const fallback = existingLocations.find((item) => item.location_type === payload.location_type);
      if (fallback) locations.push(fallback);
    }
  }

  const client = await callApi("/clients/", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      name: "Layout Audit Client",
      code: `LCL${stamp.slice(-6)}`,
      contact_email: `${stamp}@example.com`,
      billing_enabled: true,
      portal_access: true,
    }),
  });
  const sku = await callApi("/skus/", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      client_id: client.id,
      sku_code: `LAY-SKU-${stamp}`,
      name: "Layout Audit SKU",
      weight_kg: 1,
      requires_lot: false,
      requires_expiry: false,
    }),
  });

  const inbound = await callApi("/receiving/inbound", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      warehouse_id: warehouse.id,
      client_id: client.id,
      order_number: `INB-${stamp}`,
      reference_number: `REF-${stamp}`,
      lines: [
        {
          sku_id: sku.id,
          quantity: 3,
          external_tracking_number: `TRK-${stamp}`,
          external_carton_mark: `CTN-${stamp}`,
        },
      ],
    }),
  });

  return { warehouse, zone, locations, client, sku, inbound };
}

async function maybeCreateClientViewer(auth, client) {
  const email = `${stamp}.portal@example.com`;
  try {
    await callApi("/users/", {
      method: "POST",
      headers: { ...authHeaders(auth), "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        full_name: "Layout Portal User",
        password: testPassword,
        role: "client_viewer",
        client_id: client.id,
      }),
    });
    return await login(email, testPassword);
  } catch (error) {
    return { error: String(error) };
  }
}

async function seedAuth(page, auth) {
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
      role: auth.user?.role,
      tenantId: auth.user?.tenant_id,
      permissions: auth.user?.permissions ?? [],
    },
  );
}

function pageDiagnostics() {
  const doc = document.documentElement;
  const body = document.body;
  const text = body?.innerText?.trim() ?? "";
  const overflowX = Math.max(0, doc.scrollWidth - doc.clientWidth);
  const viewportWidth = window.innerWidth;
  const offenders = [];
  for (const el of Array.from(document.querySelectorAll("body *"))) {
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) continue;
    if (rect.right > viewportWidth + 8 || rect.left < -8) {
      offenders.push({
        tag: el.tagName.toLowerCase(),
        className: String(el.className || "").slice(0, 80),
        text: String(el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 90),
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        width: Math.round(rect.width),
      });
    }
    if (offenders.length >= 8) break;
  }
  const blockingText = /internal server error|application error|cannot read properties|is not a function/i.test(
    text,
  );
  return {
    title: document.title,
    path: window.location.pathname,
    textLength: text.length,
    overflowX,
    offenders,
    blockingText,
    bodySample: text.slice(0, 300).replace(/\s+/g, " "),
  };
}

async function auditOne(browser, route, viewport, auth = null) {
  const page = await browser.newPage({ viewport });
  const consoleErrors = [];
  const failedResponses = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text().slice(0, 300));
  });
  page.on("response", (response) => {
    const status = response.status();
    if (status >= 500) failedResponses.push(`${status} ${response.url()}`);
  });
  if (auth) await seedAuth(page, auth);

  await page.goto(`${appUrl}${route.path}`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(route.waitMs ?? 1800);
  const diagnostics = await page.evaluate(pageDiagnostics);
  const widthLabel = viewport.width < 600 ? "mobile" : "desktop";
  const failures = [];

  if (failedResponses.length) failures.push(`server responses: ${failedResponses.join("; ")}`);
  if (diagnostics.textLength < (route.minTextLength ?? 40)) {
    failures.push(`page looked empty (${diagnostics.textLength} chars)`);
  }
  if (diagnostics.blockingText) failures.push("blocking error text appeared in page body");
  if (diagnostics.overflowX > (route.maxOverflowX ?? 12)) {
    failures.push(`page horizontal overflow ${diagnostics.overflowX}px`);
  }

  const result = {
    label: route.label,
    route: route.path,
    viewport: widthLabel,
    finalPath: diagnostics.path,
    ok: failures.length === 0,
    failures,
    consoleErrors,
    failedResponses,
    diagnostics,
  };

  if (!result.ok) {
    await fs.mkdir(screenshotDir, { recursive: true });
    const safeName = `${widthLabel}-${route.label.replace(/[^a-z0-9]+/gi, "-")}.png`;
    result.screenshot = path.join(screenshotDir, safeName);
    await page.screenshot({ path: result.screenshot, fullPage: true });
  }

  await page.close();
  return result;
}

async function main() {
  const tenantAuth = await registerTenant();
  const seeded = await seedTenant(tenantAuth);
  const portalAuth = await maybeCreateClientViewer(tenantAuth, seeded.client);
  const platformAuth =
    platformEmail && platformPassword ? await login(platformEmail, platformPassword) : null;

  const publicRoutes = [
    { label: "landing", path: "/" },
    { label: "login", path: "/login" },
    { label: "register", path: "/register" },
    { label: "forgot-password", path: "/forgot-password" },
    { label: "reset-password", path: "/reset-password" },
  ];
  const tenantRoutes = [
    { label: "dashboard", path: "/dashboard" },
    { label: "receiving", path: "/receiving", waitMs: 2600 },
    { label: "receiving-detail", path: `/receiving/orders/${seeded.inbound.id}`, waitMs: 2600 },
    { label: "putaway", path: "/putaway", waitMs: 2600 },
    { label: "inventory", path: "/inventory" },
    { label: "picking", path: "/picking" },
    { label: "shipping", path: "/shipping" },
    { label: "billing", path: "/billing" },
    { label: "billing-settings", path: "/billing-settings" },
    { label: "receiving-code-settings", path: "/receiving-code-settings" },
    { label: "receiving-label-settings", path: "/receiving-label-settings" },
    { label: "warehouses", path: "/warehouses" },
    { label: "clients", path: "/clients" },
    { label: "skus", path: "/skus" },
    { label: "migration", path: "/migration" },
    { label: "agent-console", path: "/agent-console" },
    { label: "agent-settings", path: "/agent-settings" },
    { label: "users", path: "/users" },
    { label: "warehouse-planner", path: "/warehouse-planner", waitMs: 2600 },
    { label: "setup", path: "/setup" },
    { label: "agv", path: "/agv" },
    { label: "pricing", path: "/pricing" },
    { label: "subscription", path: "/subscription" },
  ];
  const portalRoutes =
    "access_token" in portalAuth
      ? [
          { label: "portal-dashboard", path: "/portal/dashboard" },
          { label: "portal-inventory", path: "/portal/inventory" },
          { label: "portal-orders", path: "/portal/orders" },
          { label: "portal-invoices", path: "/portal/invoices" },
        ]
      : [];
  const platformRoutes = platformAuth
    ? [
        { label: "platform-users", path: "/users", waitMs: 2600 },
        { label: "platform-workspaces", path: "/workspaces", waitMs: 2600 },
        { label: "platform-dashboard-redirect", path: "/dashboard", waitMs: 1200 },
      ]
    : [];

  const browser = await chromium.launch({ headless: true });
  const results = [];

  for (const route of publicRoutes) {
    results.push(await auditOne(browser, route, desktop));
    results.push(await auditOne(browser, route, mobile));
  }
  for (const route of tenantRoutes) {
    results.push(await auditOne(browser, route, desktop, tenantAuth));
    results.push(await auditOne(browser, route, mobile, tenantAuth));
  }
  for (const route of portalRoutes) {
    results.push(await auditOne(browser, route, desktop, portalAuth));
    results.push(await auditOne(browser, route, mobile, portalAuth));
  }
  for (const route of platformRoutes) {
    results.push(await auditOne(browser, route, desktop, platformAuth));
    results.push(await auditOne(browser, route, mobile, platformAuth));
  }

  await browser.close();

  const failures = results.filter((result) => !result.ok);
  const consoleErrorCount = results.reduce((count, result) => count + result.consoleErrors.length, 0);
  const summary = {
    stamp,
    appUrl,
    apiUrl,
    checkedPages: results.length,
    failures: failures.length,
    consoleErrorCount,
    portalAudit: "access_token" in portalAuth ? "checked" : `skipped: ${portalAuth.error}`,
    platformAudit: platformAuth ? "checked" : "skipped: credentials not provided",
    screenshotDir: failures.length ? screenshotDir : null,
    failedRoutes: failures.map((result) => ({
      label: result.label,
      route: result.route,
      viewport: result.viewport,
      failures: result.failures,
      offenders: result.diagnostics.offenders,
      screenshot: result.screenshot,
    })),
  };

  console.log(JSON.stringify({ summary, results }, null, 2));
  if (failures.length) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
