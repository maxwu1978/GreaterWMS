import { registerOrBootstrapAuditTenant } from "./audit-tenant-bootstrap.mjs";

const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const password = process.env.WMS_AUDIT_PASSWORD ?? "Aaa200058";
const platformEmail = process.env.WMS_AUDIT_PLATFORM_EMAIL;
const platformPassword = process.env.WMS_AUDIT_PLATFORM_PASSWORD;

const stamp = `boot${Date.now().toString().slice(-6)}`;
const email = `${stamp}@example.com`;
const companyCode = `BT${stamp}`.slice(0, 12);

if (!platformEmail || !platformPassword) {
  throw new Error(
    "Missing platform bootstrap credentials. Set WMS_AUDIT_PLATFORM_EMAIL and WMS_AUDIT_PLATFORM_PASSWORD or create .env.audit.local.",
  );
}

const auth = await registerOrBootstrapAuditTenant({
  apiUrl,
  platformEmail,
  platformPassword,
  email,
  password,
  companyName: `Bootstrap Smoke ${stamp}`,
  companyCode,
  adminName: "Bootstrap Smoke Admin",
  bootstrapPlanCode: "enterprise",
});

if (!auth.access_token) {
  throw new Error("Bootstrap did not return a tenant admin token.");
}

console.log(
  JSON.stringify(
    {
      success: true,
      apiUrl,
      tenantId: auth.user?.tenant_id ?? auth.tenant_id,
      tenantCode: auth.tenant_code ?? companyCode,
      adminEmail: auth.user?.email ?? email,
      role: auth.user?.role ?? auth.role,
      verificationRequired: auth.verification_required ?? false,
    },
    null,
    2,
  ),
);
