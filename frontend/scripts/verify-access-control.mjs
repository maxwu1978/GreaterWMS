import { callAuditApi, loginAuditUser, registerOrBootstrapAuditTenant } from "./audit-tenant-bootstrap.mjs";

const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const platformEmail = process.env.WMS_AUDIT_PLATFORM_EMAIL;
const platformPassword = process.env.WMS_AUDIT_PLATFORM_PASSWORD;
const password = process.env.WMS_AUDIT_PASSWORD ?? "Aaa200058";
const stamp = `acl${Date.now().toString().slice(-8)}`;
const companyCode = `AC${stamp}`.slice(0, 12).toUpperCase();
const companyName = `Access Audit ${stamp}`;
const adminEmail = `${stamp}@example.com`;
const operatorEmail = `${stamp}.operator@example.com`;
const viewerEmail = `${stamp}.viewer@example.com`;

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

async function requestApi(token, path, options = {}) {
  const response = await fetch(`${apiUrl}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.headers ?? {}),
    },
  });
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  return { ok: response.ok, status: response.status, data };
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

async function cleanupPlatformTestData(platformToken) {
  return callAuditApi(apiUrl, "/maintenance/test-data/cleanup", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${platformToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      confirm: "CLEAN_TEST_DATA",
      dry_run: false,
      preserve_tenant_codes: ["PLATFORM", "GREENECOPO"],
      delete_test_tenants: true,
      archive_test_tenants: true,
      clear_operational_data_for_test_tenants: true,
      clear_operational_data_for_preserved_tenants: false,
    }),
  });
}

function hasOnly(values, expectedValues) {
  const expected = new Set(expectedValues);
  return values.length === expected.size && values.every((value) => expected.has(value));
}

async function runAccessChecks(platformAuth) {
  const tenantAuth = await registerOrBootstrapAuditTenant({
    apiUrl,
    platformEmail,
    platformPassword,
    email: adminEmail,
    password,
    companyName,
    companyCode,
    adminName: "Access Audit Admin",
    bootstrapPlanCode: "enterprise",
  });
  const tenantToken = tenantAuth.access_token;
  const tenantId = tenantAuth.tenant_id ?? tenantAuth.user?.tenant_id;
  const json = { "Content-Type": "application/json" };

  const client = await api(tenantToken, "/clients/", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      name: "Access Audit Client",
      code: "ACLCL",
      contact_email: viewerEmail,
      billing_enabled: true,
      portal_access: true,
    }),
  });

  const tenantUsers = await api(tenantToken, "/users/?page_size=100");
  expect(
    tenantUsers.items.length >= 1 && tenantUsers.items.every((user) => user.tenant_id === tenantId),
    "Tenant admin user list is not scoped to its own tenant.",
  );

  const tenantAdminCreate = await requestApi(tenantToken, "/users/", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      email: `${stamp}.tenant-admin@example.com`,
      full_name: "Forbidden Tenant Admin",
      password,
      role: "tenant_admin",
    }),
  });
  const platformAdminCreate = await requestApi(tenantToken, "/users/", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      email: `${stamp}.platform-admin@example.com`,
      full_name: "Forbidden Platform Admin",
      password,
      role: "platform_admin",
    }),
  });
  expect(tenantAdminCreate.status === 403, "Tenant admin was able to create another tenant admin.");
  expect(platformAdminCreate.status === 403, "Tenant admin was able to create a platform admin.");

  const operator = await api(tenantToken, "/users/", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      email: operatorEmail,
      full_name: "Access Audit Operator",
      password,
      role: "operator",
      permissions: ["receiving.execute", "users.manage", "billing.manage"],
    }),
  });
  expect(
    hasOnly(operator.permissions, ["receiving.execute"]),
    `Operator permissions were not clamped. Got ${JSON.stringify(operator.permissions)}`,
  );

  const viewer = await api(tenantToken, "/users/", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      email: viewerEmail,
      full_name: "Access Audit Viewer",
      password,
      role: "client_viewer",
      client_id: client.id,
      permissions: ["billing.manage"],
    }),
  });
  expect(
    hasOnly(viewer.permissions, ["portal.view"]) && viewer.client_id === client.id,
    "Client viewer permissions or client assignment were not clamped correctly.",
  );

  const operatorAuth = await loginAuditUser(apiUrl, operatorEmail, password);
  const viewerAuth = await loginAuditUser(apiUrl, viewerEmail, password);
  expect(operatorAuth.role === "operator", "Operator login did not return operator role.");
  expect(viewerAuth.role === "client_viewer", "Client viewer login did not return client_viewer role.");

  const operatorUsers = await requestApi(operatorAuth.access_token, "/users/");
  const operatorBilling = await requestApi(operatorAuth.access_token, "/billing/rate-cards");
  const operatorInventory = await requestApi(operatorAuth.access_token, "/inventory?page_size=5");
  const operatorPortal = await requestApi(
    operatorAuth.access_token,
    `/portal/dashboard?client_id=${client.id}`,
  );
  expect(operatorUsers.status === 403, "Operator can access user management.");
  expect(operatorBilling.status === 403, "Operator can access tenant-admin billing settings.");
  expect(operatorInventory.status === 200, "Operator cannot read operational inventory.");
  expect(operatorPortal.status === 200, "Operator cannot inspect portal dashboard with client_id.");

  const viewerUsers = await requestApi(viewerAuth.access_token, "/users/");
  const viewerBilling = await requestApi(viewerAuth.access_token, "/billing/rate-cards");
  const viewerInventory = await requestApi(viewerAuth.access_token, "/inventory?page_size=5");
  const viewerPortal = await requestApi(viewerAuth.access_token, "/portal/dashboard");
  expect(viewerUsers.status === 403, "Client viewer can access user management.");
  expect(viewerBilling.status === 403, "Client viewer can access tenant-admin billing settings.");
  expect(viewerInventory.status === 200, "Client viewer cannot read filtered inventory.");
  expect(viewerPortal.status === 200, "Client viewer cannot access its portal dashboard.");

  const platformUsers = await api(platformAuth.access_token, "/users/?page_size=100");
  expect(
    platformUsers.items.some((user) => user.tenant_id === tenantId),
    "Platform admin cannot see the audit tenant user set.",
  );

  return {
    tenant: companyName,
    tenantCode: companyCode,
    checks: {
      tenantUserListScoped: true,
      tenantCannotCreateTenantAdmin: true,
      tenantCannotCreatePlatformAdmin: true,
      operatorPermissionsClamped: operator.permissions,
      clientViewerPermissionsClamped: viewer.permissions,
      operatorBlockedFromUsers: operatorUsers.status,
      operatorBlockedFromBilling: operatorBilling.status,
      operatorCanReadInventory: operatorInventory.status,
      clientViewerBlockedFromUsers: viewerUsers.status,
      clientViewerBlockedFromBilling: viewerBilling.status,
      clientViewerCanReadFilteredInventory: viewerInventory.status,
      clientViewerCanOpenPortal: viewerPortal.status,
      platformCanSeeTenantUsers: true,
    },
  };
}

async function main() {
  if (!platformEmail || !platformPassword) {
    throw new Error(
      "Platform credentials are required. Set WMS_AUDIT_PLATFORM_EMAIL and WMS_AUDIT_PLATFORM_PASSWORD.",
    );
  }

  const platformAuth = await loginAuditUser(apiUrl, platformEmail, platformPassword);
  let auditResult;
  let cleanup;
  let cleanupError;

  try {
    auditResult = await runAccessChecks(platformAuth);
  } finally {
    try {
      cleanup = await cleanupPlatformTestData(platformAuth.access_token);
    } catch (error) {
      cleanupError = error;
      console.error("Access audit cleanup failed.", error);
    }
  }

  if (cleanupError) throw cleanupError;

  const cleanupRowTotal = Object.values(cleanup.deleted?.test_tenant_rows ?? {}).reduce(
    (sum, value) => sum + Number(value || 0),
    0,
  );

  console.log(
    JSON.stringify(
      {
        ...auditResult,
        cleanup: {
          deletedTestTenants: cleanup.deleted?.test_tenants ?? 0,
          deletedTestTenantRowTotal: cleanupRowTotal,
          deletedPreservedOperationalRows: Object.values(
            cleanup.deleted?.preserved_operational_rows ?? {},
          ).reduce((sum, value) => sum + Number(value || 0), 0),
        },
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
