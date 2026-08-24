#!/usr/bin/env node

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const agentPythonPath = resolve(repoRoot, "wms-agent/.venv/bin/python");
const backendPythonPath = resolve(repoRoot, "backend/.venv/bin/python");
const fallbackPython = "python3";
const host = process.env.WMS_LOCAL_AGENT_HOST || "127.0.0.1";
const port = process.env.WMS_LOCAL_AGENT_PORT || "8787";

function usage() {
  console.log(`Usage:
  node tools/local-agent.mjs start
  node tools/local-agent.mjs smoke

Environment:
  WMS_LOCAL_AGENT_HOST=${host}
  WMS_LOCAL_AGENT_PORT=${port}
  WMS_LOCAL_AGENT_MODEL_PROVIDER=deepseek
  WMS_LOCAL_AGENT_MODEL_BASE_URL=https://api.deepseek.com/v1
  WMS_LOCAL_AGENT_MODEL_NAME=deepseek-chat
  WMS_LOCAL_AGENT_MODEL_API_KEY=...
`);
}

function run(command, args, options = {}) {
  const child = spawn(command, args, {
    stdio: "inherit",
    cwd: repoRoot,
    env: {
      ...process.env,
      PYTHONPATH: resolve(repoRoot, "wms-agent"),
    },
    ...options,
  });
  child.on("exit", (code) => process.exit(code ?? 1));
}

const action = process.argv[2] || "help";
// Prefer the agent environment so a clean checkout does not accidentally use
// a system Python missing the standalone agent dependencies.
const python = existsSync(agentPythonPath)
  ? agentPythonPath
  : existsSync(backendPythonPath)
    ? backendPythonPath
    : fallbackPython;

if (action === "start") {
  console.log(`Starting WMS Local Agent at http://${host}:${port}`);
  run(python, ["-m", "uvicorn", "local_agent.server:app", "--app-dir", "wms-agent", "--host", host, "--port", port]);
} else if (action === "smoke") {
  run(python, ["-m", "pytest", "wms-agent/tests", "-q"]);
} else {
  usage();
}
