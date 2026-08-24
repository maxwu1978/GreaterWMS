import { useQuery } from "@tanstack/react-query";
import {
  cancelSubscription,
  fetchCurrentSubscription,
  fetchSubscriptionUsage,
} from "../../shared/api/subscriptions";
import { queryKeys } from "../../shared/api/queryKeys";

export default function SubscriptionPage() {
  const { data: sub } = useQuery({
    queryKey: queryKeys.subscriptions.current(),
    queryFn: fetchCurrentSubscription,
  });

  const { data: usage } = useQuery({
    queryKey: queryKeys.subscriptions.usage(),
    queryFn: fetchSubscriptionUsage,
  });

  if (!sub) return <div className="text-gray-400 p-8">Loading...</div>;

  const statusColor: Record<string, string> = {
    trial: "bg-blue-100 text-blue-700",
    active: "bg-green-100 text-green-700",
    past_due: "bg-yellow-100 text-yellow-700",
    cancelled: "bg-red-100 text-red-600",
    expired: "bg-red-100 text-red-600",
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Subscription</h1>

      {/* Status card */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm text-gray-500">Current Plan</p>
            <p className="text-2xl font-bold">{sub.plan_name || sub.plan || "None"}</p>
          </div>
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${statusColor[sub.status] || "bg-gray-100"}`}>
            {sub.status}
          </span>
        </div>
        {sub.trial_end && (
          <p className="text-sm text-blue-600">Trial ends: {sub.trial_end}</p>
        )}
        {sub.period_end && (
          <p className="text-sm text-gray-500">Current period ends: {sub.period_end}</p>
        )}
        <div className="flex gap-3 mt-4">
          <a href="/pricing" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium">
            {sub.status === "active" ? "Upgrade Plan" : "Choose Plan"}
          </a>
          {sub.status === "active" && (
            <button
              onClick={async () => {
                if (confirm("Are you sure you want to cancel? You will retain access until the end of your billing period.")) {
                  await cancelSubscription("User initiated");
                  window.location.reload();
                }
              }}
              className="px-4 py-2 bg-gray-100 text-gray-600 rounded-lg text-sm"
            >
              Cancel Plan
            </button>
          )}
        </div>
      </div>

      {/* Usage */}
      {usage?.usage && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">Resource Usage</h2>
          <div className="space-y-4">
            {Object.entries(usage.usage as Record<string, { used: number; limit: number; pct: number }>).map(
              ([key, val]) => (
                <div key={key}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="capitalize font-medium">{key}</span>
                    <span className="text-gray-500">
                      {val.used} / {val.limit === 999999 ? "∞" : val.limit}
                    </span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        val.pct >= 90 ? "bg-red-500" : val.pct >= 70 ? "bg-yellow-400" : "bg-blue-500"
                      }`}
                      style={{ width: `${Math.min(val.pct, 100)}%` }}
                    />
                  </div>
                </div>
              )
            )}
          </div>
        </div>
      )}
    </div>
  );
}
