import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  calculateBilling as calculateBillingRequest,
  createBillingInvoice,
  fetchBillingInvoicePdf,
  fetchBillingInvoices,
  fetchCurrentTenant,
  fetchRateCards,
  updateBillingInvoiceStatus,
} from "../../shared/api/billing";
import { fetchClients } from "../../shared/api/clients";
import { queryKeys } from "../../shared/api/queryKeys";
import DataTable from "../../shared/components/DataTable";
import MetricTile from "../../shared/components/MetricTile";
import StatusBadge from "../../shared/components/StatusBadge";
import { getApiErrorMessage } from "../../shared/api/error-message";
import { useI18n } from "../../shared/i18n";
import { sortTableRows, type SortDirection } from "../../shared/utils/tableSort";

type InvoiceSortField = "invoice_number" | "status" | "total_amount" | "issued_date" | "follow_up" | "next_action";
type InvoiceStatusValue = "sent" | "paid" | "overdue" | "draft";

export default function BillingPage() {
  const { t, locale } = useI18n();
  const queryClient = useQueryClient();
  const { data: rateCards = [] } = useQuery({
    queryKey: queryKeys.billing.rateCards(),
    queryFn: fetchRateCards,
  });
  const { data: clientPage } = useQuery({
    queryKey: queryKeys.clients.billing(),
    queryFn: () => fetchClients({ limit: 500 }),
  });
  const { data: tenantProfile } = useQuery({
    queryKey: queryKeys.billing.tenantProfile(),
    queryFn: fetchCurrentTenant,
  });

  const clients = clientPage?.items || [];
  const [businessMode, setBusinessMode] = useState<"3pl" | "self_use">("3pl");
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [selectedClientId, setSelectedClientId] = useState("");
  const [periodStart, setPeriodStart] = useState(defaultPeriodStart());
  const [periodEnd, setPeriodEnd] = useState(defaultPeriodEnd());
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [calcResult, setCalcResult] = useState<any | null>(null);
  const [invoiceResult, setInvoiceResult] = useState<any | null>(null);
  const [invoiceStatusFilter, setInvoiceStatusFilter] = useState<"all" | "draft" | "sent" | "paid" | "overdue">("all");
  const [invoiceSortField, setInvoiceSortField] = useState<InvoiceSortField>("issued_date");
  const [invoiceSortDirection, setInvoiceSortDirection] = useState<SortDirection>("desc");
  const [recentInvoiceMove, setRecentInvoiceMove] = useState<{
    invoiceId: string;
    invoiceNumber?: string;
    status: InvoiceStatusValue;
  } | null>(null);
  const clientRateCards = rateCards.filter((card: any) => !selectedClientId || card.client_id === selectedClientId);
  const latestRateCard = clientRateCards[0] || null;

  useEffect(() => {
    const nextMode = tenantProfile?.settings?.business_mode;
    if (nextMode === "3pl" || nextMode === "self_use") {
      setBusinessMode(nextMode);
      return;
    }
    setBusinessMode("3pl");
  }, [tenantProfile]);

  useEffect(() => {
    if (clients.length === 0) {
      if (selectedClientId) setSelectedClientId("");
      return;
    }
    if (!selectedClientId || !clients.some((client: any) => client.id === selectedClientId)) {
      setSelectedClientId(clients[0].id);
    }
  }, [clients, selectedClientId]);

  const selectedClient = clients.find((client: any) => client.id === selectedClientId) || null;
  const suggestedInvoiceNumber = useMemo(() => {
    if (!selectedClient) return "";
    const yyyymm = periodStart.replaceAll("-", "").slice(0, 6);
    return `INV-${selectedClient.code || "CLIENT"}-${yyyymm}`;
  }, [periodStart, selectedClient]);

  useEffect(() => {
    if (!invoiceNumber && suggestedInvoiceNumber) {
      setInvoiceNumber(suggestedInvoiceNumber);
    }
  }, [invoiceNumber, suggestedInvoiceNumber]);

  useEffect(() => {
    setCalcResult(null);
    setInvoiceResult(null);
    setFeedback(null);
    setInvoiceNumber("");
    setRecentInvoiceMove(null);
  }, [selectedClientId, periodStart, periodEnd]);

  const { data: invoices = [], isLoading: invoicesLoading } = useQuery({
    queryKey: queryKeys.billing.invoices(selectedClientId, invoiceStatusFilter),
    enabled: Boolean(selectedClientId),
    queryFn: () => {
      const params = new URLSearchParams();
      if (selectedClientId) params.set("client_id", selectedClientId);
      if (invoiceStatusFilter !== "all") params.set("status_filter", invoiceStatusFilter);
      return fetchBillingInvoices(params.toString());
    },
  });

  const calculateBilling = useMutation({
    mutationFn: async () =>
      calculateBillingRequest({
        client_id: selectedClientId,
        period_start: periodStart,
        period_end: periodEnd,
      }),
    onSuccess: (data) => {
      setCalcResult(data);
      setInvoiceResult(null);
      setFeedback({
        type: "success",
        text: businessMode === "self_use"
          ? t("billing.calcSuccessSelfUse", "Cost preview generated. Review the drivers before you turn this into an internal charge story.")
          : t("billing.calcSuccess", "Billing preview generated. Review the charges before creating the invoice."),
      });
    },
    onError: (error: any) => {
      setCalcResult(null);
      setInvoiceResult(null);
      setFeedback({
        type: "error",
        text: getApiErrorMessage(error, t("billing.calcError", "Could not calculate billing for this period.")),
      });
    },
  });

  const generateInvoice = useMutation({
    mutationFn: async () =>
      createBillingInvoice({
        client_id: selectedClientId,
        period_id: calcResult?.period_id,
        invoice_number: invoiceNumber || suggestedInvoiceNumber,
      }),
    onSuccess: async (data) => {
      setInvoiceResult(data);
      setFeedback({
        type: "success",
        text: businessMode === "self_use"
          ? t("billing.invoiceSuccessSelfUse", "Internal billing document created. You can now export the supporting PDF.")
          : t("billing.invoiceSuccess", "Invoice draft created. You can now export the PDF."),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.billing.invoices(selectedClientId) });
    },
    onError: (error: any) => {
      setFeedback({
        type: "error",
        text: getApiErrorMessage(error, t("billing.invoiceError", "Could not generate the invoice draft.")),
      });
    },
  });

  const updateInvoiceStatus = useMutation({
    mutationFn: async ({ invoiceId, status }: { invoiceId: string; invoiceNumber?: string; status: InvoiceStatusValue }) =>
      updateBillingInvoiceStatus(invoiceId, status),
    onSuccess: async (_, variables) => {
      const invoiceLabel = variables.invoiceNumber ? `${variables.invoiceNumber} ` : "";
      setRecentInvoiceMove({
        invoiceId: variables.invoiceId,
        invoiceNumber: variables.invoiceNumber,
        status: variables.status,
      });
      setFeedback({
        type: "success",
        text:
          variables.status === "paid"
            ? t("billing.markPaidMoved", "{invoice}marked as paid and moved to Paid.", { invoice: invoiceLabel })
            : variables.status === "sent"
              ? t("billing.markSentMoved", "{invoice}marked as sent and moved to Sent.", { invoice: invoiceLabel })
              : variables.status === "overdue"
                ? t("billing.markOverdueMoved", "{invoice}marked as overdue and moved to Overdue.", { invoice: invoiceLabel })
                : t("billing.statusMoved", "{invoice}moved to {status}.", {
                  invoice: invoiceLabel,
                  status: getInvoiceStatusLabel(variables.status, t),
                }),
      });
      if (invoiceStatusFilter !== "all" && invoiceStatusFilter !== variables.status) {
        setInvoiceStatusFilter(variables.status);
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.billing.invoices(selectedClientId) });
    },
    onError: (error: any) => {
      setFeedback({
        type: "error",
        text: getApiErrorMessage(error, t("billing.statusUpdateError", "Could not update the invoice status.")),
      });
    },
  });

  async function handleDownloadInvoice(invoiceId: string, targetInvoiceNumber?: string) {
    try {
      const response = await fetchBillingInvoicePdf(invoiceId);
      const blobUrl = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = `${targetInvoiceNumber || invoiceId}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(blobUrl);
    } catch (error: any) {
      setFeedback({
        type: "error",
        text: getApiErrorMessage(error, t("billing.downloadError", "Could not download the invoice PDF.")),
      });
    }
  }

  const isSelfUse = businessMode === "self_use";
  const rateCardCount = rateCards.length;
  const clientsCovered = new Set(rateCards.map((rateCard: any) => rateCard.client_id)).size;
  const rulesTracked = rateCards.reduce((sum: number, rateCard: any) => sum + Object.keys(rateCard.rules || {}).length, 0);
  const calcHasError = Boolean(calcResult?.charges?.some((item: any) => item?.error));
  const calcErrorMessage = calcResult?.charges?.find((item: any) => item?.error)?.error || null;
  const invoiceSummary = useMemo(() => {
    return invoices.reduce(
      (summary: Record<string, number>, invoice: any) => {
        const status = String(invoice.status || "draft");
        summary[status] = (summary[status] || 0) + 1;
        return summary;
      },
      { draft: 0, sent: 0, paid: 0, overdue: 0 },
    );
  }, [invoices]);
  const actionableInvoices = useMemo(() => {
    const rank: Record<string, number> = {
      overdue: 0,
      draft: 1,
      sent: 2,
      paid: 3,
    };
    return [...invoices].sort((left: any, right: any) => {
      const rankDiff = (rank[left.status] ?? 9) - (rank[right.status] ?? 9);
      if (rankDiff !== 0) return rankDiff;
      const leftDate = new Date(left.updated_at || left.issued_date || left.created_at || 0).getTime();
      const rightDate = new Date(right.updated_at || right.issued_date || right.created_at || 0).getTime();
      return rightDate - leftDate;
    });
  }, [invoices]);
  const getInvoiceComparable = (invoice: any) => {
    if (invoiceSortField === "follow_up") return getInvoiceLifecycleDate(invoice);
    if (invoiceSortField === "next_action") return getInvoiceNextActionLabel(invoice.status, t);
    return invoice?.[invoiceSortField] ?? "";
  };
  const sortedInvoices = useMemo(
    () => sortTableRows(actionableInvoices, getInvoiceComparable, invoiceSortDirection),
    [actionableInvoices, invoiceSortDirection, invoiceSortField, t],
  );
  const pinnedInvoices = useMemo(() => {
    if (!recentInvoiceMove) return sortedInvoices;
    const movedIndex = sortedInvoices.findIndex((invoice: any) => invoice.id === recentInvoiceMove.invoiceId);
    if (movedIndex <= 0) return sortedInvoices;
    const nextInvoices = [...sortedInvoices];
    const [movedInvoice] = nextInvoices.splice(movedIndex, 1);
    return [movedInvoice, ...nextInvoices];
  }, [recentInvoiceMove, sortedInvoices]);
  const displayedInvoices = pinnedInvoices.slice(0, 8);
  const nextInvoice = displayedInvoices[0] || null;
  const handleInvoiceHeaderClick = (key: string) => {
    if (!["invoice_number", "status", "total_amount", "issued_date", "follow_up", "next_action"].includes(key)) {
      return;
    }
    if (invoiceSortField === key) {
      setInvoiceSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setInvoiceSortField(key as InvoiceSortField);
    setInvoiceSortDirection("asc");
  };
  const invoiceColumns = [
    {
      key: "__row_number",
      header: t("common.rowNumber", "No."),
      className: "w-[72px] text-[#7f8d98]",
      render: (_invoice: any, index: number) => index + 1,
    },
    {
      key: "invoice_number",
      header: isSelfUse ? t("billing.outputNumberSelfUse", "Internal document #") : t("common.invoiceNumber", "Invoice #"),
      className: "min-w-[220px]",
      sortable: true,
      render: (invoice: any) => (
        <div>
          <p className="font-semibold text-[#13212c]">{invoice.invoice_number}</p>
          <p className="mt-1 text-xs text-[#61717d]">{invoice.client_name || selectedClient?.name || "—"}</p>
        </div>
      ),
    },
    {
      key: "status",
      header: t("common.status", "Status"),
      className: "min-w-[120px]",
      sortable: true,
      render: (invoice: any) => <StatusBadge status={invoice.status} />,
    },
    {
      key: "total_amount",
      header: t("common.amount", "Amount"),
      className: "min-w-[120px] font-semibold text-[#13212c]",
      sortable: true,
      render: (invoice: any) => `$${Number(invoice.total_amount || 0).toFixed(2)}`,
    },
    {
      key: "issued_date",
      header: t("billing.issueDate", "Issued"),
      className: "min-w-[130px]",
      sortable: true,
      render: (invoice: any) => formatDate(locale, invoice.issued_date),
    },
    {
      key: "follow_up",
      header: t("billing.followUpDate", "Follow-up date"),
      className: "min-w-[150px]",
      sortable: true,
      render: (invoice: any) => formatDate(locale, getInvoiceLifecycleDate(invoice)),
    },
    {
      key: "next_action",
      header: t("billing.nextAction", "Next action"),
      className: "min-w-[220px]",
      sortable: true,
      render: (invoice: any) => (
        <span className="text-[#13212c]">{getInvoiceNextActionLabel(invoice.status, t)}</span>
      ),
    },
    {
      key: "actions",
      header: t("billing.invoiceActions", "Actions"),
      className: "min-w-[190px]",
      render: (invoice: any) => (
        <div className="flex w-[180px] flex-col items-stretch gap-2">
          <button
            type="button"
            onClick={() => handleDownloadInvoice(invoice.id, invoice.invoice_number)}
            className="inline-flex min-h-[44px] w-full items-center justify-center rounded-full border border-[#13212c]/10 bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#13212c] transition hover:bg-[#fbf8f2]"
          >
            {t("billing.downloadPdf", "Download PDF")}
          </button>
          {invoice.status === "draft" ? (
            <button
              type="button"
              onClick={() => updateInvoiceStatus.mutate({ invoiceId: invoice.id, invoiceNumber: invoice.invoice_number, status: "sent" })}
              disabled={updateInvoiceStatus.isPending}
              className="inline-flex min-h-[44px] w-full items-center justify-center rounded-full border border-[#8db6ff]/20 bg-[#8db6ff]/10 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#5d89dd] transition hover:bg-[#8db6ff]/16 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t("billing.markSent", "Mark sent")}
            </button>
          ) : null}
          {invoice.status !== "paid" ? (
            <button
              type="button"
              onClick={() => updateInvoiceStatus.mutate({ invoiceId: invoice.id, invoiceNumber: invoice.invoice_number, status: "paid" })}
              disabled={updateInvoiceStatus.isPending}
              className="inline-flex min-h-[44px] w-full items-center justify-center rounded-full border border-[#4da36f]/20 bg-[#4da36f]/10 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#296346] transition hover:bg-[#4da36f]/16 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t("billing.markPaid", "Mark paid")}
            </button>
          ) : null}
          {invoice.status === "sent" ? (
            <button
              type="button"
              onClick={() => updateInvoiceStatus.mutate({ invoiceId: invoice.id, invoiceNumber: invoice.invoice_number, status: "overdue" })}
              disabled={updateInvoiceStatus.isPending}
              className="inline-flex min-h-[44px] w-full items-center justify-center rounded-full border border-[#d47854]/20 bg-[#d47854]/10 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8b432a] transition hover:bg-[#d47854]/16 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t("billing.markOverdue", "Mark overdue")}
            </button>
          ) : null}
        </div>
      ),
    },
  ];
  const workspaceStateLabel = calcResult
    ? isSelfUse
      ? t("billing.stateCostPreviewReady", "Cost preview ready")
      : t("billing.statePreviewReady", "Billing preview ready")
    : latestRateCard
      ? t("billing.stateReadyForRun", "Ready for period run")
      : t("billing.stateNeedsRateCard", "Needs rate card first");
  const workspaceStateTone = calcResult ? "ready" : latestRateCard ? "steady" : "warning";

  const pageCopy = useMemo(() => {
    if (isSelfUse) {
      return {
        eyebrow: t("billing.selfUseEyebrow", "Warehouse cost control"),
        title: t("billing.selfUseTitle", "Cost & internal charging"),
        body: t(
          "billing.selfUseBody",
          "Use this page to explain what warehouse work costs internally. Keep operating activity visible, identify cost drivers, and only use rate cards when one business unit must recharge another.",
        ),
      };
    }
    return {
      eyebrow: t("billing.eyebrow", "3PL commercial control"),
      title: t("billing.title", "Billing"),
      body: t(
        "billing.body",
        "Billing should explain how warehouse work turns into client charges. Keep rate logic visible, invoice operations predictable, and commercial trust tied to operational truth.",
      ),
    };
  }, [isSelfUse, t]);
  const tenantBillingProfile = useMemo(() => extractTenantBillingProfile(tenantProfile), [tenantProfile]);
  const tenantTaxRegion = useMemo(
    () => normalizeTaxRegion(tenantBillingProfile.tax_region),
    [tenantBillingProfile.tax_region],
  );
  const clientBillingProfile = useMemo(() => extractClientBillingProfile(selectedClient), [selectedClient]);
  const formalInvoiceChecklist = useMemo(() => {
    if (isSelfUse) return [];
    const missing: string[] = [];
    const issuerLegalName = String(tenantBillingProfile.legal_name || tenantProfile?.name || "").trim();
    const issuerTaxId = String(tenantBillingProfile.tax_id || "").trim();
    const issuerVatId = String(tenantBillingProfile.vat_id || "").trim();
    const clientLegalName = String(clientBillingProfile.legal_name || selectedClient?.name || "").trim();
    if (!issuerLegalName) missing.push(t("billing.readinessIssuerLegal", "Issuer legal name"));
    if (tenantTaxRegion === "eu" && !issuerTaxId && !issuerVatId) {
      missing.push(t("billing.readinessIssuerTax", "Issuer tax or VAT registration"));
    }
    if (!clientLegalName) missing.push(t("billing.readinessClientLegal", "Bill-to legal name"));
    return missing;
  }, [
    clientBillingProfile.legal_name,
    isSelfUse,
    selectedClient?.name,
    t,
    tenantBillingProfile.legal_name,
    tenantBillingProfile.tax_id,
    tenantBillingProfile.vat_id,
    tenantProfile?.name,
    tenantTaxRegion,
  ]);
  const formalInvoiceBlocked = formalInvoiceChecklist.length > 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl">
          <p className="text-xs uppercase tracking-[0.24em] text-[#7f8e98]">{pageCopy.eyebrow}</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-[#13212c] md:text-3xl md:tracking-[-0.04em]">{pageCopy.title}</h1>
          <p className="mt-3 hidden text-sm leading-7 text-[#5f6f7c] md:block">{pageCopy.body}</p>
        </div>
        <div className="rounded-full border border-[#13212c]/10 bg-white/75 px-3 py-1.5 text-[11px] uppercase tracking-[0.18em] text-[#61717d]">
          {businessMode === "3pl" ? t("billing.mode3plTitle", "3PL service mode") : t("billing.modeSelfUseTitle", "Self-use warehouse mode")}
        </div>
      </div>

      <div
        className="rounded-[1.1rem] border border-[#13212c]/10 bg-white/84 px-4 py-3 text-sm leading-6 text-[#51606b] md:hidden"
        data-testid="desktop-first-mobile-notice"
      >
        <p className="font-semibold text-[#13212c]">
          {t("billing.mobileManagementNoticeTitle", "Billing is a management workspace")}
        </p>
        <p className="mt-1">
          {t(
            "billing.mobileManagementNoticeBody",
            "Use this phone view for a quick client and period check. Run detailed invoice review, PDFs, and status clean-up on iPad or desktop.",
          )}
        </p>
        <Link
          to="/dashboard"
          className="mt-3 inline-flex min-h-[44px] w-full items-center justify-center rounded-full border border-[#13212c]/10 bg-[#13212c] px-4 text-xs font-semibold uppercase tracking-[0.14em] text-[#f4efe8]"
        >
          {t("billing.mobileBackToWorkAction", "Back to warehouse work")}
        </Link>
      </div>

      {feedback ? (
        <div
          className={`rounded-[1.4rem] border px-4 py-3 text-sm ${
            feedback.type === "success"
              ? "border-[#4da36f]/20 bg-[#4da36f]/8 text-[#296346]"
              : "border-[#d47854]/20 bg-[#d47854]/8 text-[#8b432a]"
          }`}
        >
          {feedback.text}
        </div>
      ) : null}

      <section className="rounded-[1.35rem] border border-[#13212c]/10 bg-white/84 p-4 shadow-[0_24px_60px_rgba(19,33,44,0.08)] md:rounded-[2rem] md:p-5">
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl">
              <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
                {isSelfUse ? t("billing.executionDeskSelfUse", "Cost workbench") : t("billing.executionDesk", "Billing workbench")}
              </p>
              <h2 className="mt-2 text-lg font-semibold tracking-[-0.02em] text-[#13212c] md:text-xl md:tracking-[-0.03em]">
                {isSelfUse
                  ? t("billing.execTitleSelfUse", "Choose the client and period you want to turn into a cost summary.")
                  : t("billing.execTitle", "Choose the client and period you want to turn into a billing preview.")}
              </h2>
            </div>
            <StatePill tone={workspaceStateTone} label={workspaceStateLabel} />
          </div>

          <div className="grid gap-3 xl:grid-cols-[minmax(220px,1.15fr)_minmax(220px,1.05fr)_minmax(160px,0.7fr)_minmax(160px,0.7fr)]">
            <Field label={t("common.client", "Client")}>
              <select
                value={selectedClientId}
                onChange={(e) => setSelectedClientId(e.target.value)}
                className="min-h-[44px] w-full rounded-xl border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/25"
              >
                {clients.length === 0 ? <option value="">{t("billing.noClients", "No clients available")}</option> : null}
                {clients.map((client: any) => (
                  <option key={client.id} value={client.id}>
                    {client.name} · {client.code}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("common.rateCard", "Rate Card")}>
              <div className="min-h-[44px] rounded-xl border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-3 text-sm text-[#13212c]">
                {latestRateCard
                  ? `${latestRateCard.name} · ${t("billing.rulesCount", "{count} rules", { count: String(Object.keys(latestRateCard.rules || {}).length) })}`
                  : isSelfUse
                    ? t("billing.noRateCardSelfUse", "No cost rule configured yet")
                    : t("billing.noRateCard", "No active rate card configured yet")}
              </div>
            </Field>
            <Field label={t("billing.periodStart", "Period start")}>
              <input
                type="date"
                value={periodStart}
                onChange={(e) => setPeriodStart(e.target.value)}
                className="min-h-[44px] w-full rounded-xl border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/25"
              />
            </Field>
            <Field label={t("billing.periodEnd", "Period end")}>
              <input
                type="date"
                value={periodEnd}
                onChange={(e) => setPeriodEnd(e.target.value)}
                className="min-h-[44px] w-full rounded-xl border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/25"
              />
            </Field>
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
            <div className="hidden md:block">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                {t("billing.workspacePulse", "Workspace pulse")}
              </p>
              <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                <WorkbenchMetric label={t("billing.metricActiveRateCards", "Active Rate Cards")} value={rateCardCount} />
                <WorkbenchMetric label={t("billing.metricClientsCovered", "Clients Covered")} value={clientsCovered} />
                <WorkbenchMetric label={t("billing.metricRulesTracked", "Rules Tracked")} value={rulesTracked} />
                <WorkbenchMetric label={isSelfUse ? t("billing.recentOutputsCount", "Recent outputs in view") : t("billing.recentInvoiceCount", "Recent invoices in view")} value={invoices.length} />
              </div>
            </div>
            <div className="flex flex-wrap gap-3 xl:justify-end">
              <button
                type="button"
                onClick={() => calculateBilling.mutate()}
                disabled={!selectedClientId || !periodStart || !periodEnd || calculateBilling.isPending}
                className="inline-flex min-h-[44px] w-full items-center justify-center rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#243545] disabled:cursor-not-allowed disabled:bg-[#a9b2b8] sm:w-auto"
              >
                {calculateBilling.isPending
                  ? t("billing.calculating", "Calculating...")
                  : isSelfUse
                    ? t("billing.calculateSelfUseAction", "Preview internal cost")
                    : t("billing.calculateAction", "Preview billing")}
              </button>
              <Link
                to="/clients"
                className="inline-flex min-h-[44px] w-full items-center justify-center rounded-full border border-[#13212c]/10 bg-white px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#fbf8f2] sm:w-auto"
              >
                {t("billing.openClientProfiles", "Open client profiles")}
              </Link>
            </div>
          </div>

          <details className="rounded-[1rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-3 md:hidden">
            <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
              {t("billing.workspacePulse", "Workspace pulse")}
            </summary>
            <div className="mt-3 grid gap-2">
              <WorkbenchMetric label={t("billing.metricActiveRateCards", "Active Rate Cards")} value={rateCardCount} />
              <WorkbenchMetric label={t("billing.metricClientsCovered", "Clients Covered")} value={clientsCovered} />
              <WorkbenchMetric label={t("billing.metricRulesTracked", "Rules Tracked")} value={rulesTracked} />
              <WorkbenchMetric label={isSelfUse ? t("billing.recentOutputsCount", "Recent outputs in view") : t("billing.recentInvoiceCount", "Recent invoices in view")} value={invoices.length} />
            </div>
          </details>
        </div>

        {!latestRateCard ? (
          <div className="mt-4 rounded-[1.3rem] border border-[#f2a486]/24 bg-[#fff1eb] px-4 py-3 text-sm text-[#8b432a]">
            <p className="font-semibold">{t("billing.setupRateCardHintTitle", "Billing cannot close the loop until a rate card exists.")}</p>
            <p className="mt-1 leading-6">
              {t("billing.setupRateCardHintBody", "Open the client profile to define storage, receiving, picking, shipping, and minimum monthly rules for this client.")}
            </p>
            <Link
              to="/clients"
              className="mt-3 inline-flex min-h-[44px] w-full items-center justify-center rounded-full bg-[#13212c] px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-[#f4efe8] md:w-auto"
            >
              {t("billing.setupRateCardAction", "Set up rate card")}
            </Link>
          </div>
        ) : null}
      </section>

      <section className="rounded-[1.35rem] border border-[#13212c]/10 bg-white/84 p-4 shadow-[0_24px_60px_rgba(19,33,44,0.08)] md:rounded-[2rem] md:p-5">
        <div>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                {isSelfUse ? t("billing.previewEyebrowSelfUse", "Cost preview") : t("billing.previewEyebrow", "Billing preview")}
              </p>
              <h2 className="mt-3 text-xl font-semibold tracking-[-0.02em] text-[#13212c] md:text-2xl md:tracking-[-0.03em]">
                {calcResult
                  ? isSelfUse
                    ? t("billing.previewTitleReadySelfUse", "Review the cost drivers before you publish an internal charging story.")
                    : t("billing.previewTitleReady", "Review the charges before you create the invoice draft.")
                  : isSelfUse
                    ? t("billing.previewTitleSelfUse", "No cost preview yet")
                    : t("billing.previewTitle", "No billing preview yet")}
              </h2>
            </div>
            <div className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-[#677682]">
              {isSelfUse ? t("billing.report", "Report") : t("billing.invoice", "Invoice")}
            </div>
          </div>
          <p className="mt-3 hidden text-sm leading-7 text-[#5f6f7c] md:block">
            {calcResult
              ? isSelfUse
                ? t("billing.previewBodyReadySelfUse", "This summary is the bridge between warehouse work and internal recharge or cost review.")
                : t("billing.previewBodyReady", "This summary is the bridge between warehouse work and the invoice the client will eventually see.")
              : isSelfUse
                ? t("billing.previewBodySelfUse", "Run a preview to see which warehouse activities are driving internal cost this period.")
                : t("billing.previewBody", "Run a preview to see which warehouse activities are becoming billable charges this period.")}
          </p>

          {calcResult ? (
            <div className="mt-5 space-y-4">
              <details className="rounded-[1.2rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-3 md:hidden">
                <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
                  {t("billing.previewSummary", "Preview summary")}
                </summary>
                <div className="mt-3 grid gap-3">
                  <MetricTile density="compact" label={t("billing.previewTotal", "Preview total")} value={Number(calcResult.total || 0).toFixed(2)} />
                  <MetricTile density="compact" label={t("billing.previewLines", "Charge lines")} value={calcResult.charges?.filter((item: any) => !item.error).length || 0} />
                  <MetricTile density="compact" label={t("billing.previewPeriod", "Billing period")} value={`${periodStart} → ${periodEnd}`} />
                </div>
              </details>

              <div className="hidden gap-4 md:grid md:grid-cols-3">
                <MetricTile density="compact" label={t("billing.previewTotal", "Preview total")} value={Number(calcResult.total || 0).toFixed(2)} />
                <MetricTile density="compact" label={t("billing.previewLines", "Charge lines")} value={calcResult.charges?.filter((item: any) => !item.error).length || 0} />
                <MetricTile density="compact" label={t("billing.previewPeriod", "Billing period")} value={`${periodStart} → ${periodEnd}`} />
              </div>

              <details className="rounded-[1.2rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-3 md:hidden">
                <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
                  {t("billing.chargeLines", "Charge lines")}
                </summary>
                <div className="mt-3 grid gap-3">
                  {calcResult.charges?.map((item: any, index: number) => (
                    <div key={`${item.charge_type || "mobile-line"}-${index}`} className="rounded-[1rem] border border-[#13212c]/8 bg-white px-3 py-3 text-sm text-[#253441]">
                      <p className="font-semibold text-[#13212c]">{item.description || item.charge_type || t("billing.unknownCharge", "Charge line")}</p>
                      {item.error ? <p className="mt-1 text-xs text-[#a45637]">{item.error}</p> : null}
                      <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-[#61717d]">
                        <span>{item.quantity ?? "—"}</span>
                        <span>{item.unit_price != null ? `$${Number(item.unit_price).toFixed(2)}` : "—"}</span>
                        <span className="font-semibold text-[#13212c]">{item.total_amount != null ? `$${Number(item.total_amount).toFixed(2)}` : "—"}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </details>

              <div className="hidden overflow-hidden rounded-[1.6rem] border border-[#13212c]/10 bg-[#fbf8f2] md:block">
                <div className="grid grid-cols-[1.2fr_0.6fr_0.6fr_0.6fr] gap-3 border-b border-[#13212c]/8 px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#71808c]">
                  <span>{t("billing.chargeType", "Charge")}</span>
                  <span>{t("common.quantity", "Quantity")}</span>
                  <span>{t("billing.unitPrice", "Unit price")}</span>
                  <span>{t("common.amount", "Amount")}</span>
                </div>
                <div className="divide-y divide-[#13212c]/8">
                  {calcResult.charges?.map((item: any, index: number) => (
                    <div key={`${item.charge_type || "line"}-${index}`} className="grid grid-cols-[1.2fr_0.6fr_0.6fr_0.6fr] gap-3 px-4 py-3 text-sm text-[#253441]">
                      <div>
                        <p className="font-medium text-[#13212c]">{item.description || item.charge_type || t("billing.unknownCharge", "Charge line")}</p>
                        {item.error ? <p className="mt-1 text-xs text-[#a45637]">{item.error}</p> : null}
                      </div>
                      <span>{item.quantity ?? "—"}</span>
                      <span>{item.unit_price != null ? `$${Number(item.unit_price).toFixed(2)}` : "—"}</span>
                      <span className="font-medium">{item.total_amount != null ? `$${Number(item.total_amount).toFixed(2)}` : "—"}</span>
                    </div>
                  ))}
                </div>
              </div>

              {calcHasError ? (
                <div className="rounded-[1.4rem] border border-[#d47854]/18 bg-[#fff1eb] px-4 py-3 text-sm text-[#8b432a]">
                  <p className="font-semibold">{t("billing.calcBlockedTitle", "Preview is blocked by missing billing rules.")}</p>
                  <p className="mt-1 leading-6">
                    {calcErrorMessage === "No active rate card found for this client"
                      ? t("billing.calcBlockedRateCard", "This period does not have an active rate card yet. Open the billing setup step and set the rate-card effective date so it covers this period.")
                      : calcErrorMessage}
                  </p>
                </div>
              ) : null}

              {!isSelfUse ? (
                <div className={`rounded-[1.4rem] border px-4 py-3 text-sm ${formalInvoiceBlocked ? "border-[#f3b54d]/22 bg-[#fff7e8] text-[#8b6407]" : "border-[#4da36f]/18 bg-[#eef8f1] text-[#296346]"}`}>
                  <p className="font-semibold">
                    {formalInvoiceBlocked
                      ? t("billing.formalInvoiceChecklistTitle", "Formal invoice checklist still has gaps.")
                      : t("billing.formalInvoiceReadyTitle", "Formal invoice data is ready.")}
                  </p>
                  <p className="mt-1 leading-6">
                    {formalInvoiceBlocked
                      ? t("billing.formalInvoiceChecklistBody", "Fill the missing issuer and bill-to details before you create a customer-facing invoice draft.")
                      : t("billing.formalInvoiceReadyBody", "Issuer tax data, bill-to legal name, and currency settings are present for this invoice run.")}
                  </p>
                  {formalInvoiceBlocked ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {formalInvoiceChecklist.map((item) => (
                        <span key={item} className="rounded-full border border-[#f3b54d]/20 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8b6407]">
                          {item}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className="rounded-[1.5rem] border border-[#13212c]/10 bg-white px-4 py-4">
                <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
                  <Field label={isSelfUse ? t("billing.outputNumberSelfUse", "Internal document #") : t("common.invoiceNumber", "Invoice #")}>
                    <input
                      type="text"
                      value={invoiceNumber}
                      onChange={(e) => setInvoiceNumber(e.target.value)}
                      className="min-h-[44px] w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]"
                    />
                  </Field>
                  <button
                    type="button"
                    onClick={() => generateInvoice.mutate()}
                    disabled={!calcResult?.period_id || !invoiceNumber || generateInvoice.isPending || calcHasError || formalInvoiceBlocked}
                    className="inline-flex min-h-[44px] items-center justify-center rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f5efe5] transition hover:bg-[#1d3140] disabled:cursor-not-allowed disabled:bg-[#a9b2b8]"
                  >
                    {generateInvoice.isPending
                      ? t("billing.generatingInvoice", "Generating...")
                      : isSelfUse
                        ? t("billing.generateSelfUseDocument", "Create internal document")
                        : t("billing.generateInvoice", "Create invoice draft")}
                  </button>
                </div>

                {invoiceResult ? (
                  <div className="mt-4 flex flex-wrap items-center gap-3 rounded-[1.2rem] border border-[#4da36f]/20 bg-[#4da36f]/8 px-4 py-3 text-sm text-[#296346]">
                    <span>
                      {isSelfUse
                        ? t("billing.documentReady", "The internal billing document is ready.")
                        : t("billing.invoiceReady", "The invoice draft is ready.")}
                    </span>
                    <span className="font-semibold">{invoiceResult.invoice_number}</span>
                    <button
                      type="button"
                      onClick={() => handleDownloadInvoice(invoiceResult.invoice_id, invoiceResult.invoice_number)}
                      className="min-h-[44px] rounded-full border border-[#296346]/15 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#296346]"
                    >
                      {t("billing.downloadPdf", "Download PDF")}
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="mt-5 rounded-[1.6rem] border border-dashed border-[#13212c]/14 bg-[#fbf8f2] px-5 py-5 text-sm text-[#61717d]">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-semibold text-[#13212c]">
                    {isSelfUse
                      ? t("billing.previewEmptyCompactTitleSelfUse", "Run a cost estimate first, then decide whether to generate internal documents.")
                      : t("billing.previewEmptyCompactTitle", "Run a billing estimate first, then decide whether to create an invoice draft.")}
                  </p>
                  <p className="mt-2 leading-6">
                    {isSelfUse
                      ? t("billing.previewEmptyCompactBodySelfUse", "Nothing to show yet because no cost summary has been generated for this period.")
                      : t("billing.previewEmptyCompactBody", "Nothing to show yet because no billing summary has been generated for this period.")}
                  </p>
                </div>
                <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                  {t("billing.previewEmptyState", "Not estimated yet")}
                </span>
              </div>
              <details className="mt-4 rounded-[1.2rem] border border-[#13212c]/8 bg-white/70 px-4 py-3">
                <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c] marker:hidden">
                  {isSelfUse
                    ? t("billing.previewEmptyExpandSelfUse", "Expand to see what this cost estimate will include")
                    : t("billing.previewEmptyExpand", "Expand to see what this billing estimate will include")}
                </summary>
                <p className="mt-3 leading-7 text-[#61717d]">
                  {isSelfUse
                    ? t("billing.previewEmptySelfUse", "Choose a client and period on the left, then preview internal cost. The page will show storage, receiving, picking, shipping, and minimum adjustments in one review layer.")
                    : t("billing.previewEmpty", "Choose a client and period on the left, then preview billing. The page will show storage, receiving, picking, shipping, and minimum adjustments before you generate the invoice draft.")}
                </p>
              </details>
            </div>
          )}
        </div>
      </section>

      <section className="rounded-[1.35rem] border border-[#13212c]/10 bg-white/84 p-4 shadow-[0_24px_60px_rgba(19,33,44,0.08)] md:rounded-[2rem] md:p-5">
        <div>
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                {isSelfUse ? t("billing.recentEyebrowSelfUse", "Recent outputs") : t("billing.recentEyebrow", "Recent invoices")}
              </p>
              <h2 className="mt-3 text-xl font-semibold tracking-[-0.02em] text-[#13212c] md:text-2xl md:tracking-[-0.03em]">
                {isSelfUse
                  ? t("billing.recentTitleSelfUse", "Keep the latest internal charging outputs close to the rate logic.")
                  : t("billing.recentTitle", "Keep the latest invoices close to the rate logic.")}
              </h2>
            </div>
            {selectedClient ? (
              <div className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-[#61717d]">
                {selectedClient.name}
              </div>
            ) : null}
          </div>

          {nextInvoice ? (
            <div className="mt-4 rounded-[1.1rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-3 md:hidden">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#71808c]">
                {t("billing.nextInvoiceStep", "Next invoice step")}
              </p>
              <p className="mt-1 text-sm font-semibold text-[#13212c]">{nextInvoice.invoice_number}</p>
              <p className="mt-1 text-sm text-[#61717d]">{getInvoiceNextActionLabel(nextInvoice.status, t)}</p>
            </div>
          ) : null}

          <details className="mt-4 rounded-[1.1rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-3 md:hidden">
            <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
              {t("billing.viewFiltersAndCounts", "View filters and counts")}
            </summary>
            <div className="mt-3 space-y-3">
              <div className="flex flex-wrap gap-2">
                {[
                  { key: "all", label: t("billing.filterAllInvoices", "All invoices") },
                  { key: "draft", label: t("status.draft", "draft") },
                  { key: "sent", label: t("status.sent", "sent") },
                  { key: "paid", label: t("status.paid", "paid") },
                  { key: "overdue", label: t("status.overdue", "overdue") },
                ].map((filter) => (
                  <button
                    key={filter.key}
                    type="button"
                    onClick={() => {
                      setRecentInvoiceMove(null);
                      setInvoiceStatusFilter(filter.key as typeof invoiceStatusFilter);
                    }}
                    className={`min-h-[44px] rounded-full px-4 py-2 text-sm font-medium transition ${
                      invoiceStatusFilter === filter.key ? "bg-[#13212c] text-[#f4efe8]" : "border border-[#13212c]/10 bg-white text-[#13212c] hover:bg-[#fbf8f2]"
                    }`}
                  >
                    {filter.label}
                  </button>
                ))}
              </div>
              <div className="grid gap-3">
                <MetricTile density="compact" label={t("billing.queueDraft", "Draft")} value={invoiceSummary.draft || 0} />
                <MetricTile density="compact" label={t("billing.queueSent", "Sent")} value={invoiceSummary.sent || 0} />
                <MetricTile density="compact" label={t("billing.queuePaid", "Paid")} value={invoiceSummary.paid || 0} />
                <MetricTile density="compact" label={t("billing.queueOverdue", "Overdue")} value={invoiceSummary.overdue || 0} />
              </div>
            </div>
          </details>

          <div className="mt-4 hidden flex-wrap gap-2 md:flex">
            {[
              { key: "all", label: t("billing.filterAllInvoices", "All invoices") },
              { key: "draft", label: t("status.draft", "draft") },
              { key: "sent", label: t("status.sent", "sent") },
              { key: "paid", label: t("status.paid", "paid") },
              { key: "overdue", label: t("status.overdue", "overdue") },
            ].map((filter) => (
              <button
                key={filter.key}
                type="button"
                onClick={() => {
                  setRecentInvoiceMove(null);
                  setInvoiceStatusFilter(filter.key as typeof invoiceStatusFilter);
                }}
                className={`min-h-[44px] rounded-full px-4 py-2 text-sm font-medium transition ${
                  invoiceStatusFilter === filter.key ? "bg-[#13212c] text-[#f4efe8]" : "border border-[#13212c]/10 bg-white text-[#13212c] hover:bg-[#fbf8f2]"
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>

          <div className="mt-4 hidden gap-3 md:grid md:grid-cols-4">
            <MetricTile density="compact" label={t("billing.queueDraft", "Draft")} value={invoiceSummary.draft || 0} />
            <MetricTile density="compact" label={t("billing.queueSent", "Sent")} value={invoiceSummary.sent || 0} />
            <MetricTile density="compact" label={t("billing.queuePaid", "Paid")} value={invoiceSummary.paid || 0} />
            <MetricTile density="compact" label={t("billing.queueOverdue", "Overdue")} value={invoiceSummary.overdue || 0} />
          </div>
          <p className="mt-3 text-xs leading-6 text-[#71808c]">
            {t(
              "billing.statusMoveHint",
              "Status actions move invoices between these filters. After a move, the list follows the invoice to its new status.",
            )}
          </p>
          {recentInvoiceMove ? (
            <div className="mt-3 rounded-[1.2rem] border border-[#4da36f]/18 bg-[#eef8f1] px-4 py-3 text-sm text-[#296346]">
              {t(
                "billing.movedInvoicePinned",
                "{invoice} is pinned here after moving to {status}.",
                {
                  invoice: recentInvoiceMove.invoiceNumber || t("billing.thisInvoice", "This invoice"),
                  status: getInvoiceStatusLabel(recentInvoiceMove.status, t),
                },
              )}
            </div>
          ) : null}

          <div className="mt-5">
            <DataTable
              columns={invoiceColumns}
              data={displayedInvoices}
              loading={invoicesLoading}
              mobileDetailLimit={3}
              onHeaderClick={handleInvoiceHeaderClick}
              rowClassName={(invoice) =>
                recentInvoiceMove?.invoiceId === invoice.id
                  ? "bg-[#eef8f1] ring-1 ring-inset ring-[#4da36f]/18"
                  : ""
              }
              sortField={invoiceSortField}
              sortDirection={invoiceSortDirection}
              emptyTitle={isSelfUse ? t("billing.noRecentSelfUseTitle", "No outputs") : t("billing.noRecentTitle", "No invoices")}
              emptyMessage={
                isSelfUse
                  ? t("billing.noRecentSelfUse", "No internal charging outputs yet for this client.")
                  : t("billing.noRecent", "No invoices yet for this client.")
              }
            />
            {actionableInvoices.length > displayedInvoices.length ? (
              <p className="mt-3 text-xs text-[#71808c]">
                {t("billing.invoiceTableLimit", "Showing the first {count} invoices in this view.", {
                  count: String(displayedInvoices.length),
                })}
              </p>
            ) : null}
          </div>
        </div>
      </section>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-2">
      <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#71808c]">{label}</span>
      {children}
    </label>
  );
}

function WorkbenchMetric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex min-h-[58px] items-center justify-between gap-3 rounded-[1rem] border border-[#13212c]/8 bg-[#fbf8f2] px-3 py-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#71808c]">{label}</p>
      <p className="text-lg font-semibold text-[#13212c]">{value}</p>
    </div>
  );
}

function getInvoiceLifecycleDate(invoice: any) {
  if (invoice.status === "paid") return invoice.paid_date;
  if (invoice.status === "sent") return invoice.due_date || invoice.issued_date;
  return invoice.issued_date || invoice.due_date;
}

function getInvoiceNextActionLabel(
  status: string,
  t: (key: string, fallback?: string, vars?: Record<string, string | number>) => string,
) {
  if (status === "draft") return t("billing.nextActionSend", "Next: send to client");
  if (status === "sent") return t("billing.nextActionCollect", "Next: collect payment");
  if (status === "overdue") return t("billing.nextActionResolve", "Next: resolve overdue payment");
  return t("billing.nextActionFiled", "Closed for now");
}

function getInvoiceStatusLabel(
  status: "sent" | "paid" | "overdue" | "draft",
  t: (key: string, fallback?: string, vars?: Record<string, string | number>) => string,
) {
  if (status === "sent") return t("status.sent", "sent");
  if (status === "paid") return t("status.paid", "paid");
  if (status === "overdue") return t("status.overdue", "overdue");
  return t("status.draft", "draft");
}

function StatePill({
  tone,
  label,
}: {
  tone: "ready" | "steady" | "warning";
  label: string;
}) {
  const classes = tone === "ready"
    ? "border-[#8ed9aa]/45 bg-[#1d4630] text-[#e8fff0] shadow-[0_10px_28px_rgba(23,56,39,0.24)]"
    : tone === "steady"
      ? "border-[#f6d27c]/45 bg-[#5c4720] text-[#fff3cf] shadow-[0_10px_28px_rgba(78,56,18,0.24)]"
      : "border-[#f2a486]/45 bg-[#5a3228] text-[#ffe1d6] shadow-[0_10px_28px_rgba(81,42,31,0.22)]";

  return (
    <div className={`rounded-full border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] ${classes}`}>
      {label}
    </div>
  );
}

function defaultPeriodStart() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
}

function defaultPeriodEnd() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
}

function formatDate(locale: string, value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function extractTenantBillingProfile(tenantProfile: any) {
  return (tenantProfile?.settings?.billing_profile || {}) as Record<string, any>;
}

function extractClientBillingProfile(client: any) {
  return (client?.settings?.billing_profile || {}) as Record<string, any>;
}

function normalizeTaxRegion(value?: string | null): "eu" | "us" {
  return value === "us" ? "us" : "eu";
}
