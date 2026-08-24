/**
 * Typed API module for the AI agent console/settings.
 */

import api from "./client";

export function fetchAgentSettings<T = any>(): Promise<T> {
  return api.get("/agent/settings").then((r) => r.data as T);
}

export function updateAgentSettings<T = any>(payload: Record<string, unknown>): Promise<T> {
  return api.put("/agent/settings", payload).then((r) => r.data as T);
}

export function runAgentTool<T = any>(payload: { tool_name: string; args: Record<string, unknown> }): Promise<T> {
  return api.post("/agent/tools/run", payload).then((r) => r.data as T);
}
