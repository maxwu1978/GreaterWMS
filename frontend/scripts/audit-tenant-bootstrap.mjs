import "./load-audit-env.mjs";

export async function callAuditApi(apiUrl, pathname, options = {}) {
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

export function normalizeAuditAuth(data, email) {
  const role = data.role ?? data.user?.role ?? "tenant_admin";
  const tenantId = data.tenant_id ?? data.user?.tenant_id ?? null;
  const permissions = data.permissions ?? data.user?.permissions ?? [];
  return {
    ...data,
    role,
    tenant_id: tenantId,
    permissions,
    user: {
      ...(data.user ?? {}),
      email: data.email ?? data.user?.email ?? email,
      role,
      tenant_id: tenantId,
      permissions,
      client_id: data.client_id ?? data.user?.client_id ?? null,
      job_title: data.job_title ?? data.user?.job_title ?? null,
    },
  };
}

export async function loginAuditUser(apiUrl, email, password) {
  const data = await callAuditApi(apiUrl, "/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return normalizeAuditAuth(data, email);
}

export async function bootstrapVerifiedTenantViaPlatform({
  apiUrl,
  platformEmail,
  platformPassword,
  email,
  password,
  companyName,
  companyCode,
  adminName = "QA Test Admin",
  planCode = "enterprise",
}) {
  if (!platformEmail || !platformPassword) {
    throw new Error(
      "Platform credentials are required for verified audit tenant bootstrap. Set WMS_AUDIT_PLATFORM_EMAIL and WMS_AUDIT_PLATFORM_PASSWORD.",
    );
  }

  const platformAuth = await loginAuditUser(apiUrl, platformEmail, platformPassword);
  const data = await callAuditApi(apiUrl, "/maintenance/test-tenant/bootstrap", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${platformAuth.access_token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      company_name: companyName,
      company_code: companyCode,
      admin_email: email,
      admin_password: password,
      admin_name: adminName,
      plan_code: planCode,
    }),
  });
  return normalizeAuditAuth(data, email);
}

export async function registerOrBootstrapAuditTenant({
  apiUrl,
  platformEmail,
  platformPassword,
  email,
  password,
  companyName,
  companyCode,
  adminName = "QA Test Admin",
  registrationPlanCode = "starter",
  bootstrapPlanCode = "enterprise",
}) {
  if (platformEmail && platformPassword) {
    return bootstrapVerifiedTenantViaPlatform({
      apiUrl,
      platformEmail,
      platformPassword,
      email,
      password,
      companyName,
      companyCode,
      adminName,
      planCode: bootstrapPlanCode,
    });
  }

  const registration = await callAuditApi(apiUrl, "/subscriptions/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      company_name: companyName,
      company_code: companyCode,
      admin_email: email,
      admin_password: password,
      admin_name: adminName,
      plan_code: registrationPlanCode,
      accept_terms: true,
      accept_risk_notice: true,
    }),
  });
  if (registration.access_token) return normalizeAuditAuth(registration, email);
  return loginAuditUser(apiUrl, email, password);
}
