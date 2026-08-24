#!/usr/bin/env python3
"""Validate the checked-in environment/release contract without network access."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "release" / "environment-manifest.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def fail(message: str) -> None:
    print(f"release manifest error: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read {MANIFEST_PATH}: {exc}")

    environments = manifest.get("environments")
    if not isinstance(environments, dict):
        fail("environments must be an object")

    for name in ("legacy_production", "migrated_staging"):
        env = environments.get(name)
        if not isinstance(env, dict):
            fail(f"missing environment: {name}")
        sha = env.get("verified_commit")
        if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
            fail(f"{name}.verified_commit must be a full Git SHA")
        if not env.get("render_service_id"):
            fail(f"{name}.render_service_id is required")

    production = environments["legacy_production"]
    staging = environments["migrated_staging"]
    if production["git_branch"] == "main":
        fail("legacy production must not track main")
    if production["render_service_id"] == staging["render_service_id"]:
        fail("production and staging must use different Render services")
    if production["verified_commit"] == staging["verified_commit"]:
        fail("legacy production and migrated staging commits must be reviewed separately")
    if not production.get("release_tag", "").startswith("prod-"):
        fail("legacy production must have a prod-* release tag")

    render_yaml = (ROOT / "render.yaml").read_text()
    if "name: wms-quickstart-staging" not in render_yaml:
        fail("render.yaml must identify the migrated backend as wms-quickstart-staging")
    if "branch: main" not in render_yaml:
        fail("render.yaml migrated backend must track main")

    print(
        "release manifest valid: "
        f"production={production['verified_commit'][:8]} "
        f"staging={staging['verified_commit'][:8]}"
    )


if __name__ == "__main__":
    main()
