import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, ScanLine, Tags } from "lucide-react";
import { Link } from "react-router-dom";
import { queryKeys } from "../../shared/api/queryKeys";
import { fetchReceivingCodeRules, updateReceivingCodeRules } from "../../shared/api/receiving";
import { getApiErrorMessage } from "../../shared/api/error-message";
import { useI18n } from "../../shared/i18n";

const SEPARATOR_OPTIONS = [
  { value: "-", label: "-" },
  { value: "_", label: "_" },
  { value: "", label: "None" },
] as const;

export default function ReceivingCodeSettingsPage() {
  const { t } = useI18n();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    prefix: "RCV",
    separator: "-",
    include_order_number: true,
    sequence_padding: 3,
    uppercase: true,
  });

  const rulesQuery = useQuery({
    queryKey: queryKeys.receiving.codeRules(),
    queryFn: fetchReceivingCodeRules,
  });

  useEffect(() => {
    if (!rulesQuery.data) return;
    setForm({
      prefix: rulesQuery.data.prefix,
      separator: rulesQuery.data.separator,
      include_order_number: rulesQuery.data.include_order_number,
      sequence_padding: rulesQuery.data.sequence_padding,
      uppercase: rulesQuery.data.uppercase,
    });
  }, [rulesQuery.data]);

  const saveMutation = useMutation({
    mutationFn: async () =>
      updateReceivingCodeRules({
        prefix: form.prefix,
        separator: form.separator,
        include_order_number: form.include_order_number,
        sequence_padding: form.sequence_padding,
        uppercase: form.uppercase,
      }),
    onSuccess: (data) => {
      rulesQuery.refetch();
      setMessage(
        t(
          "receivingCodeSettings.saveSuccess",
          "Internal receiving code rules saved. New inbound labels will use this pattern.",
        ),
      );
      setError("");
      setForm({
        prefix: data.prefix,
        separator: data.separator,
        include_order_number: data.include_order_number,
        sequence_padding: data.sequence_padding,
        uppercase: data.uppercase,
      });
    },
    onError: (err: any) => {
      setMessage("");
      setError(
        getApiErrorMessage(
          err,
          t("receivingCodeSettings.saveError", "Could not save internal receiving code rules."),
        ),
      );
    },
  });

  const currentSample = rulesQuery.data?.sample_code || buildLocalSample(form);

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <section className="rounded-[1.5rem] border border-[#13212c]/8 bg-white p-6 shadow-[0_10px_26px_rgba(19,33,44,0.05)]">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-[11px] uppercase tracking-[0.24em] text-[#7e8d98]">
              {t("receivingCodeSettings.eyebrow", "Receiving code settings")}
            </p>
            <h1 className="mt-3 text-[2rem] font-semibold tracking-[-0.04em] text-[#13212c]">
              {t(
                "receivingCodeSettings.title",
                "Generate an internal code every time inbound stock enters the warehouse.",
              )}
            </h1>
            <p className="mt-4 text-sm leading-7 text-[#61717d]">
              {t(
                "receivingCodeSettings.body",
                "External carton marks, tracking numbers, and customer labels can stay as identification inputs. This page decides the warehouse-owned code pattern that new receiving labels will follow.",
              )}
            </p>
          </div>
          <div className="grid w-full gap-3 lg:max-w-md lg:grid-cols-2">
            <SummaryChip
              label={t("receivingCodeSettings.summaryPrefix", "Prefix")}
              value={form.prefix || "RCV"}
            />
            <SummaryChip
              label={t("receivingCodeSettings.summarySample", "Sample code")}
              value={currentSample}
            />
          </div>
        </div>
      </section>

      <section
        className="rounded-[1.1rem] border border-[#13212c]/10 bg-white/84 px-4 py-3 text-sm leading-6 text-[#51606b] md:hidden"
        data-testid="receiving-code-mobile-governance"
        data-admin-mobile-contract="receiving-settings-desktop-first"
      >
        <p className="font-semibold text-[#13212c]">
          {t("receivingCodeSettings.mobileNoticeTitle", "Receiving code settings are desktop-first")}
        </p>
        <p className="mt-1">
          {t("receivingCodeSettings.mobileNoticeBody", "Use this phone view to check the current sample code. Change label code patterns on iPad or desktop before dock execution.")}
        </p>
      </section>

      <details
        className="rounded-[1.1rem] border border-[#13212c]/8 bg-white/84 px-4 py-3 md:hidden"
        data-testid="receiving-code-mobile-settings-collapsed"
      >
        <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
          {t("receivingCodeSettings.mobileEditSummary", "Edit pattern on desktop")}
        </summary>
        <p className="mt-2 text-sm leading-6 text-[#61717d]">
          {t("receivingCodeSettings.mobileEditBody", "Prefix, separator, sequence digits, and uppercase rules affect every newly printed receiving label, so edits stay in the desktop management path.")}
        </p>
      </details>

      <section className="hidden rounded-[1.5rem] border border-[#13212c]/8 bg-white p-6 shadow-[0_10px_26px_rgba(19,33,44,0.05)] md:block">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <div className="space-y-5">
            <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-full border border-[#13212c]/10 bg-white text-[#13212c]">
                  <Tags size={18} />
                </div>
                <div>
                  <p className="text-sm font-semibold text-[#13212c]">
                    {t("receivingCodeSettings.patternTitle", "Internal receiving label pattern")}
                  </p>
                  <p className="text-sm leading-6 text-[#61717d]">
                    {t(
                      "receivingCodeSettings.patternBody",
                      "Keep this short, printable, and easy to read over a radio call. The system UUID stays hidden; operators only need the warehouse code.",
                    )}
                  </p>
                </div>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <Field label={t("receivingCodeSettings.prefixLabel", "Prefix")}>
                  <input
                    type="text"
                    value={form.prefix}
                    onChange={(e) => setForm((prev) => ({ ...prev, prefix: e.target.value.toUpperCase() }))}
                    placeholder="RCV"
                    className="w-full rounded-[0.9rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>

                <Field label={t("receivingCodeSettings.separatorLabel", "Separator")}>
                  <select
                    value={form.separator}
                    onChange={(e) => setForm((prev) => ({ ...prev, separator: e.target.value }))}
                    className="w-full rounded-[0.9rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  >
                    {SEPARATOR_OPTIONS.map((option) => (
                      <option key={option.value || "none"} value={option.value}>
                        {option.value === "" ? t("receivingCodeSettings.separatorNone", option.label) : option.label}
                      </option>
                    ))}
                  </select>
                </Field>

                <Field label={t("receivingCodeSettings.sequencePaddingLabel", "Sequence digits")}>
                  <input
                    type="number"
                    min={1}
                    max={8}
                    value={form.sequence_padding}
                    onChange={(e) =>
                      setForm((prev) => ({
                        ...prev,
                        sequence_padding: Math.max(1, Math.min(8, Number(e.target.value || 1))),
                      }))
                    }
                    className="w-full rounded-[0.9rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>

                <Field label={t("receivingCodeSettings.liveSampleLabel", "Live sample")}>
                  <div className="rounded-[0.9rem] border border-dashed border-[#13212c]/15 bg-white px-4 py-3 font-mono text-sm text-[#13212c]">
                    {currentSample}
                  </div>
                </Field>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <ToggleCard
                title={t("receivingCodeSettings.includeOrderLabel", "Include inbound order number")}
                detail={t(
                  "receivingCodeSettings.includeOrderBody",
                  "Recommended when operators need to read the code and tie it back to the inbound quickly.",
                )}
                checked={form.include_order_number}
                onChange={(checked) => setForm((prev) => ({ ...prev, include_order_number: checked }))}
              />
              <ToggleCard
                title={t("receivingCodeSettings.uppercaseLabel", "Uppercase format")}
                detail={t(
                  "receivingCodeSettings.uppercaseBody",
                  "Keeps the printed label more legible and reduces confusion between similar lowercase characters.",
                )}
                checked={form.uppercase}
                onChange={(checked) => setForm((prev) => ({ ...prev, uppercase: checked }))}
              />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                className="inline-flex items-center gap-2 rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold text-[#f4efe8] disabled:opacity-50"
              >
                <CheckCircle2 size={16} />
                {saveMutation.isPending
                  ? t("receivingCodeSettings.saving", "Saving...")
                  : t("receivingCodeSettings.saveAction", "Save receiving code rules")}
              </button>
              <Link
                to="/receiving"
                className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/12 bg-white px-5 py-3 text-sm font-semibold text-[#13212c]"
              >
                <ScanLine size={16} />
                {t("receivingCodeSettings.backToReceiving", "Back to inbound receiving")}
              </Link>
            </div>

            {message ? <p className="text-sm text-[#2a6c42]">{message}</p> : null}
            {error ? <p className="text-sm text-[#9b382d]">{error}</p> : null}
          </div>

          <div className="space-y-4">
            <InfoCard
              eyebrow={t("receivingCodeSettings.governanceEyebrow", "Governance")}
              title={t("receivingCodeSettings.governanceTitle", "Always generate the warehouse code, even when customer codes already exist.")}
              body={t(
                "receivingCodeSettings.governanceBody",
                "Customer tracking, carton marks, and supplier labels stay as entry points. New receiving labels and downstream handling-unit tracking should still anchor on the warehouse-owned code.",
              )}
            />
            <InfoCard
              eyebrow={t("receivingCodeSettings.scopeEyebrow", "Scope")}
              title={t("receivingCodeSettings.scopeTitle", "This rule applies to newly generated receiving labels.")}
              body={t(
                "receivingCodeSettings.scopeBody",
                "Existing printed labels keep their current codes. Use this page to decide how future inbounds, mobile scans, and printed dock labels should look.",
              )}
            />
            <InfoCard
              eyebrow={t("receivingCodeSettings.bestPracticeEyebrow", "Best practice")}
              title={t("receivingCodeSettings.bestPracticeTitle", "Keep the code short enough for stickers, radios, and scan guns.")}
              body={t(
                "receivingCodeSettings.bestPracticeBody",
                "A short prefix, the inbound number, and a padded sequence are usually enough. Avoid stuffing too much business meaning into the printed code.",
              )}
            />
          </div>
        </div>
      </section>
    </div>
  );
}

function buildLocalSample(form: {
  prefix: string;
  separator: string;
  include_order_number: boolean;
  sequence_padding: number;
  uppercase: boolean;
}) {
  const separator = form.separator ?? "-";
  const prefix = (form.prefix || "RCV").trim() || "RCV";
  const orderNumber = form.uppercase ? "INB-20260416" : "Inb-20260416";
  const sequence = String(1).padStart(Math.max(1, Math.min(8, form.sequence_padding || 3)), "0");
  const parts = [form.uppercase ? prefix.toUpperCase() : prefix];
  if (form.include_order_number) parts.push(orderNumber);
  parts.push(sequence);
  return parts.join(separator);
}

function SummaryChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] p-4">
      <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{label}</p>
      <p className="mt-2 break-all text-sm font-semibold text-[#13212c]">{value}</p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="space-y-2">
      <span className="text-xs font-semibold uppercase tracking-[0.16em] text-[#61717d]">{label}</span>
      {children}
    </label>
  );
}

function ToggleCard({
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
    <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-[#13212c]">{title}</p>
          <p className="mt-2 text-sm leading-6 text-[#61717d]">{detail}</p>
        </div>
        <label className="inline-flex cursor-pointer items-center">
          <input type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
          <span className="relative h-6 w-11 rounded-full bg-[#dbe3e8] transition peer-checked:bg-[#13212c]">
            <span className="absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition peer-checked:left-[22px]" />
          </span>
        </label>
      </div>
    </div>
  );
}

function InfoCard({ eyebrow, title, body }: { eyebrow: string; title: string; body: string }) {
  return (
    <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] p-5">
      <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{eyebrow}</p>
      <p className="mt-2 text-sm font-semibold text-[#13212c]">{title}</p>
      <p className="mt-2 text-sm leading-6 text-[#61717d]">{body}</p>
    </div>
  );
}
