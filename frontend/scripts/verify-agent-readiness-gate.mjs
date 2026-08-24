import { existsSync, readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

const repoRoot = resolve(import.meta.dirname, "../..");
const cliPath = resolve(repoRoot, "tools/wms.mjs");
const failures = [];

function expect(condition, message) {
  if (!condition) failures.push(message);
}

function read(path) {
  expect(existsSync(path), `Missing expected file: ${path}`);
  return existsSync(path) ? readFileSync(path, "utf8") : "";
}

function runCli(args) {
  const stdout = execFileSync(process.execPath, [cliPath, ...args], {
    cwd: repoRoot,
    encoding: "utf8",
  });
  return JSON.parse(stdout);
}

const requiredSkills = [
  "wms-agent-operator",
  "wms-receiving-operator",
  "wms-fulfillment-operator",
  "wms-inventory-operator",
  "wms-release-gate-verifier",
  "wms-recovery-debugger",
  "wms-local-agent-operator",
];

for (const skill of requiredSkills) {
  const body = read(resolve(repoRoot, ".codex/skills", skill, "SKILL.md"));
  expect(body.includes("name:"), `${skill} is missing skill frontmatter`);
  expect(body.includes("description:"), `${skill} is missing skill description`);
}

const wcsSkillPaths = [
  "wms-agent/skills/wms-wcs-operator/SKILL.md",
  "wms-agent/local_agent/bundled_skills/wms-wcs-operator/SKILL.md",
];
for (const path of wcsSkillPaths) {
  const body = read(resolve(repoRoot, path));
  expect(body.includes("name: wms-wcs-operator"), `${path} is missing WCS skill frontmatter`);
  for (const phrase of [
    "wcs ready-config",
    "wcs quality-complete",
    "wcs config update",
    "wcs certification task",
    "wcs point-mappings",
    "Do not call live",
    "Do not run `wcs certification task --confirm-create`",
    "live `editReadyConfig` or `/QualityComplete`",
  ]) {
    expect(body.includes(phrase), `${path} missing ${phrase}`);
  }
}

const capabilities = runCli(["capabilities", "--json"]);
const wcsCommands = [
  "wcs config",
  "wcs config update",
  "wcs certification task",
  "wcs bindings",
  "wcs gate-check",
  "wcs dispatch",
  "wcs callback replay",
  "wcs ready-config",
  "wcs quality-complete",
  "wcs point-mappings list",
  "wcs point-mappings validate",
  "wcs point-mappings import",
];
for (const commandName of wcsCommands) {
  expect(
    Boolean(capabilities.commands?.find((item) => item.command === commandName)),
    `capabilities missing ${commandName}`,
  );
}

const pointMappingImport = capabilities.commands?.find(
  (item) => item.command === "wcs point-mappings import",
);
expect(
  pointMappingImport?.requires?.includes("--validate-only or --confirm-import"),
  "wcs point-mappings import must require validate-only or confirm-import",
);

const enabledGateCommands = [
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
  "settings receiving-codes preview",
  "settings receiving-labels preview",
  "settings client-profile preview",
  "settings sku preview",
  "settings warehouse-location preview",
  "inbound import preview",
  "outbound import preview",
  "inventory import preview",
];

for (const commandName of enabledGateCommands) {
  const command = capabilities.commands?.find((item) => item.command === commandName);
  expect(Boolean(command), `capabilities missing ${commandName}`);
  expect(command?.agent_write_gate?.enabled === true, `${commandName} gate is not enabled`);
  expect(Boolean(command?.agent_write_gate?.preview_endpoint), `${commandName} missing preview endpoint`);
  expect(Boolean(command?.agent_write_gate?.agent_endpoint), `${commandName} missing agent endpoint`);
  expect(Boolean(command?.agent_write_gate?.token_prefix), `${commandName} missing token prefix`);
}

const cliReference = read(resolve(repoRoot, "docs/25-cli-reference.md"));
for (const phrase of [
  "inventory release --dry-run --live-preview",
  "inventory release --confirm",
  "evidence list",
  "evidence detail",
  "evidence failed",
  "evidence replay-preview",
  "inventory transactions",
  "inventory import preview",
  "settings receiving-codes preview --confirm",
  "settings receiving-labels preview --confirm",
  "settings client-profile preview --confirm",
  "settings sku preview --confirm",
  "settings warehouse-location preview --confirm",
  "inbound import preview --confirm",
  "outbound import preview --confirm",
  "inventory import preview --confirm",
  "smoke:agent-settings-confirm-production",
]) {
  expect(cliReference.includes(phrase), `CLI reference missing ${phrase}`);
}

const dryRuns = [
  runCli(["inventory", "release", "--dry-run", "--inventory-id", "INV-GATE", "--quantity", "1", "--reason", "Gate check"]),
  runCli(["shipping", "pack", "--dry-run", "--order-id", "OUT-GATE", "--sku-id", "SKU-GATE", "--quantity", "1"]),
  runCli(["picking", "short", "--dry-run", "--task-id", "PICK-GATE", "--quantity", "0", "--reason", "Gate check"]),
];

for (const payload of dryRuns) {
  expect(payload.ok === true, `${payload.action} dry-run did not return ok=true`);
  expect(payload.dry_run === true, `${payload.action} did not mark dry_run=true`);
  expect(payload.confirmation_required_for_write === true, `${payload.action} must require confirmation`);
  expect(
    payload.planned_request?.idempotency_key_required_for_write === true,
    `${payload.action} must require idempotency`,
  );
}

const result = {
  ok: failures.length === 0,
  action: "agent.readiness_gate",
  checked_skills: requiredSkills,
  checked_wcs_skills: wcsSkillPaths,
  checked_wcs_commands: wcsCommands,
  checked_write_gates: enabledGateCommands,
  failures,
};

console.log(JSON.stringify(result, null, 2));
if (failures.length) process.exitCode = 1;
