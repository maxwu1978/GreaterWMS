import { useQuery } from "@tanstack/react-query";
import { fetchPortalDashboard, fetchPortalOutboundOrders } from "../../shared/api/portal";
import { queryKeys } from "../../shared/api/queryKeys";
import DataTable from "../../shared/components/DataTable";
import StatusBadge from "../../shared/components/StatusBadge";
import { ArrowRight, Package, Receipt, Truck, Warehouse } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useI18n } from "../../shared/i18n";

export default function PortalDashboard() {
  const { t } = useI18n();
  const location = useLocation();
  const { data: stats } = useQuery({
    queryKey: queryKeys.portal.dashboard(),
    queryFn: fetchPortalDashboard,
  });

  const { data: orders = [] } = useQuery({
    queryKey: queryKeys.portal.outbound(),
    queryFn: fetchPortalOutboundOrders,
  });

  const s = stats || {
    client_name: "",
    client_code: "",
    client_contact_email: "",
    client_contact_phone: "",
    warehouse_operator_name: "",
    total_skus: 0,
    total_units_on_hand: 0,
    pending_outbound: 0,
    outstanding_invoices: 0,
  };

  const portalNav = [
    { to: "/portal/dashboard", label: t("nav.dashboard", "Dashboard") },
    { to: "/portal/inventory", label: t("nav.inventory", "Inventory") },
    { to: "/portal/orders", label: t("nav.orders", "Orders") },
    { to: "/portal/invoices", label: t("nav.invoices", "Invoices") },
  ];
  const todayFocus = [
    {
      title: t("portal.focusPendingOrders", "Pending outbound"),
      value: s.pending_outbound,
      detail:
        s.pending_outbound > 0
          ? t("portal.focusPendingOrdersDetail", "Start with orders if the client expects same-day movement updates.")
          : t("portal.focusPendingOrdersClear", "No queued outbound pressure is visible right now."),
      to: "/portal/orders",
      cta: t("portal.openOrders", "Open orders"),
    },
    {
      title: t("portal.focusInventory", "Available stock"),
      value: s.total_units_on_hand,
      detail:
        s.total_units_on_hand > 0
          ? t("portal.focusInventoryDetail", "Inventory is the next best stop when the client asks what can still ship.")
          : t("portal.focusInventoryEmpty", "Inventory looks empty, so the client may need receiving or replenishment context."),
      to: "/portal/inventory",
      cta: t("portal.openInventory", "Open inventory"),
    },
    {
      title: t("portal.focusInvoices", "Outstanding invoices"),
      value: `$${s.outstanding_invoices.toFixed(2)}`,
      detail:
        s.outstanding_invoices > 0
          ? t("portal.focusInvoicesDetail", "Commercial follow-up is still open and should stay close to the operational picture.")
          : t("portal.focusInvoicesClear", "No unpaid invoice value is visible right now."),
      to: "/portal/invoices",
      cta: t("portal.openInvoices", "Open invoices"),
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.24em] text-[#7f8e98]">{t("portal.dashboardEyebrow", "Client visibility")}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[#13212c]">{t("portal.dashboardTitle", "Client Portal")}</h1>
        <p className="mt-3 max-w-2xl text-sm leading-7 text-[#5f6f7c]">
          {t(
            "portal.dashboardBody",
            "This portal gives clients a readable view of inventory, outbound movement, and invoices without needing manual status emails from the warehouse team.",
          )}
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {portalNav.map((item) => (
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
              <p className="text-[11px] uppercase tracking-[0.24em] text-[#90a7b5]">{t("portal.flow", "Portal flow")}</p>
              <h2 className="mt-3 text-2xl font-semibold tracking-[-0.03em]">{t("portal.dashboardFlowTitle", "Connect stock, orders, and billing in one client-facing view.")}</h2>
            </div>
            <div className="rounded-full border border-[#f7bf45]/30 bg-[#f7bf45]/12 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-[#f7bf45]">
              {t("portal.readOnly", "Read-only")}
            </div>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <PortalFlowCard icon={Warehouse} title={t("portal.inventoryCard", "Inventory")} text={t("portal.inventoryCardDetail", "Clients see what is in stock and what is already committed.")} />
            <PortalFlowCard icon={Truck} title={t("portal.ordersCard", "Orders")} text={t("portal.ordersCardDetail", "Outbound movement stays visible after the warehouse starts work.")} />
            <PortalFlowCard icon={Receipt} title={t("portal.invoicesCard", "Invoices")} text={t("portal.invoicesCardDetail", "Commercial status lives in the same system as operational truth.")} />
          </div>
        </section>

        <section className="rounded-[2rem] border border-[#13212c]/10 bg-white/80 p-6 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur">
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("portal.guide", "How to use this page")}</p>
          <div className="mt-4 space-y-3">
            <PortalGuideRow label={t("portal.dashboardGuide1Title", "1. Check stock first")} detail={t("portal.dashboardGuide1Detail", "Inventory confirms what is available before you ask for outbound changes.")} />
            <PortalGuideRow label={t("portal.dashboardGuide2Title", "2. Watch pending orders")} detail={t("portal.dashboardGuide2Detail", "Recent outbound orders show what is moving through fulfillment now.")} />
            <PortalGuideRow label={t("portal.dashboardGuide3Title", "3. Follow invoices here too")} detail={t("portal.dashboardGuide3Detail", "Operational visibility and billing status stay connected.")} />
          </div>
        </section>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat icon={Package} label={t("portal.statsSkus", "SKUs in Stock")} value={s.total_skus} />
        <Stat icon={Warehouse} label={t("portal.statsUnits", "Total Units")} value={s.total_units_on_hand.toLocaleString()} />
        <Stat icon={Truck} label={t("portal.statsPendingOrders", "Pending Orders")} value={s.pending_outbound} />
        <Stat icon={Receipt} label={t("portal.statsOutstanding", "Outstanding")} value={`$${s.outstanding_invoices.toFixed(2)}`} />
      </div>

      <section className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/80 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("portal.todayFocus", "Today in the portal")}</p>
            <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-[#13212c]">
              {t("portal.todayFocusTitle", "What your client will likely ask about next")}
            </h2>
          </div>
          <div className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] uppercase tracking-[0.16em] text-[#61717d]">
            {t("portal.dailyEntry", "daily entrypoint")}
          </div>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          {todayFocus.map((item) => (
            <Link
              key={item.title}
              to={item.to}
              className="rounded-[1.35rem] border border-[#13212c]/10 bg-[#f7f4ee] p-4 transition hover:bg-white"
            >
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">{item.title}</p>
              <p className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[#13212c]">{item.value}</p>
              <p className="mt-3 text-sm leading-6 text-[#61717d]">{item.detail}</p>
              <div className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-[#13212c]">
                {item.cta}
                <ArrowRight size={15} />
              </div>
            </Link>
          ))}
        </div>
      </section>

      <div className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/80 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
        <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("portal.yourCompany", "Your company")}</p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <p className="text-sm text-[#7d8c97]">{t("portal.clientCompany", "Client company")}</p>
            <p className="mt-1 text-xl font-semibold text-[#13212c]">{s.client_name || t("portal.notConfigured", "Not configured")}</p>
            <p className="mt-1 text-sm text-[#61717d]">{t("portal.codeLabel", "Code")}: {s.client_code || t("common.pending", "Pending")}</p>
          </div>
          <div>
            <p className="text-sm text-[#7d8c97]">{t("portal.contacts", "Portal contacts")}</p>
            <p className="mt-1 text-sm text-[#13212c]">{s.client_contact_email || t("portal.noClientEmail", "No client email on file")}</p>
            <p className="mt-1 text-sm text-[#61717d]">{s.client_contact_phone || t("portal.noClientPhone", "No phone on file")}</p>
          </div>
        </div>
        <div className="mt-4 rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-3 text-sm text-[#61717d]">
          {t("portal.servicedBy", "Serviced by")} <span className="font-semibold text-[#13212c]">{s.warehouse_operator_name || t("portal.yourOperator", "your warehouse operator")}</span>.
        </div>
      </div>

      <div className="bg-white rounded-lg shadow p-5">
        <h2 className="text-lg font-semibold mb-4">{t("portal.recentOrders", "Recent Orders")}</h2>
        <DataTable
          columns={[
            { key: "order_number", header: t("portal.orderNumber", "Order #") },
            { key: "status", header: t("common.status", "Status"), render: (r: any) => <StatusBadge status={r.status} /> },
            { key: "carrier", header: t("shipping.carrier", "Carrier") },
            { key: "tracking_number", header: t("shipping.tracking", "Tracking") },
          ]}
          data={orders.slice(0, 10)}
          emptyMessage={t("portal.noRecentOrders", "No recent orders")}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <ActionPanel
          title={t("portal.nextInventory", "Review inventory next")}
          detail={t("portal.nextInventoryDetail", "Use the inventory page when the client needs the clearest stock and lot picture before changing outbound plans.")}
          cta={t("portal.openInventory", "Open inventory")}
          to="/portal/inventory"
        />
        <ActionPanel
          title={t("portal.nextInvoices", "Then confirm invoices")}
          detail={t("portal.nextInvoicesDetail", "Stay in the same portal when the conversation shifts from fulfillment to commercial follow-up.")}
          cta={t("portal.openInvoices", "Open invoices")}
          to="/portal/invoices"
        />
      </div>
    </div>
  );
}

function Stat({ icon: Icon, label, value }: { icon: any; label: string; value: any }) {
  return (
    <div className="rounded-[1.7rem] border border-[#13212c]/10 bg-white/80 p-4 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
      <div className="flex items-center gap-3">
        <div className="rounded-2xl border border-[#8db6ff]/28 bg-[#8db6ff]/12 p-2.5 text-[#7da9ff]">
          <Icon size={18} />
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-[#7d8c97]">{label}</p>
          <p className="text-lg font-semibold text-[#13212c]">{value}</p>
        </div>
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
