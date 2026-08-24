import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchPortalInventory } from "../../shared/api/portal";
import { queryKeys } from "../../shared/api/queryKeys";
import DataTable from "../../shared/components/DataTable";
import MetricTile from "../../shared/components/MetricTile";
import { ArrowRight, Boxes, Layers3, Warehouse } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useI18n } from "../../shared/i18n";

export default function PortalInventory() {
  const { t } = useI18n();
  const location = useLocation();
  const [query, setQuery] = useState("");
  const { data: inventory = [], isLoading } = useQuery({
    queryKey: queryKeys.portal.inventory(),
    queryFn: fetchPortalInventory,
  });

  const filteredInventory = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return inventory;
    return inventory.filter((row: any) =>
      [row.sku_code, row.sku_name, row.lot_number]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(term)),
    );
  }, [inventory, query]);
  const inventorySummary = useMemo(() => {
    return filteredInventory.reduce(
      (acc: { onHand: number; allocated: number; available: number; lots: Set<string> }, row: any) => {
        acc.onHand += Number(row.quantity_on_hand || 0);
        acc.allocated += Number(row.quantity_allocated || 0);
        acc.available += Number(row.quantity_available || 0);
        if (row.lot_number) acc.lots.add(String(row.lot_number));
        return acc;
      },
      { onHand: 0, allocated: 0, available: 0, lots: new Set<string>() },
    );
  }, [filteredInventory]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.24em] text-[#7f8e98]">{t("portal.inventoryEyebrow", "Client stock view")}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[#13212c]">{t("portal.inventoryTitle", "My Inventory")}</h1>
        <p className="mt-3 max-w-2xl text-sm leading-7 text-[#5f6f7c]">
          {t("portal.inventoryBody", "Review available stock, allocations, and lot-level detail without asking the warehouse team for manual exports.")}
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
              <p className="text-[11px] uppercase tracking-[0.24em] text-[#90a7b5]">{t("portal.inventoryTransparency", "Inventory transparency")}</p>
              <h2 className="mt-3 text-2xl font-semibold tracking-[-0.03em]">{t("portal.inventoryFlowTitle", "Use the portal to understand on-hand, allocated, and available stock.")}</h2>
            </div>
            <div className="rounded-full border border-[#f7bf45]/30 bg-[#f7bf45]/12 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-[#f7bf45]">
              {t("portal.clientView", "Client view")}
            </div>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <PortalFlowCard icon={Warehouse} title={t("portal.onHand", "On hand")} text={t("portal.onHandDetail", "See what is physically stored in the warehouse now.")} />
            <PortalFlowCard icon={Layers3} title={t("portal.allocated", "Allocated")} text={t("portal.allocatedDetail", "Understand what is already reserved for existing orders.")} />
            <PortalFlowCard icon={Boxes} title={t("portal.available", "Available")} text={t("portal.availableDetail", "Focus on the quantity still open to fulfill new demand.")} />
          </div>
        </section>

        <section className="rounded-[2rem] border border-[#13212c]/10 bg-white/80 p-6 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur">
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("portal.readThisPage", "How to read this page")}</p>
          <div className="mt-4 space-y-3">
            <PortalGuideRow label={t("portal.inventoryGuide1Title", "1. Start with available")} detail={t("portal.inventoryGuide1Detail", "This is the clearest number for what can still be sold or shipped.")} />
            <PortalGuideRow label={t("portal.inventoryGuide2Title", "2. Compare on-hand vs allocated")} detail={t("portal.inventoryGuide2Detail", "That gap explains what is already committed to outbound work.")} />
            <PortalGuideRow label={t("portal.inventoryGuide3Title", "3. Use lot and expiry when relevant")} detail={t("portal.inventoryGuide3Detail", "Those details support replenishment and aging review.")} />
          </div>
        </section>
      </div>

      <div className="rounded-[1.5rem] border border-[#13212c]/10 bg-white/80 p-4 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">{t("portal.inventorySearch", "Search inventory")}</p>
            <p className="mt-1 text-sm text-[#61717d]">{t("portal.inventorySearchDetail", "Filter by SKU, product name, or lot to answer client questions faster.")}</p>
          </div>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("portal.inventorySearchPlaceholder", "Search SKU, name, or lot")}
            className="w-full rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 md:max-w-xs"
          />
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile
          label={t("portal.inventoryMetricVisible", "Visible rows")}
          value={filteredInventory.length}
          detail={query ? t("portal.inventoryMetricVisibleDetail", "Rows matching the current client search.") : t("portal.inventoryMetricVisibleAll", "Rows currently visible to the client.")}
        />
        <MetricTile
          label={t("portal.inventoryMetricOnHand", "On hand total")}
          value={inventorySummary.onHand.toLocaleString()}
          detail={t("portal.inventoryMetricOnHandDetail", "Total physical units shown in the current filtered view.")}
        />
        <MetricTile
          label={t("portal.inventoryMetricAvailable", "Available total")}
          value={inventorySummary.available.toLocaleString()}
          detail={t("portal.inventoryMetricAvailableDetail", "What can still move against new demand from the rows on screen.")}
        />
        <MetricTile
          label={t("portal.inventoryMetricLots", "Lots visible")}
          value={inventorySummary.lots.size}
          detail={t("portal.inventoryMetricLotsDetail", "Distinct lots visible after the current filter is applied.")}
        />
      </div>

      <DataTable
        columns={[
          { key: "sku_code", header: t("common.sku", "SKU") },
          { key: "sku_name", header: t("common.product", "Product") },
          { key: "quantity_on_hand", header: t("portal.onHand", "On Hand"), className: "font-medium" },
          { key: "quantity_allocated", header: t("portal.allocated", "Allocated") },
          { key: "quantity_available", header: t("portal.available", "Available"), className: "font-medium text-green-700" },
          { key: "lot_number", header: t("common.lot", "Lot") },
          { key: "expiry_date", header: t("common.expiry", "Expiry") },
        ]}
        data={filteredInventory}
        loading={isLoading}
        emptyMessage={t("portal.noInventory", "No inventory")}
      />

      <div className="grid gap-4 md:grid-cols-2">
        <ActionPanel
          title={t("portal.inventoryActionOne", "Need outbound context?")}
          detail={t("portal.inventoryActionOneDetail", "Move to orders when inventory questions turn into shipping or fulfillment timing questions.")}
          cta={t("portal.openOrders", "Open orders")}
          to="/portal/orders"
        />
        <ActionPanel
          title={t("portal.inventoryActionTwo", "Need the summary view?")}
          detail={t("portal.inventoryActionTwoDetail", "Go back to the portal dashboard for the client-wide picture across stock, orders, and invoices.")}
          cta={t("portal.returnDashboard", "Back to dashboard")}
          to="/portal/dashboard"
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
