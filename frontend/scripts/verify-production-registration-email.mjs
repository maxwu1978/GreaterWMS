import "./load-audit-env.mjs";

const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const baseEmail = process.env.WMS_AUDIT_MAIL_TO ?? process.env.WMS_AUDIT_PLATFORM_EMAIL;
const password = process.env.WMS_AUDIT_PASSWORD ?? "Aaa200058";

if (!baseEmail || !baseEmail.includes("@")) {
  throw new Error("Set WMS_AUDIT_MAIL_TO or WMS_AUDIT_PLATFORM_EMAIL for the test recipient.");
}

const [localPart, domain] = baseEmail.split("@");
const stamp = Date.now().toString().slice(-8);
const adminEmail = `${localPart.replace(/\+.*/, "")}+mail${stamp}@${domain}`;
const companyCode = `MAIL${stamp}`.slice(0, 12);

const response = await fetch(`${apiUrl}/subscriptions/register`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    company_name: `MailerSend Smoke ${stamp}`,
    company_code: companyCode,
    admin_email: adminEmail,
    admin_password: password,
    admin_name: "MailerSend Smoke Admin",
    plan_code: "starter",
    accept_terms: true,
    accept_risk_notice: true,
  }),
});

const text = await response.text();
let data = {};
try {
  data = text ? JSON.parse(text) : {};
} catch {
  data = { raw: text };
}

const sanitizedData = JSON.parse(
  JSON.stringify(data).replace(
    /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g,
    "<redacted-email>",
  ),
);

console.log(
  JSON.stringify(
    {
      success: response.ok,
      apiUrl,
      status: response.status,
      verificationRequired: data.verification_required ?? null,
      tenantId: data.tenant_id ?? null,
      userId: data.user_id ?? null,
      plan: data.plan ?? null,
      detail: sanitizedData.detail ?? sanitizedData.message ?? null,
    },
    null,
    2,
  ),
);

if (!response.ok) {
  process.exitCode = 2;
}
