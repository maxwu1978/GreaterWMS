import { chromium } from "playwright";

const appUrl = process.env.WMS_AUDIT_APP_URL ?? "http://127.0.0.1:4173";

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

async function json(route, body, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function setupApiMocks(page) {
  return page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^.*\/api\/v1/, "") || "/";

    if (path === "/agent/settings") {
      return json(route, {
        enabled: true,
        provider_label: "DeepSeek",
        model_name: "deepseek-chat",
        validation_status: "valid",
        allowed_tools: [
          "setup.progress",
          "inventory.search",
          "inventory.explain",
          "orders.inbound.list",
          "billing.rate_cards.list",
          "receiving.inbound.preview_import",
          "receiving.inbound.import_with_mapping",
          "users.create",
          "users.update_permissions",
        ],
        has_api_key: true,
        requires_human_confirmation_for_writes: true,
        tool_catalog: [
          { key: "setup.progress", risk: "low" },
          { key: "inventory.search", risk: "low" },
          { key: "inventory.explain", risk: "low" },
          { key: "orders.inbound.list", risk: "low" },
          { key: "billing.rate_cards.list", risk: "low" },
          { key: "receiving.inbound.preview_import", risk: "low" },
          { key: "receiving.inbound.import_with_mapping", risk: "medium" },
          { key: "users.create", risk: "high" },
          { key: "users.update_permissions", risk: "high" },
        ],
      });
    }

    if (path === "/agent/tools/run" && request.method() === "POST") {
      const payload = request.postDataJSON();
      if (payload?.tool_name === "setup.progress") {
        return json(route, {
          tool_name: "setup.progress",
          risk: "low",
          scope: { tenant_id: "tenant-1", role: "tenant_admin" },
          audit_logged_at: new Date(0).toISOString(),
          result: {
            steps: [
              { name: "warehouse", step: 1, done: true },
              { name: "team", step: 2, done: false },
            ],
          },
        });
      }
      return json(route, {
        tool_name: payload?.tool_name || "inventory.search",
        risk: "low",
        scope: { tenant_id: "tenant-1", role: "tenant_admin" },
        audit_logged_at: new Date(0).toISOString(),
        result: { items: [] },
      });
    }

    if (path.startsWith("/users/") || path === "/users") {
      return json(route, {
        items: [
          {
            id: "user-1",
            email: "operator@warehouse.test",
            full_name: "Warehouse Operator",
            role: "operator",
            job_title: "Receiver",
            permissions: ["receiving.execute", "picking.execute", "shipping.execute"],
            is_active: true,
            client_id: null,
            tenant_id: "tenant-1",
            tenant_name: "Demo Tenant",
          },
        ],
      });
    }

    if (path.startsWith("/clients/") || path === "/clients") {
      return json(route, {
        items: [
          {
            id: "client-1",
            tenant_id: "tenant-1",
            name: "Demo Client",
            code: "DEMO",
            legal_name: "Demo Client LLC",
            contact_email: "billing@client.test",
            contact_phone: "",
            billing_email: "billing@client.test",
            billing_enabled: true,
            billing_currency: "USD",
            billing_tax_id: "",
            billing_payment_terms: "Net 30",
            portal_enabled: false,
            is_active: true,
          },
        ],
      });
    }

    if (path.startsWith("/warehouses/") || path === "/warehouses") {
      if (path.endsWith("/zones")) return json(route, []);
      if (path.endsWith("/locations")) return json(route, []);
      return json(route, {
        items: [
          {
            id: "warehouse-1",
            name: "Budapest Fulfillment",
            code: "BUD",
            timezone: "Europe/Budapest",
            is_active: true,
          },
        ],
      });
    }

    if (path.startsWith("/skus/") || path === "/skus") {
      return json(route, {
        items: [
          {
            id: "sku-1",
            client_id: "client-1",
            sku_code: "SKU-1",
            name: "Demo SKU",
            barcode: "5991234567890",
            weight_kg: 1,
            requires_lot: false,
            requires_expiry: false,
          },
        ],
      });
    }

    if (path === "/billing/rate-cards") {
      return json(route, []);
    }

    if (path.startsWith("/billing/")) {
      return json(route, { items: [] });
    }

    if (path.startsWith("/tenants/") || path === "/tenants") {
      if (path === "/tenants/current/receiving-code-rules") {
        return json(route, {
          prefix: "RCV",
          separator: "-",
          include_order_number: true,
          sequence_padding: 3,
          uppercase: true,
          sample_code: "RCV-INB-001",
        });
      }
      if (path === "/tenants/current/receiving-label-template") {
        return json(route, {
          fields: ["order_number", "sku_code", "expected_qty"],
          show_field_labels: true,
          available_fields: ["order_number", "sku_code", "expected_qty", "tracking_number"],
        });
      }
      if (path === "/tenants/current") {
        return json(route, { id: "tenant-1", name: "Demo Tenant", settings: { business_mode: "3pl" } });
      }
      return json(route, { items: [{ id: "tenant-1", name: "Demo Tenant", code: "DEMO" }] });
    }

    if (path === "/setup/progress") {
      return json(route, {
        steps: [
          { name: "warehouse", title: "Warehouse", done: true },
          { name: "locations", title: "Locations", done: true },
          { name: "client", title: "Client", done: true },
          { name: "skus", title: "SKUs", done: true },
        ],
      });
    }

    return json(route, { items: [] });
  });
}

async function seedAuth(page) {
  await page.addInitScript(() => {
    localStorage.setItem("wms_token", "visual.audit.token");
    localStorage.setItem("wms_role", "tenant_admin");
    localStorage.setItem("wms_tenant_id", "tenant-1");
    localStorage.setItem(
      "wms_permissions",
      JSON.stringify([
        "inbound_orders.manage",
        "inbound_orders.import",
        "receiving.execute",
        "outbound_orders.manage",
        "picking.execute",
        "shipping.execute",
        "master_data.manage",
        "users.manage",
        "billing.manage",
        "planner.manage",
      ]),
    );
  });
}

async function assertVisibleTestId(page, testId, label) {
  const locator = page.getByTestId(testId).first();
  try {
    await locator.waitFor({ state: "visible", timeout: 20000 });
  } catch (error) {
    const bodyText = await page.locator("body").innerText({ timeout: 1000 }).catch(() => "");
    throw new Error(`${label} was not visible at ${page.url()}. Body text: ${bodyText.slice(0, 500)}`, {
      cause: error,
    });
  }
  const text = (await locator.innerText()).trim();
  expect(text.length > 0, `${label} rendered without readable text`);
  return locator;
}

async function assertDetailsClosed(page, testId, label) {
  const locator = await assertVisibleTestId(page, testId, label);
  const isOpen = await locator.evaluate((node) => node instanceof HTMLDetailsElement && node.open);
  expect(!isOpen, `${label} should be collapsed by default`);
}

async function assertNoHorizontalOverflow(page, label) {
  const overflowX = await page.evaluate(() =>
    Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
  );
  expect(overflowX <= 8, `${label} has horizontal overflow: ${overflowX}px`);
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== "0" });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true });
page.on("pageerror", (error) => {
  console.error(`[admin-mobile-visual] page error: ${error.message}`);
});
page.on("console", (message) => {
  if (message.type() === "error") {
    console.error(`[admin-mobile-visual] console error: ${message.text()}`);
  }
});
await setupApiMocks(page);
await seedAuth(page);

await page.goto(`${appUrl}/agent-settings`, { waitUntil: "domcontentloaded" });
await assertVisibleTestId(page, "agent-settings-mobile-governance", "Agent Settings mobile governance");
expect(!(await page.getByTestId("agent-settings-desktop-management").first().isVisible()), "Agent Settings desktop management should be hidden on phone");
await assertNoHorizontalOverflow(page, "Agent Settings mobile");

await page.goto(`${appUrl}/agent-console`, { waitUntil: "domcontentloaded" });
await assertVisibleTestId(page, "agent-console-mobile-governance", "Agent Console mobile governance");
await assertVisibleTestId(page, "agent-console-mobile-import-boundary", "Agent Console mobile import boundary");
await assertDetailsClosed(page, "agent-console-mobile-tool-policy", "Agent Console mobile tool policy");
expect(!(await page.getByTestId("agent-console-desktop-attach-csv").first().isVisible()), "Agent Console CSV upload should not be primary on phone");
expect(!(await page.getByTestId("agent-console-desktop-tool-catalog").first().isVisible()), "Agent Console full tool catalog should be hidden on phone");
await assertNoHorizontalOverflow(page, "Agent Console mobile");

await page.goto(`${appUrl}/users`, { waitUntil: "domcontentloaded" });
await assertVisibleTestId(page, "users-mobile-governance", "Users mobile governance");
await assertDetailsClosed(page, "users-mobile-add-user-collapsed", "Users mobile add-user boundary");
await assertNoHorizontalOverflow(page, "Users mobile");

await page.goto(`${appUrl}/clients`, { waitUntil: "domcontentloaded" });
await assertVisibleTestId(page, "desktop-first-mobile-notice", "Billing settings mobile notice");
await assertNoHorizontalOverflow(page, "Billing settings mobile");

await page.goto(`${appUrl}/warehouses`, { waitUntil: "domcontentloaded" });
await assertVisibleTestId(page, "warehouses-mobile-governance", "Warehouses mobile governance");
await assertDetailsClosed(page, "warehouses-mobile-add-collapsed", "Warehouses mobile add boundary");
await assertNoHorizontalOverflow(page, "Warehouses mobile");

await page.goto(`${appUrl}/skus`, { waitUntil: "domcontentloaded" });
await assertVisibleTestId(page, "desktop-first-mobile-notice", "SKUs mobile governance");
await assertDetailsClosed(page, "skus-mobile-add-collapsed", "SKUs mobile add boundary");
await assertNoHorizontalOverflow(page, "SKUs mobile");

await page.goto(`${appUrl}/receiving-code-settings`, { waitUntil: "domcontentloaded" });
await assertVisibleTestId(page, "receiving-code-mobile-governance", "Receiving code mobile governance");
await assertDetailsClosed(page, "receiving-code-mobile-settings-collapsed", "Receiving code mobile settings boundary");
await assertNoHorizontalOverflow(page, "Receiving code settings mobile");

await page.goto(`${appUrl}/receiving-label-settings`, { waitUntil: "domcontentloaded" });
await assertVisibleTestId(page, "receiving-label-mobile-governance", "Receiving label mobile governance");
await assertDetailsClosed(page, "receiving-label-mobile-settings-collapsed", "Receiving label mobile settings boundary");
await assertNoHorizontalOverflow(page, "Receiving label settings mobile");

await page.goto(`${appUrl}/migration`, { waitUntil: "domcontentloaded" });
await assertVisibleTestId(page, "migration-mobile-governance", "Migration mobile governance");
await assertDetailsClosed(page, "migration-mobile-import-collapsed", "Migration mobile import boundary");
expect(!(await page.getByTestId("migration-desktop-import-workbench").first().isVisible()), "Migration import workbench should be hidden on phone");
await assertNoHorizontalOverflow(page, "Migration mobile");

await browser.close();

console.log(
  JSON.stringify(
    {
      pass: true,
      appUrl,
      checked: [
        "agent-settings",
        "agent-console",
        "users",
        "billing-settings",
        "warehouses",
        "skus",
        "receiving-code-settings",
        "receiving-label-settings",
        "migration",
      ],
    },
    null,
    2,
  ),
);
