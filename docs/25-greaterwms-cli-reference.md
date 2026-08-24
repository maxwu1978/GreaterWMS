# WMS Agent And CLI Integration Reference

Current repository: WMS QuickStart
Last reconciled: 2026-08-24

## Important Repository Note

This file is retained at its historical path so existing links do not break.
The current checkout does not contain tools/greaterwms.mjs or tools/wms.mjs.
The old GreaterWMS command examples are not executable against this source tree
and must not be used for production operations.

The supported integration surfaces are:

1. the WMS platform Agent API under /api/v1/agent;
2. the local governed agent in wms-agent/, launched by tools/local-agent.mjs;
3. the MCP adapter in mcp-server/.

## Local Agent

From the repository root:

    node tools/local-agent.mjs start
    node tools/local-agent.mjs smoke

The default local URL is http://127.0.0.1:8787. Override it with:

    WMS_LOCAL_AGENT_HOST=127.0.0.1 WMS_LOCAL_AGENT_PORT=8787 \
      node tools/local-agent.mjs start

The local agent is a governed client. It requires WMS login, does not store the
WMS password, and does not execute writes from ordinary chat text. It renders
preview and confirmation cards and forwards approved operations to the WMS
platform API.

## MCP Client

Install the adapter:

    cd mcp-server
    uv sync

Claude Code/Desktop configuration:

    {
      "mcpServers": {
        "wms": {
          "command": "uv",
          "args": [
            "run",
            "--directory",
            "/ABSOLUTE/PATH/TO/mcp-server",
            "python",
            "-m",
            "wms_mcp.server"
          ],
          "env": {
            "WMS_API_BASE_URL": "https://api.maxsmartwms.online/api/v1",
            "WMS_EMAIL": "least-privilege@example.com",
            "WMS_PASSWORD": "supplied-outside-source-control"
          }
        }
      }
    }

For local development, use http://localhost:8000/api/v1. The MCP server
supports account verification, governed tool discovery, inventory search, and
two-phase agent tools. See ../mcp-server/README.md for the current tool list.

## Platform Agent Contract

The backend owns the operation catalog and safety gates. A write-capable flow
must preserve:

- authenticated tenant and operator identity;
- role and permission checks;
- warehouse/client scope checks;
- preview-to-confirm binding to the exact payload and content hash;
- source evidence where the operation requires an external instruction;
- expiration and idempotency checks;
- audit logging without passwords, API keys, or confirmation secrets.

The client must not bypass those gates by calling a lower-level endpoint,
reusing another operation's token, or treating a message such as confirm or yes
as authorization.

## Production Endpoint

The documented production API base is:

    https://api.maxsmartwms.online/api/v1

The documented local base is:

    http://localhost:8000/api/v1

Use a least-privilege tenant account. Confirm the live deployed SHA and health
endpoint before testing production. This reference does not grant access to
production and does not replace the release gate.

## Narrow Utility Scripts

Some files under tools/ are migration, backup, or verification utilities, for
example tools/import_sku_delta_to_greaterwms.py and
tools/build_session_backup.py. They are not a general-purpose WMS CLI. Read the
script, check its target environment, and use an isolated test tenant before
any write.

## Related Documents

- ../README.md: project entry point and quick start.
- 41-project-handoff.md: complete ownership transfer record.
- 26-wms-agent-operator-sop.md: historical operator SOP; reconcile its command
  examples with this document before use.
- 30-local-agent-platform-contract-handoff.md: local/platform ownership boundary.
- 17-release-gate-and-access-audit.md: release and access checks.
