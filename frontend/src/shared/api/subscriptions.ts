/**
 * Typed API module for subscription/plan management and tenant registration.
 */

import api from "./client";

export function fetchCurrentSubscription(): Promise<any> {
  return api.get("/subscriptions/current").then((r) => r.data);
}

export function fetchSubscriptionUsage(): Promise<any> {
  return api.get("/subscriptions/usage").then((r) => r.data);
}

export function fetchSubscriptionPlans(): Promise<any> {
  return api.get("/subscriptions/plans").then((r) => r.data);
}

export function activateSubscription(payload: { plan_code: string; billing_cycle: string }) {
  return api.post("/subscriptions/activate", payload);
}

export function cancelSubscription(reason: string) {
  return api.post("/subscriptions/cancel", { reason });
}

export function registerTenant(payload: Record<string, unknown>): Promise<any> {
  return api.post("/subscriptions/register", payload).then((r) => r.data);
}
