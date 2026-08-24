/**
 * Typed API module for dashboard/report queries.
 */

import api from "./client";

export function fetchDashboardReport(): Promise<any> {
  return api.get("/reports/dashboard").then((r) => r.data);
}
