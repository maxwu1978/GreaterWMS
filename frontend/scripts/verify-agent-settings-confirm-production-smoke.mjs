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

function resultItems(payload) {
  return payload?.result?.result?.items || payload?.result?.items || payload?.items || [];
}

function confirmationToken(preview) {
  return (
    preview?.confirmation_payload?.confirmation_token ||
    preview?.result?.confirmation_payload?.confirmation_token ||
    ""
  );
}

function previewEvidenceId(preview) {
  return preview?.evidence_id || preview?.result?.evidence_id || null;
}

function expectConfirmReplay(name, first, replay, idempotencyKey) {
  expect(first.ok === true, `${name} confirm failed`);
  expect(replay.ok === true, `${name} idempotency replay failed`);
  expect(first.idempotency_key === idempotencyKey, `${name} did not echo idempotency key`);
  expect(replay.idempotency_key === idempotencyKey, `${name} replay did not echo idempotency key`);
  expect(first.evidence_id === replay.evidence_id, `${name} replay did not reuse evidence`);
}

function confirmSettings({ name, previewArgs, confirmArgs, idempotencyKey, env }) {
  const preview = runCli(previewArgs, env);
  const token = confirmationToken(preview);
  expect(preview.ok === true, `${name} preview failed`);
  expect(Boolean(token), `${name} preview did not return a confirmation token`);
  if (!token) {
    return { name, preview_ok: preview.ok, evidence_id: previewEvidenceId(preview), skipped: "missing token" };
  }

  const confirmBase = [
    ...confirmArgs,
    "--confirm",
    token,
    "--production-confirm",
    "--idempotency-key",
    idempotencyKey,
  ];
  const first = runCli(confirmBase, env);
  const replay = runCli(confirmBase, env);
  expectConfirmReplay(name, first, replay, idempotencyKey);
  return {
    name,
    preview_ok: preview.ok,
    evidence_id: first.evidence_id || previewEvidenceId(preview),
    changed_fields: first.changed_fields || [],
    idempotency_key: first.idempotency_key,
    replay_ok: replay.ok,
  };
}

const targetApiUrl = process.env.WMS_API_URL || "https://api.maxsmartwms.online";
const token = process.env.WMS_TOKEN || "";
const shouldConfirm = process.env.WMS_SETTINGS_CONFIRM_SMOKE === "true";
const stamp = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 12);
const evidence = {
  ok: false,
  action: "agent.settings_confirm_production_smoke",
  target_api_url: targetApiUrl,
  mode: shouldConfirm ? "preview_and_confirm" : "capability_or_preview_only",
  checks: {},
  failures,
};

const health = runCli(["health", "--timeout-ms", "30000"]);
evidence.checks.health = health;
expect(health.ok === true, "health command failed");
expect(health.result?.status === "ok", "production health status is not ok");

const capabilities = runCli(["capabilities", "--json"]);
const settingsCommands = [
  "settings receiving-codes preview",
  "settings receiving-labels preview",
  "settings client-profile preview",
  "settings sku preview",
  "settings warehouse-location preview",
];
evidence.checks.capabilities = {
  ok: capabilities.ok,
  settings_write_gates: settingsCommands.map((command) => {
    const item = capabilities.commands?.find((candidate) => candidate.command === command);
    return {
      command,
      auth: item?.auth,
      write_gate_enabled: item?.agent_write_gate?.enabled,
      preview_endpoint: item?.agent_write_gate?.preview_endpoint,
      agent_endpoint: item?.agent_write_gate?.agent_endpoint,
    };
  }),
};
for (const item of evidence.checks.capabilities.settings_write_gates) {
  expect(item.auth === true, `${item.command} must require auth`);
  expect(item.write_gate_enabled === true, `${item.command} must expose an enabled write gate`);
  expect(Boolean(item.preview_endpoint), `${item.command} missing preview endpoint`);
  expect(Boolean(item.agent_endpoint), `${item.command} missing agent endpoint`);
}

if (!token) {
  evidence.skipped = "Set WMS_TOKEN and WMS_SETTINGS_CONFIRM_SMOKE=true to run settings confirms.";
  evidence.ok = failures.length === 0;
  console.log(JSON.stringify(evidence, null, 2));
  process.exit(evidence.ok ? 0 : 1);
}

const env = { WMS_API_URL: targetApiUrl };

if (!shouldConfirm) {
  const preview = runCli(
    [
      "settings",
      "receiving-codes",
      "preview",
      "--settings",
      JSON.stringify({ prefix: "CHK", sequence_padding: 4 }),
    ],
    env,
  );
  evidence.checks.preview = {
    ok: preview.ok,
    evidence_id: previewEvidenceId(preview),
    confirmation_required_for_write: preview.confirmation_required_for_write,
    has_confirmation_token: Boolean(confirmationToken(preview)),
  };
  expect(preview.ok === true, "settings receiving-codes preview failed");
  evidence.skipped = "Set WMS_SETTINGS_CONFIRM_SMOKE=true to execute settings confirms.";
  evidence.ok = failures.length === 0;
  console.log(JSON.stringify(evidence, null, 2));
  process.exit(evidence.ok ? 0 : 1);
}

const clients = runCli(["client", "list", "--limit", "1"], env);
const skus = runCli(["sku", "list", "--limit", "1"], env);
const locations = runCli(["settings", "warehouse-locations", "--limit", "10"], env);
const client = resultItems(clients)[0];
const sku = resultItems(skus)[0];
const location = resultItems(locations).find((item) => item.location_type === "storage") || resultItems(locations)[0];
expect(Boolean(client?.id), "no client found for settings confirm smoke");
expect(Boolean(sku?.id), "no SKU found for settings confirm smoke");
expect(Boolean(location?.id), "no location found for settings confirm smoke");

const checks = [];
if (client?.id && sku?.id && location?.id) {
  checks.push(
    confirmSettings({
      name: "receiving-codes",
      previewArgs: [
        "settings",
        "receiving-codes",
        "preview",
        "--settings",
        JSON.stringify({ prefix: "SMK", separator: "-", include_order_number: true, sequence_padding: 4, uppercase: true }),
      ],
      confirmArgs: [
        "settings",
        "receiving-codes",
        "preview",
        "--settings",
        JSON.stringify({ prefix: "SMK", separator: "-", include_order_number: true, sequence_padding: 4, uppercase: true }),
      ],
      idempotencyKey: `settings-confirm:receiving-codes:${stamp}`,
      env,
    }),
    confirmSettings({
      name: "receiving-labels",
      previewArgs: [
        "settings",
        "receiving-labels",
        "preview",
        "--settings",
        JSON.stringify({ fields: ["order_number", "tracking_number", "sku_code"], show_field_labels: true }),
      ],
      confirmArgs: [
        "settings",
        "receiving-labels",
        "preview",
        "--settings",
        JSON.stringify({ fields: ["order_number", "tracking_number", "sku_code"], show_field_labels: true }),
      ],
      idempotencyKey: `settings-confirm:receiving-labels:${stamp}`,
      env,
    }),
    confirmSettings({
      name: "client-profile",
      previewArgs: [
        "settings",
        "client-profile",
        "preview",
        "--client-id",
        client.id,
        "--changes",
        JSON.stringify({ contact_phone: `+1-925-555-${stamp.slice(-4)}` }),
      ],
      confirmArgs: [
        "settings",
        "client-profile",
        "preview",
        "--client-id",
        client.id,
        "--changes",
        JSON.stringify({ contact_phone: `+1-925-555-${stamp.slice(-4)}` }),
      ],
      idempotencyKey: `settings-confirm:client-profile:${stamp}`,
      env,
    }),
    confirmSettings({
      name: "sku",
      previewArgs: [
        "settings",
        "sku",
        "preview",
        "--sku-id",
        sku.id,
        "--changes",
        JSON.stringify({ name: `${sku.name || sku.sku_code} Smoke ${stamp.slice(-4)}` }),
      ],
      confirmArgs: [
        "settings",
        "sku",
        "preview",
        "--sku-id",
        sku.id,
        "--changes",
        JSON.stringify({ name: `${sku.name || sku.sku_code} Smoke ${stamp.slice(-4)}` }),
      ],
      idempotencyKey: `settings-confirm:sku:${stamp}`,
      env,
    }),
    confirmSettings({
      name: "warehouse-location",
      previewArgs: [
        "settings",
        "warehouse-location",
        "preview",
        "--location-id",
        location.id,
        "--changes",
        JSON.stringify({ pick_sequence: Number(location.pick_sequence || 0) + 1 }),
      ],
      confirmArgs: [
        "settings",
        "warehouse-location",
        "preview",
        "--location-id",
        location.id,
        "--changes",
        JSON.stringify({ pick_sequence: Number(location.pick_sequence || 0) + 1 }),
      ],
      idempotencyKey: `settings-confirm:warehouse-location:${stamp}`,
      env,
    }),
  );
}

evidence.checks.settings_confirms = checks;
evidence.ok = failures.length === 0;
console.log(JSON.stringify(evidence, null, 2));
process.exit(evidence.ok ? 0 : 1);
