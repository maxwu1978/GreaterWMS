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

if (failures.length) {
  console.error("GreaterWMS shell contract failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("GreaterWMS shell contract passed: one legacy-style shell, separate Dashboard and Mail2Task routes.");
