import { callAuditApi, loginAuditUser } from "./audit-tenant-bootstrap.mjs";

const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const platformEmail = process.env.WMS_AUDIT_PLATFORM_EMAIL;
const platformPassword = process.env.WMS_AUDIT_PLATFORM_PASSWORD;
const preserveTenantCodes = (process.env.WMS_CLEANUP_PRESERVE_TENANTS ?? "PLATFORM,GREENECOPO")
  .split(",")
  .map((code) => code.trim())
  .filter(Boolean);

function sumRows(rows = {}) {
  return Object.values(rows).reduce((sum, value) => sum + Number(value || 0), 0);
}

async function cleanup(authToken, dryRun) {
  return callAuditApi(apiUrl, "/maintenance/test-data/cleanup", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${authToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      confirm: "CLEAN_TEST_DATA",
      dry_run: dryRun,
      preserve_tenant_codes: preserveTenantCodes,
      delete_test_tenants: true,
      archive_test_tenants: true,
      clear_operational_data_for_test_tenants: true,
      clear_operational_data_for_preserved_tenants: false,
    }),
  });
}

function summarize(result) {
  return {
    dryRun: result.dry_run,
    testTenantCandidates: result.test_tenant_candidates,
    testTenantRowTotal: sumRows(result.before?.test_tenant_rows),
    preservedTenantCodes: result.preserved_tenants.map((tenant) => tenant.code),
    preservedOperationalRowTotal: sumRows(result.before?.preserved_operational_rows),
    deletedTestTenants: result.deleted?.test_tenants ?? 0,
    deletedTestTenantRowTotal: sumRows(result.deleted?.test_tenant_rows),
    deletedPreservedOperationalRowTotal: sumRows(result.deleted?.preserved_operational_rows),
    examples: result.test_tenant_examples.map((tenant) => ({
      name: tenant.name,
      code: tenant.code,
    })),
  };
}

async function main() {
  if (!platformEmail || !platformPassword) {
    throw new Error(
      "Platform credentials are required. Set WMS_AUDIT_PLATFORM_EMAIL and WMS_AUDIT_PLATFORM_PASSWORD.",
    );
  }

  const auth = await loginAuditUser(apiUrl, platformEmail, platformPassword);
  const before = await cleanup(auth.access_token, true);
  const beforeSummary = summarize(before);

  let executed = null;
  if (beforeSummary.testTenantCandidates > 0 || beforeSummary.testTenantRowTotal > 0) {
    executed = summarize(await cleanup(auth.access_token, false));
  }

  const after = summarize(await cleanup(auth.access_token, true));
  const result = {
    before: beforeSummary,
    executed,
    after,
    pass:
      after.testTenantCandidates === 0 &&
      after.testTenantRowTotal === 0 &&
      after.deletedPreservedOperationalRowTotal === 0,
  };

  console.log(JSON.stringify(result, null, 2));
  if (!result.pass) {
    throw new Error("Production test-data cleanup did not finish cleanly.");
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
