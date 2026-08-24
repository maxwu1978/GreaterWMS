import { execFileSync } from "node:child_process";
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

function firstRateCardId(payload) {
  const items = payload?.result?.result?.items || payload?.result?.items || payload?.items || [];
  return items[0]?.id || "";
}

const targetApiUrl = process.env.WMS_API_URL || "https://api.maxsmartwms.online";
const token = process.env.WMS_TOKEN || "";
const evidence = {
  ok: false,
  action: "agent.billing_production_smoke",
  target_api_url: targetApiUrl,
  mode: "preview_only",
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
  billing_read: capabilities.commands?.find((item) => item.command === "settings billing"),
  rate_cards_list: capabilities.commands?.find((item) => item.command === "billing rate-cards list"),
  rate_card_preview: capabilities.commands?.find(
    (item) => item.command === "settings billing-rate-card preview",
  ),
};
expect(capabilities.ok === true, "capabilities command failed");
expect(Boolean(evidence.checks.capabilities.billing_read), "missing settings billing command");
expect(Boolean(evidence.checks.capabilities.rate_cards_list), "missing billing rate-cards list command");
expect(
  evidence.checks.capabilities.rate_card_preview?.agent_write_gate?.enabled !== true,
  "billing rate-card preview must remain preview-only without an enabled write gate",
);

if (!token) {
  evidence.skipped = "Set WMS_TOKEN for authenticated billing reads and preview-only rate-card smoke.";
  evidence.ok = failures.length === 0;
  console.log(JSON.stringify(evidence, null, 2));
  process.exit(evidence.ok ? 0 : 1);
}

const env = { WMS_API_URL: targetApiUrl };
const billing = runCli(["settings", "billing"], env);
evidence.checks.billing = {
  ok: billing.ok,
  action: billing.action,
  evidence_id: billing.evidence_id,
  active_rate_cards: billing.result?.result?.billing_summary?.active_rate_cards,
};
expect(billing.ok === true, "settings billing read failed");

const rateCards = runCli(["billing", "rate-cards", "list", "--limit", "5"], env);
const rateCardId = firstRateCardId(rateCards);
evidence.checks.rate_cards = {
  ok: rateCards.ok,
  count: rateCards.result?.result?.count,
  first_rate_card_id: rateCardId || null,
};
expect(rateCards.ok === true, "billing rate-cards list failed");

if (!rateCardId) {
  evidence.checks.preview = {
    skipped: "No rate card returned for this tenant; preview-only write design was not exercised.",
  };
} else {
  const preview = runCli(
    [
      "settings",
      "billing-rate-card",
      "preview",
      "--rate-card-id",
      rateCardId,
      "--changes",
      '{"notes":"Agent preview-only smoke; no write executed"}',
    ],
    env,
  );
  evidence.checks.preview = {
    ok: preview.ok,
    action: preview.action,
    evidence_id: preview.evidence_id,
    writes: preview.result?.result?.writes,
    confirmation_required_for_write: preview.result?.result?.confirmation_required_for_write,
    target: preview.result?.result?.target,
  };
  expect(preview.ok === true, "billing rate-card preview failed");
  expect(
    preview.result?.result?.confirmation_required_for_write !== true,
    "billing rate-card preview must not return a confirmable write card",
  );
}

evidence.ok = failures.length === 0;
console.log(JSON.stringify(evidence, null, 2));
process.exit(evidence.ok ? 0 : 1);
