/**
 * Typed API module for warehouse task queries (pick/putaway/etc.).
 */

import api from "./client";

export type TaskQueryParams = {
  status?: string;
  task_type?: string;
  assigned_type?: string;
  assigned_to?: string;
  limit?: number;
};

/** GET /tasks/ — raw response body. */
export function fetchTasks<T = any>(params: TaskQueryParams): Promise<T> {
  return api.get("/tasks/", { params }).then((r) => r.data);
}
