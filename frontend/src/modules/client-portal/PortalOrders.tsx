import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ClipboardList, PackageCheck, Truck } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { fetchPortalOutboundOrders } from "../../shared/api/portal";
import { queryKeys } from "../../shared/api/queryKeys";
import DataTable from "../../shared/components/DataTable";
import MetricTile from "../../shared/components/MetricTile";
import StatusBadge from "../../shared/components/StatusBadge";
import { useI18n } from "../../shared/i18n";

export default function PortalOrders() {
  const { t } = useI18n();
  const location = useLocation();
  const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "shipped">("all");
  const { data: orders = [], isLoading } = useQuery({
    queryKey: queryKeys.portal.orders(),
    queryFn: fetchPortalOutboundOrders,
  });

  const queuedCount = orders.filter((order: any) => String(order.status || "").toLowerCase() === "pending").length;
  const shippedCount = orders.filter((order: any) => String(order.status || "").toLowerCase() === "shipped").length;
  const trackedCount = orders.filter((order: any) => Boolean(order.tracking_number)).length;
  const filteredOrders = useMemo(() => {
    if (statusFilter === "all") return orders;
    return orders.filter((order: any) => String(order.status || "").toLowerCase() === statusFilter);
  }, [orders, statusFilter]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.24em] text-[#7f8e98]">{t("portal.ordersEyebrow", "Client order view")}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[#13212c]">{t("portal.ordersTitle", "My Orders")}</h1>
        <p className="mt-3 max-w-2xl text-sm leading-7 text-[#5f6f7c]">
          {t("portal.ordersBody", "Follow outbound order progress from release through shipment without asking the operations team for a manual update.")}
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {[
          { to: "/portal/dashboard", label: t("nav.dashboard", "Dashboard") },
          { to: "/portal/inventory", label: t("nav.inventory", "Inventory") },
          { to: "/portal/orders", label: t("nav.orders", "Orders") },
          { to: "/portal/invoices", label: t("nav.invoices", "Invoices") },
        ].map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className={`rounded-full px-4 py-2 text-sm font-medium transition ${
              location.pathname === item.to ? "bg-[#13212c] text-[#f4efe8]" : "border border-[#13212c]/10 bg-white/80 text-[#13212c] hover:bg-white"
            }`}
          >
            {item.label}
          </Link>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.08fr)_360px]">
        <section className="overflow-hidden rounded-[2rem] border border-[#13212c]/10 bg-[linear-gradient(135deg,#13212c_0%,#1a2d39_60%,#253847_100%)] p-6 text-[#f4efe8] shadow-[0_30px_80px_rgba(19,33,44,0.16)]">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.24em] text-[#90a7b5]">{t("portal.orderVisibility", "Order visibility")}</p>
              <h2 className="mt-3 text-2xl font-semibold tracking-[-0.03em]">{t("portal.ordersFlowTitle", "See where each outbound order sits in the fulfillment chain.")}</h2>
            </div>
            <div className="rounded-full border border-[#f7bf45]/30 bg-[#f7bf45]/12 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-[#f7bf45]">
              {t("portal.clientView", "Client view")}
            </div>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <PortalFlowCard icon={ClipboardList} title={t("portal.queued", "Queued")} text={t("portal.queuedDetail", "Orders appear here once they enter outbound processing.")} />
            <PortalFlowCard icon={PackageCheck} title={t("portal.fulfilled", "Fulfilled")} text={t("portal.fulfilledDetail", "Status shows whether the warehouse has allocated, picked, or packed the order.")} />
            <PortalFlowCard icon={Truck} title={t("portal.shipped", "Shipped")} text={t("portal.shippedDetail", "Carrier and tracking fields close the loop once the order leaves the facility.")} />
          </div>
        </section>

        <section className="rounded-[2rem] border border-[#13212c]/10 bg-white/80 p-6 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur">
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("portal.guide", "How to use this page")}</p>
          <div className="mt-4 space-y-3">
            <PortalGuideRow label={t("portal.ordersGuide1Title", "1. Start with status")} detail={t("portal.ordersGuide1Detail", "It tells you whether the order is waiting, in progress, or already shipped.")} />
            <PortalGuideRow label={t("portal.ordersGuide2Title", "2. Use tracking when shipped")} detail={t("portal.ordersGuide2Detail", "Carrier and tracking fields are the handoff point to customer delivery visibility.")} />
            <PortalGuideRow label={t("portal.ordersGuide3Title", "3. Cross-check with inventory if needed")} detail={t("portal.ordersGuide3Detail", "Order questions often become stock questions when an item is delayed.")} />
          </div>
        </section>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <MetricTile
          label={t("portal.ordersMetricQueued", "Queued now")}
          value={queuedCount}
          detail={t("portal.ordersMetricQueuedDetail", "Orders still waiting for the warehouse to complete the flow.")}
        />
        <MetricTile
          label={t("portal.ordersMetricShipped", "Shipped")}
          value={shippedCount}
          detail={t("portal.ordersMetricShippedDetail", "Orders already closed with outbound completion.")}
        />
        <MetricTile
          label={t("portal.ordersMetricTracked", "With tracking")}
          value={trackedCount}
          detail={t("portal.ordersMetricTrackedDetail", "Orders that already expose carrier tracking back to the client.")}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {[
          { key: "all", label: t("portal.filterAll", "All orders") },
          { key: "pending", label: t("portal.filterPending", "Pending only") },
          { key: "shipped", label: t("portal.filterShipped", "Shipped only") },
        ].map((filter) => (
          <button
            key={filter.key}
            type="button"
            onClick={() => setStatusFilter(filter.key as "all" | "pending" | "shipped")}
            className={`rounded-full px-4 py-2 text-sm font-medium transition ${
              statusFilter === filter.key ? "bg-[#13212c] text-[#f4efe8]" : "border border-[#13212c]/10 bg-white/80 text-[#13212c] hover:bg-white"
            }`}
          >
            {filter.label}
          </button>
        ))}
      </div>

      <DataTable
        columns={[
          { key: "order_number", header: t("portal.orderNumber", "Order #") },
          { key: "status", header: t("common.status", "Status"), render: (r: any) => <StatusBadge status={r.status} /> },
          { key: "reference_number", header: t("common.reference", "Reference") },
          { key: "carrier", header: t("shipping.carrier", "Carrier") },
          { key: "tracking_number", header: t("shipping.tracking", "Tracking") },
        ]}
        data={filteredOrders}
        loading={isLoading}
        emptyMessage={t("portal.noOutboundOrders", "No outbound orders yet")}
      />

      <div className="grid gap-4 md:grid-cols-2">
        <ActionPanel
          title={t("portal.ordersActionOne", "Need formal billing copies?")}
          detail={t("portal.ordersActionOneDetail", "Open invoices when the shipment question becomes a billing confirmation question.")}
          cta={t("portal.openInvoices", "Open invoices")}
          to="/portal/invoices"
        />
        <ActionPanel
          title={t("portal.ordersActionTwo", "Need stock context?")}
          detail={t("portal.ordersActionTwoDetail", "Jump back to inventory if an order is waiting because stock is allocated or unavailable.")}
          cta={t("portal.openInventory", "Open inventory")}
          to="/portal/inventory"
        />
      </div>
    </div>
  );
}

function PortalFlowCard({ icon: Icon, title, text }: { icon: any; title: string; text: string }) {
  return (
    <div className="rounded-[1.4rem] border border-white/10 bg-white/5 p-4">
      <div className="inline-flex rounded-2xl border border-[#8db6ff]/30 bg-[#8db6ff]/10 p-2.5 text-[#9dc0ff]">
        <Icon size={18} />
      </div>
      <p className="mt-4 text-lg font-semibold text-[#f5efe5]">{title}</p>
      <p className="mt-2 text-sm leading-6 text-[#c4d3dc]">{text}</p>
    </div>
  );
}

function PortalGuideRow({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="rounded-[1.25rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-[#13212c]">{label}</p>
          <p className="mt-1.5 text-sm leading-6 text-[#61717d]">{detail}</p>
        </div>
        <ArrowRight size={15} className="mt-1 shrink-0 text-[#13212c]" />
      </div>
    </div>
  );
}

function ActionPanel({ title, detail, cta, to }: { title: string; detail: string; cta: string; to: string }) {
  return (
    <Link to={to} className="rounded-[1.5rem] border border-[#13212c]/10 bg-white/80 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)] transition hover:bg-white">
      <p className="text-base font-semibold text-[#13212c]">{title}</p>
      <p className="mt-2 text-sm leading-6 text-[#61717d]">{detail}</p>
      <div className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-[#13212c]">
        {cta}
        <ArrowRight size={15} />
      </div>
    </Link>
  );
}
