import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(frontendRoot, "..");
const docsPath = resolve(repoRoot, "docs/ui-language-rules.md");
const sourceRoot = resolve(frontendRoot, "src");

const operatorPrefixes = ["receiving", "receivingFlow", "putaway", "picking", "shipping", "dashboard", "inventory"];
const operatorFiles = [
  "src/modules/receiving/ReceivingFlow.tsx",
  "src/modules/receiving/ReceivingPage.tsx",
  "src/modules/putaway/PutawayPage.tsx",
  "src/modules/picking/PickingFlow.tsx",
  "src/modules/picking/PickingPage.tsx",
  "src/modules/shipping/ShippingPage.tsx",
  "src/modules/dashboard/DashboardPage.tsx",
  "src/modules/inventory/InventoryPage.tsx",
  "src/shared/i18n.tsx",
];

const requiredDocSections = [
  "## Core Contract",
  "## Glossary",
  "## Buttons",
  "## Status And Action Words",
  "## Errors",
  "## Mobile Copy",
  "## Review Checklist",
  "## Automated Checks",
];

const requiredGlossaryTerms = ["Inbound order", "Package", "Dock", "Putaway", "Picking", "Shipping"];
const blockedInternalTerms = ["workbench", "live receiving", "live picking", "source staging", "group progress", "snapshot"];
const reviewOnlyTerms = ["handoff", "focus"];
const recoveryActions = [
  "retry",
  "refresh",
  "scan",
  "rescan",
  "return",
  "go back",
  "open",
  "choose",
  "adjust",
  "confirm",
  "continue",
  "print",
  "fix",
  "finish",
  "switch",
  "correct",
  "move",
];

const nonLabelKeyPattern = /body|detail|title|meta|validation|confirmArchive|confirmRestore|confirmVoid|confirmDelete|missing|blocked/i;

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

function read(path) {
  return readFileSync(path, "utf8");
}

function walk(dir) {
  const entries = [];
  for (const name of readdirSync(dir)) {
    const path = resolve(dir, name);
    const stat = statSync(path);
    if (stat.isDirectory()) {
      if (!["node_modules", "dist", "coverage"].includes(name)) entries.push(...walk(path));
    } else if (/\.(tsx|ts)$/.test(name)) {
      entries.push(path);
    }
  }
  return entries;
}

function unescapeString(value) {
  return value.replace(/\\n/g, " ").replace(/\\"/g, '"').replace(/\\'/g, "'").replace(/\s+/g, " ").trim();
}

function stripInterpolation(value) {
  return value.replace(/\{[^}]+\}/g, "0").replace(/\s+/g, " ").trim();
}

function visibleLength(value) {
  return stripInterpolation(value).length;
}

function isOperatorKey(key) {
  return operatorPrefixes.some((prefix) => key === prefix || key.startsWith(`${prefix}.`));
}

function extractTranslations(file, source) {
  const entries = [];
  const tCallPattern = /t\(\s*["'`]([^"'`]+)["'`]\s*,\s*(["'`])((?:\\.|(?!\2)[\s\S])*?)\2/g;
  for (const match of source.matchAll(tCallPattern)) {
    entries.push({
      file,
      key: match[1],
      text: unescapeString(match[3]),
      kind: "t",
    });
  }

  if (file.endsWith("src/shared/i18n.tsx")) {
    const i18nPattern = /["']([^"']+)["']\s*:\s*(["'`])((?:\\.|(?!\2)[\s\S])*?)\2/g;
    for (const match of source.matchAll(i18nPattern)) {
      entries.push({
        file,
        key: match[1],
        text: unescapeString(match[3]),
        kind: "i18n",
      });
    }
  }
  return entries;
}

function extractButtonTexts(file, source) {
  const labels = [];
  const buttonPattern = /<button\b[\s\S]*?<\/button>/g;
  for (const blockMatch of source.matchAll(buttonPattern)) {
    const block = blockMatch[0];
    const tCallPattern = /t\(\s*["'`]([^"'`]+)["'`]\s*,\s*(["'`])((?:\\.|(?!\2)[\s\S])*?)\2/g;
    for (const match of block.matchAll(tCallPattern)) {
      labels.push({
        file,
        key: match[1],
        text: unescapeString(match[3]),
      });
    }
  }
  return labels;
}

function location(entry) {
  return `${relative(repoRoot, entry.file)}:${entry.key}`;
}

expect(existsSync(docsPath), "docs/ui-language-rules.md is missing");

const doc = read(docsPath);
const failures = [];
const reviewHits = [];

for (const section of requiredDocSections) {
  if (!doc.includes(section)) failures.push(`Language rules doc is missing ${section}`);
}

for (const term of requiredGlossaryTerms) {
  if (!doc.includes(term)) failures.push(`Language rules glossary is missing ${term}`);
}

const allSourceFiles = walk(sourceRoot);
const sourceByFile = new Map(allSourceFiles.map((file) => [file, read(file)]));
const configuredFiles = operatorFiles.map((file) => resolve(frontendRoot, file));

for (const file of configuredFiles) {
  if (!sourceByFile.has(file)) failures.push(`Configured UI language source is missing: ${relative(repoRoot, file)}`);
}

const translations = configuredFiles
  .filter((file) => sourceByFile.has(file))
  .flatMap((file) => extractTranslations(file, sourceByFile.get(file)));
const operatorTranslations = translations.filter((entry) => isOperatorKey(entry.key));
const buttonLabels = configuredFiles
  .filter((file) => sourceByFile.has(file))
  .flatMap((file) => extractButtonTexts(file, sourceByFile.get(file)));

for (const entry of operatorTranslations) {
  const lower = entry.text.toLowerCase();
  for (const term of blockedInternalTerms) {
    if (lower.includes(term)) {
      failures.push(`${location(entry)} exposes internal term "${term}" in "${entry.text}"`);
    }
  }
  for (const term of reviewOnlyTerms) {
    if (lower.includes(term)) reviewHits.push(`${location(entry)} contains review term "${term}"`);
  }

  if (/mobile.*title|title.*mobile/i.test(entry.key) && visibleLength(entry.text) > 48) {
    failures.push(`${location(entry)} mobile title is ${visibleLength(entry.text)} chars: "${entry.text}"`);
  }

  if (/recovery.*body|scan.*missing.*body/i.test(entry.key)) {
    const hasRecoveryAction = recoveryActions.some((action) => lower.includes(action));
    if (!hasRecoveryAction) {
      failures.push(`${location(entry)} recovery copy has no next action: "${entry.text}"`);
    }
  }
}

for (const label of buttonLabels) {
  if (nonLabelKeyPattern.test(label.key) || /[.?]/.test(label.text)) continue;
  if (visibleLength(label.text) > 28) {
    failures.push(`${location(label)} button label is ${visibleLength(label.text)} chars: "${label.text}"`);
  }
}

const summary = {
  pass: failures.length === 0,
  docsPath: relative(repoRoot, docsPath),
  checkedFiles: configuredFiles.map((file) => relative(repoRoot, file)),
  checkedOperatorStrings: operatorTranslations.length,
  checkedButtonLabels: buttonLabels.length,
  reviewOnlyHits: reviewHits.length,
  failures,
};

console.log(JSON.stringify(summary, null, 2));
expect(failures.length === 0, `UI language validation failed:\n${failures.join("\n")}`);
