import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, KeyRound } from "lucide-react";
import { fetchAgentSettings, updateAgentSettings } from "../../shared/api/agent";
import { queryKeys } from "../../shared/api/queryKeys";
import { getApiErrorMessage } from "../../shared/api/error-message";
import { useI18n } from "../../shared/i18n";
import PasswordInput from "../../shared/components/PasswordInput";

type ToolItem = { key: string; risk: string };

type AgentSettings = {
  enabled: boolean;
  provider_type: string | null;
  provider_label: string | null;
  base_url: string | null;
  model_name: string | null;
  region: string | null;
  has_api_key: boolean;
  allow_data_logging: boolean;
  allow_model_training: boolean;
  requires_human_confirmation_for_writes: boolean;
  allowed_tools: string[];
  tool_catalog: ToolItem[];
  validation_status?: string | null;
  validation_message?: string | null;
  validation_checked_at?: string | null;
};

const PROVIDER_OPTIONS = [
  { value: "openai", labelKey: "agent.providerOpenAI", fallback: "OpenAI" },
  { value: "anthropic_claude", labelKey: "agent.providerClaude", fallback: "Claude (Anthropic)" },
  { value: "google_gemini", labelKey: "agent.providerGemini", fallback: "Gemini (Google)" },
  { value: "kimi", labelKey: "agent.providerKimi", fallback: "Kimi (Moonshot AI)" },
  { value: "minimax", labelKey: "agent.providerMiniMax", fallback: "MiniMax" },
  { value: "deepseek", labelKey: "agent.providerDeepSeek", fallback: "DeepSeek" },
  { value: "azure_openai", labelKey: "agent.providerAzureOpenAI", fallback: "Azure OpenAI" },
  { value: "aws_bedrock", labelKey: "agent.providerBedrock", fallback: "AWS Bedrock" },
  { value: "google_vertex_ai", labelKey: "agent.providerVertex", fallback: "Google Vertex AI" },
  { value: "openai_compatible", labelKey: "agent.providerCompatible", fallback: "OpenAI-compatible endpoint" },
] as const;

const MODEL_FAMILIES = [
  {
    provider: "openai",
    providerLabelKey: "agent.providerOpenAI",
    providerFallback: "OpenAI",
    models: ["gpt-5.4", "gpt-5.4-mini", "gpt-4.1"],
  },
  {
    provider: "anthropic_claude",
    providerLabelKey: "agent.providerClaude",
    providerFallback: "Claude (Anthropic)",
    models: ["claude-sonnet-4-20250514", "claude-opus-4-20250514"],
  },
  {
    provider: "google_gemini",
    providerLabelKey: "agent.providerGemini",
    providerFallback: "Gemini (Google)",
    models: ["gemini-2.5-pro", "gemini-2.5-flash"],
  },
  {
    provider: "kimi",
    providerLabelKey: "agent.providerKimi",
    providerFallback: "Kimi (Moonshot AI)",
    models: ["kimi-k2", "moonshot-v1-32k"],
  },
  {
    provider: "minimax",
    providerLabelKey: "agent.providerMiniMax",
    providerFallback: "MiniMax",
    models: ["MiniMax-M1", "abab7-chat"],
  },
  {
    provider: "deepseek",
    providerLabelKey: "agent.providerDeepSeek",
    providerFallback: "DeepSeek",
    models: ["deepseek-v4-flash", "deepseek-v4-pro"],
  },
] as const;

const PROVIDER_HELP: Record<
  string,
  {
    baseUrl?: string;
    modelExample?: string;
    regionExample?: string;
  }
> = {
  openai: {
    baseUrl: "https://api.openai.com/v1",
    modelExample: "gpt-5.4 / gpt-4.1",
  },
  anthropic_claude: {
    baseUrl: "https://api.anthropic.com",
    modelExample: "claude-sonnet-4-20250514",
  },
  google_gemini: {
    baseUrl: "https://generativelanguage.googleapis.com",
    modelExample: "gemini-2.5-pro / gemini-2.5-flash",
  },
  kimi: {
    baseUrl: "https://api.moonshot.cn/v1",
    modelExample: "moonshot-v1-32k / kimi-k2",
  },
  minimax: {
    baseUrl: "https://api.minimaxi.com/v1",
    modelExample: "MiniMax-M1 / abab7-chat",
  },
  deepseek: {
    baseUrl: "https://api.deepseek.com",
    modelExample: "deepseek-v4-flash / deepseek-v4-pro",
  },
  azure_openai: {
    baseUrl: "https://<resource>.openai.azure.com",
    modelExample: "deployment name",
    regionExample: "swedencentral / eastus2",
  },
  aws_bedrock: {
    modelExample: "anthropic.claude-3-7-sonnet / amazon.nova-pro",
    regionExample: "us-east-1 / eu-central-1",
  },
  google_vertex_ai: {
    modelExample: "gemini-2.5-pro",
    regionExample: "us-central1 / europe-west4",
  },
  openai_compatible: {
    baseUrl: "https://your-endpoint/v1",
    modelExample: "provider model name",
  },
};

const REGION_REQUIRED_PROVIDERS = new Set(["azure_openai", "aws_bedrock", "google_vertex_ai"]);
const REGION_OPTIONS: Record<string, string[]> = {
  azure_openai: ["eastus2", "swedencentral", "westeurope", "uksouth"],
  aws_bedrock: ["us-east-1", "us-west-2", "eu-central-1", "eu-west-1"],
  google_vertex_ai: ["us-central1", "europe-west4", "europe-west1", "asia-southeast1"],
};

const TOOL_GROUPS = [
  {
    key: "read",
    titleKey: "agent.toolsGroupRead",
    titleFallback: "Search and inspect",
    bodyKey: "agent.toolsGroupReadBody",
    bodyFallback: "The safest group to enable first: check status, master data, setup progress, and inventory.",
    match: (toolKey: string) =>
      [
        "inventory.search",
        "inventory.explain",
        "clients.list",
        "clients.get",
        "skus.list",
        "warehouses.list",
        "orders.inbound.list",
        "orders.outbound.list",
        "setup.progress",
        "billing.rate_cards.list",
      ].includes(toolKey),
  },
  {
    key: "import",
    titleKey: "agent.toolsGroupImport",
    titleFallback: "Import and preview",
    bodyKey: "agent.toolsGroupImportBody",
    bodyFallback: "This group previews or imports data for you. Better suited for a second phase.",
    match: (toolKey: string) =>
      [
        "receiving.inbound.preview_import",
        "receiving.inbound.import_with_mapping",
        "migration.inventory.preview",
        "migration.inventory.import",
      ].includes(toolKey),
  },
  {
    key: "write",
    titleKey: "agent.toolsGroupWrite",
    titleFallback: "Create and modify",
    bodyKey: "agent.toolsGroupWriteBody",
    bodyFallback: "These tools really change data. Enable them last, and only the ones you actually need.",
    match: (toolKey: string) =>
      [
        "clients.create",
        "skus.create",
        "receiving.inbound.create",
        "users.create",
        "users.update_permissions",
      ].includes(toolKey),
  },
] as const;

function normalizeUrl(value: string) {
  return value.trim().replace(/\/+$/, "");
}

export default function AgentSettingsPage() {
  const { t } = useI18n();
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [form, setForm] = useState({
    enabled: false,
    provider_type: "",
    provider_label: "",
    base_url: "",
    model_name: "",
    region: "",
    api_key: "",
    allow_data_logging: false,
    allow_model_training: false,
    requires_human_confirmation_for_writes: true,
    allowed_tools: [] as string[],
  });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const settingsQuery = useQuery({
    queryKey: queryKeys.agent.settings(),
    queryFn: () => fetchAgentSettings<AgentSettings>(),
  });

  useEffect(() => {
    if (!settingsQuery.data) return;
    const data = settingsQuery.data;
    setForm({
      enabled: data.enabled,
      provider_type: data.provider_type || "",
      provider_label: data.provider_label || "",
      base_url: data.base_url || "",
      model_name: data.model_name || "",
      region: data.region || "",
      api_key: "",
      allow_data_logging: data.allow_data_logging,
      allow_model_training: data.allow_model_training,
      requires_human_confirmation_for_writes: data.requires_human_confirmation_for_writes,
      allowed_tools: data.allowed_tools || [],
    });
  }, [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        ...form,
        requires_human_confirmation_for_writes: true,
        provider_type: form.provider_type || null,
        provider_label: generatedProviderLabel || null,
        base_url: form.base_url || null,
        model_name: form.model_name || null,
        region: form.region || null,
        api_key: form.api_key || null,
      };
      return updateAgentSettings<AgentSettings>(payload);
    },
    onSuccess: (data) => {
      settingsQuery.refetch();
      setForm((prev) => ({ ...prev, api_key: "", allowed_tools: data.allowed_tools }));
      setError("");
      if (data.validation_status === "valid") {
        setMessage(
          t(
            "agent.saveSuccessValidated",
            `Settings saved. ${data.provider_label || data.provider_type} / ${data.model_name} is ready to use.`,
          ),
        );
      } else if (data.validation_status === "unsupported") {
        setMessage(data.validation_message || t("agent.saveSuccess", "Agent settings saved."));
      } else {
        setMessage(t("agent.saveSuccess", "Agent settings saved."));
      }
    },
    onError: (err: any) => {
      setMessage("");
      setError(getApiErrorMessage(err, t("agent.saveError", "Could not save agent settings.")));
    },
  });

  const toolCatalog = settingsQuery.data?.tool_catalog || [];
  const providerHelp = PROVIDER_HELP[form.provider_type] || {};
  const providerOption = PROVIDER_OPTIONS.find((option) => option.value === form.provider_type);
  const combinedModelValue = (() => {
    const family = MODEL_FAMILIES.find((item) => item.provider === form.provider_type);
    if (family && family.models.some((model) => model === form.model_name)) {
      return `${form.provider_type}::${form.model_name}`;
    }
    if (form.provider_type || form.model_name) return "__custom__";
    return "";
  })();
  const selectedFamily = MODEL_FAMILIES.find((family) => family.provider === form.provider_type);
  const selectedMainstreamModel = selectedFamily?.models.find((model) => model === form.model_name);
  const expectedBaseUrl = providerHelp.baseUrl ? normalizeUrl(providerHelp.baseUrl) : "";
  const currentBaseUrl = form.base_url ? normalizeUrl(form.base_url) : "";
  const requiresRegion = REGION_REQUIRED_PROVIDERS.has(form.provider_type);
  const regionOptions = REGION_OPTIONS[form.provider_type] || [];
  const regionSelectValue = !requiresRegion
    ? ""
    : form.region && !regionOptions.includes(form.region)
      ? "__custom__"
      : form.region || "";
  const compatibilityIssues = [
    selectedMainstreamModel && !selectedFamily
      ? t("agent.compatModelProviderMismatch", "The model provider and model name do not match.")
      : null,
    selectedMainstreamModel && expectedBaseUrl && currentBaseUrl && expectedBaseUrl !== currentBaseUrl
      ? t("agent.compatEndpointMismatch", "The endpoint address does not match this model.")
      : null,
    !requiresRegion && form.region
      ? t("agent.compatRegionUnused", "This model usually does not need a service region. Consider clearing it.")
      : null,
  ].filter(Boolean) as string[];
  const canRestoreManagedDefaults =
    !!selectedFamily && !!selectedMainstreamModel;
  const generatedProviderLabel =
    form.provider_type && form.model_name
      ? `${providerOption ? t(providerOption.labelKey, providerOption.fallback) : form.provider_type} · ${form.model_name}`
      : form.provider_label || "";
  const groupedTools = TOOL_GROUPS.map((group) => ({
    ...group,
    tools: toolCatalog.filter((tool) => group.match(tool.key)),
  })).filter((group) => group.tools.length > 0);
  const currentModelLabel =
    form.model_name ||
    settingsQuery.data?.model_name ||
    t("agent.noModelConfigured", "Not selected yet");
  const assistantStatusLabel = form.enabled
    ? t("agent.statusOn", "On")
    : t("agent.statusOff", "Off");
  const validationStatusLabel =
    settingsQuery.data?.validation_status === "valid"
      ? t("agent.validationOkShort", "Passed")
      : settingsQuery.data?.validation_status === "unsupported"
        ? t("agent.validationNeedsAttentionShort", "Needs attention")
        : t("agent.validationPendingShort", "Not validated yet");

  function applyManagedDefaults() {
    setForm((prev) => ({
      ...prev,
      provider_type: selectedFamily?.provider || prev.provider_type,
      model_name: selectedMainstreamModel || prev.model_name,
      base_url: providerHelp.baseUrl || "",
      region: REGION_REQUIRED_PROVIDERS.has(selectedFamily?.provider || "") ? prev.region : "",
    }));
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <section
        className="hidden rounded-[1.5rem] border border-[#13212c]/8 bg-white p-6 shadow-[0_10px_26px_rgba(19,33,44,0.05)] md:block"
        data-testid="agent-settings-desktop-management"
      >
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-[11px] uppercase tracking-[0.24em] text-[#7e8d98]">
              {t("agent.settingsEyebrow", "AI settings")}
            </p>
            <h1 className="mt-3 text-[2rem] font-semibold tracking-[-0.04em] text-[#13212c]">
              {t("agent.settingsTitleSimple", "Connect the AI assistant first, then start in the AI console")}
            </h1>
            <p className="mt-4 text-sm leading-7 text-[#61717d]">
              {t(
                "agent.settingsBodySimple",
                "This page does three things: choose a model, store the API key, and decide which tools the AI assistant can touch. Once validated, go back to the AI console to start chatting and operating.",
              )}
            </p>
          </div>
          <div className="grid w-full gap-3 lg:max-w-md lg:grid-cols-3">
            <StatusChip
              label={t("agent.summaryAssistant", "AI assistant")}
              value={assistantStatusLabel}
            />
            <StatusChip
              label={t("agent.summaryModel", "Current model")}
              value={currentModelLabel}
            />
            <StatusChip
              label={t("agent.summaryValidation", "Setup status")}
              value={validationStatusLabel}
            />
          </div>
        </div>
      </section>

      <section
        className="rounded-[1.1rem] border border-[#13212c]/10 bg-white/84 px-4 py-3 text-sm leading-6 text-[#51606b] md:hidden"
        data-testid="agent-settings-mobile-governance"
        data-admin-mobile-contract="desktop-first"
      >
        <p className="font-semibold text-[#13212c]">
          {t("agent.mobileGovernanceTitle", "AI settings are desktop-first")}
        </p>
        <p className="mt-1">
          {t(
            "agent.mobileGovernanceBody",
            "Use this phone view to check provider health and enabled state. Rotate secrets, review the full tool catalog, and change high-risk governance on iPad or desktop.",
          )}
        </p>
        <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#425461]">
          <span className="rounded-[0.8rem] border border-[#13212c]/8 bg-[#f7f4ee] px-2 py-2 text-center">
            {assistantStatusLabel}
          </span>
          <span className="rounded-[0.8rem] border border-[#13212c]/8 bg-[#f7f4ee] px-2 py-2 text-center">
            {validationStatusLabel}
          </span>
          <span className="rounded-[0.8rem] border border-[#13212c]/8 bg-[#f7f4ee] px-2 py-2 text-center">
            {t("agent.desktopPreferred", "Desktop")}
          </span>
        </div>
      </section>

      <section className="rounded-[1.5rem] border border-[#13212c]/8 bg-white p-6 shadow-[0_10px_26px_rgba(19,33,44,0.05)]">
          <div className="grid gap-4">
            <ToggleRow
              title={t("agent.enabled", "Enable tenant agent")}
              detail={t("agent.enabledBody", "Turns the agent console on for this tenant once the first provider is configured.")}
              checked={form.enabled}
              onChange={(checked) => setForm((prev) => ({ ...prev, enabled: checked }))}
            />
            {!form.enabled ? (
              <p className="rounded-[1.1rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-3 text-sm leading-6 text-[#61717d]">
                {t(
                  "agent.preconfigHint",
                  "You can configure the model and key ahead of time. Until the AI assistant is turned on, these settings stay staged and do not take effect in the agent console.",
                )}
              </p>
            ) : null}
          </div>

          <p className="mt-4 text-sm leading-6 text-[#61717d]">
            {t(
              "agent.confirmationInline",
              "Create, modify, and import actions pause in the agent console and wait for your confirmation.",
            )}
          </p>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <Field label={t("agent.modelChoice", "AI model")}>
              <div className="space-y-2">
                <select
                  value={combinedModelValue}
                  onChange={(e) => {
                    const next = e.target.value;
                    if (!next) {
                      setForm((prev) => ({ ...prev, provider_type: "", model_name: "", base_url: "", region: "" }));
                      return;
                    }
                    if (next === "__custom__") return;
                    const [provider_type, model_name] = next.split("::");
                    const defaults = PROVIDER_HELP[provider_type] || {};
                    setForm((prev) => ({
                      ...prev,
                      provider_type,
                      model_name,
                      base_url: defaults.baseUrl || "",
                      region: REGION_REQUIRED_PROVIDERS.has(provider_type) ? prev.region : "",
                    }));
                  }}
                  className="w-full rounded-[0.9rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                >
                  <option value="">{t("agent.chooseModel", "Choose AI model")}</option>
                  {combinedModelValue === "__custom__" ? (
                    <option value="__custom__">
                      {t("agent.currentCustomModel", "Current custom model")} · {form.provider_type || "custom"} / {form.model_name || "custom"}
                    </option>
                  ) : null}
                  {MODEL_FAMILIES.map((family) => (
                    <optgroup
                      key={family.provider}
                      label={t(family.providerLabelKey, family.providerFallback)}
                    >
                      {family.models.map((model) => (
                        <option key={`${family.provider}::${model}`} value={`${family.provider}::${model}`}>
                          {model}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
                <p className="text-sm leading-6 text-[#61717d]">
                  {t(
                    "agent.modelChoiceBody",
                    "Choose from the maintained mainstream models first. If you need a private endpoint or a custom model name, open the advanced settings below.",
                  )}
                </p>
                {compatibilityIssues.length ? (
                  <div className="rounded-[0.9rem] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                    <p className="font-semibold">{t("agent.compatibilityTitle", "Some of the advanced fields do not match this model.")}</p>
                    <div className="mt-2 space-y-1">
                      {compatibilityIssues.map((issue) => (
                        <p key={issue}>• {issue}</p>
                      ))}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {canRestoreManagedDefaults ? (
                        <button
                          type="button"
                          onClick={applyManagedDefaults}
                          className="rounded-full border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-900"
                        >
                          {t("agent.fixToManagedDefaults", "Restore this model's defaults")}
                        </button>
                      ) : null}
                      {!requiresRegion && form.region ? (
                        <button
                          type="button"
                          onClick={() => setForm((prev) => ({ ...prev, region: "" }))}
                          className="rounded-full border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-900"
                        >
                          {t("agent.clearRegion", "Clear service region")}
                        </button>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </div>
            </Field>
            <Field label={t("agent.apiKey", "API key or credential")}>
              <div className="space-y-2">
                <PasswordInput
                  value={form.api_key}
                  onChange={(e) => setForm((prev) => ({ ...prev, api_key: e.target.value }))}
                  placeholder={
                    settingsQuery.data?.has_api_key
                      ? t("agent.apiKeySaved", "Stored already. Enter a new one only if you need to rotate it.")
                      : t("agent.apiKeyPlaceholder", "Paste tenant-scoped provider secret")
                  }
                  className="w-full rounded-[0.9rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                />
                {settingsQuery.data?.has_api_key ? (
                  <p className="inline-flex items-center gap-2 text-sm text-[#4d6354]">
                    <KeyRound size={14} />
                    {t("agent.apiKeyStored", "A provider secret is already stored for this tenant.")}
                  </p>
                ) : null}
                {settingsQuery.data?.validation_status === "valid" ? (
                  <p className="inline-flex items-center gap-2 text-sm text-[#2a6c42]">
                    <CheckCircle2 size={14} />
                    {t(
                      "agent.validationValid",
                      `${settingsQuery.data.provider_label || settingsQuery.data.provider_type} / ${settingsQuery.data.model_name} is validated and ready to use.`,
                    )}
                  </p>
                ) : null}
                {settingsQuery.data?.validation_status === "unsupported" && settingsQuery.data.validation_message ? (
                  <p className="text-sm text-[#8a6a26]">{settingsQuery.data.validation_message}</p>
                ) : null}
              </div>
            </Field>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="inline-flex items-center gap-2 rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold text-[#f4efe8] disabled:opacity-50"
            >
              <CheckCircle2 size={16} />
              {saveMutation.isPending ? t("agent.saving", "Saving...") : t("agent.savePrimaryAction", "Confirm and save")}
            </button>
            <p className="text-sm leading-6 text-[#61717d]">
              {t(
                "agent.saveHint",
                "After choosing a model or updating the key, confirm and save first, then test it in the agent console.",
              )}
            </p>
          </div>

          <div className="mt-6 rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] p-5">
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div className="max-w-2xl">
                <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                  {t("agent.advancedTitle", "Advanced model settings")}
                </p>
                <p className="mt-2 text-sm leading-6 text-[#61717d]">
                  {t(
                    "agent.advancedBody",
                    "Only touch these fields when you need a private endpoint, a custom model name, or a cloud region that your provider explicitly requires.",
                  )}
                </p>
                <p className="mt-2 text-sm leading-6 text-[#61717d]">
                  {t(
                    "agent.advancedPrivacyBody",
                    "Provider-side logging and model training are also managed here, because they are governance and privacy choices rather than first-step setup fields.",
                  )}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowAdvanced((prev) => !prev)}
                className="inline-flex items-center rounded-full border border-[#13212c]/12 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c]"
              >
                {showAdvanced ? t("agent.hideAdvanced", "Hide advanced fields") : t("agent.showAdvanced", "Show advanced fields")}
              </button>
            </div>
            {showAdvanced ? (
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <Field label={t("agent.providerType", "Provider type")}>
                  <select
                    value={form.provider_type}
                    onChange={(e) =>
                      setForm((prev) => {
                        const nextProvider = e.target.value;
                        const nextHelp = PROVIDER_HELP[nextProvider] || {};
                        const hasManagedModel = MODEL_FAMILIES.some(
                          (family) =>
                            family.provider === nextProvider &&
                            (family.models as readonly string[]).includes(prev.model_name),
                        );
                        return {
                          ...prev,
                          provider_type: nextProvider,
                          model_name: hasManagedModel ? prev.model_name : "",
                          base_url: nextHelp.baseUrl || prev.base_url,
                          region: REGION_REQUIRED_PROVIDERS.has(nextProvider) ? prev.region : "",
                        };
                      })
                    }
                    className="w-full rounded-[0.9rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  >
                    <option value="">{t("agent.chooseProvider", "Choose provider")}</option>
                    {PROVIDER_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {t(option.labelKey, option.fallback)}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label={t("agent.modelName", "Model name")}>
                  <input
                    type="text"
                    value={form.model_name}
                    onChange={(e) => setForm((prev) => ({ ...prev, model_name: e.target.value }))}
                    placeholder={providerHelp.modelExample || t("agent.modelNamePlaceholder", "gpt-5.4 / claude / gemini / kimi / minimax / deepseek")}
                    className="w-full rounded-[0.9rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>
                <Field label={t("agent.baseUrl", "Endpoint address")}>
                  <div className="space-y-2">
                    <input
                      type="text"
                      value={form.base_url}
                      onChange={(e) => setForm((prev) => ({ ...prev, base_url: e.target.value }))}
                      placeholder={providerHelp.baseUrl || "https://..."}
                      className="w-full rounded-[0.9rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                    />
                    {expectedBaseUrl ? (
                      <p className="text-sm leading-6 text-[#61717d]">
                        {t("agent.baseUrlBody", "If you use a system-maintained mainstream model, keep the suggested endpoint address. Only private endpoints or compatible proxies need a change here.")}{" "}
                        <span className="font-medium text-[#13212c]">{expectedBaseUrl}</span>
                      </p>
                    ) : null}
                  </div>
                </Field>
                {requiresRegion ? (
                  <Field label={t("agent.region", "Service region")}>
                    <div className="space-y-2">
                      <select
                        value={regionSelectValue}
                        onChange={(e) => {
                          const next = e.target.value;
                          if (next === "__custom__") {
                            setForm((prev) => ({ ...prev, region: prev.region && !regionOptions.includes(prev.region) ? prev.region : "" }));
                            return;
                          }
                          setForm((prev) => ({ ...prev, region: next }));
                        }}
                        className="w-full rounded-[0.9rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                      >
                        <option value="">{t("agent.chooseRegion", "Choose service region")}</option>
                        {regionOptions.map((region) => (
                          <option key={region} value={region}>
                            {region}
                          </option>
                        ))}
                        <option value="__custom__">{t("agent.customRegion", "Custom region")}</option>
                      </select>
                      {regionSelectValue === "__custom__" ? (
                        <input
                          type="text"
                          value={form.region}
                          onChange={(e) => setForm((prev) => ({ ...prev, region: e.target.value }))}
                          placeholder={providerHelp.regionExample || t("agent.regionPlaceholder", "Optional unless your provider requires it")}
                          className="w-full rounded-[0.9rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                        />
                      ) : null}
                      <p className="text-sm leading-6 text-[#61717d]">
                        {t(
                          "agent.regionBody",
                          "Service region is only needed for providers such as Azure OpenAI, AWS Bedrock, or Vertex AI. If you use OpenAI, Claude, Kimi, MiniMax, or DeepSeek, you can usually leave it empty.",
                        )}
                      </p>
                    </div>
                  </Field>
                ) : (
                  <div className="rounded-[0.9rem] border border-dashed border-[#d7dfe5] bg-white/70 px-4 py-3 text-sm leading-6 text-[#61717d]">
                    <p className="font-semibold text-[#13212c]">{t("agent.regionNotNeededTitle", "This model usually does not need a service region.")}</p>
                    <p className="mt-1">
                      {t("agent.regionNotNeededBody", "Only region-deployed services such as Azure OpenAI, AWS Bedrock, or Vertex AI need a service region.")}
                    </p>
                  </div>
                )}
                <div className="md:col-span-2 grid gap-4 md:grid-cols-2">
                  <ToggleRow
                    title={t("agent.allowDataLogging", "Allow provider-side data logging")}
                    detail={t("agent.allowDataLoggingBody", "Enable only if the tenant's legal and procurement policies allow provider logging.")}
                    checked={form.allow_data_logging}
                    onChange={(checked) => setForm((prev) => ({ ...prev, allow_data_logging: checked }))}
                  />
                  <ToggleRow
                    title={t("agent.allowModelTraining", "Allow provider-side model training")}
                    detail={t("agent.allowModelTrainingBody", "Keep this off unless the tenant explicitly accepts provider training or retention on submitted prompts and data.")}
                    checked={form.allow_model_training}
                    onChange={(checked) => setForm((prev) => ({ ...prev, allow_model_training: checked }))}
                  />
                </div>
              </div>
            ) : null}
          </div>

          <div className="mt-6 rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] p-5">
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
              {t("agent.allowedTools", "Agent-allowed tools")}
            </p>
            <p className="mt-2 text-sm leading-6 text-[#61717d]">
              {t("agent.allowedToolsBody", "Start with the lowest-risk operational tools. The first agent release should focus on mapping imports, inventory lookup, and guided setup help.")}  
            </p>
            <div className="mt-4 space-y-4">
              {groupedTools.map((group) => (
                <section
                  key={group.key}
                  className="rounded-[1rem] border border-[#13212c]/8 bg-white p-4"
                >
                  <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                    <div>
                      <p className="text-sm font-semibold text-[#13212c]">
                        {t(group.titleKey, group.titleFallback)}
                      </p>
                      <p className="mt-1 text-sm leading-6 text-[#61717d]">
                        {t(group.bodyKey, group.bodyFallback)}
                      </p>
                    </div>
                    <span className="inline-flex rounded-full border border-[#d7dfe5] bg-[#f7f4ee] px-3 py-1 text-xs font-semibold text-[#425461]">
                      {t("agent.toolCount", "{count} tools", { count: String(group.tools.length) })}
                    </span>
                  </div>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    {group.tools.map((tool) => (
                      <label
                        key={tool.key}
                        className="flex items-start gap-3 rounded-[0.9rem] border border-[#13212c]/8 bg-white px-4 py-3 text-sm text-[#13212c]"
                      >
                        <input
                          type="checkbox"
                          checked={form.allowed_tools.includes(tool.key)}
                          onChange={(e) =>
                            setForm((prev) => ({
                              ...prev,
                              allowed_tools: e.target.checked
                                ? [...prev.allowed_tools, tool.key]
                                : prev.allowed_tools.filter((value) => value !== tool.key),
                            }))
                          }
                          className="mt-1 h-4 w-4 rounded border-[#c3ccd4] text-[#13212c]"
                        />
                        <div className="min-w-0">
                          <p className="font-medium">{t(tool.key, tool.key)}</p>
                          <p className="mt-1 text-xs uppercase tracking-[0.08em] text-[#7e8d98]">
                            {t("agent.risk", "Risk")}: {tool.risk}
                          </p>
                          <details className="mt-2">
                            <summary className="cursor-pointer text-xs text-[#61717d]">
                              {t("agent.toolTechnical", "View technical key")}
                            </summary>
                            <p className="mt-2 rounded-[0.75rem] border border-[#d7dfe5] bg-[#f7f4ee] px-3 py-2 font-mono text-[11px] text-[#425461]">
                              {tool.key}
                            </p>
                          </details>
                        </div>
                      </label>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </div>

          {message ? (
            <p className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              {message}
            </p>
          ) : null}
          {error ? (
            <p className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </p>
          ) : null}
          <div className="mt-6 grid gap-3 md:grid-cols-3">
            <InlineHint
              title={t("agent.side1TitleSimple", "Enable the safest batch first")}
              body={t("agent.side1BodySimple", "Start with search and inspect, then add import previews as needed. Leave the tools that really change data for last.")}
            />
            <InlineHint
              title={t("agent.side2TitleSimple", "What happens if the key is wrong")}
              body={t("agent.side2BodySimple", "After saving, the system reports whether the model is usable. If the key is invalid or fields do not match, this page prompts you to fix it.")}
            />
            <InlineHint
              title={t("agent.side3TitleSimple", "Where to use it after setup")}
              body={t("agent.side3BodySimple", "Go back to the AI console, run the system check first, then use chat to look up inventory, review orders, and run governed imports.")}
            />
          </div>
      </section>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="block">
      <span className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.18em] text-[#71808c]">{label}</span>
      {children}
    </div>
  );
}

function ToggleRow({
  title,
  detail,
  checked,
  onChange,
}: {
  title: string;
  detail: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="rounded-[1rem] border border-[#13212c]/8 bg-[#f7f4ee] px-5 py-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-[#13212c]">{title}</p>
          <p className="mt-2 text-sm leading-6 text-[#61717d]">{detail}</p>
        </div>
        <button
          type="button"
          onClick={() => onChange(!checked)}
          className={`relative inline-flex h-7 w-12 shrink-0 rounded-full transition ${checked ? "bg-[#13212c]" : "bg-[#d7dfe5]"}`}
        >
          <span
            className={`absolute top-1 h-5 w-5 rounded-full bg-white transition ${checked ? "left-6" : "left-1"}`}
          />
        </button>
      </div>
    </div>
  );
}

function InlineHint({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-[1rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4">
      <p className="text-sm font-semibold text-[#13212c]">{title}</p>
      <p className="mt-2 text-sm leading-6 text-[#61717d]">{body}</p>
    </div>
  );
}

function StatusChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">{label}</p>
      <p className="mt-2 text-sm font-semibold text-[#13212c]">{value}</p>
    </div>
  );
}
