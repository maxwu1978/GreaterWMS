import { spawn } from "node:child_process";

const appUrl = process.env.WMS_AUDIT_APP_URL ?? "https://app.maxsmartwms.online";

const stages = [
  {
    name: "Action-first mobile surfaces",
    command: ["node", "./scripts/verify-action-first-mobile-surfaces.mjs"],
    covers: ["Dashboard", "Inventory", "Putaway", "Picking", "Shipping"],
  },
  {
    name: "Receiving to Putaway mobile handoff",
    command: ["node", "./scripts/verify-receiving-putaway-action-surfaces.mjs"],
    covers: ["Receiving", "Putaway"],
  },
  {
    name: "Putaway and Picking recovery actions",
    command: ["node", "./scripts/verify-recovery-action-clicks.mjs"],
    covers: ["Putaway", "Picking"],
  },
  {
    name: "Shipping mobile recovery and handoff",
    command: ["node", "./scripts/verify-shipping-flow.mjs"],
    covers: ["Shipping"],
  },
  {
    name: "Admin mobile governance",
    command: ["node", "./scripts/verify-admin-mobile-governance-visual.mjs"],
    covers: ["Admin", "Agent", "Master Data", "Migration"],
  },
];

function run(command, env = {}) {
  return new Promise((resolve) => {
    const [bin, ...args] = command;
    const startedAt = Date.now();
    const child = spawn(bin, args, {
      cwd: process.cwd(),
      env: { ...process.env, WMS_AUDIT_APP_URL: appUrl, ...env },
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
      process.stdout.write(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
      process.stderr.write(chunk);
    });
    child.on("close", (code) => {
      resolve({
        code,
        durationMs: Date.now() - startedAt,
        stdout: stdout.trim(),
        stderr: stderr.trim(),
      });
    });
  });
}

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

const results = [];
let failed = false;

for (const stage of stages) {
  console.error(`[mobile-orchestrator] start: ${stage.name}`);
  const result = await run(stage.command);
  results.push({
    stage: stage.name,
    covers: stage.covers,
    command: stage.command.join(" "),
    pass: result.code === 0,
    durationMs: result.durationMs,
  });
  if (result.code !== 0) {
    failed = true;
    console.error(`[mobile-orchestrator] failed: ${stage.name}`);
    break;
  }
  console.error(`[mobile-orchestrator] passed: ${stage.name}`);
}

const cleanup = await run(["node", "./scripts/cleanup-production-test-data.mjs"]);
results.push({
  stage: "Production test data cleanup",
  covers: ["cleanup"],
  command: "node ./scripts/cleanup-production-test-data.mjs",
  pass: cleanup.code === 0,
  durationMs: cleanup.durationMs,
});

const coveredFlows = new Set(results.filter((result) => result.pass).flatMap((result) => result.covers));
const summary = {
  pass: !failed && cleanup.code === 0,
  appUrl,
  coveredFlows: Array.from(coveredFlows).filter((flow) => flow !== "cleanup").sort(),
  stages: results,
};

console.log(JSON.stringify(summary, null, 2));

expect(summary.pass, "Mobile UAT orchestrator failed");
for (const flow of ["Receiving", "Putaway", "Picking", "Shipping"]) {
  expect(coveredFlows.has(flow), `Mobile UAT orchestrator did not cover ${flow}`);
}
for (const flow of ["Dashboard", "Inventory"]) {
  expect(coveredFlows.has(flow), `Mobile UAT orchestrator did not cover ${flow}`);
}
for (const flow of ["Admin", "Agent", "Master Data", "Migration"]) {
  expect(coveredFlows.has(flow), `Mobile UAT orchestrator did not cover ${flow}`);
}
