---
name: wms-release-gate-verifier
description: Use when verifying WMS release readiness, CI/deploy status, production health, agent capability metadata, CLI contract, smoke output, and evidence/audit boundaries.
---

# WMS Release Gate Verifier

Run local gates before commit and production gates after deploy.

## Local

```bash
node --check tools/wms.mjs
cd backend && uv run ruff check app tests/test_regressions.py
cd backend && uv run mypy app
cd backend && uv run pytest -q
cd frontend && npm run check:agent-contract
cd frontend && npm run smoke:agent-production
cd frontend && npm run lint -- --quiet
git diff --check
```

## Production

```bash
gh run list --branch main --limit 5 --json databaseId,headSha,status,conclusion,workflowName,url
curl -fsS https://api.maxsmartwms.online/health
```

Completion requires CI success, Render deploy success, production `health`
`status: ok`, and `build_sha` matching the pushed commit.
