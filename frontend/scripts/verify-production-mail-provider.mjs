import { callAuditApi, loginAuditUser } from "./audit-tenant-bootstrap.mjs";

const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const platformEmail = process.env.WMS_AUDIT_PLATFORM_EMAIL;
const platformPassword = process.env.WMS_AUDIT_PLATFORM_PASSWORD;
const toEmail = process.env.WMS_AUDIT_MAIL_TO ?? platformEmail;

if (!platformEmail || !platformPassword) {
  throw new Error(
    "Missing platform credentials. Set WMS_AUDIT_PLATFORM_EMAIL and WMS_AUDIT_PLATFORM_PASSWORD or create .env.audit.local.",
  );
}

if (!toEmail) {
  throw new Error("Missing diagnostic recipient. Set WMS_AUDIT_MAIL_TO or WMS_AUDIT_PLATFORM_EMAIL.");
}

const platformAuth = await loginAuditUser(apiUrl, platformEmail, platformPassword);
const headers = {
  Authorization: `Bearer ${platformAuth.access_token}`,
  "Content-Type": "application/json",
};

const status = await callAuditApi(apiUrl, "/maintenance/email-provider/status", {
  method: "GET",
  headers,
});

const diagnostic = await callAuditApi(apiUrl, "/maintenance/email-provider/test", {
  method: "POST",
  headers,
  body: JSON.stringify({ to_email: toEmail }),
});

console.log(
  JSON.stringify(
    {
      success: diagnostic.success,
      apiUrl,
      requestedProvider: status.status?.requested_provider,
      selectedProvider: diagnostic.selected_provider,
      deliveredBy: diagnostic.delivered_by,
      deliveryEnabled: status.status?.delivery_enabled,
      verificationRequired: status.status?.verification_required,
      attempts: diagnostic.attempts,
      configuredCandidates: status.status?.configured_candidates,
      readyProviders: (status.status?.providers ?? [])
        .filter((provider) => provider.ready)
        .map((provider) => provider.provider),
      message: diagnostic.message,
    },
    null,
    2,
  ),
);
