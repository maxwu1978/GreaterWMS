import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

const repoRoot = resolve(process.cwd(), "..");
const cliPath = resolve(repoRoot, "tools/wms.mjs");
const failures = [];

function expect(condition, message) {
  if (!condition) failures.push(message);
}

function runCli(args, env = {}) {
  try {
    const stdout = execFileSync(process.execPath, [cliPath, ...args], {
      cwd: repoRoot,
      encoding: "utf8",
      env: { ...process.env, ...env },
    });
    return JSON.parse(stdout);
  } catch (error) {
    const stdout = String(error.stdout || "");
    if (stdout.trim()) return JSON.parse(stdout);
    throw error;
  }
}

function resultItems(payload) {
  return (
    payload?.result?.result?.items ||
    payload?.result?.items ||
    payload?.items ||
    []
  );
}

function firstClientId(payload) {
  return resultItems(payload)[0]?.id || "";
}

const targetApiUrl = process.env.WMS_API_URL || "https://api.maxsmartwms.online";
const token = process.env.WMS_TOKEN || "";
const adminCommands = [
  "admin subscription-status",
  "admin warehouse-setup",
  "admin billing-readiness",
  "admin integration-status",
  "admin audit-summary",
];

const evidence = {
  ok: false,
  action: "agent.admin_production_smoke",
  target_api_url: targetApiUrl,
  mode: token ? "authenticated_read" : "capability_only",
  checks: {},
  failures,
};

const health = runCli(["health", "--timeout-ms", "30000"]);
evidence.checks.health = health;
expect(health.ok === true, "health command failed");
expect(health.result?.status === "ok", "production health status is not ok");

const capabilities = runCli(["capabilities", "--json"]);
const adminCapabilities = (capabilities.commands || []).filter((item) =>
  item.command?.startsWith("admin "),
);
evidence.checks.capabilities = {
  ok: capabilities.ok,
  admin_commands: adminCapabilities.map((item) => ({
    command: item.command,
    auth: item.auth,
    write_gate_enabled: item.agent_write_gate?.enabled,
  })),
};
expect(capabilities.ok === true, "capabilities command failed");
for (const command of adminCommands) {
  const capability = adminCapabilities.find((item) => item.command === command);
  expect(Boolean(capability), `missing admin command: ${command}`);
  expect(capability?.auth === true, `admin command must require auth: ${command}`);
  expect(
    capability?.agent_write_gate?.enabled === false,
    `admin command must not expose write gate: ${command}`,
  );
}

if (!token) {
  evidence.skipped = "Set WMS_TOKEN to run authenticated admin reads.";
  evidence.ok = failures.length === 0;
  console.log(JSON.stringify(evidence, null, 2));
  process.exit(evidence.ok ? 0 : 1);
}

const env = { WMS_API_URL: targetApiUrl };
const subscription = runCli(["admin", "subscription-status"], env);
evidence.checks.subscription = {
  ok: subscription.ok,
  action: subscription.action,
  status: subscription.result?.subscription?.status || subscription.result?.subscription?.message,
};
expect(subscription.ok === true, "admin subscription-status failed");

const setup = runCli(["admin", "warehouse-setup"], env);
evidence.checks.setup = {
  ok: setup.ok,
  action: setup.action,
  next_action: setup.next_action,
};
expect(setup.ok === true, "admin warehouse-setup failed");

const billing = runCli(["admin", "billing-readiness"], env);
evidence.checks.billing = {
  ok: billing.ok,
  action: billing.action,
  ready: billing.result?.summary?.ready,
  clients_without_rate_cards: billing.result?.summary?.clients_without_rate_cards?.length,
};
expect(billing.ok === true, "admin billing-readiness failed");

const audit = runCli(["admin", "audit-summary", "--limit", "5"], env);
evidence.checks.audit = {
  ok: audit.ok,
  action: audit.action,
  failed_count: audit.result?.failed_count,
};
expect(audit.ok === true, "admin audit-summary failed");

const clients = runCli(["client", "list", "--limit", "1"], env);
const clientId = firstClientId(clients);
evidence.checks.client_lookup = {
  ok: clients.ok,
  client_id: clientId || null,
};
expect(clients.ok === true, "client lookup for integration status failed");

if (clientId) {
  const integration = runCli(["admin", "integration-status", "--client-id", clientId], env);
  evidence.checks.integration = {
    ok: integration.ok,
    action: integration.action,
    client_id: integration.entity?.id,
    shopify_configured: integration.result?.shopify?.configured,
    amazon_configured: integration.result?.amazon?.configured,
  };
  expect(integration.ok === true, "admin integration-status failed");
} else {
  evidence.checks.integration = {
    skipped: "No client returned for this tenant.",
  };
}

evidence.ok = failures.length === 0;
console.log(JSON.stringify(evidence, null, 2));
process.exit(evidence.ok ? 0 : 1);
