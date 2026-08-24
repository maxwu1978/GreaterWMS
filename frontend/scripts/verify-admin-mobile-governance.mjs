import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const checks = [
  {
    file: "src/modules/admin/AgentSettingsPage.tsx",
    tokens: [
      'data-testid="agent-settings-mobile-governance"',
      'data-admin-mobile-contract="desktop-first"',
      'data-testid="agent-settings-desktop-management"',
      "hidden rounded-[1.5rem]",
      "provider health",
      "full tool catalog",
      "high-risk governance",
    ],
  },
  {
    file: "src/modules/admin/AgentConsolePage.tsx",
    tokens: [
      'data-testid="agent-console-mobile-governance"',
      'data-admin-mobile-contract="read-tools-first"',
      'data-testid="agent-console-mobile-tool-policy"',
      'data-testid="agent-console-mobile-import-boundary"',
      "const TOOL_GOVERNANCE",
      "function mobileToolPolicy",
      "mobilePolicy",
      "confirmation",
      "low-risk read tools",
      "high-risk confirmations",
      "const canRunTool",
    ],
  },
  {
    file: "src/modules/admin/UsersPage.tsx",
    tokens: [
      'data-testid="users-mobile-governance"',
      'data-admin-mobile-contract="desktop-first"',
      'data-testid="users-mobile-add-user-collapsed"',
      "User management is desktop-first",
      "Permission matrices",
      "role changes",
    ],
  },
  {
    file: "src/modules/billing/BillingSettingsPage.tsx",
    tokens: [
      'data-testid="desktop-first-mobile-notice"',
      'data-admin-mobile-contract="billing-settings-desktop-first"',
      "management workspace",
      "iPad or desktop",
    ],
  },
  {
    file: "src/modules/admin/WarehousesPage.tsx",
    tokens: [
      'data-testid="warehouses-mobile-governance"',
      'data-admin-mobile-contract="warehouse-desktop-first"',
      'data-testid="warehouses-mobile-add-collapsed"',
      "Create records, zones, locations, planner rules, and AGV constraints",
    ],
  },
  {
    file: "src/modules/admin/SkusPage.tsx",
    tokens: [
      'data-admin-mobile-contract="sku-desktop-first"',
      'data-testid="skus-mobile-add-collapsed"',
      "barcode details, weight, lot tracking, and expiry rules",
    ],
  },
  {
    file: "src/modules/receiving/ReceivingCodeSettingsPage.tsx",
    tokens: [
      'data-testid="receiving-code-mobile-governance"',
      'data-admin-mobile-contract="receiving-settings-desktop-first"',
      'data-testid="receiving-code-mobile-settings-collapsed"',
    ],
  },
  {
    file: "src/modules/receiving/ReceivingLabelSettingsPage.tsx",
    tokens: [
      'data-testid="receiving-label-mobile-governance"',
      'data-admin-mobile-contract="receiving-settings-desktop-first"',
      'data-testid="receiving-label-mobile-settings-collapsed"',
    ],
  },
  {
    file: "src/modules/admin/DataMigrationPage.tsx",
    tokens: [
      'data-testid="migration-mobile-governance"',
      'data-admin-mobile-contract="migration-desktop-first"',
      'data-testid="migration-mobile-import-collapsed"',
      'data-testid="migration-desktop-import-workbench"',
    ],
  },
];

function expectToken(source, token, file) {
  if (!source.includes(token)) {
    throw new Error(`${file} is missing required admin mobile governance token: ${token}`);
  }
}

for (const check of checks) {
  const source = readFileSync(resolve(root, check.file), "utf8");
  for (const token of check.tokens) {
    expectToken(source, token, check.file);
  }
}

console.log(
  JSON.stringify(
    {
      pass: true,
      checked: checks.map((check) => check.file),
    },
    null,
    2,
  ),
);
