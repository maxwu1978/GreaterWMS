#!/usr/bin/env python3
"""Fail fast when a GreaterWMS release points at the wrong repository/branch."""

import argparse
import os


EXPECTED_REPO = "https://github.com/maxwu1978/GreaterWMS.git"
EXPECTED_BRANCH = "codex/sn-receiving"
EXPECTED_SERVICE = "greaterwms-v2-test3-sn"
EXPECTED_SERVICE_ID = "srv-d9r3c41t0dsc73b94l2g"
EXPECTED_URL = "https://greaterwms-v2-test3-sn.onrender.com"


def normalize_repo(value):
    value = value.strip().rstrip("/")
    if value.startswith("git@github.com:"):
        return "https://github.com/" + value[len("git@github.com:") :]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote-url", default=os.environ.get("GREATERWMS_DEPLOY_REPO", EXPECTED_REPO))
    parser.add_argument("--target-branch", default=EXPECTED_BRANCH)
    args = parser.parse_args()

    if args.target_branch != EXPECTED_BRANCH:
        raise SystemExit(
            f"Refusing release: target branch must be {EXPECTED_BRANCH}, got {args.target_branch}"
        )

    remote = normalize_repo(args.remote_url)
    if remote != EXPECTED_REPO:
        raise SystemExit(
            f"Refusing release: deployment repository must be {EXPECTED_REPO}, got {remote or '<missing>'}"
        )

    print(f"GreaterWMS release target verified: {EXPECTED_SERVICE} ({EXPECTED_SERVICE_ID})")
    print(f"repository: {EXPECTED_REPO}")
    print(f"branch: {EXPECTED_BRANCH}")
    print(f"url: {EXPECTED_URL}")


if __name__ == "__main__":
    main()
