import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");

function read(relativePath) {
  return fs.readFileSync(path.join(frontendDir, relativePath), "utf8");
}

const layout = read("src/shared/components/Layout.tsx");
const app = read("src/App.tsx");
const dashboard = read("src/modules/dashboard/DashboardPage.tsx");
const mail2task = read("src/modules/dashboard/Mail2TaskPage.tsx");
const operationsBoard = read("src/modules/dashboard/OperationsBoard.tsx");
const mailTaskBoard = read("src/modules/dashboard/MailTaskBoard.tsx");
const tablePrimitive = read("src/shared/components/GreaterWmsTable.tsx");
const failures = [];

const requiredShellMarkers = [
  '56px top bar',
  'w-[200px]',
  'h-14',
  'GreaterWMS',
  'PEAK SMART LOGISTICS',
];

for (const marker of requiredShellMarkers) {
  if (!layout.includes(marker)) failures.push(`shell marker missing: ${marker}`);
}

if (!app.includes('path="/mail2task"')) failures.push("Mail2Task route is missing");
if (dashboard.includes("MailTaskBoard")) failures.push("Dashboard must not render MailTaskBoard");
if (!mail2task.includes("MailTaskBoard")) failures.push("Mail2Task page must render MailTaskBoard");
if (!tablePrimitive.includes("GREATER_WMS_TABLE_SPEC")) failures.push("shared GreaterWmsTable visual contract is missing");
if (operationsBoard.includes("GreaterWmsTable")) failures.push("Warehouse Operations canonical table must not be replaced by the new shared primitive");
if (!operationsBoard.includes("bg-[#3f4b69]") || !operationsBoard.includes("grid-cols-[218px_190px_220px_minmax(190px,1fr)_165px_200px_100px_170px_48px]")) {
  failures.push("Warehouse Operations canonical GreaterWMS table markers are missing");
}
if (!mailTaskBoard.includes("GreaterWmsTableHeader") || !mailTaskBoard.includes("GreaterWmsTableRow")) {
  failures.push("Mail2Task must use the shared GreaterWmsTable primitives");
}

if (failures.length) {
  console.error("GreaterWMS shell contract failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("GreaterWMS shell/table contract passed: canonical Warehouse Operations table preserved, Mail2Task uses the shared contract.");
