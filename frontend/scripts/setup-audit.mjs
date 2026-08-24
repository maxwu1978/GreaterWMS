import { chromium } from "playwright";

const loginEmail = process.env.WMS_AUDIT_EMAIL;
const loginPassword = process.env.WMS_AUDIT_PASSWORD;
const appUrl = process.env.WMS_AUDIT_APP_URL ?? "https://app.maxsmartwms.online";
const apiUrl = process.env.WMS_AUDIT_API_URL ?? "https://api.maxsmartwms.online/api/v1";
const language = process.env.WMS_AUDIT_LANGUAGE ?? "en";

if (!loginEmail || !loginPassword) {
  console.error("Missing WMS_AUDIT_EMAIL or WMS_AUDIT_PASSWORD.");
  process.exit(1);
}

const steps = ["warehouse", "locations", "client", "skus", "billing", "team"];
const englishPhrases = [
  "Your warehouse",
  "Shelf layout",
  "First client",
  "Products (SKUs)",
  "Billing rates",
  "Your team",
  "Client company name",
  "Client email",
  "Portal login",
  "Portal password",
  "Product name",
  "Storage $/pallet/day",
  "Minimum monthly $",
  "Name",
  "Email",
  "Step ",
  "Build the first workable warehouse environment before operators touch live stock.",
];

const loginResponse = await fetch(`${apiUrl}/auth/login`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    email: loginEmail,
    password: loginPassword,
  }),
});

if (!loginResponse.ok) {
  console.error(`Login failed with status ${loginResponse.status}.`);
  process.exit(1);
}

const auth = await loginResponse.json();
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

await page.goto(`${appUrl}/dashboard`, { waitUntil: "domcontentloaded" });
await page.evaluate(
  ({ nextLanguage, token, role, tenantId, permissions }) => {
    localStorage.setItem("wms.language", nextLanguage);
    localStorage.setItem("wms_token", token);
    localStorage.setItem("wms_role", role);
    localStorage.setItem("wms_tenant_id", tenantId);
    localStorage.setItem("wms_permissions", JSON.stringify(permissions ?? []));
  },
  {
    nextLanguage: language,
    token: auth.access_token,
    role: auth.user?.role ?? "",
    tenantId: auth.user?.tenant_id ?? "",
    permissions: auth.user?.permissions ?? [],
  },
);

for (const step of steps) {
  await page.goto(`${appUrl}/setup?step=${step}`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1000);
  const text = await page.locator("body").innerText();
  const hits = englishPhrases.filter((phrase) => text.includes(phrase));
  console.log(`${step}: ${JSON.stringify(hits)}`);
}

await browser.close();
