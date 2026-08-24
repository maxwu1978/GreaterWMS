import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const repoRoot = resolve(process.cwd(), "..");
const agentSpecPath = resolve(repoRoot, "docs/06-agent-console-spec.md");
const adminAuditPath = resolve(repoRoot, "docs/22-desktop-first-mobile-admin-audit.md");
const pageDisciplinePath = resolve(repoRoot, "docs/09-action-first-page-discipline.md");
const manualUatPath = resolve(repoRoot, "docs/20-manual-uat-checklist.md");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

function read(path) {
  expect(existsSync(path), `Missing expected doc: ${path}`);
  return readFileSync(path, "utf8");
}

const agentSpec = read(agentSpecPath);
const adminAudit = read(adminAuditPath);
const pageDiscipline = read(pageDisciplinePath);
const manualUat = read(manualUatPath);
const failures = [];

function requireText(name, text, values) {
  for (const value of values) {
    if (!text.includes(value)) failures.push(`${name} is missing '${value}'`);
  }
}

requireText("agent spec", agentSpec, [
  "Tool Governance Matrix",
  "Confirmation Payload Contract",
  "Desktop And Mobile Boundaries",
  "OpenAI",
  "Anthropic Claude",
  "Google Gemini",
  "Kimi / Moonshot AI",
  "MiniMax",
  "DeepSeek",
  "Azure OpenAI",
  "AWS Bedrock",
  "Google Vertex AI",
  "Private OpenAI-compatible endpoint",
  "`inventory.search`",
  "`receiving.inbound.import_with_mapping`",
  "`migration.inventory.import`",
  "`users.update_permissions`",
  "Strong confirmation",
  "The agent may not treat natural-language approval",
]);

requireText("desktop-first admin audit", adminAudit, [
  "Desktop-First Mobile Admin Audit",
  "Billing workbench",
  "Billing settings",
  "Clients",
  "SKUs",
  "Users",
  "Agent settings",
  "Agent console",
  "first mobile viewport",
  "full desktop management",
]);

requireText("page discipline", pageDiscipline, [
  "22-desktop-first-mobile-admin-audit.md",
  "desktop-first management areas",
]);

requireText("manual UAT", manualUat, [
  "M-UAT-MD-07",
  "M-UAT-MD-08",
  "M-UAT-MD-09",
]);

const summary = {
  pass: failures.length === 0,
  docs: {
    agentSpecPath,
    adminAuditPath,
    pageDisciplinePath,
    manualUatPath,
  },
  failures,
};

console.log(JSON.stringify(summary, null, 2));
expect(failures.length === 0, `Agent governance doc validation failed:\n${failures.join("\n")}`);
