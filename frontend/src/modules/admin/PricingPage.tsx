import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Boxes, Check, ShieldCheck, Users, Workflow } from "lucide-react";
import { activateSubscription, fetchSubscriptionPlans } from "../../shared/api/subscriptions";
import { queryKeys } from "../../shared/api/queryKeys";
import { getApiErrorMessage } from "../../shared/api/error-message";

interface Plan {
  id: string;
  name: string;
  code: string;
  price_monthly: number;
  price_yearly: number;
  max_clients: number;
  max_skus: number;
  max_orders_per_day: number;
  max_users: number;
  max_warehouses: number;
  features: Record<string, boolean>;
  trial_days: number;
}

const pricingNotes = [
  {
    icon: Users,
    label: "3PL fit",
    value: "Choose the plan that matches current clients, users, and daily order flow.",
  },
  {
    icon: Workflow,
    label: "Operational continuity",
    value: "The pricing story should still reinforce receiving, shipping, billing, and client visibility in one system.",
  },
  {
    icon: ShieldCheck,
    label: "Future-ready posture",
    value: "AGV readiness is part of the product narrative, not a separate redesign later.",
  },
];

export default function PricingPage() {
  const { data: plans = [] } = useQuery<Plan[]>({
    queryKey: queryKeys.subscriptions.plans(),
    queryFn: fetchSubscriptionPlans,
  });

  const handleSelect = async (planCode: string) => {
    try {
      await activateSubscription({ plan_code: planCode, billing_cycle: "monthly" });
      window.location.href = "/dashboard";
    } catch (err: any) {
      alert(getApiErrorMessage(err, "Failed to activate plan"));
    }
  };

  return (
    <div className="space-y-8">
      <section className="overflow-hidden rounded-[2rem] border border-[#13212c]/10 bg-[#13212c] text-[#f4efe8] shadow-[0_24px_60px_rgba(19,33,44,0.14)]">
        <div className="grid gap-10 px-6 py-8 md:px-8 lg:grid-cols-[0.88fr_1.12fr] lg:px-10">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/5">
                <Boxes size={18} />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.28em] text-[#9eb2bf]">Pricing</p>
                <p className="font-semibold">WMS QuickStart plans</p>
              </div>
            </div>
            <h1 className="mt-6 max-w-xl text-4xl font-semibold tracking-[-0.03em]">
              Pricing should feel like the same product story as the rest of the site.
            </h1>
            <p className="mt-4 max-w-lg text-sm leading-7 text-[#c2d0d8]">
              Start with a free trial, evaluate the warehouse workflow in a real operating context,
              and only then decide how far the rollout should go.
            </p>
            <div className="mt-6 flex flex-wrap gap-3 text-xs uppercase tracking-[0.18em] text-[#f7bf45]">
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-2">14-day trial on Starter and Growth</span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-2">No credit card to start</span>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            {pricingNotes.map((item) => (
              <div key={item.label} className="rounded-[1.5rem] border border-white/10 bg-white/5 p-5">
                <item.icon size={18} className="text-[#f7bf45]" />
                <p className="mt-4 text-xs uppercase tracking-[0.22em] text-[#91a6b4]">{item.label}</p>
                <p className="mt-2 text-sm leading-7 text-[#d7e2e8]">{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        {plans.map((plan) => {
          const featured = plan.code === "growth";
          return (
            <div
              key={plan.id}
              className={`flex flex-col rounded-[2rem] border p-7 shadow-[0_18px_45px_rgba(19,33,44,0.06)] ${
                featured
                  ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                  : "border-[#13212c]/10 bg-white/75 text-[#13212c]"
              }`}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-2xl font-semibold">{plan.name}</h2>
                    {featured ? (
                      <span className="rounded-full bg-[#f7bf45] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#13212c]">
                        Most popular
                      </span>
                    ) : null}
                  </div>
                  <p className={`mt-3 text-sm leading-7 ${featured ? "text-[#cbd8e0]" : "text-[#5d6c78]"}`}>
                    {plan.trial_days > 0 ? `${plan.trial_days}-day trial` : "Contact sales"} · Built for growing 3PL warehouse flow
                  </p>
                </div>
                <div
                  className={`rounded-full border px-3 py-1 text-xs uppercase tracking-[0.18em] ${
                    featured ? "border-white/12 text-[#f7bf45]" : "border-[#13212c]/10 text-[#687682]"
                  }`}
                >
                  {plan.code}
                </div>
              </div>

              <div className="mt-8">
                <span className="text-5xl font-semibold tracking-[-0.04em]">${plan.price_monthly}</span>
                <span className={`ml-2 text-sm uppercase tracking-[0.16em] ${featured ? "text-[#96aab7]" : "text-[#80909c]"}`}>
                  per month
                </span>
                <p className={`mt-2 text-xs uppercase tracking-[0.18em] ${featured ? "text-[#8fa4b2]" : "text-[#8a98a4]"}`}>
                  ${(plan.price_yearly / 12).toFixed(0)}/mo billed yearly
                </p>
              </div>

              <ul className="mt-8 flex-1 space-y-3 text-sm">
                <PlanLine featured={featured}>{formatLimit(plan.max_clients)} clients</PlanLine>
                <PlanLine featured={featured}>{formatLimit(plan.max_skus)} SKUs</PlanLine>
                <PlanLine featured={featured}>{formatLimit(plan.max_orders_per_day)} orders/day</PlanLine>
                <PlanLine featured={featured}>{formatLimit(plan.max_users)} users</PlanLine>
                <PlanLine featured={featured}>
                  {formatLimit(plan.max_warehouses)} warehouse{plan.max_warehouses > 1 && plan.max_warehouses !== 999999 ? "s" : ""}
                </PlanLine>
                <PlanLine featured={featured} enabled={plan.features?.shopify}>Shopify / Amazon</PlanLine>
                <PlanLine featured={featured} enabled={plan.features?.agv}>AGV integration path</PlanLine>
              </ul>

              <button
                onClick={() => handleSelect(plan.code)}
                className={`mt-8 inline-flex items-center justify-center gap-2 rounded-full px-5 py-3.5 text-sm font-semibold uppercase tracking-[0.14em] transition ${
                  featured
                    ? "bg-[#f7bf45] text-[#13212c] hover:bg-[#ffd26f]"
                    : "bg-[#13212c] text-[#f6f2ea] hover:bg-[#1d3140]"
                }`}
              >
                {plan.trial_days > 0 ? `Start ${plan.trial_days}-day trial` : "Contact sales"}
                <ArrowRight size={16} />
              </button>
            </div>
          );
        })}
      </section>
    </div>
  );
}

function PlanLine({
  children,
  enabled = true,
  featured,
}: {
  children: React.ReactNode;
  enabled?: boolean;
  featured: boolean;
}) {
  return (
    <li className="flex items-center gap-3">
      <span
        className={`flex h-6 w-6 items-center justify-center rounded-full ${
          enabled
            ? featured
              ? "bg-white/10 text-[#f7bf45]"
              : "bg-[#13212c]/8 text-[#13212c]"
            : featured
              ? "bg-white/5 text-[#617785]"
              : "bg-[#13212c]/5 text-[#9aa8b3]"
        }`}
      >
        <Check size={14} />
      </span>
      <span className={enabled ? "" : featured ? "text-[#8aa0ae]" : "text-[#9aa8b3]"}>{children}</span>
    </li>
  );
}

function formatLimit(value: number) {
  return value === 999999 ? "Unlimited" : value.toLocaleString();
}
