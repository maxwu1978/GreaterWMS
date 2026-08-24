import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

const repoRoot = resolve(process.cwd(), "..");
const docsPath = resolve(repoRoot, "docs/21-recovery-code-coverage.md");
const scriptsDir = resolve(process.cwd(), "scripts");
const sourceFiles = [
  resolve(process.cwd(), "src/modules/receiving/ReceivingFlow.tsx"),
  resolve(process.cwd(), "src/modules/putaway/PutawayPage.tsx"),
  resolve(process.cwd(), "src/modules/picking/PickingFlow.tsx"),
  resolve(process.cwd(), "src/modules/shipping/ShippingPage.tsx"),
  resolve(process.cwd(), "src/shared/components/WorkflowRecoveryPanel.tsx"),
];

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

function read(path) {
  return readFileSync(path, "utf8");
}

function section(markdown, title) {
  const pattern = new RegExp(`## ${title}\\n([\\s\\S]*?)(?=\\n## |\\n# |$)`);
  return markdown.match(pattern)?.[1] ?? "";
}

function parseRows(block) {
  return block
    .split(/\r?\n/)
    .filter((line) => line.startsWith("| `"))
    .map((line) => {
      const cells = line.split("|").slice(1, -1).map((cell) => cell.trim());
      return {
        code: cells[0]?.replaceAll("`", "") ?? "",
        scenario: cells[1] ?? "",
        recommendedAction: cells[2]?.replaceAll("`", "") ?? "",
        safeExit: cells[3]?.replaceAll("`", "") ?? "",
        automatedCoverage: cells[4] ?? "",
      };
    });
}

function codeIsPresent(code, sourceText) {
  const [flow, localCode] = code.split(".");
  if (!flow || !localCode) return false;
  if (sourceText.includes(localCode)) return true;
  if (localCode.endsWith("*")) return sourceText.includes(localCode.slice(0, -1));
  return false;
}

expect(existsSync(docsPath), "Recovery matrix doc is missing");
for (const file of sourceFiles) {
  expect(existsSync(file), `Expected source file is missing: ${file}`);
}

const markdown = read(docsPath);
const sourceText = sourceFiles.map(read).join("\n");
const scriptFiles = readdirSync(scriptsDir).filter((file) => file.endsWith(".mjs"));
const scriptText = scriptFiles.map((file) => read(resolve(scriptsDir, file))).join("\n");
const flows = ["Receiving", "Putaway", "Picking", "Shipping"];
const results = {};
const failures = [];

for (const flow of flows) {
  const rows = parseRows(section(markdown, flow));
  results[flow] = {
    rowCount: rows.length,
    automatedRows: rows.filter((row) => !/manual\/uat/i.test(row.automatedCoverage)).length,
    codes: rows.map((row) => row.code),
  };
  if (rows.length === 0) failures.push(`${flow} has no recovery matrix rows`);
  if (!rows.some((row) => !/manual\/uat/i.test(row.automatedCoverage))) {
    failures.push(`${flow} has no automated recovery coverage row`);
  }

  for (const row of rows) {
    if (!row.code.startsWith(`${flow.toLowerCase()}.`)) {
      failures.push(`${flow} row has wrong code prefix: ${row.code}`);
    }
    if (!row.recommendedAction) failures.push(`${row.code} is missing recommended action`);
    if (!row.safeExit) failures.push(`${row.code} is missing safe exit`);
    if (!codeIsPresent(row.code, sourceText)) {
      failures.push(`${row.code} is documented but was not found in recovery source`);
    }
    const coverageMatch = row.automatedCoverage.match(/`([^`]+\.mjs)`/);
    if (coverageMatch) {
      const script = coverageMatch[1];
      if (!scriptFiles.includes(script)) failures.push(`${row.code} references missing script ${script}`);
      if (!scriptText.includes(row.code)) failures.push(`${script} does not assert documented code ${row.code}`);
    }
  }
}

for (const selector of [
  "receiving-recovery-panel",
  "putaway-recovery-panel",
  "picking-recovery-panel",
  "shipping-recovery-panel",
  "data-recovery-code",
  "data-recovery-action",
  "data-recovery-safe-exit",
]) {
  if (!markdown.includes(selector)) failures.push(`Matrix doc does not mention selector ${selector}`);
}

const summary = {
  pass: failures.length === 0,
  docsPath,
  flows: results,
  failures,
};

console.log(JSON.stringify(summary, null, 2));
expect(failures.length === 0, `Recovery matrix validation failed:\n${failures.join("\n")}`);
