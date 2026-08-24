#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

exec codex \
  --dangerously-bypass-approvals-and-sandbox \
  --no-alt-screen \
  -C "$ROOT_DIR" \
  "$@"
