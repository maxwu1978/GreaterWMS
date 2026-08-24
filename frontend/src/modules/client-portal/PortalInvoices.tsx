import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchPortalInvoices } from "../../shared/api/portal";
import { fetchBillingInvoicePdf } from "../../shared/api/billing";
import { queryKeys } from "../../shared/api/queryKeys";
import DataTable from "../../shared/components/DataTable";
import MetricTile from "../../shared/components/MetricTile";
import StatusBadge from "../../shared/components/StatusBadge";
import { ArrowRight, CreditCard, Receipt, ShieldCheck } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { getApiErrorMessage } from "../../shared/api/error-message";
import { useI18n } from "../../shared/i18n";

export default function PortalInvoices() {
  const { t } = useI18n();
  const location = useLocation();
  const [statusFilter, setStatusFilter] = useState<"all" | "open" | "overdue" | "paid">("all");
  const { data: invoices = [], isLoading } = useQuery({
    queryKey: queryKeys.portal.invoices(),
    queryFn: fetchPortalInvoices,
  });
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const overdueCount = invoices.filter((invoice: any) => String(invoice.status || "").toLowerCase() === "overdue").length;
  const paidCount = invoices.filter((invoice: any) => String(invoice.status || "").toLowerCase() === "paid").length;
  const openBalance = invoices
    .filter((invoice: any) => !["paid", "cancelled"].includes(String(invoice.status || "").toLowerCase()))
    .reduce((sum: number, invoice: any) => sum + Number(invoice.total_amount || 0), 0);
  const filteredInvoices = invoices.filter((invoice: any) => {
    const status = String(invoice.status || "").toLowerCase();
    if (statusFilter === "all") return true;
    if (statusFilter === "open") return !["paid", "cancelled"].includes(status);
    return status === statusFilter;
  });

  async function handleDownload(invoiceId: string, invoiceNumber?: string) {
    setDownloadingId(invoiceId);
    try {
      const response = await fetchBillingInvoicePdf(invoiceId);

      const blobUrl = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      const safeInvoiceNumber = invoiceNumber || invoiceId;
      link.href = blobUrl;
      link.download = `invoice-${safeInvoiceNumber}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(blobUrl);
    } catch (error: any) {
      window.alert(getApiErrorMessage(error, "Could not download invoice PDF."));
    } finally {
      setDownloadingId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.24em] text-[#7f8e98]">{t("portal.invoicesEyebrow", "Client billing view")}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[#13212c]">{t("portal.invoicesTitle", "My Invoices")}</h1>
        <p className="mt-3 max-w-2xl text-sm leading-7 text-[#5f6f7c]">
          {t("portal.invoicesBody", "Review invoice status, due dates, and downloadable billing documents from the same portal that shows your warehouse activity.")}
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
              <p className="text-[11px] uppercase tracking-[0.24em] text-[#90a7b5]">{t("portal.invoiceVisibility", "Invoice visibility")}</p>
              <h2 className="mt-3 text-2xl font-semibold tracking-[-0.03em]">{t("portal.invoicesFlowTitle", "Keep payment status easy to read and close to the work that created it.")}</h2>
            </div>
            <div className="rounded-full border border-[#f7bf45]/30 bg-[#f7bf45]/12 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-[#f7bf45]">
              {t("portal.finance", "Finance")}
            </div>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <PortalFlowCard icon={Receipt} title={t("portal.review", "Review")} text={t("portal.reviewDetail", "See invoice numbers, dates, and amounts in one place.")} />
            <PortalFlowCard icon={CreditCard} title={t("portal.track", "Track")} text={t("portal.trackDetail", "Watch sent, overdue, and paid status without chasing email.")} />
            <PortalFlowCard icon={ShieldCheck} title={t("portal.download", "Download")} text={t("portal.downloadDetail", "Pull the PDF directly when finance or operations needs a copy.")} />
          </div>
        </section>

        <section className="rounded-[2rem] border border-[#13212c]/10 bg-white/80 p-6 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur">
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("portal.guide", "How to use this page")}</p>
          <div className="mt-4 space-y-3">
            <PortalGuideRow label={t("portal.invoicesGuide1Title", "1. Start with newest invoices")} detail={t("portal.invoicesGuide1Detail", "Recent periods usually explain the latest operational charges.")} />
            <PortalGuideRow label={t("portal.invoicesGuide2Title", "2. Watch status and due date together")} detail={t("portal.invoicesGuide2Detail", "That pair shows what still needs action from finance.")} />
            <PortalGuideRow label={t("portal.invoicesGuide3Title", "3. Download PDF when needed")} detail={t("portal.invoicesGuide3Detail", "Use the portal as the source for formal invoice copies.")} />
          </div>
        </section>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <MetricTile
          label={t("portal.invoicesMetricOpen", "Open balance")}
          value={`$${openBalance.toFixed(2)}`}
          detail={t("portal.invoicesMetricOpenDetail", "Outstanding invoice value still visible to client finance teams.")}
        />
        <MetricTile
          label={t("portal.invoicesMetricOverdue", "Overdue")}
          value={overdueCount}
          detail={t("portal.invoicesMetricOverdueDetail", "Invoice count already past the due date.")}
        />
        <MetricTile
          label={t("portal.invoicesMetricPaid", "Paid")}
          value={paidCount}
          detail={t("portal.invoicesMetricPaidDetail", "Invoices already closed with payment received.")}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {[
          { key: "all", label: t("portal.filterAllInvoices", "All invoices") },
          { key: "open", label: t("portal.filterOpen", "Open balance") },
          { key: "overdue", label: t("portal.filterOverdue", "Overdue only") },
          { key: "paid", label: t("portal.filterPaid", "Paid only") },
        ].map((filter) => (
          <button
            key={filter.key}
            type="button"
            onClick={() => setStatusFilter(filter.key as "all" | "open" | "overdue" | "paid")}
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
          { key: "invoice_number", header: t("common.invoiceNumber", "Invoice #") },
          { key: "status", header: t("common.status", "Status"), render: (r: any) => <StatusBadge status={r.status} /> },
          { key: "total_amount", header: t("common.amount", "Amount"), render: (r: any) => `$${r.total_amount.toFixed(2)}`, className: "font-medium" },
          { key: "currency", header: t("common.currency", "Currency") },
          { key: "issued_date", header: t("common.issued", "Issued") },
          { key: "due_date", header: t("common.due", "Due") },
          {
            key: "download",
            header: "",
            render: (r: any) => (
              <button
                type="button"
                onClick={() => handleDownload(r.id, r.invoice_number)}
                disabled={downloadingId === r.id}
                className="rounded-full border border-[#8db6ff]/30 bg-[#8db6ff]/10 px-3 py-1.5 text-xs font-medium text-[#5d89dd] hover:bg-[#8db6ff]/18"
              >
                {downloadingId === r.id ? t("portal.downloading", "Downloading...") : t("portal.downloadPdf", "PDF")}
              </button>
            ),
          },
        ]}
        data={filteredInvoices}
        loading={isLoading}
        emptyMessage={t("portal.noInvoices", "No invoices")}
      />

      <div className="grid gap-4 md:grid-cols-2">
        <ActionPanel
          title={t("portal.invoicesActionOne", "Return to the client summary")}
          detail={t("portal.invoicesActionOneDetail", "Go back to the dashboard when finance questions turn into broader stock or order questions.")}
          cta={t("portal.returnDashboard", "Back to dashboard")}
          to="/portal/dashboard"
        />
        <ActionPanel
          title={t("portal.invoicesActionTwo", "Check live outbound status")}
          detail={t("portal.invoicesActionTwoDetail", "Open orders if the invoice follow-up depends on what the warehouse shipped or has not shipped yet.")}
          cta={t("portal.openOrders", "Open orders")}
          to="/portal/orders"
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
