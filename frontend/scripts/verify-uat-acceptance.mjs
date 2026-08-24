import { chromium } from "playwright";
import { callAuditApi, registerOrBootstrapAuditTenant } from "./audit-tenant-bootstrap.mjs";

const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const appUrl = process.env.WMS_AUDIT_APP_URL ?? "https://app.maxsmartwms.online";
const password = process.env.WMS_AUDIT_PASSWORD ?? "Aaa200058";
const platformEmail = process.env.WMS_AUDIT_PLATFORM_EMAIL;
const platformPassword = process.env.WMS_AUDIT_PLATFORM_PASSWORD;
const today = new Date().toISOString().slice(0, 10);
const defaultBatch = `UAT-${today.replaceAll("-", "")}-01`;
const batch = process.env.WMS_UAT_BATCH ?? defaultBatch;
const stamp = `uat${Date.now().toString().slice(-8)}`;
const companyCode = `UA${stamp}`.slice(0, 12).toUpperCase();
const email = `${stamp}@example.com`;
const companyName = `Acceptance UAT ${batch} Full Flow ${stamp}`;

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

async function api(token, path, options = {}) {
  return callAuditApi(apiUrl, path, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.headers ?? {}),
    },
  });
}

function sumByLocation(items, locationId) {
  return (items ?? [])
    .filter((item) => item.location_id === locationId)
    .reduce((sum, item) => sum + Number(item.quantity_on_hand || 0), 0);
}

async function setSession(page, auth) {
  await page.goto(`${appUrl}/dashboard`, { waitUntil: "domcontentloaded" });
  await page.evaluate(
    ({ token, role, tenantId, permissions }) => {
      localStorage.setItem("wms.language", "en");
      localStorage.setItem("wms_token", token);
      localStorage.setItem("wms_role", role ?? "tenant_admin");
      localStorage.setItem("wms_tenant_id", tenantId ?? "");
      localStorage.setItem("wms_permissions", JSON.stringify(permissions ?? []));
    },
    {
      token: auth.access_token,
      role: auth.user?.role ?? "tenant_admin",
      tenantId: auth.user?.tenant_id ?? "",
      permissions: auth.user?.permissions ?? [],
    },
  );
}

async function pageContains(page, path, needles) {
  await page.goto(`${appUrl}${path}`, { waitUntil: "networkidle" });
  const text = await page.locator("body").innerText();
  return needles.every((needle) => text.includes(needle));
}

async function pickingTaskVisible(page, orderNumber, skuCode) {
  await page.goto(`${appUrl}/picking`, { waitUntil: "networkidle" });
  await page
    .waitForFunction(
      ({ orderNumber, skuCode }) => {
        const text = document.body?.innerText || "";
        return (
          text.includes(orderNumber) ||
          text.includes(skuCode) ||
          Array.from(document.querySelectorAll("button")).some((button) =>
            /Picking Work|Pick tasks|Task queue|Start picking|任務|揀貨工作|工作/i.test(button.textContent || ""),
          )
        );
      },
      { orderNumber, skuCode },
      { timeout: 15000 },
    )
    .catch(() => undefined);

  const taskButtons = page.getByRole("button", {
    name: /Picking Work|Pick tasks|Task queue|Start picking|任務|揀貨工作|工作/i,
  });
  const taskButtonCount = await taskButtons.count();
  for (let index = 0; index < taskButtonCount; index += 1) {
    const taskButton = taskButtons.nth(index);
    if (!(await taskButton.isVisible()) || !(await taskButton.isEnabled())) continue;
    await taskButton.click();
    break;
  }
  await page
    .waitForFunction(
      ({ orderNumber, skuCode }) => {
        const text = document.body?.innerText || "";
        return text.includes(orderNumber) || text.includes(skuCode);
      },
      { orderNumber, skuCode },
      { timeout: 15000 },
    )
    .catch(() => undefined);
  const text = await page.locator("body").innerText();
  return text.includes(orderNumber) || text.includes(skuCode);
}

async function confirmPickInUi(page, orderNumber, skuCode) {
  await page.goto(`${appUrl}/picking`, { waitUntil: "networkidle" });
  const workButton = page.getByRole("button", {
    name: /Picking Work|Pick tasks|Task queue|Start picking|任務|揀貨工作|工作/i,
  }).first();
  if ((await workButton.count()) > 0 && (await workButton.isVisible()) && (await workButton.isEnabled())) {
    await workButton.click();
  }
  await page.waitForFunction(
    ({ orderNumber, skuCode }) => {
      const text = document.body?.innerText || "";
      return text.includes(orderNumber) || text.includes(skuCode) || text.includes("Pick task queue");
    },
    { orderNumber, skuCode },
    { timeout: 15000 },
  );
  const openPickTaskButton = page.getByRole("button", { name: /Open pick task/i }).first();
  if ((await openPickTaskButton.count()) > 0 && (await openPickTaskButton.isVisible())) {
    await openPickTaskButton.click();
  }
  await page.getByRole("button", { name: /Confirm source location/i }).first().click();
  await page.getByRole("button", { name: /Confirm SKU/i }).first().click();
  await page.getByRole("button", { name: /Confirm pick/i }).first().click();
  await page.getByTestId("picking-success-next-step").waitFor({ state: "visible", timeout: 15000 });
  const successText = await page.getByTestId("picking-success-next-step").innerText();
  expect(/Next:/i.test(successText), "picking success state did not show a next-step instruction");
  return true;
}

async function main() {
  const json = { "Content-Type": "application/json" };
  const registration = await registerOrBootstrapAuditTenant({
    apiUrl,
    platformEmail,
    platformPassword,
    email,
    password,
    companyName,
    companyCode,
    adminName: "UAT Full Flow Admin",
    bootstrapPlanCode: "enterprise",
  });
  const token = registration.access_token;

  const consoleErrors = [];
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await setSession(page, registration);

  const pageChecks = {
    dashboard: await pageContains(page, "/dashboard", ["Dashboard"]),
  };

  await api(token, "/tenants/current/settings", {
    method: "PATCH",
    headers: json,
    body: JSON.stringify({
      business_mode: "3pl",
      billing_profile: {
        legal_name: "Acceptance UAT 3PL Ltd.",
        tax_region: "eu",
        vat_id: "HU-UAT-12345678",
        currency: "EUR",
        payment_terms_days: 15,
        payment_terms_label: "Net 15",
        tax_rate_pct: 27,
        tax_label: "VAT",
        billing_email: "billing@example.com",
      },
    }),
  });

  const warehouse = await api(token, "/warehouses/", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      name: "UAT Warehouse",
      code: "UATWH",
      timezone: "Europe/Budapest",
    }),
  });
  const zone = await api(token, `/warehouses/${warehouse.id}/zones`, {
    method: "POST",
    headers: json,
    body: JSON.stringify({ name: "Zone A", code: "A", sequence: 1 }),
  });
  const dock = await api(token, `/warehouses/${warehouse.id}/locations`, {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      zone_id: zone.id,
      barcode: "DOCK-UAT-FULL-01",
      aisle: "DOCK",
      rack: "01",
      level: "00",
      position: "00",
      location_type: "dock",
    }),
  });
  const storage = await api(token, `/warehouses/${warehouse.id}/locations`, {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      zone_id: zone.id,
      barcode: "A-UAT-FULL-01-01",
      aisle: "01",
      rack: "01",
      level: "01",
      position: "01",
      location_type: "storage",
    }),
  });

  const client = await api(token, "/clients/", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      name: "UAT Client",
      code: "UATCL",
      contact_email: email,
      billing_enabled: true,
      portal_access: true,
      settings: {
        billing_profile: {
          legal_name: "UAT Client Kft.",
          tax_region: "eu",
          billing_email: email,
        },
      },
    }),
  });
  const skuA = await api(token, "/skus/", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      client_id: client.id,
      sku_code: "UAT-SKU-A",
      name: "UAT Flour Case",
      weight_kg: 2.5,
      requires_lot: false,
      requires_expiry: false,
    }),
  });
  await api(token, "/skus/", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      client_id: client.id,
      sku_code: "UAT-SKU-B",
      name: "UAT Shortage SKU",
      weight_kg: 1,
      requires_lot: false,
      requires_expiry: false,
    }),
  });
  const rateCard = await api(token, "/billing/rate-cards", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      client_id: client.id,
      name: "UAT Standard Rate Card",
      effective_from: today,
      rules: {
        storage_per_pallet_day: 0.5,
        receiving_per_unit: 0.25,
        pick_per_line: 0.5,
        pick_per_order: 2,
        shipping_handling_per_order: 1.5,
        minimum_monthly: 0,
      },
    }),
  });

  const inbound = await api(token, "/receiving/inbound", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      client_id: client.id,
      warehouse_id: warehouse.id,
      order_number: `${batch}-INB-FULL`,
      reference_number: `${batch}-INB-REF`,
      supplier_name: "UAT Supplier",
      lines: [
        {
          sku_id: skuA.id,
          quantity: 5,
          packages: [
            {
              package_number: 1,
              expected_qty: 2,
              package_type: "carton",
              external_tracking_number: `${batch}-TRK-1`,
              external_carton_mark: `${batch}-CTN-1`,
            },
            {
              package_number: 2,
              expected_qty: 3,
              package_type: "crate",
              external_tracking_number: `${batch}-TRK-2`,
              external_carton_mark: `${batch}-CRT-2`,
            },
          ],
        },
      ],
    }),
  });
  pageChecks.receivingOrderListed = await pageContains(page, "/receiving", [
    `${batch}-INB-FULL`,
  ]);

  await api(token, `/receiving/inbound/${inbound.id}/start-receiving`, { method: "POST" });
  const packages = await api(token, `/receiving/inbound/${inbound.id}/packages`);
  expect(packages.length === 2, `expected 2 packages after start, got ${packages.length}`);
  expect(
    packages.some((pkg) => pkg.external_tracking_number === `${batch}-TRK-1`) &&
      packages.some((pkg) => pkg.external_tracking_number === `${batch}-TRK-2`),
    "prebooked package tracking values did not survive into live receiving",
  );

  for (const pkg of packages) {
    await api(token, `/receiving/inbound/${inbound.id}/packages/${pkg.id}/receive`, {
      method: "POST",
      headers: json,
      body: JSON.stringify({
        quantity_received: pkg.expected_qty,
        quantity_damaged: 0,
        staging_location_id: dock.id,
        pallet_count: pkg.package_type === "crate" ? 1 : 0,
        package_count: 1,
        measured_weight_kg: pkg.package_type === "crate" ? 7.5 : 5,
        measured_length_cm: 40,
        measured_width_cm: 30,
        measured_height_cm: 20,
        receiving_note: `UAT received package ${pkg.package_number}`,
      }),
    });
  }
  const completeReceiving = await api(token, `/receiving/inbound/${inbound.id}/complete`, {
    method: "POST",
  });
  expect(
    completeReceiving.status === "putaway",
    `expected inbound putaway after receiving, got ${completeReceiving.status}`,
  );

  let putawayTasks = await api(token, "/tasks/?status=pending&task_type=putaway");
  putawayTasks = putawayTasks.filter((task) => task.reference_id === inbound.id);
  expect(putawayTasks.length === 2, `expected 2 putaway tasks, got ${putawayTasks.length}`);
  pageChecks.putawayTasksListed = await pageContains(page, "/putaway", ["UAT-SKU-A"]);

  for (const task of putawayTasks) {
    await api(token, "/fulfillment/putaway/confirm", {
      method: "POST",
      headers: json,
      body: JSON.stringify({ task_id: task.id, destination_location_id: storage.id }),
    });
  }
  const inboundCompleted = await api(token, `/order-details/inbound/${inbound.id}`);
  expect(
    inboundCompleted.status === "completed",
    `expected inbound completed, got ${inboundCompleted.status}`,
  );
  const inventoryAfterPutaway = await api(token, "/inventory?page_size=200");
  expect(
    sumByLocation(inventoryAfterPutaway.items, storage.id) === 5,
    "storage qty after putaway should be 5",
  );
  pageChecks.inventoryAfterPutaway = await pageContains(page, "/inventory", ["UAT-SKU-A"]);

  const shortCsv = [
    "order_number,client_code,warehouse_code,sku_code,quantity,reference_number,carrier",
    `${batch}-OUT-SHORT,UATCL,UATWH,UAT-SKU-B,9,${batch}-SHORT-REF,DHL`,
  ].join("\n");
  const shortForm = new FormData();
  shortForm.append("file", new Blob([shortCsv], { type: "text/csv" }), "short.csv");
  await api(token, "/orders/outbound/import-csv", { method: "POST", body: shortForm });
  let outboundOrders = await api(token, "/orders/outbound");
  const shortOrder = outboundOrders.find((row) => row.order_number === `${batch}-OUT-SHORT`);
  expect(shortOrder, "shortage outbound not found");
  const shortageAllocation = await api(token, "/fulfillment/pick/allocate", {
    method: "POST",
    headers: json,
    body: JSON.stringify({ order_id: shortOrder.id }),
  });
  expect(shortageAllocation.fully_allocated === false, "shortage order should not fully allocate");
  let shortageReleaseError = null;
  try {
    await api(token, "/fulfillment/pick/create-tasks", {
      method: "POST",
      headers: json,
      body: JSON.stringify({ order_id: shortOrder.id }),
    });
  } catch (error) {
    shortageReleaseError = String(error.message || error);
  }
  expect(
    shortageReleaseError?.includes("Only allocated outbound orders"),
    "shortage order should not release pick tasks",
  );

  const outboundCsv = [
    "order_number,client_code,warehouse_code,sku_code,quantity,reference_number,carrier",
    `${batch}-OUT-FULL,UATCL,UATWH,UAT-SKU-A,2,${batch}-OUT-REF,DHL`,
  ].join("\n");
  const outboundForm = new FormData();
  outboundForm.append("file", new Blob([outboundCsv], { type: "text/csv" }), "outbound.csv");
  await api(token, "/orders/outbound/import-csv", { method: "POST", body: outboundForm });
  outboundOrders = await api(token, "/orders/outbound");
  const outbound = outboundOrders.find((row) => row.order_number === `${batch}-OUT-FULL`);
  expect(outbound, "normal outbound not found");
  pageChecks.pickingOrderListed = await pageContains(page, "/picking", [`${batch}-OUT-FULL`]);

  const normalAllocation = await api(token, "/fulfillment/pick/allocate", {
    method: "POST",
    headers: json,
    body: JSON.stringify({ order_id: outbound.id }),
  });
  expect(normalAllocation.fully_allocated === true, "normal order should fully allocate");
  const createdPickTasks = await api(token, "/fulfillment/pick/create-tasks", {
    method: "POST",
    headers: json,
    body: JSON.stringify({ order_id: outbound.id }),
  });
  expect(createdPickTasks.task_ids?.length === 1, "normal order should create 1 pick task");
  pageChecks.pickTaskListed = await pickingTaskVisible(page, `${batch}-OUT-FULL`, "UAT-SKU-A");

  const overPick = await api(token, "/fulfillment/pick/confirm", {
    method: "POST",
    headers: json,
    body: JSON.stringify({ task_id: createdPickTasks.task_ids[0], quantity_picked: 99 }),
  });
  expect(
    overPick.success === false,
    `over-pick should be rejected, got ${JSON.stringify(overPick)}`,
  );
  const inventoryAfterRejectedPick = await api(token, "/inventory?page_size=200");
  expect(
    sumByLocation(inventoryAfterRejectedPick.items, storage.id) === 5,
    "rejected over-pick should not change inventory",
  );
  const pickNextStepVisible = await confirmPickInUi(page, `${batch}-OUT-FULL`, "UAT-SKU-A");
  const outboundPicked = await api(token, `/order-details/outbound/${outbound.id}`);
  expect(outboundPicked.status === "picked", `expected picked, got ${outboundPicked.status}`);
  pageChecks.shippingPickedOrderListed = await pageContains(page, "/shipping", [
    `${batch}-OUT-FULL`,
  ]);

  await api(token, "/fulfillment/pack/verify", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      order_id: outbound.id,
      scanned_items: [{ sku_id: skuA.id, quantity: 2 }],
    }),
  });
  const outboundPacked = await api(token, `/order-details/outbound/${outbound.id}`);
  expect(outboundPacked.status === "packed", `expected packed, got ${outboundPacked.status}`);
  await api(token, "/fulfillment/ship/confirm", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      order_id: outbound.id,
      carrier: "DHL",
      tracking_number: `${batch}-TRACK-FULL`,
      service_level: "standard",
    }),
  });
  const outboundShipped = await api(token, `/order-details/outbound/${outbound.id}`);
  expect(outboundShipped.status === "shipped", `expected shipped, got ${outboundShipped.status}`);
  const shippingSummary = await api(token, `/fulfillment/ship/${outbound.id}/summary`);
  expect(
    shippingSummary.tracking_number === `${batch}-TRACK-FULL`,
    "shipping tracking number did not persist",
  );
  const inventoryAfterShip = await api(token, "/inventory?page_size=200");
  expect(
    sumByLocation(inventoryAfterShip.items, storage.id) === 3,
    "storage qty after ship flow should be 3",
  );

  const billingCalc = await api(token, "/billing/calculate", {
    method: "POST",
    headers: json,
    body: JSON.stringify({ client_id: client.id, period_start: today, period_end: today }),
  });
  expect(
    !billingCalc.charges.some((charge) => charge.error),
    `billing calc returned errors: ${JSON.stringify(billingCalc.charges)}`,
  );
  expect(billingCalc.total > 0, "billing total should be > 0");
  const invoice = await api(token, "/billing/invoice", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      client_id: client.id,
      period_id: billingCalc.period_id,
      invoice_number: `INV-${batch}-FULL`,
    }),
  });
  expect(invoice.status === "draft", `expected draft invoice, got ${invoice.status}`);
  const sentInvoice = await api(token, `/billing/invoice/${invoice.invoice_id}/status`, {
    method: "PATCH",
    headers: json,
    body: JSON.stringify({ status: "sent" }),
  });
  expect(sentInvoice.status === "sent", "invoice did not move to sent");
  const paidInvoice = await api(token, `/billing/invoice/${invoice.invoice_id}/status`, {
    method: "PATCH",
    headers: json,
    body: JSON.stringify({ status: "paid" }),
  });
  expect(paidInvoice.status === "paid", "invoice did not move to paid");
  expect(Boolean(paidInvoice.paid_date), "paid invoice did not record paid_date");
  pageChecks.billingInvoiceListed = await pageContains(page, "/billing", [
    `INV-${batch}-FULL`,
  ]);
  pageChecks.clientListed = await pageContains(page, "/clients", ["UAT Client"]);

  await browser.close();

  expect(
    Object.values(pageChecks).every(Boolean),
    `one or more page checks failed: ${JSON.stringify(pageChecks)}`,
  );
  expect(consoleErrors.length === 0, `browser console errors: ${consoleErrors.join(" | ")}`);

  const health = await (await fetch("https://api.maxsmartwms.online/health")).json();
  const result = {
    batch,
    tenant: companyName,
    health,
    setup: { warehouse: warehouse.code, client: client.code, rateCard: rateCard.name },
    receiving: {
      packageCount: packages.length,
      completedStatus: inboundCompleted.status,
      putawayTasks: putawayTasks.length,
    },
    inventory: {
      afterPutaway: sumByLocation(inventoryAfterPutaway.items, storage.id),
      afterRejectedOverPick: sumByLocation(inventoryAfterRejectedPick.items, storage.id),
      afterShipFlow: sumByLocation(inventoryAfterShip.items, storage.id),
    },
    outbound: {
      shortageFullyAllocated: shortageAllocation.fully_allocated,
      shortageReleaseBlocked: Boolean(shortageReleaseError),
      normalFullyAllocated: normalAllocation.fully_allocated,
      overPickRejected: overPick.success === false,
      pickNextStepVisible,
      finalStatus: outboundShipped.status,
      trackingNumberPersisted: shippingSummary.tracking_number === `${batch}-TRACK-FULL`,
    },
    billing: {
      total: billingCalc.total,
      invoiceStatusAfterSend: sentInvoice.status,
      invoiceStatusAfterPaid: paidInvoice.status,
      paidDateRecorded: Boolean(paidInvoice.paid_date),
    },
    pageChecks,
    consoleErrors: consoleErrors.length,
  };

  console.log(JSON.stringify(result, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
