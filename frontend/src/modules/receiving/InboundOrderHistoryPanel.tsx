import { useNavigate } from "react-router-dom";
import { useI18n } from "../../shared/i18n";
import InboundOrderRecordStateBadge from "./InboundOrderRecordStateBadge";

function packageOriginLabel(
  origin: string | null | undefined,
  t: (key: string, fallback: string, vars?: Record<string, string | number>) => string,
) {
  if (origin === "dock_created") return t("receiving.packageOriginDockCreated", "Opened at dock");
  return t("receiving.packageOriginPrebooked", "Pre-booked");
}

function packageNeedsReceivingAttention(pkg: any) {
  return !["received", "staged", "putaway_pending", "stored"].includes(pkg.status || "");
}

function packageNeedsPrint(pkg: any) {
  return (pkg.receiving_labels || []).some((label: any) => (label.print_count || 0) === 0);
}

function packageNeedsPutaway(pkg: any) {
  return (
    pkg.status === "putaway_pending" ||
    (pkg.downstream_tasks || []).some((task: any) => task.status !== "completed")
  );
}

function packageReviewPriority(pkg: any) {
  return (
    (packageNeedsReceivingAttention(pkg) ? 300 : 0) +
    (packageNeedsPrint(pkg) ? 200 : 0) +
    (packageNeedsPutaway(pkg) ? 100 : 0) +
    (pkg.package_origin === "dock_created" ? 20 : 0)
  );
}

export default function InboundOrderHistoryPanel({
  detail,
  isLoading,
  className = "",
  orderId = null,
}: {
  detail: any;
  isLoading?: boolean;
  className?: string;
  orderId?: string | null;
}) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const packageSummary = detail?.package_summary || {
    total_packages: 0,
    packages_open: 0,
    packages_putaway_pending: 0,
    packages_stored: 0,
    packages_needing_action: 0,
    supervisor_review_needed: false,
    internal_labels_print_pending: 0,
  };

  const persistReceivingFocus = (payload: {
    packageId: string;
    packageNumber?: number | null;
    target: "package" | "print";
  }) => {
    if (typeof window === "undefined" || !orderId) return;
    window.sessionStorage.setItem("receiving.selectedOrderId", orderId);
    window.sessionStorage.setItem(
      "receiving.focusContext",
      JSON.stringify({
        orderId,
        packageId: payload.packageId,
        packageNumber: payload.packageNumber || null,
        target: payload.target,
      }),
    );
    navigate("/receiving");
  };

  const persistPutawayFocus = (payload: Record<string, string | null | undefined>) => {
    if (typeof window === "undefined") return;
    window.sessionStorage.setItem(
      "putaway.focusContext",
      JSON.stringify({
        source: "inbound-history",
        orderId: orderId || null,
        ...payload,
      }),
    );
    navigate("/putaway");
  };

  const actionablePackages = (detail?.lines || [])
    .flatMap((line: any) =>
      (line.packages || []).map((pkg: any) => ({
        ...pkg,
        lineSkuCode: line.sku_code,
        lineSkuName: line.sku_name,
      })),
    )
    .filter((pkg: any) => packageNeedsReceivingAttention(pkg) || packageNeedsPrint(pkg) || packageNeedsPutaway(pkg))
    .sort((a: any, b: any) => {
      const priorityDelta = packageReviewPriority(b) - packageReviewPriority(a);
      if (priorityDelta !== 0) return priorityDelta;
      return Number(a.package_number || 0) - Number(b.package_number || 0);
    });

  return (
    <div className={`rounded-[1.4rem] border border-[#13212c]/8 bg-[#faf7f2] p-4 ${className}`.trim()}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.2em] text-[#7f8d98]">
            {t("receiving.orderHistoryEyebrow", "Inbound history")}
          </p>
          <h3 className="mt-2 text-base font-semibold text-[#13212c]">{t("receiving.orderHistoryTitle", "Scanned, confirmed, and printed")}</h3>
        </div>
        {detail ? <InboundOrderRecordStateBadge order={detail} /> : null}
      </div>

      {isLoading ? (
        <p className="mt-4 text-sm text-[#61717d]">{t("receiving.orderHistoryLoading", "Loading inbound history...")}</p>
      ) : detail ? (
        <div className="mt-4 space-y-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label={t("receiving.orderHistoryCreated", "Created")}
              value={detail.created_at || "—"}
            />
            <MetricCard
              label={t("receiving.orderHistoryPackagesNeedingAction", "Packages needing action")}
              value={packageSummary.packages_needing_action || 0}
            />
            <MetricCard
              label={t("receiving.orderHistoryInternalLabels", "Internal labels printed")}
              value={`${detail.printed_internal_labels || 0} / ${detail.total_internal_labels || 0}`}
            />
            <MetricCard
              label={t("receiving.orderHistoryPrintPending", "Labels still to print")}
              value={packageSummary.internal_labels_print_pending || 0}
            />
            {(packageSummary.packages_stored || 0) > 0 ? (
              <MetricCard
                label={t("receiving.orderHistoryPackagesStored", "Packages stored")}
                value={packageSummary.packages_stored || 0}
              />
            ) : null}
          </div>

          {actionablePackages.length ? (
            <section className="rounded-[1rem] border border-[#13212c]/8 bg-white px-4 py-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                    {t("receiving.orderHistoryActionablePackages", "Package review queue")}
                  </p>
                  <h4 className="mt-2 text-sm font-semibold text-[#13212c]">
                    {t("receiving.orderHistoryActionablePackagesTitle", "Packages that still need a direct warehouse action")}
                  </h4>
                </div>
                <span className="rounded-full border border-[#d7d0c4] bg-[#f8f4ec] px-3 py-1 text-xs font-semibold text-[#51606b]">
                  {t("receiving.orderHistoryActionablePackagesCount", "{count} packages need action", {
                    count: String(actionablePackages.length),
                  })}
                </span>
              </div>

              <div className="mt-4 grid gap-3 xl:grid-cols-2">
                {actionablePackages.map((pkg: any) => {
                  const canOpenReceiving = packageNeedsReceivingAttention(pkg) && orderId;
                  const canOpenPrint = packageNeedsPrint(pkg) && orderId;
                  const openPutawayTask = (pkg.downstream_tasks || []).find((task: any) => task.status !== "completed");
                  return (
                    <div key={pkg.id} className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#faf7f2] px-4 py-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-[#13212c]">
                            {t("receiving.packageTitle", "Package {number}", {
                              number: String(pkg.package_number || 1),
                            })}
                            {pkg.lineSkuCode ? ` · ${pkg.lineSkuCode}` : ""}
                            {pkg.lineSkuName ? ` · ${pkg.lineSkuName}` : ""}
                          </p>
                          <p className="mt-1 text-sm text-[#61717d]">
                            {t(
                              "receiving.packageHistoryQuantities",
                              "Expected {expected} · Received {received} · Damaged {damaged}",
                              {
                                expected: String(pkg.expected_qty || 0),
                                received: String(pkg.received_qty || 0),
                                damaged: String(pkg.damaged_qty || 0),
                              },
                            )}
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                            {packageOriginLabel(pkg.package_origin, t)}
                          </span>
                          <span className="rounded-full bg-[#edf2f7] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#51606b]">
                            {pkg.status || "—"}
                          </span>
                        </div>
                      </div>

                      <div className="mt-3 flex flex-wrap gap-2">
                        {packageNeedsReceivingAttention(pkg) ? (
                          <span className="rounded-full bg-[#fff5e8] px-3 py-1 text-xs font-medium text-[#9a6421]">
                            {t("receiving.orderHistoryReviewReasonOpen", "Still open at dock")}
                          </span>
                        ) : null}
                        {packageNeedsPrint(pkg) ? (
                          <span className="rounded-full bg-[#edf2f7] px-3 py-1 text-xs font-medium text-[#425466]">
                            {t("receiving.orderHistoryReviewReasonPrint", "Internal label still needs printing")}
                          </span>
                        ) : null}
                        {packageNeedsPutaway(pkg) ? (
                          <span className="rounded-full bg-[#fff6e6] px-3 py-1 text-xs font-medium text-[#91621a]">
                            {t("receiving.orderHistoryReviewReasonPutaway", "Still waiting on putaway")}
                          </span>
                        ) : null}
                      </div>

                      <div className="mt-4 flex flex-wrap gap-2">
                        {canOpenReceiving ? (
                          <button
                            type="button"
                            onClick={() =>
                              persistReceivingFocus({
                                packageId: pkg.id,
                                packageNumber: pkg.package_number,
                                target: "package",
                              })
                            }
                            className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                          >
                            {t("receiving.detailOpenPackageInReceivingAction", "Open package in receiving")}
                          </button>
                        ) : null}
                        {canOpenPrint ? (
                          <button
                            type="button"
                            onClick={() =>
                              persistReceivingFocus({
                                packageId: pkg.id,
                                packageNumber: pkg.package_number,
                                target: "print",
                              })
                            }
                            className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                          >
                            {t("receiving.detailOpenPackagePrintAction", "Open package print")}
                          </button>
                        ) : null}
                        {openPutawayTask ? (
                          <button
                            type="button"
                            onClick={() =>
                              persistPutawayFocus({
                                taskId: openPutawayTask.id || null,
                                handlingUnitCode: openPutawayTask.handling_unit_code || null,
                              })
                            }
                            className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                          >
                            {t("receiving.orderHistoryOpenPackagePutawayAction", "Open package putaway")}
                          </button>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          ) : null}

          <div className="space-y-3">
            {detail.lines?.map((line: any) => (
              <div key={line.line_id} className="rounded-[1rem] border border-[#13212c]/8 bg-white px-4 py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-[#13212c]">
                      {line.sku_code} {line.sku_name ? `· ${line.sku_name}` : ""}
                    </p>
                    <p className="mt-1 text-sm text-[#61717d]">
                      {t("receiving.orderHistoryLineQuantities", "Expected {expected} · Received {received} · Damaged {damaged}", {
                        expected: String(line.quantity_expected || 0),
                        received: String(line.quantity_received || 0),
                        damaged: String(line.quantity_damaged || 0),
                      })}
                    </p>
                  </div>
                  {line.staging_location_id ? (
                    <span className="rounded-full border border-[#d7d0c4] bg-[#f8f4ec] px-3 py-1 text-xs font-medium text-[#51606b]">
                      {t("receiving.orderHistoryStaging", "Staging")} {line.staging_location_id}
                    </span>
                  ) : null}
                </div>

                {line.external_tracking_number || line.external_carton_mark || line.external_customer_barcode ? (
                  <div className="mt-3 flex flex-wrap gap-2 text-xs text-[#51606b]">
                    {line.external_tracking_number ? (
                      <span className="rounded-full bg-[#f2efe9] px-3 py-1">
                        {t("receiving.detectedCodeTypeTracking", "Tracking Number")}: {line.external_tracking_number}
                      </span>
                    ) : null}
                    {line.external_carton_mark ? (
                      <span className="rounded-full bg-[#f2efe9] px-3 py-1">
                        {t("receiving.detectedCodeTypeCarton", "Carton Mark")}: {line.external_carton_mark}
                      </span>
                    ) : null}
                    {line.external_customer_barcode ? (
                      <span className="rounded-full bg-[#f2efe9] px-3 py-1">
                        {t("receiving.detectedCodeTypeCustomerBox", "Customer Box Code")}: {line.external_customer_barcode}
                      </span>
                    ) : null}
                  </div>
                ) : null}

                <div className="mt-3 grid gap-3 xl:grid-cols-2">
                  {line.packages?.length ? (
                    <div className="xl:col-span-2 space-y-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                        {t("receiving.orderHistoryPackages", "Packages")}
                      </p>
                      <div className="grid gap-3 xl:grid-cols-2">
                        {line.packages.map((pkg: any) => (
                          <div key={pkg.id} className="rounded-[1rem] border border-[#13212c]/8 bg-[#faf7f2] p-4">
                              {(() => {
                                const packageStillOpen = !["received", "staged", "putaway_pending", "stored"].includes(
                                  pkg.status || "",
                                );
                                const packagePrintPending = (pkg.receiving_labels || []).some(
                                  (label: any) => (label.print_count || 0) === 0,
                                );
                                return (
                                  <div className="mb-3 flex flex-wrap justify-end gap-2">
                                    {packageStillOpen && orderId ? (
                                      <button
                                        type="button"
                                        onClick={() =>
                                          persistReceivingFocus({
                                            packageId: pkg.id,
                                            packageNumber: pkg.package_number,
                                            target: "package",
                                          })
                                        }
                                        className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                                      >
                                        {t("receiving.detailOpenPackageInReceivingAction", "Open package in receiving")}
                                      </button>
                                    ) : null}
                                    {packagePrintPending && orderId ? (
                                      <button
                                        type="button"
                                        onClick={() =>
                                          persistReceivingFocus({
                                            packageId: pkg.id,
                                            packageNumber: pkg.package_number,
                                            target: "print",
                                          })
                                        }
                                        className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                                      >
                                        {t("receiving.detailOpenPackagePrintAction", "Open package print")}
                                      </button>
                                    ) : null}
                                  </div>
                                );
                              })()}
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div>
                                  <p className="text-sm font-semibold text-[#13212c]">
                                    {t("receiving.packageTitle", "Package {number}", { number: String(pkg.package_number || 1) })}
                                  </p>
                                <p className="mt-1 text-sm text-[#61717d]">
                                  {t(
                                    "receiving.packageHistoryQuantities",
                                    "Expected {expected} · Received {received} · Damaged {damaged}",
                                    {
                                      expected: String(pkg.expected_qty || 0),
                                      received: String(pkg.received_qty || 0),
                                      damaged: String(pkg.damaged_qty || 0),
                                    },
                                  )}
                                </p>
                              </div>
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                                  {packageOriginLabel(pkg.package_origin, t)}
                                </span>
                                <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                                  {pkg.status || "—"}
                                </span>
                                {pkg.staging_location_barcode ? (
                                  <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                                    {t("receiving.orderHistoryStaging", "Staging")} {pkg.staging_location_barcode}
                                  </span>
                                ) : null}
                              </div>
                            </div>

                            {pkg.external_tracking_number || pkg.external_carton_mark || pkg.external_customer_barcode ? (
                              <div className="mt-3 flex flex-wrap gap-2 text-xs text-[#51606b]">
                                {pkg.external_tracking_number ? (
                                  <span className="rounded-full bg-white px-3 py-1">
                                    {t("receiving.detectedCodeTypeTracking", "Tracking Number")}: {pkg.external_tracking_number}
                                  </span>
                                ) : null}
                                {pkg.external_carton_mark ? (
                                  <span className="rounded-full bg-white px-3 py-1">
                                    {t("receiving.detectedCodeTypeCarton", "Carton Mark")}: {pkg.external_carton_mark}
                                  </span>
                                ) : null}
                                {pkg.external_customer_barcode ? (
                                  <span className="rounded-full bg-white px-3 py-1">
                                    {t("receiving.detectedCodeTypeCustomerBox", "Customer Box Code")}: {pkg.external_customer_barcode}
                                  </span>
                                ) : null}
                              </div>
                            ) : null}

                            <div className="mt-3 grid gap-3 xl:grid-cols-2">
                              <div>
                                <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                                  {t("receiving.orderHistoryObservedCodes", "Observed codes")}
                                </p>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {pkg.observed_codes?.length ? (
                                    pkg.observed_codes.map((code: any) => (
                                      <span
                                        key={code.id}
                                        className={`rounded-full px-3 py-1 text-xs font-medium ${
                                          code.is_confirmed ? "bg-[#eef7ef] text-[#2f6c43]" : "bg-[#fff5e8] text-[#9a6421]"
                                        }`}
                                      >
                                        {code.code_value}
                                        {code.is_primary ? ` · ${t("receiving.primaryCodeBadge", "Primary")}` : ""}
                                      </span>
                                    ))
                                  ) : (
                                    <p className="text-sm text-[#7f8d98]">
                                      {t("receiving.orderHistoryNoObservedCodes", "No freight codes captured yet.")}
                                    </p>
                                  )}
                                </div>
                              </div>

                              <div>
                                <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                                  {t("receiving.orderHistoryInternalLabels", "Internal labels printed")}
                                </p>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {pkg.receiving_labels?.length ? (
                                    pkg.receiving_labels.map((label: any) => (
                                      <span
                                        key={label.id}
                                        className={`rounded-full px-3 py-1 text-xs font-medium ${
                                          (label.print_count || 0) > 0 ? "bg-[#eef7ef] text-[#2f6c43]" : "bg-[#edf2f7] text-[#425466]"
                                        }`}
                                      >
                                        {label.label_code}
                                        {(label.print_count || 0) > 0
                                          ? ` · ${t("receiving.orderHistoryPrintedCount", "Printed {count}x", { count: String(label.print_count) })}`
                                          : ` · ${t("receiving.orderHistoryReadyToPrint", "Ready to print")}`}
                                      </span>
                                    ))
                                  ) : (
                                    <p className="text-sm text-[#7f8d98]">
                                      {t("receiving.orderHistoryNoInternalLabels", "No internal labels issued yet.")}
                                    </p>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <>
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                          {t("receiving.orderHistoryObservedCodes", "Observed codes")}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {line.observed_codes?.length ? (
                            line.observed_codes.map((code: any) => (
                              <span
                                key={code.id}
                                className={`rounded-full px-3 py-1 text-xs font-medium ${
                                  code.is_confirmed ? "bg-[#eef7ef] text-[#2f6c43]" : "bg-[#fff5e8] text-[#9a6421]"
                                }`}
                              >
                                {code.code_value}
                                {code.is_primary ? ` · ${t("receiving.primaryCodeBadge", "Primary")}` : ""}
                              </span>
                            ))
                          ) : (
                            <p className="text-sm text-[#7f8d98]">{t("receiving.orderHistoryNoObservedCodes", "No freight codes captured yet.")}</p>
                          )}
                        </div>
                      </div>

                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                          {t("receiving.orderHistoryInternalLabels", "Internal labels printed")}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {line.receiving_labels?.length ? (
                            line.receiving_labels.map((label: any) => (
                              <span
                                key={label.id}
                                className={`rounded-full px-3 py-1 text-xs font-medium ${
                                  (label.print_count || 0) > 0 ? "bg-[#eef7ef] text-[#2f6c43]" : "bg-[#edf2f7] text-[#425466]"
                                }`}
                              >
                                {label.label_code}
                                {(label.print_count || 0) > 0
                                  ? ` · ${t("receiving.orderHistoryPrintedCount", "Printed {count}x", { count: String(label.print_count) })}`
                                  : ` · ${t("receiving.orderHistoryReadyToPrint", "Ready to print")}`}
                              </span>
                            ))
                          ) : (
                            <p className="text-sm text-[#7f8d98]">{t("receiving.orderHistoryNoInternalLabels", "No internal labels issued yet.")}</p>
                          )}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="mt-4 text-sm text-[#61717d]">{t("receiving.orderHistoryEmpty", "No inbound history is available for this order yet.")}</p>
      )}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-[1rem] border border-[#13212c]/8 bg-white px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">{label}</p>
      <p className="mt-2 text-sm font-semibold text-[#13212c]">{value}</p>
    </div>
  );
}
