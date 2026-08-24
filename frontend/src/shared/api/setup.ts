/**
 * Typed API module for onboarding/setup progress.
 */

import api from "./client";

export type SetupProgress = {
  steps?: any[];
  completed?: number;
  total?: number;
  all_done?: boolean;
} & Record<string, unknown>;

export function fetchSetupProgress(): Promise<SetupProgress> {
  return api.get("/setup/progress").then((r) => r.data);
}

export function runQuickSetup(data: any) {
  return api.post("/setup/quick", data);
}
