import { registerOrBootstrapAuditTenant } from "./audit-tenant-bootstrap.mjs";

const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const password = process.env.WMS_AUDIT_TEST_PASSWORD ?? "Aaa200058";
const platformEmail = process.env.WMS_AUDIT_PLATFORM_EMAIL;
const platformPassword = process.env.WMS_AUDIT_PLATFORM_PASSWORD;
const stamp = `pack${Date.now().toString().slice(-8)}`;
const email = `${stamp}@example.com`;
const companyCode = `PK${stamp}`.slice(0, 12).toUpperCase();
const skuCodeA = `PACK-A-${stamp}`;
const skuCodeB = `PACK-B-${stamp}`;
const clientCode = `PCL${stamp.slice(-6)}`;

function items(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.items)) return payload.items;
  return [];
}

function expect(condition, message) {
  if (!condition) throw new Error(message);
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

async function callApiRaw(path, options = {}) {
  const response = await fetch(`${apiUrl}${path}`, options);
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  return { status: response.status, ok: response.ok, data };
}

async function registerOrBootstrapTenant() {
  return registerOrBootstrapAuditTenant({
    apiUrl,
    platformEmail,
    platformPassword,
    email,
    password,
    companyName: `Pack Completeness ${stamp}`,
    companyCode,
    adminName: "Pack Audit Admin",
  });
}

async function ensureWarehouseContext(jsonHeaders, authHeaders) {
  let warehouse;
  try {
    warehouse = await callApi("/warehouses/", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        name: `Pack Warehouse ${stamp}`,
        code: `PKWH${stamp.slice(-4)}`,
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
      body: JSON.stringify({ name: `Pack Zone ${stamp}`, code: `PZ${stamp.slice(-4)}`, sequence: 1 }),
    });
  } catch {
    zone = items(await callApi(`/warehouses/${warehouse.id}/zones`, { headers: authHeaders }))[0];
  }
  if (!zone) throw new Error("No warehouse zone available for pack audit");

  let location;
  const storageBarcode = `PK-STOR-${stamp}`;
  try {
    location = await callApi(`/warehouses/${warehouse.id}/locations`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        zone_id: zone.id,
        barcode: storageBarcode,
        aisle: "PK",
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
  if (!location) throw new Error("No storage location available for pack audit");
  return { warehouse, zone, location };
}

async function main() {
  const tenantLogin = await registerOrBootstrapTenant();
  const authHeaders = { Authorization: `Bearer ${tenantLogin.access_token}` };
  const jsonHeaders = { ...authHeaders, "Content-Type": "application/json" };

  const { warehouse, location } = await ensureWarehouseContext(jsonHeaders, authHeaders);
  const client = await callApi("/clients/", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      name: "Pack Client",
      code: clientCode,
      contact_email: email,
      billing_enabled: true,
      portal_access: true,
    }),
  });
  const skuA = await callApi("/skus/", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      client_id: client.id,
      sku_code: skuCodeA,
      name: "Pack SKU A",
      weight_kg: 1,
      requires_lot: false,
      requires_expiry: false,
    }),
  });
  const skuB = await callApi("/skus/", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      client_id: client.id,
      sku_code: skuCodeB,
      name: "Pack SKU B",
      weight_kg: 1,
      requires_lot: false,
      requires_expiry: false,
    }),
  });

  await callApi("/data/inventory/manual", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      warehouse_id: warehouse.id,
      location_barcode: location.barcode,
      sku_code: skuCodeA,
      client_id: client.id,
      quantity: 8,
      lot_number: `LOT-A-${stamp}`,
    }),
  });
  await callApi("/data/inventory/manual", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      warehouse_id: warehouse.id,
      location_barcode: location.barcode,
      sku_code: skuCodeB,
      client_id: client.id,
      quantity: 8,
      lot_number: `LOT-B-${stamp}`,
    }),
  });

  const earlyOrder = await callApi("/orders/outbound", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      client_id: client.id,
      warehouse_id: warehouse.id,
      order_number: `OUT-EARLY-${stamp}`,
      reference_number: `REF-EARLY-${stamp}`,
      lines: [{ sku_id: skuA.id, quantity: 1 }],
    }),
  });
  const earlyPack = await callApiRaw("/fulfillment/pack/verify", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      order_id: earlyOrder.id,
      scanned_items: [{ sku_id: skuA.id, quantity: 1 }],
    }),
  });
  expect(earlyPack.status === 409, `pack-before-pick should return 409, got ${earlyPack.status}`);

  const order = await callApi("/orders/outbound", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      client_id: client.id,
      warehouse_id: warehouse.id,
      order_number: `OUT-PACK-${stamp}`,
      reference_number: `REF-PACK-${stamp}`,
      carrier: "DHL",
      lines: [
        { sku_id: skuA.id, quantity: 2 },
        { sku_id: skuB.id, quantity: 3 },
      ],
    }),
  });

  const allocation = await callApi("/fulfillment/pick/allocate", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ order_id: order.id }),
  });
  expect(
    allocation.fully_allocated === true,
    `outbound order was not fully allocated: ${JSON.stringify(allocation)}`,
  );

  const taskCreate = await callApi("/fulfillment/pick/create-tasks", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ order_id: order.id }),
  });
  expect(taskCreate.task_ids?.length === 2, "two pick tasks were not created");

  const pickTasks = items(
    await callApi("/tasks/?status=pending&task_type=pick", { headers: authHeaders }),
  ).filter((task) => task.reference_id === order.id);
  expect(pickTasks.length === 2, `expected two pending pick tasks, found ${pickTasks.length}`);
  for (const task of pickTasks) {
    const picked = await callApi("/fulfillment/pick/confirm", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ task_id: task.id, quantity_picked: task.quantity }),
    });
    expect(picked.success === true, `pick task ${task.id} did not complete`);
  }

  const partialPack = await callApi("/fulfillment/pack/verify", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      order_id: order.id,
      scanned_items: [{ sku_id: skuA.id, quantity: 2 }],
    }),
  });
  expect(partialPack.verified === false, "partial pack unexpectedly verified");
  expect(
    partialPack.errors?.some(
      (error) =>
        error.sku_id === skuB.id &&
        error.error === "quantity_mismatch" &&
        error.expected === 3 &&
        error.scanned === 0,
    ),
    "partial pack did not report missing picked SKU B",
  );

  const afterPartial = items(await callApi("/orders/outbound", { headers: authHeaders })).find(
    (item) => item.id === order.id,
  );
  expect(afterPartial?.status === "picked", `partial pack changed order to ${afterPartial?.status}`);

  const completePack = await callApi("/fulfillment/pack/verify", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      order_id: order.id,
      scanned_items: [
        { sku_id: skuA.id, quantity: 1 },
        { sku_id: skuA.id, quantity: 1 },
        { sku_id: skuB.id, quantity: 3 },
      ],
    }),
  });
  expect(completePack.verified === true, "complete pack did not verify");

  const ship = await callApi("/fulfillment/ship/confirm", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      order_id: order.id,
      carrier: "DHL",
      tracking_number: `TRK-${stamp}`,
      service_level: "ground",
    }),
  });
  expect(ship.status === "shipped", "ship confirm failed");

  const summary = await callApi(`/fulfillment/ship/${order.id}/summary`, { headers: authHeaders });
  expect(summary.status === "shipped", "shipment summary was not shipped");

  console.log(
    JSON.stringify(
      {
        orderNumber: order.order_number,
        earlyPackStatus: earlyPack.status,
        partialVerified: partialPack.verified,
        completeVerified: completePack.verified,
        finalStatus: summary.status,
      },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
