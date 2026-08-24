/**
 * Typed API module for pick allocation and pick-task creation.
 * Task list queries go through ./tasks.ts.
 */

import api from "./client";

export function allocatePick(orderId: string): Promise<any> {
  return api.post("/fulfillment/pick/allocate", { order_id: orderId }).then((r) => r.data);
}

export function createPickTasks(orderId: string): Promise<any> {
  return api.post("/fulfillment/pick/create-tasks", { order_id: orderId }).then((r) => r.data);
}
