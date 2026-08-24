#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { copyFileSync, cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { basename, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const agentRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(agentRoot, "..");
const distDir = resolve(repoRoot, "dist", "wms-agent");
const stageRoot = resolve(distDir, "stage", "wms-agent");
const version = "0.1.0";

function run(command, args, options = {}) {
  execFileSync(command, args, { stdio: "inherit", ...options });
}

function copyTree(name) {
  cpSync(resolve(agentRoot, name), resolve(stageRoot, name), {
    recursive: true,
    filter: (source) => {
      const leaf = basename(source);
      return !["__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "dist", "build"].includes(leaf);
    },
  });
}

rmSync(distDir, { recursive: true, force: true });
mkdirSync(stageRoot, { recursive: true });

for (const name of ["local_agent", "skills", "install", "scripts", "tests"]) copyTree(name);
for (const name of ["README.md", "pyproject.toml", ".env.example"]) {
  copyFileSync(resolve(agentRoot, name), resolve(stageRoot, name));
}

const macZip = resolve(distDir, `wms-agent-${version}-macos.zip`);
const windowsZip = resolve(distDir, `wms-agent-${version}-windows.zip`);
const sourceZip = resolve(distDir, `wms-agent-${version}-source.zip`);

run("python3", ["-m", "zipfile", "-c", macZip, "wms-agent"], {
  cwd: resolve(distDir, "stage"),
});
run("python3", ["-m", "zipfile", "-c", windowsZip, "wms-agent"], {
  cwd: resolve(distDir, "stage"),
});
run("python3", ["-m", "zipfile", "-c", sourceZip, "wms-agent"], {
  cwd: resolve(distDir, "stage"),
});

if (!existsSync(macZip) || !existsSync(windowsZip) || !existsSync(sourceZip)) {
  throw new Error("Failed to create one or more WMS Agent archives.");
}

console.log(`Created:
- ${macZip}
- ${windowsZip}
- ${sourceZip}`);
