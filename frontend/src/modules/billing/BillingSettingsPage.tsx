import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowRight, Plus } from "lucide-react";
import {
  createRateCard as createRateCardRequest,
  fetchCurrentTenant,
  fetchRateCards,
  updateTenantSettings,
} from "../../shared/api/billing";
import {
  createClient as createClientRequest,
  fetchClients,
  updateClient,
} from "../../shared/api/clients";
import { queryKeys } from "../../shared/api/queryKeys";
import DataTable from "../../shared/components/DataTable";
import { getApiErrorMessage } from "../../shared/api/error-message";
import { useI18n } from "../../shared/i18n";
import { sortTableRows, type SortDirection } from "../../shared/utils/tableSort";

type RateCardSortField =
  | "client"
  | "contact"
  | "billing_enabled"
  | "portal_access"
  | "status"
  | "rate_card"
  | "effective_from"
  | "rules";

type ClientDetailTab = "profile" | "billing" | "rate_cards" | "portal" | "activity";
type ReadinessTone = "neutral" | "success" | "warning";

type ClientReadiness = {
  label: string;
  detail: string;
  missing: string[];
  tone: ReadinessTone;
  sortKey: string;
};

type TranslationFn = (key: string, fallback: string, variables?: Record<string, string>) => string;

type RateCardTableRow = {
  client_id: string;
  client_label: string;
  client: any;
  rate_card: any | null;
  readiness: ClientReadiness;
  has_duplicate_name: boolean;
};

const NEW_RATE_CARD_VALUE = "__new_rate_card__";

export default function BillingSettingsPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { data: rateCards = [], isLoading } = useQuery({
    queryKey: queryKeys.billing.rateCards(),
    queryFn: fetchRateCards,
  });
  const { data: clientPage, isLoading: clientsLoading } = useQuery({
    queryKey: queryKeys.clients.billing(),
    queryFn: () => fetchClients({ limit: 500 }),
  });
  const { data: tenantProfile } = useQuery({
    queryKey: queryKeys.billing.tenantProfile(),
    queryFn: fetchCurrentTenant,
  });

  const clients = clientPage?.items || [];
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [businessMode, setBusinessMode] = useState<"3pl" | "self_use">("3pl");
  const [selectedClientId, setSelectedClientId] = useState("");
  const [clientAccountDraft, setClientAccountDraft] = useState({
    name: "",
    code: "",
    contact_email: "",
    contact_phone: "",
    billing_enabled: true,
    portal_access: true,
  });
  const [newClientDraft, setNewClientDraft] = useState({
    name: "",
    code: "",
    contact_email: "",
    contact_phone: "",
    billing_enabled: true,
    portal_access: true,
  });
  const [rateCardDraft, setRateCardDraft] = useState({
    name: "",
    effective_from: defaultPeriodStart(),
    storage_per_pallet_day: "0.85",
    receiving_per_unit: "0.25",
    pick_per_order: "2.00",
    pick_per_line: "0.50",
    shipping_handling_per_order: "1.50",
    minimum_monthly: "200",
  });
  const [selectedRateCardVersionId, setSelectedRateCardVersionId] = useState(NEW_RATE_CARD_VALUE);
  const [billToLegalNameMode, setBillToLegalNameMode] = useState<"client" | "custom">("client");
  const [clientDetailTab, setClientDetailTab] = useState<ClientDetailTab>("profile");
  const [tenantBillingDraft, setTenantBillingDraft] = useState({
    tax_region: "eu",
    legal_name: "",
    tax_id: "",
    vat_id: "",
    billing_email: "",
    tax_rate_pct: "0",
    tax_label: "VAT",
    tax_exemption_note: "",
    reverse_charge_note: "",
    bank_name: "",
    bank_account: "",
    iban: "",
    swift: "",
    payment_terms_days: "30",
    payment_terms_label: "Net 30",
    currency: "USD",
    invoice_notes: "",
    invoice_footer_legal: "",
  });
  const [clientBillingDraft, setClientBillingDraft] = useState({
    tax_region: "",
    legal_name: "",
    tax_id: "",
    vat_id: "",
    billing_email: "",
    tax_rate_pct: "",
    tax_label: "",
    tax_exemption_note: "",
    reverse_charge_note: "",
    payment_terms_label: "",
    street: "",
    city: "",
    state: "",
    zip: "",
    country: "",
  });
  const [rateCardSortField, setRateCardSortField] = useState<RateCardSortField>("client");
  const [rateCardSortDirection, setRateCardSortDirection] = useState<SortDirection>("asc");
  const [showCompanyProfile, setShowCompanyProfile] = useState(false);

  useEffect(() => {
    const nextMode = tenantProfile?.settings?.business_mode;
    if (nextMode === "3pl" || nextMode === "self_use") {
      setBusinessMode(nextMode);
      return;
    }
    setBusinessMode("3pl");
  }, [tenantProfile]);

  const latestRateCardByClientId = useMemo(() => {
    const sortedCards = [...rateCards].sort((a: any, b: any) => {
      const fromCompare = String(b.effective_from || "").localeCompare(String(a.effective_from || ""));
      if (fromCompare !== 0) return fromCompare;
      return String(b.id || "").localeCompare(String(a.id || ""));
    });
    const map = new Map<string, any>();
    sortedCards.forEach((card: any) => {
      if (card.client_id && !map.has(card.client_id)) {
        map.set(card.client_id, card);
      }
    });
    return map;
  }, [rateCards]);
  const clientNameCounts = useMemo(() => {
    const counts = new Map<string, number>();
    clients.forEach((client: any) => {
      const key = normalizeClientName(client.name);
      if (!key) return;
      counts.set(key, (counts.get(key) || 0) + 1);
    });
    return counts;
  }, [clients]);
  const selectedClient = clients.find((client: any) => client.id === selectedClientId) || null;
  const latestRateCard = selectedClientId ? latestRateCardByClientId.get(selectedClientId) || null : null;
  const selectedClientReadiness = useMemo(
    () => getClientReadiness(selectedClient, latestRateCard, t),
    [selectedClient, latestRateCard, t],
  );
  const selectedClientRateCards = useMemo(
    () => [...rateCards]
      .filter((card: any) => card.client_id === selectedClientId)
      .sort((a: any, b: any) => {
        const fromCompare = String(b.effective_from || "").localeCompare(String(a.effective_from || ""));
        if (fromCompare !== 0) return fromCompare;
        return String(b.id || "").localeCompare(String(a.id || ""));
      }),
    [rateCards, selectedClientId],
  );
  const clientsWithBilling = clients.filter((client: any) => client.billing_enabled).length;
  const clientsWithPortal = clients.filter((client: any) => client.portal_access).length;
  const clientsWithRateCards = clients.filter((client: any) => latestRateCardByClientId.has(client.id)).length;
  const rateCardRows = useMemo<RateCardTableRow[]>(
    () => clients.map((client: any) => {
      const rateCard = latestRateCardByClientId.get(client.id) || null;
      return {
        client_id: client.id,
        client_label: client.code ? `${client.name} · ${client.code}` : client.name,
        client,
        rate_card: rateCard,
        readiness: getClientReadiness(client, rateCard, t),
        has_duplicate_name: (clientNameCounts.get(normalizeClientName(client.name)) || 0) > 1,
      };
    }),
    [clients, latestRateCardByClientId, clientNameCounts, t],
  );
  const getRateCardRowComparable = useCallback((row: RateCardTableRow) => {
    if (rateCardSortField === "client") return row.client_label;
    if (rateCardSortField === "contact") return row.client.contact_email || "";
    if (rateCardSortField === "billing_enabled") return row.client.billing_enabled ? "1-enabled" : "0-off";
    if (rateCardSortField === "portal_access") return row.client.portal_access ? "1-enabled" : "0-off";
    if (rateCardSortField === "status") return row.readiness.sortKey;
    if (rateCardSortField === "rate_card") return row.rate_card?.name || "";
    if (rateCardSortField === "effective_from") return row.rate_card?.effective_from || "";
    if (rateCardSortField === "rules") return row.rate_card ? getRateCardRuleCount(row.rate_card) : 0;
    return "";
  }, [rateCardSortField]);
  const sortedRateCardRows = useMemo(
    () => sortTableRows(rateCardRows, getRateCardRowComparable, rateCardSortDirection),
    [rateCardRows, rateCardSortDirection, getRateCardRowComparable],
  );
  const handleRateCardHeaderClick = (key: string) => {
    if (!["client", "contact", "billing_enabled", "portal_access", "status", "rate_card", "effective_from", "rules"].includes(key)) return;
    if (rateCardSortField === key) {
      setRateCardSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setRateCardSortField(key as RateCardSortField);
    setRateCardSortDirection("asc");
  };
  const handleRateCardRowClick = useCallback((row: RateCardTableRow) => {
    setFeedback(null);
    setSelectedClientId(row.client_id);
    window.requestAnimationFrame(() => {
      document.getElementById("client-master-workbench")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  }, []);

  useEffect(() => {
    if (!selectedClient) return;
    setClientAccountDraft({
      name: selectedClient.name || "",
      code: selectedClient.code || "",
      contact_email: selectedClient.contact_email || "",
      contact_phone: selectedClient.contact_phone || "",
      billing_enabled: Boolean(selectedClient.billing_enabled),
      portal_access: Boolean(selectedClient.portal_access),
    });
    setSelectedRateCardVersionId(latestRateCard?.id || NEW_RATE_CARD_VALUE);
    setRateCardDraft(buildRateCardDraft(latestRateCard, selectedClient));
  }, [selectedClient?.id, latestRateCard?.id]);

  useEffect(() => {
    const billingProfile = extractTenantBillingProfile(tenantProfile);
    const taxRegion = normalizeTaxRegion(billingProfile.tax_region);
    setTenantBillingDraft({
      legal_name: billingProfile.legal_name || tenantProfile?.name || "",
      tax_region: taxRegion,
      tax_id: billingProfile.tax_id || "",
      vat_id: billingProfile.vat_id || "",
      billing_email: billingProfile.billing_email || tenantProfile?.contact_email || "",
      tax_rate_pct: String(billingProfile.tax_rate_pct ?? 0),
      tax_label: billingProfile.tax_label || taxLabelForRegion(taxRegion),
      tax_exemption_note: billingProfile.tax_exemption_note || "",
      reverse_charge_note: billingProfile.reverse_charge_note || "",
      bank_name: billingProfile.bank_name || "",
      bank_account: billingProfile.bank_account || "",
      iban: billingProfile.iban || "",
      swift: billingProfile.swift || "",
      payment_terms_days: String(billingProfile.payment_terms_days ?? 30),
      payment_terms_label: billingProfile.payment_terms_label || "Net 30",
      currency: billingProfile.currency || "USD",
      invoice_notes: billingProfile.invoice_notes || "",
      invoice_footer_legal: billingProfile.invoice_footer_legal || "",
    });
  }, [tenantProfile?.id, tenantProfile?.settings, tenantProfile?.contact_email, tenantProfile?.name]);

  useEffect(() => {
    const billingProfile = extractClientBillingProfile(selectedClient);
    const taxRegion = billingProfile.tax_region ? normalizeTaxRegion(billingProfile.tax_region) : "";
    const legalName = billingProfile.legal_name || selectedClient?.name || "";
    setBillToLegalNameMode(legalName && selectedClient?.name && legalName !== selectedClient.name ? "custom" : "client");
    setClientBillingDraft({
      legal_name: legalName,
      tax_region: taxRegion,
      tax_id: billingProfile.tax_id || "",
      vat_id: billingProfile.vat_id || "",
      billing_email: billingProfile.billing_email || selectedClient?.contact_email || "",
      tax_rate_pct: billingProfile.tax_rate_pct != null ? String(billingProfile.tax_rate_pct) : "",
      tax_label: billingProfile.tax_label || (taxRegion ? taxLabelForRegion(taxRegion) : ""),
      tax_exemption_note: billingProfile.tax_exemption_note || "",
      reverse_charge_note: billingProfile.reverse_charge_note || "",
      payment_terms_label: billingProfile.payment_terms_label || "",
      street: selectedClient?.address?.street || "",
      city: selectedClient?.address?.city || "",
      state: selectedClient?.address?.state || "",
      zip: selectedClient?.address?.zip || "",
      country: selectedClient?.address?.country || "",
    });
  }, [selectedClient?.id, selectedClient?.settings, selectedClient?.contact_email, selectedClient?.name, selectedClient?.address]);

  const createRateCard = useMutation({
    mutationFn: async () =>
      createRateCardRequest({
        client_id: selectedClientId,
        name: rateCardDraft.name,
        effective_from: rateCardDraft.effective_from,
        rules: {
          storage_per_pallet_day: Number(rateCardDraft.storage_per_pallet_day || 0),
          receiving_per_unit: Number(rateCardDraft.receiving_per_unit || 0),
          pick_per_order: Number(rateCardDraft.pick_per_order || 0),
          pick_per_line: Number(rateCardDraft.pick_per_line || 0),
          shipping_handling_per_order: Number(rateCardDraft.shipping_handling_per_order || 0),
          minimum_monthly: Number(rateCardDraft.minimum_monthly || 0),
        },
      }),
    onSuccess: async () => {
      setFeedback({
        type: "success",
        text: t("billing.rateCardSaved", "Rate card saved. You can now preview this billing period with the new rules."),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.billing.rateCards() });
    },
    onError: (error: any) => {
      setFeedback({
        type: "error",
        text: getApiErrorMessage(error, t("billing.rateCardSaveError", "Could not save the rate card.")),
      });
    },
  });

  const createClient = useMutation({
    mutationFn: async () =>
      createClientRequest({
        name: newClientDraft.name,
        code: newClientDraft.code,
        contact_email: newClientDraft.contact_email || null,
        contact_phone: newClientDraft.contact_phone || null,
        billing_enabled: newClientDraft.billing_enabled,
        portal_access: newClientDraft.portal_access,
      }).then((r) => r.data),
    onSuccess: async (client) => {
      setFeedback({
        type: "success",
        text: t("clients.created", "Client created."),
      });
      setNewClientDraft({
        name: "",
        code: "",
        contact_email: "",
        contact_phone: "",
        billing_enabled: true,
        portal_access: true,
      });
      setSelectedClientId(client.id);
      await queryClient.invalidateQueries({ queryKey: queryKeys.clients.billing() });
      window.requestAnimationFrame(() => {
        document.getElementById("client-master-workbench")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
    },
    onError: (error: any) => {
      setFeedback({
        type: "error",
        text: getApiErrorMessage(error, t("clients.createError", "Could not create the client.")),
      });
    },
  });

  const saveClientAccount = useMutation({
    mutationFn: async () => {
      if (!selectedClientId) throw new Error("No client selected");
      return updateClient(selectedClientId, {
        name: clientAccountDraft.name,
        code: clientAccountDraft.code,
        contact_email: clientAccountDraft.contact_email || null,
        contact_phone: clientAccountDraft.contact_phone || null,
        billing_enabled: clientAccountDraft.billing_enabled,
        portal_access: clientAccountDraft.portal_access,
      }).then((r) => r.data);
    },
    onSuccess: async () => {
      setFeedback({
        type: "success",
        text: t("clients.accountSaved", "Client account profile saved."),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.clients.billing() });
    },
    onError: (error: any) => {
      setFeedback({
        type: "error",
        text: getApiErrorMessage(error, t("clients.accountSaveError", "Could not save the client account profile.")),
      });
    },
  });

  const saveTenantBillingProfile = useMutation({
    mutationFn: async () =>
      updateTenantSettings({
        business_mode: businessMode,
        billing_profile: {
          legal_name: tenantBillingDraft.legal_name,
          tax_region: tenantBillingDraft.tax_region,
          tax_id: tenantBillingDraft.tax_id,
          vat_id: tenantBillingDraft.vat_id,
          billing_email: tenantBillingDraft.billing_email,
          tax_rate_pct: Number(tenantBillingDraft.tax_rate_pct || 0),
          tax_label: tenantBillingDraft.tax_label,
          tax_exemption_note: tenantBillingDraft.tax_exemption_note,
          reverse_charge_note: tenantBillingDraft.reverse_charge_note,
          bank_name: tenantBillingDraft.bank_name,
          bank_account: tenantBillingDraft.bank_account,
          iban: tenantBillingDraft.iban,
          swift: tenantBillingDraft.swift,
          payment_terms_days: Number(tenantBillingDraft.payment_terms_days || 0),
          payment_terms_label: tenantBillingDraft.payment_terms_label,
          currency: tenantBillingDraft.currency,
          invoice_notes: tenantBillingDraft.invoice_notes,
          invoice_footer_legal: tenantBillingDraft.invoice_footer_legal,
        },
      }).then((r) => r.data),
    onSuccess: async () => {
      setFeedback({
        type: "success",
        text: t("billing.issuerProfileSaved", "Issuer billing profile saved."),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.billing.tenantProfile() });
    },
    onError: (error: any) => {
      setFeedback({
        type: "error",
        text: getApiErrorMessage(error, t("billing.issuerProfileSaveError", "Could not save issuer billing profile.")),
      });
    },
  });

  const saveClientBillingProfile = useMutation({
    mutationFn: async () => {
      if (!selectedClientId) throw new Error("No client selected");
      const nextSettings = {
        ...(selectedClient?.settings || {}),
        billing_profile: {
          ...extractClientBillingProfile(selectedClient),
          legal_name: clientBillingDraft.legal_name,
          tax_region: clientBillingDraft.tax_region,
          tax_id: clientBillingDraft.tax_id,
          vat_id: clientBillingDraft.vat_id,
          billing_email: clientBillingDraft.billing_email,
          tax_rate_pct: clientBillingDraft.tax_rate_pct ? Number(clientBillingDraft.tax_rate_pct) : null,
          tax_label: clientBillingDraft.tax_label,
          tax_exemption_note: clientBillingDraft.tax_exemption_note,
          reverse_charge_note: clientBillingDraft.reverse_charge_note,
          payment_terms_label: clientBillingDraft.payment_terms_label,
        },
      };
      return updateClient(selectedClientId, {
        contact_email: clientBillingDraft.billing_email || selectedClient?.contact_email || null,
        address: {
          street: clientBillingDraft.street,
          city: clientBillingDraft.city,
          state: clientBillingDraft.state,
          zip: clientBillingDraft.zip,
          country: clientBillingDraft.country,
        },
        settings: nextSettings,
      }).then((r) => r.data);
    },
    onSuccess: async () => {
      setFeedback({
        type: "success",
        text: t("billing.clientInvoiceProfileSaved", "Client invoice profile saved."),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.clients.billing() });
    },
    onError: (error: any) => {
      setFeedback({
        type: "error",
        text: getApiErrorMessage(error, t("billing.clientInvoiceProfileSaveError", "Could not save client invoice profile.")),
      });
    },
  });

  const columns = [
    {
      key: "__row_number",
      header: t("common.rowNumber", "No."),
      className: "w-[72px] text-[#7f8d98]",
      render: (_row: any, index: number) => index + 1,
    },
    {
      key: "__edit_state",
      header: t("clients.editStateColumn", "Edit state"),
      className: "min-w-[120px]",
      render: (row: RateCardTableRow) => row.client_id === selectedClientId ? (
        <span className="inline-flex items-center gap-2 rounded-full border border-[#3da76a]/20 bg-[#eaf8f0] px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#256444]">
          <span className="h-3 w-3 rounded-full border border-[#3da76a] bg-[#3da76a]" aria-hidden="true" />
          {t("clients.editingThisClient", "Editing")}
        </span>
      ) : (
        <button
          type="button"
          aria-pressed="false"
          aria-label={t("clients.selectClientForEditing", "Select this client for editing")}
          onClick={(event) => {
            event.stopPropagation();
            handleRateCardRowClick(row);
          }}
          className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/12 bg-white px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d] transition hover:border-[#285f93]/35 hover:bg-[#eef6ff] hover:text-[#285f93]"
        >
          <span className="h-3 w-3 rounded-full border border-[#8d9aa4] bg-white" aria-hidden="true" />
          {t("common.select", "Select")}
        </button>
      ),
    },
    {
      key: "client",
      header: t("billingSettings.clientCodeColumn", "Client / code"),
      className: "min-w-[260px]",
      sortable: true,
      render: (row: RateCardTableRow) => (
        <div className="space-y-2">
          <p className="font-semibold text-[#13212c]">{row.client.name}</p>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
              {t("billingSettings.clientCodeLabel", "Code")} {row.client.code || "—"}
            </span>
            {row.has_duplicate_name ? (
              <span className="rounded-full border border-[#e1b24a]/25 bg-[#fff7df] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7d5b12]">
                {t("billingSettings.sameNameClient", "Same name")}
              </span>
            ) : null}
          </div>
        </div>
      ),
    },
    {
      key: "contact",
      header: t("common.contact", "Contact"),
      className: "min-w-[190px]",
      sortable: true,
      render: (row: RateCardTableRow) => row.client.contact_email || (
        <span className="text-[#8d9aa4]">{t("common.noEmail", "No email")}</span>
      ),
    },
    {
      key: "billing_enabled",
      header: t("nav.billing", "Billing"),
      className: "min-w-[140px]",
      sortable: true,
      render: (row: RateCardTableRow) => (
        <StatusPill
          label={row.client.billing_enabled ? t("common.enabled", "Enabled") : t("common.off", "Off")}
          tone={row.client.billing_enabled ? "success" : "neutral"}
        />
      ),
    },
    {
      key: "portal_access",
      header: t("section.clientPortal", "Client Portal"),
      className: "min-w-[150px]",
      sortable: true,
      render: (row: RateCardTableRow) => (
        <StatusPill
          label={row.client.portal_access ? t("common.enabled", "Enabled") : t("common.off", "Off")}
          tone={row.client.portal_access ? "success" : "neutral"}
        />
      ),
    },
    {
      key: "status",
      header: t("clients.readinessColumn", "Readiness"),
      className: "min-w-[190px]",
      sortable: true,
      render: (row: RateCardTableRow) => (
        <StatusPill
          label={row.readiness.label}
          tone={row.readiness.tone}
        />
      ),
    },
    {
      key: "rate_card",
      header: t("billingSettings.currentRateCardColumn", "Current rate card"),
      className: "min-w-[240px]",
      sortable: true,
      render: (row: RateCardTableRow) => row.rate_card?.name || (
        <span className="text-[#8d9aa4]">{t("billing.noRateCard", "No active rate card configured yet")}</span>
      ),
    },
    {
      key: "effective_from",
      header: t("common.effectiveFrom", "Effective From"),
      className: "min-w-[150px]",
      sortable: true,
      render: (row: RateCardTableRow) => row.rate_card?.effective_from || "—",
    },
    {
      key: "effective_to",
      header: t("common.effectiveTo", "Effective To"),
      className: "min-w-[150px]",
      render: (row: RateCardTableRow) => row.rate_card ? row.rate_card.effective_to || t("common.open", "Open") : "—",
    },
    {
      key: "rules",
      header: t("common.rules", "Rules"),
      className: "min-w-[120px]",
      sortable: true,
      render: (row: RateCardTableRow) => row.rate_card
        ? t("billing.rulesCount", "{count} rules", { count: String(getRateCardRuleCount(row.rate_card)) })
        : "—",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl">
          <p className="text-xs uppercase tracking-[0.24em] text-[#7f8e98]">
            {t("clients.eyebrow", "Customer accounts")}
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-[#13212c] md:text-3xl md:tracking-[-0.04em]">
            {t("clients.unifiedTitle", "Client master data")}
          </h1>
          <p className="mt-3 hidden text-sm leading-7 text-[#5f6f7c] md:block">
            {t("clients.unifiedBody", "Maintain each client as one master record for operations, portal access, bill-to details, tax overrides, and rate-card rules. Your company invoice profile stays in its own section below.")}
          </p>
        </div>
        <Link
          to="/billing"
          className="inline-flex min-h-[44px] items-center justify-center rounded-full border border-[#13212c]/10 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#fbf8f2]"
        >
          {t("clients.openBillingRun", "Open billing run")}
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

      <div
        className="rounded-[1.1rem] border border-[#13212c]/10 bg-white/84 px-4 py-3 text-sm leading-6 text-[#51606b] md:hidden"
        data-testid="desktop-first-mobile-notice"
        data-admin-mobile-contract="billing-settings-desktop-first"
      >
        <p className="font-semibold text-[#13212c]">
          {t("clients.mobileManagementNoticeTitle", "Client settings are a management workspace")}
        </p>
        <p className="mt-1">
          {t(
            "clients.mobileManagementNoticeBody",
            "Use this phone view to pick one client and check readiness. Do detailed billing profile, rate card, and portal setup on iPad or desktop.",
          )}
        </p>
      </div>

      <details className="rounded-[1.1rem] border border-[#13212c]/8 bg-white/84 px-4 py-3 md:hidden">
        <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
          {t("clients.viewClientCounts", "View client counts")}
        </summary>
        <div className="mt-3 grid gap-3">
          <ClientMetric label={t("clients.metricActive", "Active Clients")} value={clients.length} />
          <ClientMetric label={t("clients.metricBilling", "Billing Enabled")} value={clientsWithBilling} />
          <ClientMetric label={t("clients.metricPortal", "Portal Enabled")} value={clientsWithPortal} />
          <ClientMetric label={t("clients.metricRateCards", "Live Rate Cards")} value={clientsWithRateCards} />
        </div>
      </details>

      <div className="hidden gap-4 md:grid md:grid-cols-2 xl:grid-cols-4">
        <ClientMetric label={t("clients.metricActive", "Active Clients")} value={clients.length} />
        <ClientMetric label={t("clients.metricBilling", "Billing Enabled")} value={clientsWithBilling} />
        <ClientMetric label={t("clients.metricPortal", "Portal Enabled")} value={clientsWithPortal} />
        <ClientMetric label={t("clients.metricRateCards", "Live Rate Cards")} value={clientsWithRateCards} />
      </div>

      <section className="rounded-[1.35rem] border border-[#13212c]/10 bg-white/84 p-4 shadow-[0_24px_60px_rgba(19,33,44,0.08)] md:rounded-[2rem] md:p-5">
        <SectionIntro
          eyebrow={t("clients.directoryEyebrow", "Client directory")}
          title={t("clients.directoryTitle", "One client record owns operations, portal access, and billing setup.")}
          detail={t("clients.directoryBody", "Use the Edit state column to select one client for editing. The selected client appears in the focused tabs below; new commercial accounts can be added from the panel on the right.")}
        />

        <div className="mt-4 grid gap-5 2xl:grid-cols-[minmax(0,1fr)_380px]">
          <div className="hidden md:block">
            <DataTable
              columns={columns}
              data={sortedRateCardRows}
              loading={isLoading || clientsLoading}
              onHeaderClick={handleRateCardHeaderClick}
              onRowClick={handleRateCardRowClick}
              rowClassName={(row) => row.client_id === selectedClientId ? "bg-[#eef6ff] shadow-[inset_4px_0_0_#285f93]" : ""}
              sortField={rateCardSortField}
              sortDirection={rateCardSortDirection}
              emptyMessage={t("clients.empty", "No clients configured yet")}
              emptyHint={t("clients.emptyHint", "Clients should exist before inbound, outbound, billing, and portal visibility can represent a real account.")}
            />
          </div>

          <div className="space-y-3 md:hidden">
            {isLoading || clientsLoading ? (
              <div className="rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-6 text-center text-sm text-[#61717d]">
                {t("common.loading", "Loading...")}
              </div>
            ) : sortedRateCardRows.length === 0 ? (
              <div className="rounded-[1.1rem] border border-dashed border-[#13212c]/16 bg-[#fbf8f2] px-4 py-6 text-center text-sm text-[#61717d]">
                {t("clients.empty", "No clients configured yet")}
              </div>
            ) : (
              sortedRateCardRows.map((row) => {
                const isSelected = row.client_id === selectedClientId;
                return (
                  <button
                    key={row.client_id}
                    type="button"
                    onClick={() => handleRateCardRowClick(row)}
                    className={`min-h-[74px] w-full rounded-[1.1rem] border px-4 py-3 text-left transition ${
                      isSelected
                        ? "border-[#285f93]/30 bg-[#eef6ff] shadow-[inset_4px_0_0_#285f93]"
                        : "border-[#13212c]/10 bg-white hover:bg-[#fbf8f2]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-[#13212c]">{row.client.name}</p>
                        <p className="mt-1 text-xs uppercase tracking-[0.14em] text-[#71808c]">
                          {row.client.code || "—"}
                        </p>
                      </div>
                      <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${
                        isSelected
                          ? "border-[#285f93]/20 bg-white text-[#285f93]"
                          : "border-[#13212c]/10 bg-[#fbf8f2] text-[#61717d]"
                      }`}>
                        {isSelected ? t("clients.editingThisClient", "Editing") : t("common.select", "Select")}
                      </span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <StatusPill label={row.readiness.label} tone={row.readiness.tone} />
                      <span className="rounded-full border border-[#13212c]/10 bg-[#fbf8f2] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#61717d]">
                        {row.rate_card ? t("billing.rateReady", "Rate ready") : t("billing.noRate", "No rate")}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>

          <div className="hidden rounded-xl border border-[#13212c]/8 bg-[#fbf8f2] p-4 md:block">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-[#f7bf45]/28 bg-[#f7bf45]/12 p-2.5 text-[#d19009]">
                <Plus size={18} />
              </div>
              <div>
                <p className="text-sm font-semibold text-[#13212c]">{t("clients.addClient", "Add client")}</p>
                <p className="text-sm leading-6 text-[#61717d]">
                  {t("clients.addClientBody", "Create the customer account here so inbound, outbound, billing, and portal visibility all point to the same business record.")}
                </p>
              </div>
            </div>

            <div className="mt-4 space-y-4">
              <Field label={t("common.client", "Client")}>
                <input
                  type="text"
                  value={newClientDraft.name}
                  onChange={(e) => setNewClientDraft((current) => ({ ...current, name: e.target.value }))}
                  placeholder={t("clients.namePlaceholder", "Danube Foods Kft.")}
                  className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]"
                />
              </Field>

              <Field label={t("common.code", "Code")}>
                <input
                  type="text"
                  value={newClientDraft.code}
                  onChange={(e) => setNewClientDraft((current) => ({ ...current, code: e.target.value.toUpperCase() }))}
                  placeholder={t("clients.codePlaceholder", "DANUBE")}
                  className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]"
                />
              </Field>

              <Field label={t("common.contact", "Contact")}>
                <input
                  type="email"
                  value={newClientDraft.contact_email}
                  onChange={(e) => setNewClientDraft((current) => ({ ...current, contact_email: e.target.value }))}
                  placeholder={t("clients.emailPlaceholder", "ops@client.example")}
                  className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]"
                />
              </Field>

              <Field label={t("clients.phone", "Phone")}>
                <input
                  type="text"
                  value={newClientDraft.contact_phone}
                  onChange={(e) => setNewClientDraft((current) => ({ ...current, contact_phone: e.target.value }))}
                  placeholder={t("clients.phonePlaceholder", "+36 1 555 0100")}
                  className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]"
                />
              </Field>

              <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-1">
                <label className="flex items-center gap-3 rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]">
                  <input
                    type="checkbox"
                    checked={newClientDraft.billing_enabled}
                    onChange={(e) => setNewClientDraft((current) => ({ ...current, billing_enabled: e.target.checked }))}
                  />
                  {t("clients.enableBilling", "Enable billing")}
                </label>
                <label className="flex items-center gap-3 rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]">
                  <input
                    type="checkbox"
                    checked={newClientDraft.portal_access}
                    onChange={(e) => setNewClientDraft((current) => ({ ...current, portal_access: e.target.checked }))}
                  />
                  {t("clients.enablePortal", "Enable portal access")}
                </label>
              </div>

              <button
                type="button"
                disabled={createClient.isPending || !newClientDraft.name || !newClientDraft.code}
                onClick={() => createClient.mutate()}
                className="inline-flex min-h-[44px] w-full items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#1d3040] disabled:cursor-not-allowed disabled:bg-[#a9b2b8]"
              >
                {createClient.isPending ? t("clients.creating", "Creating client...") : t("clients.create", "Create client")}
                <ArrowRight size={15} />
              </button>
            </div>
          </div>
        </div>

        <details className="mt-4 rounded-[1.1rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-3 md:hidden">
          <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
            {t("clients.mobileAddClientSummary", "Add client is desktop-preferred")}
          </summary>
          <p className="mt-2 text-sm leading-6 text-[#61717d]">
            {t("clients.mobileAddClientBody", "Use phone to select one client and check readiness. Create client accounts, billing profile, rate cards, and portal setup on iPad or desktop.")}
          </p>
        </details>
      </section>

      <section id="client-master-workbench" className="scroll-mt-6 rounded-[1.35rem] border border-[#13212c]/10 bg-white/80 p-4 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur md:rounded-[2rem] md:p-6">
        <SectionIntro
          eyebrow={t("clients.maintenanceEyebrow", "Selected client")}
          title={t("clients.maintenanceTitle", "Maintain the selected client in focused tabs.")}
          detail={t("clients.maintenanceDetail", "Use Profile for the account record, Billing profile for invoice identity, Rate cards for commercial rules, Portal access for visibility, and Activity for available record history.")}
          action={<SelectedClientBadge client={selectedClient} t={t} />}
        />

        {selectedClient ? (
          <>
            <ClientReadinessStrip readiness={selectedClientReadiness} t={t} />
            <ClientDetailTabs activeTab={clientDetailTab} onChange={setClientDetailTab} t={t} />

            <div className="mt-5">
              <div className={clientDetailTab === "profile" ? "space-y-5" : "hidden"}>
            <div className="rounded-xl border border-[#13212c]/8 bg-[#fbf8f2] p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#71808c]">
                {t("clients.accountProfileTitle", "Account profile")}
              </p>
              <p className="mt-2 text-sm leading-6 text-[#61717d]">
                {t("clients.accountProfileBody", "Keep the customer name, code, contact, billing switch, and portal access in the same master record.")}
              </p>
              <div className="mt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-[minmax(0,1.2fr)_180px]">
                  <Field label={t("common.client", "Client")}>
                    <input
                      type="text"
                      value={clientAccountDraft.name}
                      onChange={(e) => setClientAccountDraft((current) => ({ ...current, name: e.target.value }))}
                      className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]"
                    />
                  </Field>
                  <Field label={t("common.code", "Code")}>
                    <input
                      type="text"
                      value={clientAccountDraft.code}
                      onChange={(e) => setClientAccountDraft((current) => ({ ...current, code: e.target.value.toUpperCase() }))}
                      className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]"
                    />
                  </Field>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <Field label={t("common.contact", "Contact")}>
                    <input
                      type="email"
                      value={clientAccountDraft.contact_email}
                      onChange={(e) => setClientAccountDraft((current) => ({ ...current, contact_email: e.target.value }))}
                      className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]"
                    />
                  </Field>
                  <Field label={t("clients.phone", "Phone")}>
                    <input
                      type="text"
                      value={clientAccountDraft.contact_phone}
                      onChange={(e) => setClientAccountDraft((current) => ({ ...current, contact_phone: e.target.value }))}
                      className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]"
                    />
                  </Field>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <label className="flex items-center gap-3 rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]">
                    <input
                      type="checkbox"
                      checked={clientAccountDraft.billing_enabled}
                      onChange={(e) => setClientAccountDraft((current) => ({ ...current, billing_enabled: e.target.checked }))}
                    />
                    {t("clients.enableBilling", "Enable billing")}
                  </label>
                  <label className="flex items-center gap-3 rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]">
                    <input
                      type="checkbox"
                      checked={clientAccountDraft.portal_access}
                      onChange={(e) => setClientAccountDraft((current) => ({ ...current, portal_access: e.target.checked }))}
                    />
                    {t("clients.enablePortal", "Enable portal access")}
                  </label>
                </div>
                <button
                  type="button"
                  onClick={() => saveClientAccount.mutate()}
                  disabled={!selectedClientId || !clientAccountDraft.name || !clientAccountDraft.code || saveClientAccount.isPending}
                  className="inline-flex items-center justify-center rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f5efe5] transition hover:bg-[#1d3140] disabled:cursor-not-allowed disabled:bg-[#a9b2b8]"
                >
                  {saveClientAccount.isPending ? t("clients.savingAccount", "Saving account...") : t("clients.saveAccount", "Save account profile")}
                </button>
              </div>
            </div>
          </div>

          <div className={clientDetailTab === "billing" ? "space-y-5" : "hidden"}>
            <div className="rounded-xl border border-[#13212c]/8 bg-[#fbf8f2] p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#71808c]">
                {t("billing.billToProfileTitle", "Bill-to profile")}
              </p>
              <div className="mt-4 space-y-4">
              <Field label={t("billing.billToLegalName", "Bill-to legal name")}>
                <select
                  value={billToLegalNameMode}
                  onChange={(e) => {
                    const nextMode = e.target.value === "custom" ? "custom" : "client";
                    setBillToLegalNameMode(nextMode);
                    if (nextMode === "client") {
                      setClientBillingDraft((current) => ({ ...current, legal_name: selectedClient?.name || "" }));
                    }
                  }}
                  className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]"
                >
                  <option value="client">
                    {t("billing.useClientLegalName", "Use client name: {name}", { name: selectedClient?.name || "—" })}
                  </option>
                  <option value="custom">{t("billing.customBillToLegalName", "Custom legal name")}</option>
                </select>
              </Field>
              {billToLegalNameMode === "custom" ? (
                <Field label={t("billing.customBillToLegalName", "Custom legal name")}>
                  <input
                    type="text"
                    value={clientBillingDraft.legal_name}
                    onChange={(e) => setClientBillingDraft((current) => ({ ...current, legal_name: e.target.value }))}
                    className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>
              ) : null}
              <div className="grid gap-4 md:grid-cols-2 xl:col-span-2">
                <Field label={t("billing.taxId", "Tax ID")}>
                  <input type="text" value={clientBillingDraft.tax_id} onChange={(e) => setClientBillingDraft((current) => ({ ...current, tax_id: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
                <Field label={t("billing.vatId", "VAT ID")}>
                  <input type="text" value={clientBillingDraft.vat_id} onChange={(e) => setClientBillingDraft((current) => ({ ...current, vat_id: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
              </div>
              <Field label={t("billing.billingEmail", "Billing email")}>
                <input type="email" value={clientBillingDraft.billing_email} onChange={(e) => setClientBillingDraft((current) => ({ ...current, billing_email: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
              </Field>
              <Field label={t("billing.taxRegion", "Tax region")}>
                <select
                  value={clientBillingDraft.tax_region}
                  onChange={(e) => {
                    const region = e.target.value ? normalizeTaxRegion(e.target.value) : "";
                    setClientBillingDraft((current) => ({
                      ...current,
                      tax_region: region,
                      tax_label: current.tax_label === "" || current.tax_label === "VAT" || current.tax_label === "Sales Tax"
                        ? (region ? taxLabelForRegion(region) : "")
                        : current.tax_label,
                    }));
                  }}
                  className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]"
                >
                  <option value="">{t("billing.inheritTaxRegion", "Inherit company tax region")}</option>
                  <option value="eu">{t("billing.taxRegionEu", "European Union (VAT)")}</option>
                  <option value="us">{t("billing.taxRegionUs", "United States (Sales Tax)")}</option>
                </select>
              </Field>
              <div className="grid gap-4 md:grid-cols-2 xl:col-span-2">
                <Field label={t("billing.taxRatePct", "Tax rate (%)")}>
                  <input type="number" min="0" step="0.01" value={clientBillingDraft.tax_rate_pct} onChange={(e) => setClientBillingDraft((current) => ({ ...current, tax_rate_pct: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" placeholder={t("billing.optionalOverride", "Optional override")} />
                </Field>
                <Field label={t("billing.taxLabel", "Tax label")}>
                  <input type="text" value={clientBillingDraft.tax_label} onChange={(e) => setClientBillingDraft((current) => ({ ...current, tax_label: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" placeholder={t("billing.optionalOverride", "Optional override")} />
                </Field>
              </div>
              <Field label={t("billing.paymentTermsLabel", "Payment terms label")}>
                <input type="text" value={clientBillingDraft.payment_terms_label} onChange={(e) => setClientBillingDraft((current) => ({ ...current, payment_terms_label: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
              </Field>
              <div className="grid gap-4 md:grid-cols-2 xl:col-span-2">
                <Field label={t("billing.street", "Street")}>
                  <input type="text" value={clientBillingDraft.street} onChange={(e) => setClientBillingDraft((current) => ({ ...current, street: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
                <Field label={t("billing.city", "City")}>
                  <input type="text" value={clientBillingDraft.city} onChange={(e) => setClientBillingDraft((current) => ({ ...current, city: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <Field label={t("billing.state", "State / region")}>
                  <input type="text" value={clientBillingDraft.state} onChange={(e) => setClientBillingDraft((current) => ({ ...current, state: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
                <Field label={t("billing.zip", "Postal code")}>
                  <input type="text" value={clientBillingDraft.zip} onChange={(e) => setClientBillingDraft((current) => ({ ...current, zip: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
                <Field label={t("billing.country", "Country")}>
                  <input type="text" value={clientBillingDraft.country} onChange={(e) => setClientBillingDraft((current) => ({ ...current, country: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
              </div>
              <Field label={t("billing.taxExemptionNote", "Tax exemption note")}>
                <textarea value={clientBillingDraft.tax_exemption_note} onChange={(e) => setClientBillingDraft((current) => ({ ...current, tax_exemption_note: e.target.value }))} rows={2} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" placeholder={t("billing.optionalOverride", "Optional override")} />
              </Field>
              <Field label={t("billing.reverseChargeNote", "Reverse-charge note")}>
                <textarea value={clientBillingDraft.reverse_charge_note} onChange={(e) => setClientBillingDraft((current) => ({ ...current, reverse_charge_note: e.target.value }))} rows={2} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" placeholder={t("billing.optionalOverride", "Optional override")} />
              </Field>
              <button type="button" onClick={() => saveClientBillingProfile.mutate()} disabled={!selectedClientId || saveClientBillingProfile.isPending} className="inline-flex items-center justify-center rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f5efe5] transition hover:bg-[#1d3140] disabled:cursor-not-allowed disabled:bg-[#a9b2b8]">
                {saveClientBillingProfile.isPending ? t("billing.savingBillToProfile", "Saving bill-to profile...") : t("billing.saveBillToProfile", "Save bill-to profile")}
              </button>
              </div>
            </div>
          </div>

          <div className={clientDetailTab === "rate_cards" ? "space-y-5" : "hidden"}>
            <div className="rounded-xl border border-[#13212c]/8 bg-[#fbf8f2] p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#71808c]">
                {t("common.rateCard", "Rate Card")}
              </p>
              <div className="mt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-[minmax(0,1.3fr)_220px]">
                  <Field label={t("common.rateCard", "Rate Card")}>
                    <select
                      value={selectedRateCardVersionId}
                      onChange={(e) => {
                        const nextValue = e.target.value;
                        setSelectedRateCardVersionId(nextValue);
                        const selectedCard = selectedClientRateCards.find((card: any) => card.id === nextValue) || null;
                        const nextDraft = buildRateCardDraft(selectedCard || latestRateCard, selectedClient);
                        setRateCardDraft(
                          nextValue === NEW_RATE_CARD_VALUE
                            ? { ...nextDraft, effective_from: defaultPeriodStart() }
                            : nextDraft,
                        );
                      }}
                      className="w-full rounded-xl border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/25"
                    >
                      {selectedClientRateCards.map((card: any) => (
                        <option key={card.id} value={card.id}>
                          {card.name} · {card.effective_from || t("common.open", "Open")}
                        </option>
                      ))}
                      <option value={NEW_RATE_CARD_VALUE}>{t("billing.newRateCardVersion", "New rate card version")}</option>
                    </select>
                  </Field>

                  <Field label={t("billing.rateCardEffectiveFrom", "Effective from")}>
                    <input
                      type="date"
                      value={rateCardDraft.effective_from}
                      onChange={(e) => setRateCardDraft((current) => ({ ...current, effective_from: e.target.value }))}
                      className="w-full rounded-xl border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/25"
                    />
                  </Field>
                </div>

                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  <RateNumberField label={t("billing.ruleStorage", "Storage / pallet / day")} value={rateCardDraft.storage_per_pallet_day} onChange={(value) => setRateCardDraft((current) => ({ ...current, storage_per_pallet_day: value }))} step="0.05" />
                  <RateNumberField label={t("billing.ruleReceiving", "Receiving / unit")} value={rateCardDraft.receiving_per_unit} onChange={(value) => setRateCardDraft((current) => ({ ...current, receiving_per_unit: value }))} step="0.01" />
                  <RateNumberField label={t("billing.rulePickOrder", "Pick / order")} value={rateCardDraft.pick_per_order} onChange={(value) => setRateCardDraft((current) => ({ ...current, pick_per_order: value }))} step="0.05" />
                  <RateNumberField label={t("billing.rulePickLine", "Pick / line")} value={rateCardDraft.pick_per_line} onChange={(value) => setRateCardDraft((current) => ({ ...current, pick_per_line: value }))} step="0.01" />
                  <RateNumberField label={t("billing.ruleShipping", "Shipping handling / order")} value={rateCardDraft.shipping_handling_per_order} onChange={(value) => setRateCardDraft((current) => ({ ...current, shipping_handling_per_order: value }))} step="0.05" />
                  <RateNumberField label={t("billing.ruleMinimum", "Minimum monthly")} value={rateCardDraft.minimum_monthly} onChange={(value) => setRateCardDraft((current) => ({ ...current, minimum_monthly: value }))} step="1" />
                </div>

                <button
                  type="button"
                  onClick={() => createRateCard.mutate()}
                  disabled={!selectedClientId || !rateCardDraft.name || !rateCardDraft.effective_from || createRateCard.isPending}
                  className="inline-flex items-center justify-center rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f5efe5] transition hover:bg-[#1d3140] disabled:cursor-not-allowed disabled:bg-[#a9b2b8]"
                >
                  {createRateCard.isPending
                    ? t("billing.rateCardSaving", "Saving rate card...")
                    : latestRateCard
                      ? t("billing.rateCardCreateNewVersion", "Update rate from new effective date")
                      : t("billing.rateCardCreate", "Create rate card")}
                </button>
              </div>
            </div>

            <div className="rounded-xl border border-[#13212c]/8 bg-white px-4 py-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#71808c]">
                {t("billing.currentRateCard", "Latest configured rate card")}
              </p>
              <p className="mt-2 text-sm font-semibold text-[#13212c]">
                {latestRateCard ? latestRateCard.name : t("billing.noRateCard", "No active rate card configured yet")}
              </p>
              <div className="mt-3 grid gap-2">
                <InfoLine label={t("billing.rateCardEffectiveFrom", "Effective from")} value={latestRateCard?.effective_from || "—"} />
                <InfoLine label={t("common.rules", "Rules")} value={latestRateCard ? t("billing.rulesCount", "{count} rules", { count: String(getRateCardRuleCount(latestRateCard)) }) : "—"} />
                <InfoLine label={t("common.client", "Client")} value={selectedClient ? `${selectedClient.name} · ${selectedClient.code}` : "—"} />
              </div>
              <p className="mt-4 text-sm leading-6 text-[#61717d]">
                {t("billing.rateCardVersionHint", "Updating the rate creates a new version from the next effective date. Past billing periods keep using the old rate card.")}
              </p>
            </div>
          </div>

              {clientDetailTab === "portal" ? (
                <ClientPortalPanel client={selectedClient} readiness={selectedClientReadiness} t={t} />
              ) : null}

              {clientDetailTab === "activity" ? (
                <ClientActivityPanel client={selectedClient} latestRateCard={latestRateCard} t={t} />
              ) : null}
            </div>
          </>
        ) : (
          <NoClientSelectedPanel t={t} />
        )}
      </section>

      <section id="billing-company-profile" className="rounded-[1.35rem] border border-[#13212c]/10 bg-white/80 p-4 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur md:rounded-[2rem] md:p-6">
        <SectionIntro
          eyebrow={t("billing.companyProfileEyebrow", "Company billing profile")}
          title={t("billing.companyProfileTitle", "Maintain your own invoice identity separately.")}
          detail={t("billing.companyProfileBody", "These issuer, tax, payment, bank, and invoice footer details belong to your company. They apply across clients and stay outside the selected customer profile.")}
          action={(
            <button
              type="button"
              onClick={() => setShowCompanyProfile((current) => !current)}
              className="inline-flex min-h-[44px] items-center justify-center rounded-full border border-[#13212c]/10 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c] md:hidden"
            >
              {showCompanyProfile ? t("common.close", "Close") : t("common.edit", "Edit")}
            </button>
          )}
        />

        <div className={`${showCompanyProfile ? "block" : "hidden"} mt-5 md:block`}>
          <div className="rounded-xl border border-[#13212c]/8 bg-[#fbf8f2] p-4">
            <p className="text-[11px] uppercase tracking-[0.18em] text-[#71808c]">
              {t("billing.issuerProfileTitle", "Issuer profile")}
            </p>
            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              <Field label={t("billing.issuerLegalName", "Legal entity name")}>
                <input type="text" value={tenantBillingDraft.legal_name} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, legal_name: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
              </Field>
              <div className="grid gap-4 md:grid-cols-2 xl:col-span-2">
                <Field label={t("billing.taxId", "Tax ID")}>
                  <input type="text" value={tenantBillingDraft.tax_id} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, tax_id: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
                <Field label={t("billing.vatId", "VAT ID")}>
                  <input type="text" value={tenantBillingDraft.vat_id} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, vat_id: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
              </div>
              <Field label={t("billing.billingEmail", "Billing email")}>
                <input type="email" value={tenantBillingDraft.billing_email} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, billing_email: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
              </Field>
              <Field label={t("billing.taxRegion", "Tax region")}>
                <select
                  value={tenantBillingDraft.tax_region}
                  onChange={(e) => {
                    const region = normalizeTaxRegion(e.target.value);
                    setTenantBillingDraft((current) => ({
                      ...current,
                      tax_region: region,
                      tax_label: current.tax_label === "" || current.tax_label === "VAT" || current.tax_label === "Sales Tax" ? taxLabelForRegion(region) : current.tax_label,
                    }));
                  }}
                  className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]"
                >
                  <option value="eu">{t("billing.taxRegionEu", "European Union (VAT)")}</option>
                  <option value="us">{t("billing.taxRegionUs", "United States (Sales Tax)")}</option>
                </select>
              </Field>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label={t("billing.taxRatePct", "Tax rate (%)")}>
                  <input type="number" min="0" step="0.01" value={tenantBillingDraft.tax_rate_pct} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, tax_rate_pct: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
                <Field label={t("billing.taxLabel", "Tax label")}>
                  <input type="text" value={tenantBillingDraft.tax_label} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, tax_label: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label={t("billing.paymentTermsDays", "Payment terms (days)")}>
                  <input type="number" min="0" step="1" value={tenantBillingDraft.payment_terms_days} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, payment_terms_days: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
                <Field label={t("billing.currencyCode", "Currency")}>
                  <input type="text" value={tenantBillingDraft.currency} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, currency: e.target.value.toUpperCase() }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
              </div>
              <Field label={t("billing.paymentTermsLabel", "Payment terms label")}>
                <input type="text" value={tenantBillingDraft.payment_terms_label} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, payment_terms_label: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
              </Field>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label={t("billing.bankName", "Bank name")}>
                  <input type="text" value={tenantBillingDraft.bank_name} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, bank_name: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
                <Field label={t("billing.bankAccount", "Bank account")}>
                  <input type="text" value={tenantBillingDraft.bank_account} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, bank_account: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label={t("billing.iban", "IBAN")}>
                  <input type="text" value={tenantBillingDraft.iban} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, iban: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
                <Field label={t("billing.swift", "SWIFT")}>
                  <input type="text" value={tenantBillingDraft.swift} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, swift: e.target.value }))} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
              </div>
              <div className="xl:col-span-2">
                <Field label={t("billing.invoiceNotes", "Invoice notes")}>
                  <textarea value={tenantBillingDraft.invoice_notes} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, invoice_notes: e.target.value }))} rows={3} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
              </div>
              <div className="xl:col-span-2">
                <Field label={t("billing.taxExemptionNote", "Tax exemption note")}>
                  <textarea value={tenantBillingDraft.tax_exemption_note} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, tax_exemption_note: e.target.value }))} rows={2} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
              </div>
              <div className="xl:col-span-2">
                <Field label={t("billing.reverseChargeNote", "Reverse-charge note")}>
                  <textarea value={tenantBillingDraft.reverse_charge_note} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, reverse_charge_note: e.target.value }))} rows={2} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
              </div>
              <div className="xl:col-span-2">
                <Field label={t("billing.invoiceFooterLegal", "Legal footer")}>
                  <textarea value={tenantBillingDraft.invoice_footer_legal} onChange={(e) => setTenantBillingDraft((current) => ({ ...current, invoice_footer_legal: e.target.value }))} rows={2} className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]" />
                </Field>
              </div>
              <div className="xl:col-span-2">
                <button type="button" onClick={() => saveTenantBillingProfile.mutate()} disabled={saveTenantBillingProfile.isPending} className="inline-flex items-center justify-center rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f5efe5] transition hover:bg-[#1d3140] disabled:cursor-not-allowed disabled:bg-[#a9b2b8]">
                  {saveTenantBillingProfile.isPending ? t("billing.savingIssuerProfile", "Saving issuer profile...") : t("billing.saveIssuerProfile", "Save issuer profile")}
                </button>
              </div>
            </div>
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

function ClientMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-[1.4rem] border border-[#13212c]/10 bg-white/86 px-5 py-4 shadow-[0_16px_40px_rgba(19,33,44,0.06)]">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[#71808c]">{label}</p>
      <p className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-[#13212c]">{value}</p>
    </div>
  );
}

function SectionIntro({
  eyebrow,
  title,
  detail,
  action,
}: {
  eyebrow: string;
  title: string;
  detail?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
      <div className="max-w-3xl">
        <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{eyebrow}</p>
        <h2 className="mt-2 text-lg font-semibold tracking-[-0.02em] text-[#13212c] md:text-xl md:tracking-[-0.03em]">{title}</h2>
        {detail ? <p className="mt-2 hidden text-sm leading-7 text-[#61717d] md:block">{detail}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

function StatusPill({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "success" | "warning";
}) {
  const toneClass = tone === "success"
    ? "border-[#3da76a]/20 bg-[#eaf8f0] text-[#256444]"
    : tone === "warning"
      ? "border-[#e1b24a]/25 bg-[#fff7df] text-[#7d5b12]"
      : "border-[#13212c]/10 bg-[#f7f4ee] text-[#61717d]";
  return (
    <span className={`inline-flex items-center rounded-full border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] ${toneClass}`}>
      {label}
    </span>
  );
}

function SelectedClientBadge({
  client,
  t,
}: {
  client: any;
  t: TranslationFn;
}) {
  const label = client
    ? client.code ? `${client.name} · ${client.code}` : client.name
    : t("billingSettings.noClientSelected", "No client selected");
  const caption = client
    ? t("billingSettings.editingClient", "Editing client")
    : t("clients.selectionRequired", "Selection required");
  return (
    <div className="rounded-xl border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-3 text-left">
      <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#71808c]">
        {caption}
      </p>
      <p className="mt-1 text-sm font-semibold text-[#13212c]">{label}</p>
    </div>
  );
}

function NoClientSelectedPanel({ t }: { t: TranslationFn }) {
  return (
    <div className="mt-5 rounded-xl border border-dashed border-[#13212c]/18 bg-[#fbf8f2] px-5 py-8 text-center">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[#71808c]">
        {t("clients.noClientSelected", "No client selected")}
      </p>
      <p className="mx-auto mt-3 max-w-2xl text-sm leading-7 text-[#61717d]">
        {t("clients.lockedUntilSelected", "Choose Open details in the client directory before editing account, billing, rate-card, portal, or activity details.")}
      </p>
      <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-[#8b6a1d]">
        {t("clients.editingLocked", "Editing is locked until a client is selected")}
      </p>
    </div>
  );
}

function ClientReadinessStrip({
  readiness,
  t,
}: {
  readiness: ClientReadiness;
  t: TranslationFn;
}) {
  return (
    <div className="mt-5 rounded-xl border border-[#13212c]/8 bg-[#fbf8f2] p-4">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[#71808c]">
            {t("clients.readinessTitle", "Client readiness")}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusPill label={readiness.label} tone={readiness.tone} />
            <span className="text-sm leading-6 text-[#61717d]">{readiness.detail}</span>
          </div>
        </div>
        <div className="min-w-0 xl:max-w-xl">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#71808c]">
            {readiness.missing.length > 0
              ? t("clients.readinessNextActions", "Next actions")
              : t("clients.readinessNoGaps", "No setup gaps")}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {(readiness.missing.length > 0 ? readiness.missing : [t("clients.readyToOperate", "Ready for operations and billing follow-up.")]).map((item) => (
              <span key={item} className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-xs font-semibold text-[#43515c]">
                {item}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function ClientDetailTabs({
  activeTab,
  onChange,
  t,
}: {
  activeTab: ClientDetailTab;
  onChange: (tab: ClientDetailTab) => void;
  t: TranslationFn;
}) {
  const tabs: { key: ClientDetailTab; label: string }[] = [
    { key: "profile", label: t("clients.tabProfile", "Profile") },
    { key: "billing", label: t("clients.tabBilling", "Billing profile") },
    { key: "rate_cards", label: t("clients.tabRateCards", "Rate cards") },
    { key: "portal", label: t("clients.tabPortal", "Portal access") },
    { key: "activity", label: t("clients.tabActivity", "Activity") },
  ];

  return (
    <div className="mt-4 overflow-x-auto rounded-full border border-[#13212c]/10 bg-white/78 p-1">
      <div className="flex min-w-max gap-1">
        {tabs.map((tab) => {
          const active = tab.key === activeTab;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => onChange(tab.key)}
              className={`min-h-[44px] rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] transition ${
                active
                  ? "bg-[#13212c] text-[#f5efe5]"
                  : "text-[#5f6f7c] hover:bg-[#fbf8f2] hover:text-[#13212c]"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ClientPortalPanel({
  client,
  readiness,
  t,
}: {
  client: any;
  readiness: ClientReadiness;
  t: TranslationFn;
}) {
  const portalEnabled = Boolean(client?.portal_access);
  const contactReady = Boolean(client?.contact_email);
  return (
    <div className="rounded-xl border border-[#13212c]/8 bg-[#fbf8f2] p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <p className="text-[11px] uppercase tracking-[0.18em] text-[#71808c]">
            {t("clients.portalPanelTitle", "Portal access")}
          </p>
          <p className="mt-2 text-sm leading-7 text-[#61717d]">
            {t("clients.portalPanelBody", "Use this tab to confirm whether the selected client should see its own inventory, orders, and invoices through the portal. Portal users are still managed from the user management page.")}
          </p>
        </div>
        <StatusPill
          label={portalEnabled ? t("clients.portalEnabled", "Portal enabled") : t("clients.portalDisabled", "Portal off")}
          tone={portalEnabled ? "success" : "neutral"}
        />
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-3">
        <InfoLine label={t("common.client", "Client")} value={client ? client.name : "—"} />
        <InfoLine label={t("common.contact", "Contact")} value={client?.contact_email || t("common.noEmail", "No email")} />
        <InfoLine
          label={t("clients.portalReadiness", "Portal readiness")}
          value={portalEnabled && contactReady ? t("clients.portalReady", "Ready") : t("clients.portalNeedsSetup", "Needs setup")}
        />
      </div>

      {readiness.missing.length > 0 ? (
        <div className="mt-4 rounded-xl border border-[#e1b24a]/20 bg-[#fff7df] px-4 py-3 text-sm leading-6 text-[#715015]">
          {t("clients.portalGapHint", "Fix the setup gaps above before treating portal access as customer-ready.")}
        </div>
      ) : null}

      <Link
        to="/users"
        className="mt-4 inline-flex items-center justify-center rounded-full border border-[#13212c]/10 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#fbf8f2]"
      >
        {t("clients.openUserManagement", "Open user management")}
      </Link>
    </div>
  );
}

function ClientActivityPanel({
  client,
  latestRateCard,
  t,
}: {
  client: any;
  latestRateCard: any | null;
  t: TranslationFn;
}) {
  return (
    <div className="rounded-xl border border-[#13212c]/8 bg-[#fbf8f2] p-4">
      <p className="text-[11px] uppercase tracking-[0.18em] text-[#71808c]">
        {t("clients.activityTitle", "Activity")}
      </p>
      <p className="mt-2 text-sm leading-7 text-[#61717d]">
        {t("clients.activityBody", "A full audit trail is not connected yet. This panel shows the timestamps and setup state available on the current records, without implying portal login or approval history.")}
      </p>
      <div className="mt-5 grid gap-3 md:grid-cols-3">
        <InfoLine label={t("clients.clientUpdated", "Client updated")} value={formatRecordDate(client?.updated_at || client?.created_at)} />
        <InfoLine label={t("billing.currentRateCard", "Latest configured rate card")} value={latestRateCard?.name || t("billing.noRateCard", "No active rate card configured yet")} />
        <InfoLine label={t("billing.rateCardEffectiveFrom", "Effective from")} value={latestRateCard?.effective_from || "—"} />
      </div>
    </div>
  );
}

function InfoLine({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border border-[#13212c]/8 bg-white px-3 py-2">
      <span className="text-[11px] uppercase tracking-[0.16em] text-[#71808c]">{label}</span>
      <span className="text-right text-sm font-semibold text-[#13212c]">{value}</span>
    </div>
  );
}

function RateNumberField({
  label,
  value,
  onChange,
  step,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  step: string;
}) {
  return (
    <Field label={label}>
      <input
        type="number"
        inputMode="decimal"
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-[1.1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c]"
      />
    </Field>
  );
}

function defaultPeriodStart() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
}

function getRateCardRuleCount(rateCard: any) {
  return Object.keys(rateCard?.rules || {}).length;
}

function getClientReadiness(client: any, latestRateCard: any | null, t: TranslationFn): ClientReadiness {
  if (!client) {
    return {
      label: t("clients.noClientSelected", "No client selected"),
      detail: t("clients.noClientSelectedDetail", "Select a client from the directory before editing setup details."),
      missing: [t("clients.selectClientAction", "Select a client")],
      tone: "neutral",
      sortKey: "0-no-client",
    };
  }

  const billingProfile = extractClientBillingProfile(client);
  const missing: string[] = [];
  const hasName = Boolean(String(client.name || "").trim());
  const hasCode = Boolean(String(client.code || "").trim());
  const hasBillingEmail = Boolean(String(billingProfile.billing_email || client.contact_email || "").trim());
  const hasLegalName = Boolean(String(billingProfile.legal_name || client.name || "").trim());

  if (!hasName || !hasCode) missing.push(t("clients.missingAccountBasics", "Complete account name and code"));
  if (client.billing_enabled) {
    if (!hasLegalName || !hasBillingEmail) missing.push(t("clients.missingBillingProfile", "Complete bill-to profile"));
    if (!latestRateCard) missing.push(t("clients.missingRateCard", "Create a rate card"));
  }
  if (client.portal_access && !client.contact_email) {
    missing.push(t("clients.missingPortalContact", "Add portal contact email"));
  }

  if (missing.length === 0) {
    return {
      label: t("clients.readyStatus", "Ready"),
      detail: t("clients.readyDetail", "Core profile, billing setup, and portal prerequisites are in place for this client."),
      missing: [],
      tone: "success",
      sortKey: "3-ready",
    };
  }

  const onlyRateCardMissing = missing.length === 1 && !latestRateCard && client.billing_enabled;
  return {
    label: onlyRateCardMissing ? t("clients.needsRateCardStatus", "Needs rate card") : t("clients.needsSetupStatus", "Needs setup"),
    detail: t("clients.needsSetupDetail", "This client can stay in the directory, but the missing items should be finished before relying on billing or portal readiness."),
    missing,
    tone: "warning",
    sortKey: onlyRateCardMissing ? "1-needs-rate-card" : "2-needs-setup",
  };
}

function formatRecordDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function buildRateCardDraft(rateCard: any | null, client: any | null) {
  const rules = rateCard?.rules || {};
  return {
    name: rateCard?.name || `${client?.name || "Client"} Rate Card`,
    effective_from: rateCard?.effective_from || defaultPeriodStart(),
    storage_per_pallet_day: String(rules.storage_per_pallet_day ?? 0.85),
    receiving_per_unit: String(rules.receiving_per_unit ?? 0.25),
    pick_per_order: String(rules.pick_per_order ?? 2.0),
    pick_per_line: String(rules.pick_per_line ?? 0.5),
    shipping_handling_per_order: String(rules.shipping_handling_per_order ?? 1.5),
    minimum_monthly: String(rules.minimum_monthly ?? 200),
  };
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

function taxLabelForRegion(region: string) {
  return normalizeTaxRegion(region) === "us" ? "Sales Tax" : "VAT";
}

function normalizeClientName(value?: string | null) {
  return (value || "").trim().replace(/\s+/g, " ").toLowerCase();
}
