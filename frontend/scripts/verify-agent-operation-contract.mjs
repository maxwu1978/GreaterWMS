import { existsSync, readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

const repoRoot = resolve(process.cwd(), "..");
const docs = {
  agentSpec: resolve(repoRoot, "docs/06-agent-console-spec.md"),
  capabilityReference: resolve(repoRoot, "docs/24-agent-capabilities-reference.md"),
  cliReference: resolve(repoRoot, "docs/25-cli-reference.md"),
  agentSop: resolve(repoRoot, "docs/26-wms-agent-operator-sop.md"),
  agentSkill: resolve(repoRoot, ".codex/skills/wms-agent-operator/SKILL.md"),
  userHierarchy: resolve(repoRoot, "docs/12-user-management-hierarchy.md"),
  index: resolve(repoRoot, "docs/README.md"),
};
const cliPath = resolve(repoRoot, "tools/wms.mjs");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

function read(path) {
  expect(existsSync(path), `Missing expected file: ${path}`);
  return readFileSync(path, "utf8");
}

function parseCli(args) {
  const stdout = execFileSync(process.execPath, [cliPath, ...args], {
    cwd: repoRoot,
    encoding: "utf8",
  });
  return JSON.parse(stdout);
}

const agentSpec = read(docs.agentSpec);
const capabilityReference = read(docs.capabilityReference);
const cliReference = read(docs.cliReference);
const agentSop = read(docs.agentSop);
const agentSkill = read(docs.agentSkill);
const userHierarchy = read(docs.userHierarchy);
const index = read(docs.index);

const failures = [];

function requireText(name, text, values) {
  for (const value of values) {
    if (!text.includes(value)) failures.push(`${name} is missing '${value}'`);
  }
}

requireText("agent operation contract", agentSpec, [
  "Agent Operation Contract",
  "Structured Result Contract",
  "Error Recovery Contract",
  "Permission And Confirmation Contract",
  "evidence_id",
  "safe_commands",
  "The agent must inherit the caller's effective permissions.",
]);

requireText("capability reference", capabilityReference, [
  "Source Of Truth",
  "`inventory.search`",
  "`orders.outbound.preview_import`",
  "`orders.outbound.import_with_mapping`",
  "Capability Discovery",
  "Read-only",
  "Receiving CLI Dry-Run Capabilities",
  "Picking CLI Dry-Run Capabilities",
  "Shipping CLI Dry-Run Capabilities",
  "Inventory CLI Dry-Run Capabilities",
]);

requireText("cli reference", cliReference, [
  "Agent-Operable WMS CLI Reference",
  "`node tools/wms.mjs capabilities --json`",
  "`node tools/wms.mjs health`",
  "`WMS_TOKEN`",
  "Read-Only Commands",
  "Receiving Dry-Run Commands",
  "--live-preview",
  "Putaway Dry-Run Commands",
  "Picking Dry-Run Commands",
  "Shipping Dry-Run Commands",
  "Inventory Dry-Run Commands",
  "Write Commands Not Yet Enabled",
]);

requireText("agent SOP", agentSop, [
  "WMS Agent Operator SOP",
  "Receiving Agent SOP",
  "Putaway Agent SOP",
  "Picking Agent SOP",
  "Shipping Agent SOP",
  "Inventory Agent SOP",
  "Evidence",
]);

requireText("agent skill", agentSkill, [
  "WMS Agent Operator",
  "Receiving SOP",
  "Putaway SOP",
  "Picking SOP",
  "Shipping SOP",
  "Inventory SOP",
  "Prohibited Actions",
  "Completion Standard",
  "Evidence Requirements",
]);

const governedWorkflows = ["Receiving", "Putaway", "Picking", "Shipping", "Inventory"];
for (const workflow of governedWorkflows) {
  requireText(`${workflow} SOP coverage`, agentSop, [`${workflow} Agent SOP`]);
  requireText(`${workflow} skill coverage`, agentSkill, [`${workflow} SOP`]);
}

const prohibitedPatterns = [
  "write directly to database tables",
  "undocumented endpoints",
  "bypass tenant",
  "treat model conversation approval as authorization",
  "silent production writes",
  "destructive",
  "billing changes",
  "permission changes",
  "invent confirmation tokens",
  "evidence ids",
  "before/after states",
];
for (const pattern of prohibitedPatterns) {
  requireText("agent skill prohibited action coverage", agentSkill, [pattern]);
}

const disabledWriteCoverage = [
  "putaway confirm",
  "Picking",
  "Shipping",
  "Inventory",
  "count",
  "adjust",
  "hold",
  "import",
  "delete",
  "void",
  "bulk-mutate",
];
for (const pattern of disabledWriteCoverage) {
  requireText("agent SOP disabled write coverage", agentSop, [pattern]);
}

requireText("user hierarchy", userHierarchy, [
  "Agent Permission Inheritance",
  "agent must inherit the caller's effective permissions",
  "tool gate",
]);

requireText("docs index", index, [
  "`24-agent-capabilities-reference.md`",
  "`25-cli-reference.md`",
  "`26-wms-agent-operator-sop.md`",
]);

const capabilities = parseCli(["capabilities", "--json"]);
expect(capabilities.ok === true, "capabilities command must return ok=true");
expect(capabilities.contract_version, "capabilities command must expose contract_version");
expect(
  capabilities.commands.some((command) => command.command === "inventory lookup"),
  "capabilities must include inventory lookup",
);
for (const commandName of [
  "inventory import preview",
  "evidence detail",
  "evidence failed",
  "evidence replay-preview",
]) {
  expect(
    capabilities.commands.some((command) => command.command === commandName && command.risk),
    `capabilities must include ${commandName}`,
  );
}
expect(
  capabilities.commands.some(
    (command) => command.command === "receiving confirm" && command.mode === "dry-run-only",
  ),
  "capabilities must include receiving confirm dry-run",
);
expect(
  capabilities.commands.some(
    (command) => command.command === "putaway confirm" && command.mode === "dry-run-only",
  ),
  "capabilities must include putaway confirm dry-run",
);
for (const commandName of [
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
    capabilities.commands.some(
      (command) => command.command === commandName && command.mode === "dry-run-only",
    ),
    `capabilities must include ${commandName} dry-run`,
  );
}
for (const commandName of [
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
  const command = capabilities.commands.find((item) => item.command === commandName);
  expect(command?.agent_write_gate?.enabled === true, `${commandName} must expose enabled agent write gate metadata`);
  expect(Boolean(command?.agent_write_gate?.preview_endpoint), `${commandName} must expose preview endpoint`);
  expect(Boolean(command?.agent_write_gate?.agent_endpoint), `${commandName} must expose agent endpoint`);
}
expect(
  capabilities.commands.every((command) => command.risk),
  "every capability command must include risk",
);

const glossary = parseCli(["glossary", "--json"]);
expect(glossary.ok === true, "glossary command must return ok=true");
expect(glossary.glossary.package === "Package", "glossary must define Package");

const workflows = parseCli(["workflow", "list", "--json"]);
expect(workflows.ok === true, "workflow list must return ok=true");
expect(workflows.workflows.length >= 5, "workflow list must include core WMS workflows");

const receivingConfirmDryRun = parseCli([
  "receiving",
  "confirm",
  "--dry-run",
  "--order-id",
  "INB-TEST",
  "--package-id",
  "PKG-TEST",
  "--quantity",
  "3",
  "--staging-location-id",
  "DOCK-TEST",
]);
expect(receivingConfirmDryRun.ok === true, "receiving confirm dry-run must return ok=true");
expect(receivingConfirmDryRun.dry_run === true, "receiving confirm dry-run must not mutate state");
expect(
  receivingConfirmDryRun.planned_request?.endpoint?.includes("/packages/PKG-TEST/receive"),
  "receiving confirm dry-run must expose planned receive endpoint",
);
expect(
  cliReference.includes("/receive/preview"),
  "CLI reference must document receiving server-side preview endpoint",
);
expect(
  cliReference.includes("/scan-label/preview") &&
    cliReference.includes("/choose-dock/preview") &&
    cliReference.includes("/recovery/preview"),
  "CLI reference must document all receiving live-preview endpoints",
);

const putawayConfirmDryRun = parseCli([
  "putaway",
  "confirm",
  "--dry-run",
  "--task-id",
  "PUT-TEST",
  "--destination-location-id",
  "LOC-TEST",
  "--quantity",
  "2",
]);
expect(putawayConfirmDryRun.ok === true, "putaway confirm dry-run must return ok=true");
expect(putawayConfirmDryRun.dry_run === true, "putaway confirm dry-run must not mutate state");
expect(
  putawayConfirmDryRun.planned_request?.endpoint ===
    "POST /api/v1/fulfillment/putaway/confirm/preview",
  "putaway confirm dry-run must expose planned putaway preview endpoint",
);

const pickingConfirmDryRun = parseCli([
  "picking",
  "confirm",
  "--dry-run",
  "--task-id",
  "PICK-TEST",
  "--quantity",
  "2",
]);
expect(pickingConfirmDryRun.ok === true, "picking confirm dry-run must return ok=true");
expect(pickingConfirmDryRun.dry_run === true, "picking confirm dry-run must not mutate state");
expect(
  pickingConfirmDryRun.planned_request?.endpoint ===
    "POST /api/v1/fulfillment/pick/confirm/preview",
  "picking confirm dry-run must expose planned pick preview endpoint",
);

const shippingPackDryRun = parseCli([
  "shipping",
  "pack",
  "--dry-run",
  "--order-id",
  "OUT-TEST",
  "--sku-id",
  "SKU-TEST",
  "--quantity",
  "2",
]);
expect(shippingPackDryRun.ok === true, "shipping pack dry-run must return ok=true");
expect(shippingPackDryRun.dry_run === true, "shipping pack dry-run must not mutate state");
expect(
  shippingPackDryRun.planned_request?.endpoint ===
    "POST /api/v1/fulfillment/pack/verify/preview",
  "shipping pack dry-run must expose planned pack preview endpoint",
);

const shippingShipDryRun = parseCli([
  "shipping",
  "ship",
  "--dry-run",
  "--order-id",
  "OUT-TEST",
  "--carrier",
  "UPS",
  "--tracking-number",
  "TRACK-TEST",
]);
expect(shippingShipDryRun.ok === true, "shipping ship dry-run must return ok=true");
expect(shippingShipDryRun.dry_run === true, "shipping ship dry-run must not mutate state");
expect(
  shippingShipDryRun.planned_request?.endpoint ===
    "POST /api/v1/fulfillment/ship/confirm/preview",
  "shipping ship dry-run must expose planned ship preview endpoint",
);

const inventoryCountDryRun = parseCli([
  "inventory",
  "count",
  "--dry-run",
  "--location-id",
  "LOC-TEST",
  "--sku-id",
  "SKU-TEST",
  "--counted-quantity",
  "4",
]);
expect(inventoryCountDryRun.ok === true, "inventory count dry-run must return ok=true");
expect(inventoryCountDryRun.dry_run === true, "inventory count dry-run must not mutate state");
expect(
  inventoryCountDryRun.planned_request?.endpoint === "POST /api/v1/cycle-count/record/preview",
  "inventory count dry-run must expose planned cycle count preview endpoint",
);

const inventoryAdjustDryRun = parseCli([
  "inventory",
  "adjust",
  "--dry-run",
  "--inventory-id",
  "INV-TEST",
  "--new-quantity",
  "4",
  "--reason",
  "Cycle count variance",
]);
expect(inventoryAdjustDryRun.ok === true, "inventory adjust dry-run must return ok=true");
expect(inventoryAdjustDryRun.dry_run === true, "inventory adjust dry-run must not mutate state");
expect(
  inventoryAdjustDryRun.planned_request?.endpoint ===
    "POST /api/v1/inventory/ops/adjust/preview",
  "inventory adjust dry-run must expose planned adjust preview endpoint",
);

const inventoryHoldDryRun = parseCli([
  "inventory",
  "hold",
  "--dry-run",
  "--inventory-id",
  "INV-TEST",
  "--reason",
  "Quality review",
]);
expect(inventoryHoldDryRun.ok === true, "inventory hold dry-run must return ok=true");
expect(inventoryHoldDryRun.dry_run === true, "inventory hold dry-run must not mutate state");
expect(
  inventoryHoldDryRun.planned_request?.endpoint ===
    "POST /api/v1/inventory/rules/freeze/preview",
  "inventory hold dry-run must expose planned hold preview endpoint",
);

const inventoryReleaseDryRun = parseCli([
  "inventory",
  "release",
  "--dry-run",
  "--inventory-id",
  "INV-TEST",
  "--quantity",
  "2",
  "--reason",
  "QA cleared",
]);
expect(inventoryReleaseDryRun.ok === true, "inventory release dry-run must return ok=true");
expect(inventoryReleaseDryRun.dry_run === true, "inventory release dry-run must not mutate state");
expect(
  inventoryReleaseDryRun.planned_request?.endpoint ===
    "POST /api/v1/inventory/rules/unfreeze/preview",
  "inventory release dry-run must expose planned release preview endpoint",
);

let rejectedConfirm = false;
try {
  parseCli([
    "receiving",
    "confirm",
    "--confirm",
    "unsafe",
    "--order-id",
    "INB-TEST",
    "--package-id",
    "PKG-TEST",
    "--quantity",
    "3",
  ]);
} catch {
  rejectedConfirm = true;
}
expect(rejectedConfirm, "receiving confirm must reject writes missing production guards");

let rejectedPutawayConfirm = false;
try {
  parseCli([
    "putaway",
    "confirm",
    "--confirm",
    "unsafe",
    "--task-id",
    "PUT-TEST",
    "--destination-location-id",
    "LOC-TEST",
  ]);
} catch {
  rejectedPutawayConfirm = true;
}
expect(rejectedPutawayConfirm, "putaway confirm must reject writes missing production guards");

let rejectedPickingConfirm = false;
try {
  parseCli([
    "picking",
    "confirm",
    "--confirm",
    "unsafe",
    "--task-id",
    "PICK-TEST",
    "--quantity",
    "2",
  ]);
} catch {
  rejectedPickingConfirm = true;
}
expect(rejectedPickingConfirm, "picking confirm must reject writes missing production guards");

let rejectedPickingShort = false;
try {
  parseCli([
    "picking",
    "short",
    "--confirm",
    "unsafe",
    "--task-id",
    "PICK-TEST",
    "--quantity",
    "1",
    "--reason",
    "Stock short",
  ]);
} catch {
  rejectedPickingShort = true;
}
expect(rejectedPickingShort, "picking short must reject writes missing production guards");

let rejectedShippingPack = false;
try {
  parseCli([
    "shipping",
    "pack",
    "--confirm",
    "unsafe",
    "--order-id",
    "OUT-TEST",
    "--sku-id",
    "SKU-TEST",
    "--quantity",
    "2",
  ]);
} catch {
  rejectedShippingPack = true;
}
expect(rejectedShippingPack, "shipping pack must reject writes missing production guards");

let rejectedShippingShip = false;
try {
  parseCli([
    "shipping",
    "ship",
    "--confirm",
    "unsafe",
    "--order-id",
    "OUT-TEST",
    "--carrier",
    "UPS",
    "--tracking-number",
    "TRACK-TEST",
  ]);
} catch {
  rejectedShippingShip = true;
}
expect(rejectedShippingShip, "shipping ship must reject writes missing production guards");

let rejectedInventoryAdjust = false;
try {
  parseCli([
    "inventory",
    "adjust",
    "--confirm",
    "unsafe",
    "--inventory-id",
    "INV-TEST",
    "--new-quantity",
    "4",
    "--reason",
    "Cycle count variance",
  ]);
} catch {
  rejectedInventoryAdjust = true;
}
expect(rejectedInventoryAdjust, "inventory adjust must reject writes missing production guards");

let rejectedInventoryCount = false;
try {
  parseCli([
    "inventory",
    "count",
    "--confirm",
    "unsafe",
    "--location-id",
    "LOC-TEST",
    "--sku-id",
    "SKU-TEST",
    "--counted-quantity",
    "4",
  ]);
} catch {
  rejectedInventoryCount = true;
}
expect(rejectedInventoryCount, "inventory count must reject writes missing production guards");

let rejectedInventoryHold = false;
try {
  parseCli([
    "inventory",
    "hold",
    "--confirm",
    "unsafe",
    "--inventory-id",
    "INV-TEST",
    "--reason",
    "Quality review",
  ]);
} catch {
  rejectedInventoryHold = true;
}
expect(rejectedInventoryHold, "inventory hold must reject writes missing production guards");

let rejectedInventoryRelease = false;
try {
  parseCli([
    "inventory",
    "release",
    "--confirm",
    "unsafe",
    "--inventory-id",
    "INV-TEST",
    "--quantity",
    "2",
    "--reason",
    "QA cleared",
  ]);
} catch {
  rejectedInventoryRelease = true;
}
expect(rejectedInventoryRelease, "inventory release must reject writes missing production guards");

const summary = {
  pass: failures.length === 0,
  docs,
  cliPath,
  cli: {
    commands: capabilities.commands.length,
    workflows: workflows.workflows.length,
  },
  failures,
};

console.log(JSON.stringify(summary, null, 2));
expect(failures.length === 0, `Agent operation contract validation failed:\n${failures.join("\n")}`);
