# WMS MCP Server

Exposes MaxSmart WMS to any MCP client (Claude Desktop, Claude Code, etc.)
while preserving the platform's governance model. The MCP layer adds **no**
privileges: authenticated tools act as the configured WMS account, and agent
tools run through the same governed engine as the in-app Agent Console
(risk tiers, allowed-tools whitelist, preview/confirm tokens, evidence audit).

## Tools

| Tool | Auth | What it does |
|---|---|---|
| `register_tenant` | none (public endpoint) | Open a new company workspace + admin account. Requires explicit `accept_terms` / `accept_risk_notice` — ask the human first. |
| `whoami` | account | Verify login; report agent status and allowed tools. |
| `create_client` | account | Create a client (cargo owner) profile — 客户开户. Duplicate codes are rejected (409) by a DB unique constraint. |
| `list_agent_tools` | account | The governed tool catalog (39 tools) with risk tiers and the tenant's whitelist. |
| `run_agent_tool` | account | Run any governed agent tool. Writes are two-phase: first call returns a dry-run preview + `confirmation_token`; re-call with the token in `args` to execute. |
| `search_inventory` | account | Convenience wrapper for the `inventory.search` governed read. |

Note: the tenant must have the Agent Console enabled (an LLM provider
configured in `/agent-settings`) before `run_agent_tool` / `search_inventory`
work; until then the API returns "Agent console is disabled for this tenant".
`register_tenant` / `create_client` / `whoami` work regardless.

## Install

```bash
cd mcp-server
uv sync
```

## Configure a client

Claude Code (`.mcp.json` in any project, or `claude mcp add`):

```json
{
  "mcpServers": {
    "wms": {
      "command": "uv",
      "args": ["run", "--directory", "/ABSOLUTE/PATH/TO/mcp-server", "python", "-m", "wms_mcp.server"],
      "env": {
        "WMS_API_BASE_URL": "https://api.maxsmartwms.online/api/v1",
        "WMS_EMAIL": "you@example.com",
        "WMS_PASSWORD": "..."
      }
    }
  }
}
```

Claude Desktop: same block under `mcpServers` in
`~/Library/Application Support/Claude/claude_desktop_config.json`.

For a local backend set `WMS_API_BASE_URL=http://localhost:8000/api/v1`.
Credentials are optional if you only need `register_tenant`.

## Security notes

- The account in `WMS_EMAIL` defines the blast radius — use a least-privilege
  account, not a platform admin, unless you need cross-tenant operations.
- Write-capable agent tools stay behind the server-side preview/confirm gate;
  an MCP client cannot skip the token handshake.
- All agent-tool calls are audit-logged server-side (evidence trail in the
  Agent Console).
