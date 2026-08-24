import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

const repoRoot = resolve(process.cwd(), "..");
const cliPath = resolve(repoRoot, "tools/wms.mjs");
const failures = [];

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
    if (stdout.trim()) {
      return JSON.parse(stdout);
    }
    throw error;
  }
}

function expect(condition, message) {
  if (!condition) failures.push(message);
}

const evidence = {
  ok: true,
  action: "agent.production_smoke",
  target_api_url: process.env.WMS_API_URL || "https://api.maxsmartwms.online",
  checks: {},
  failures,
};

const health = runCli(["health", "--timeout-ms", "30000"]);
evidence.checks.health = health;
expect(health.ok === true, "health command failed");
expect(health.result?.status === "ok", "production health status is not ok");
expect(Boolean(health.result?.build_sha), "production health did not expose build_sha");

const capabilities = runCli(["capabilities", "--json"]);
const enabledWriteGateCommands = (capabilities.commands || [])
  .filter((item) => item.agent_write_gate?.enabled === true)
  .map((item) => item.command);
const adminReadCommands = (capabilities.commands || []).filter((item) =>
  item.command?.startsWith("admin "),
);
evidence.checks.capabilities = {
  ok: capabilities.ok,
  command_count: capabilities.commands?.length || 0,
  planned_write_commands: capabilities.planned_write_commands,
  enabled_write_gate_commands: enabledWriteGateCommands,
  admin_read_commands: adminReadCommands.map((item) => item.command),
};
expect(capabilities.ok === true, "capabilities command failed");
expect(
  enabledWriteGateCommands.length === (capabilities.planned_write_commands || []).length,
  "planned_write_commands must match enabled write-gate command count",
);

for (const command of [
  "admin subscription-status",
  "admin warehouse-setup",
  "admin billing-readiness",
  "admin integration-status",
  "admin audit-summary",
]) {
  const capability = adminReadCommands.find((item) => item.command === command);
  expect(Boolean(capability), `capabilities missing admin read command: ${command}`);
  expect(capability?.auth === true, `admin read command must require auth: ${command}`);
  expect(
    capability?.agent_write_gate?.enabled === false,
    `admin read command must not expose a write gate: ${command}`,
  );
}

for (const command of [
  "settings billing-rate-card preview",
  "agent allowed-tools",
  "agent model-roster",
  "admin billing-readiness",
]) {
  const capability = capabilities.commands?.find((item) => item.command === command);
  expect(Boolean(capability), `capabilities missing blocked high-risk command: ${command}`);
  expect(
    capability?.agent_write_gate?.enabled !== true,
    `high-risk command must remain read-only or preview-only without an agent write gate: ${command}`,
  );
}

for (const command of [
  "receiving confirm",
  "putaway confirm",
  "picking confirm",
  "picking short",
  "shipping pack",
  "shipping ship",
  "inventory count",
  "inventory adjust",
  "inventory hold",
  "inventory release",
]) {
  expect(
    capabilities.commands?.some((item) => item.command === command && item.mode === "dry-run-only"),
    `capabilities missing dry-run command: ${command}`,
  );
  expect(
    capabilities.commands?.some((item) => item.command === command && item.agent_write_gate?.enabled === true),
    `capabilities missing enabled write gate metadata: ${command}`,
  );
}

const dryRuns = {
  putawayConfirm: runCli([
    "putaway",
    "confirm",
    "--dry-run",
    "--task-id",
    "PUT-SMOKE",
    "--destination-location-id",
    "LOC-SMOKE",
    "--quantity",
    "1",
  ]),
  pickingConfirm: runCli([
    "picking",
    "confirm",
    "--dry-run",
    "--task-id",
    "PICK-SMOKE",
    "--quantity",
    "1",
  ]),
  pickingShort: runCli([
    "picking",
    "short",
    "--dry-run",
    "--task-id",
    "PICK-SMOKE",
    "--quantity",
    "0",
    "--reason",
    "Smoke shortage",
  ]),
  shippingPack: runCli([
    "shipping",
    "pack",
    "--dry-run",
    "--order-id",
    "OUT-SMOKE",
    "--sku-id",
    "SKU-SMOKE",
    "--quantity",
    "1",
  ]),
  shippingShip: runCli([
    "shipping",
    "ship",
    "--dry-run",
    "--order-id",
    "OUT-SMOKE",
    "--carrier",
    "SMOKE",
    "--tracking-number",
    "TRACK-SMOKE",
  ]),
  inventoryCount: runCli([
    "inventory",
    "count",
    "--dry-run",
    "--location-id",
    "LOC-SMOKE",
    "--sku-id",
    "SKU-SMOKE",
    "--counted-quantity",
    "1",
  ]),
  inventoryAdjust: runCli([
    "inventory",
    "adjust",
    "--dry-run",
    "--inventory-id",
    "INV-SMOKE",
    "--new-quantity",
    "1",
    "--reason",
    "Smoke count variance",
  ]),
  inventoryHold: runCli([
    "inventory",
    "hold",
    "--dry-run",
    "--inventory-id",
    "INV-SMOKE",
    "--reason",
    "Smoke quality review",
  ]),
  inventoryRelease: runCli([
    "inventory",
    "release",
    "--dry-run",
    "--inventory-id",
    "INV-SMOKE",
    "--quantity",
    "1",
    "--reason",
    "Smoke release review",
  ]),
};
evidence.checks.dry_runs = dryRuns;

for (const [name, payload] of Object.entries(dryRuns)) {
  expect(payload.ok === true, `${name} dry-run did not return ok=true`);
  expect(payload.dry_run === true, `${name} dry-run did not mark dry_run=true`);
  expect(payload.confirmation_required_for_write === true, `${name} must require confirmation for write`);
  expect(payload.planned_request?.idempotency_key_required_for_write === true, `${name} must require idempotency for write`);
}

evidence.ok = failures.length === 0;
console.log(JSON.stringify(evidence, null, 2));

if (failures.length) {
  process.exitCode = 1;
}
