import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const repoRoot = resolve(process.cwd(), "..");
const cliPath = resolve(repoRoot, "tools/wms.mjs");
const failures = [];

function expect(condition, message) {
  if (!condition) failures.push(message);
}

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
    if (stdout.trim()) return JSON.parse(stdout);
    throw error;
  }
}

function csvInput() {
  const file = process.env.WMS_IMPORT_SMOKE_CSV_FILE;
  if (file && existsSync(file)) return { args: ["--file", file], source: file };
  const csvText =
    process.env.WMS_IMPORT_SMOKE_CSV ||
    "sku_code,location_barcode,quantity\nSMOKE-SKU-DO-NOT-CONFIRM,SMOKE-LOC-DO-NOT-CONFIRM,1\n";
  return { args: ["--csv-text", csvText], source: "inline" };
}

const targetApiUrl = process.env.WMS_API_URL || "https://api.maxsmartwms.online";
const shouldConfirm = process.env.WMS_IMPORT_SMOKE_CONFIRM === "true";
const token = process.env.WMS_TOKEN || "";
const evidence = {
  ok: false,
  action: "agent.import_production_smoke",
  target_api_url: targetApiUrl,
  mode: shouldConfirm ? "preview_and_confirm" : "preview_only",
  checks: {},
  failures,
};

const health = runCli(["health", "--timeout-ms", "30000"]);
evidence.checks.health = health;
expect(health.ok === true, "health command failed");
expect(health.result?.status === "ok", "production health status is not ok");

const capabilities = runCli(["capabilities", "--json"]);
evidence.checks.capabilities = {
  ok: capabilities.ok,
  import_preview_gate: capabilities.commands?.find(
    (item) => item.command === "inventory import preview",
  ),
};
expect(capabilities.ok === true, "capabilities command failed");
expect(
  evidence.checks.capabilities.import_preview_gate?.agent_write_gate?.enabled === true,
  "inventory import preview is missing enabled write-gate metadata",
);

if (!token) {
  evidence.skipped = "Set WMS_TOKEN to run the authenticated import preview.";
  evidence.ok = failures.length === 0;
  console.log(JSON.stringify(evidence, null, 2));
  process.exit(evidence.ok ? 0 : 1);
}

const input = csvInput();
const preview = runCli(["inventory", "import", "preview", ...input.args], {
  WMS_API_URL: targetApiUrl,
});
evidence.checks.preview = {
  ok: preview.ok,
  dry_run: preview.dry_run,
  writes: preview.writes,
  total_rows: preview.total_rows,
  summary: preview.summary,
  evidence_id: preview.evidence_id,
  confirmation_required_for_write: preview.confirmation_required_for_write,
  source: input.source,
};
expect(preview.dry_run === true, "import preview did not mark dry_run=true");
expect(preview.writes === false, "import preview must not write");

if (shouldConfirm) {
  const confirmationToken = preview.confirmation_payload?.confirmation_token;
  const idempotencyKey =
    process.env.WMS_IMPORT_SMOKE_IDEMPOTENCY_KEY ||
    `agent-import-smoke:${health.result?.build_sha || "unknown"}`;
  expect(Boolean(confirmationToken), "confirm mode requires a confirmable preview token");
  if (confirmationToken) {
    const confirmed = runCli(
      [
        "inventory",
        "import",
        "preview",
        ...input.args,
        "--confirm",
        confirmationToken,
        "--production-confirm",
        "--idempotency-key",
        idempotencyKey,
      ],
      { WMS_API_URL: targetApiUrl },
    );
    evidence.checks.confirm = {
      ok: confirmed.ok,
      evidence_id: confirmed.evidence_id,
      idempotency_key: confirmed.idempotency_key,
      result: confirmed.result,
    };
    expect(confirmed.ok === true, "import confirm did not return ok=true");
    expect(confirmed.idempotency_key === idempotencyKey, "confirm did not echo idempotency key");
  }
} else {
  evidence.checks.confirm = {
    skipped: "Set WMS_IMPORT_SMOKE_CONFIRM=true with a test-tenant CSV to execute one import confirm.",
  };
}

evidence.ok = failures.length === 0;
console.log(JSON.stringify(evidence, null, 2));
process.exit(evidence.ok ? 0 : 1);
