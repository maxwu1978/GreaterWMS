/**
 * Paywall banner — shows when subscription is expired, trial ending, or past due.
 * Rendered at the top of the layout when subscription status requires attention.
 */

import { useQuery } from "@tanstack/react-query";
import api from "../api/client";
import { queryKeys } from "../api/queryKeys";

export default function PaywallBanner() {
  const { data: sub } = useQuery({
    queryKey: queryKeys.subscriptions.status(),
    queryFn: () => api.get("/subscriptions/current").then((r) => r.data).catch(() => null),
    staleTime: 60_000, // Check every minute
    retry: false,
  });

  if (!sub) return null;

  // Trial ending soon (< 3 days)
  if (sub.status === "trial" && sub.trial_end) {
    const daysLeft = Math.ceil(
      (new Date(sub.trial_end).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    );
    if (daysLeft <= 3 && daysLeft > 0) {
      return (
        <Banner color="blue">
          Your free trial ends in {daysLeft} day{daysLeft > 1 ? "s" : ""}.{" "}
          <a href="/pricing" className="underline font-semibold">Choose a plan →</a>
        </Banner>
      );
    }
  }

  // Past due
  if (sub.status === "past_due") {
    return (
      <Banner color="yellow">
        Payment past due. Please{" "}
        <a href="/subscription" className="underline font-semibold">update your payment method</a>{" "}
        to avoid service interruption.
      </Banner>
    );
  }

  // Cancelled but still active
  if (sub.status === "cancelled_active") {
    return (
      <Banner color="gray">
        Your subscription is cancelled. Access continues until {sub.period_end}.{" "}
        <a href="/pricing" className="underline font-semibold">Resubscribe →</a>
      </Banner>
    );
  }

  return null;
}

function Banner({ children, color }: { children: React.ReactNode; color: "blue" | "yellow" | "red" | "gray" }) {
  const colors = {
    blue: "bg-blue-600 text-white",
    yellow: "bg-yellow-400 text-yellow-900",
    red: "bg-red-600 text-white",
    gray: "bg-gray-600 text-white",
  };
  return (
    <div className={`px-4 py-2 text-center text-sm ${colors[color]}`}>
      {children}
    </div>
  );
}
