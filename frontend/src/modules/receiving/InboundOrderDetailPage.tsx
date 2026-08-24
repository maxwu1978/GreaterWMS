import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { queryKeys } from "../../shared/api/queryKeys";
import { archiveInboundOrder, deleteInboundOrder, fetchInboundOrders, voidInboundOrder } from "../../shared/api/inboundOrders";
import { fetchInboundOrderDetail } from "../../shared/api/receiving";
import StatusBadge from "../../shared/components/StatusBadge";
import { useI18n } from "../../shared/i18n";
import { useAuthStore } from "../../shared/hooks/useAuth";
import InboundOrderHistoryPanel from "./InboundOrderHistoryPanel";
import InboundOrderLifecycleTimeline from "./InboundOrderLifecycleTimeline";
import InboundOrderDownstreamPanel from "./InboundOrderDownstreamPanel";
import InboundOrderRecordStateBadge from "./InboundOrderRecordStateBadge";

function formatTimelineTimeAgo(
  occurredAt: string | null | undefined,
  t: (key: string, fallback: string, vars?: Record<string, string>) => string,
) {
  const parsed = Date.parse(occurredAt || "");
  if (!Number.isFinite(parsed)) return t("receiving.detailLastChangedUnknown", "No recent package event recorded");
  const diffMs = Math.max(0, Date.now() - parsed);
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return t("receiving.recentActivityNow", "just now");
  if (minutes < 60) return t("receiving.recentActivityMinutes", "{count}m ago", { count: String(minutes) });
  const hours = Math.round(minutes / 60);
  if (hours < 48) return t("receiving.recentActivityHours", "{count}h ago", { count: String(hours) });
  const days = Math.round(hours / 24);
  return t("receiving.recentActivityDays", "{count}d ago", { count: String(days) });
}

function latestTimelineEvent(timeline: any[] | undefined) {
  if (!timeline?.length) return null;
  return [...timeline]
    .filter((event) => event?.occurred_at)
    .sort((a, b) => (Date.parse(b.occurred_at || "") || 0) - (Date.parse(a.occurred_at || "") || 0))[0] || null;
}

function packageNeedsReceivingAttention(pkg: any) {
  return !["received", "staged", "putaway_pending", "stored"].includes(pkg?.status || "");
}

function packageNeedsPrint(pkg: any) {
  return (pkg?.receiving_labels || []).some((label: any) => (label.print_count || 0) === 0);
}

function flattenDetailPackages(detail: any) {
  return (detail?.lines || []).flatMap((line: any) =>
    (line.packages || []).map((pkg: any) => ({
      ...pkg,
      line_id: line.line_id,
      line_number: line.line_number,
      sku_code: line.sku_code,
      sku_name: line.sku_name,
    })),
  );
}

function nextReceivingPackage(detail: any) {
  return flattenDetailPackages(detail)
    .filter((pkg: any) => packageNeedsReceivingAttention(pkg))
    .sort((a: any, b: any) => Number(a.package_number || 0) - Number(b.package_number || 0))[0] || null;
}

function nextPrintPackage(detail: any) {
  return flattenDetailPackages(detail)
    .filter((pkg: any) => packageNeedsPrint(pkg))
    .sort((a: any, b: any) => Number(a.package_number || 0) - Number(b.package_number || 0))[0] || null;
}

function receivingUnitsRemaining(detail: any) {
  return (detail?.lines || []).reduce((sum: number, line: any) => {
    const expected = Number(line.quantity_expected || 0);
    const received = Number(line.quantity_received || 0);
    return sum + Math.max(0, expected - received);
  }, 0);
}

export default function InboundOrderDetailPage() {
  const { orderId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const permissions = useAuthStore((s) => s.permissions);
  const canReceiveInbound = permissions.includes("*") || permissions.includes("receiving.execute");

  const { data: orders = [] } = useQuery({
    queryKey: queryKeys.inboundOrders.list(true),
    queryFn: () => fetchInboundOrders({ include_archived: true }),
  });

  const { data: orderDetail, isLoading } = useQuery({
    queryKey: queryKeys.inboundOrders.detail(orderId),
    enabled: !!orderId,
    queryFn: () => fetchInboundOrderDetail(orderId),
  });
  const [returnNotice, setReturnNotice] = useState<{
    handlingUnitCode?: string | null;
    destinationBarcode?: string | null;
    destinationCount?: number;
  } | null>(null);
  const packageSummary = orderDetail?.package_summary || {
    total_packages: 0,
    packages_open: 0,
    packages_putaway_pending: 0,
    packages_stored: 0,
    packages_needing_action: 0,
    supervisor_review_needed: false,
    internal_labels_print_pending: 0,
  };
  const lastTimelineEvent = latestTimelineEvent(orderDetail?.timeline || []);
  const unitsRemainingAtDock = receivingUnitsRemaining(orderDetail);
  const blockers = [
    unitsRemainingAtDock > 0
      ? t("receiving.detailBlockedUnitsRemaining", "{count} SKU units still need receiving", {
          count: String(unitsRemainingAtDock),
        })
      : null,
    packageSummary.supervisor_review_needed
      ? t("receiving.detailBlockedSupervisorReview", "Mixed package origins still need supervisor review")
      : null,
    packageSummary.packages_open
      ? t("receiving.detailBlockedPackagesOpen", "{count} packages are still open at dock", {
          count: String(packageSummary.packages_open || 0),
        })
      : null,
    packageSummary.internal_labels_print_pending
      ? t("receiving.detailBlockedPrintPending", "{count} internal labels still need printing", {
          count: String(packageSummary.internal_labels_print_pending || 0),
        })
      : null,
    packageSummary.packages_putaway_pending
      ? t("receiving.detailBlockedPutawayPending", "{count} packages still need putaway", {
          count: String(packageSummary.packages_putaway_pending || 0),
        })
      : null,
  ].filter(Boolean);
  const recommendedAction =
    unitsRemainingAtDock > 0 || packageSummary.packages_open > 0
      ? "receiving"
      : packageSummary.internal_labels_print_pending > 0
      ? "print"
      : packageSummary.packages_putaway_pending > 0
      ? "putaway"
      : "timeline";
  const focusedReceivingPackage = nextReceivingPackage(orderDetail);
  const focusedPrintPackage = nextPrintPackage(orderDetail);

  const order = orders.find((row: any) => row.id === orderId) || null;

  const persistReceivingFocus = (
    selectedOrder: any,
    options?: { target?: "package" | "print"; packageId?: string | null; packageNumber?: number | null },
  ) => {
    if (typeof window === "undefined" || !selectedOrder?.id) return;
    window.sessionStorage.setItem("receiving.selectedOrderId", selectedOrder.id);
    if (options?.target && options.packageId) {
      window.sessionStorage.setItem(
        "receiving.focusContext",
        JSON.stringify({
          source: "inbound-detail",
          orderId: selectedOrder.id,
          orderNumber: selectedOrder.order_number || null,
          referenceNumber: selectedOrder.reference_number || null,
          packageId: options.packageId,
          packageNumber: options.packageNumber || null,
          target: options.target,
        }),
      );
    } else {
      window.sessionStorage.removeItem("receiving.focusContext");
    }
  };

  useEffect(() => {
    if (!orderId || typeof window === "undefined") return;
    const raw = window.sessionStorage.getItem("receiving.inboundReturnNotice");
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw);
      if (parsed.orderId === orderId) {
        setReturnNotice({
          handlingUnitCode: parsed.handlingUnitCode || null,
          destinationBarcode: parsed.destinationBarcode || null,
          destinationCount: Number(parsed.destinationCount || 0),
        });
        window.sessionStorage.removeItem("receiving.inboundReturnNotice");
      }
    } catch {
      window.sessionStorage.removeItem("receiving.inboundReturnNotice");
    }
  }, [orderId]);

  const archiveMutation = useMutation({
    mutationFn: async ({ archived }: { archived: boolean }) =>
      archiveInboundOrder(orderId, archived).then((r) => r.data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.list() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.detail(orderId) });
    },
  });

  const voidMutation = useMutation({
    mutationFn: async () => voidInboundOrder(orderId).then((r) => r.data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.list() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.detail(orderId) });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async () => deleteInboundOrder(orderId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.list() });
      navigate("/receiving");
    },
  });

  if (!orderId) return null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-[#7f8d98]">
            {t("receiving.detailEyebrow", "Inbound order detail")}
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[#13212c]">
            {order?.order_number || t("receiving.detailLoadingTitle", "Loading inbound order")}
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to="/receiving"
            className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/10 bg-white px-4 py-2 text-sm font-semibold text-[#13212c]"
          >
            <ArrowLeft size={14} />
            {t("receiving.backToReceiving", "Back to receiving")}
          </Link>
        </div>
      </div>

      {order ? (
        <section className="rounded-[1.6rem] border border-[#13212c]/10 bg-white/90 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
                {order.archived
                  ? t("receiving.tableSelectionArchivedEyebrow", "Selected archived inbound")
                  : order.voided
                  ? t("receiving.tableSelectionVoidedEyebrow", "Selected voided inbound")
                  : order.status === "expected"
                  ? t("receiving.tableSelectionExpectedEyebrow", "Selected expected inbound")
                  : order.status === "receiving"
                  ? t("receiving.tableSelectionReceivingEyebrow", "Selected active receipt")
                  : t("receiving.tableSelectionManagedEyebrow", "Selected inbound order")}
              </p>
              <h2 className="mt-2 text-xl font-semibold text-[#13212c]">{order.order_number}</h2>
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="rounded-full border border-[#13212c]/8 bg-[#f8f5ef] px-3 py-1 text-xs font-medium text-[#51606b]">
                  {t("common.reference", "Reference")}: {order.reference_number || "—"}
                </span>
                {!order.can_delete && !order.can_void ? (
                  <span className="rounded-full border border-[#13212c]/8 bg-[#f8f5ef] px-3 py-1 text-xs font-medium text-[#51606b]">
                    {t("receiving.lifecycleLockHint", "Archive instead of delete once scans, labels, or downstream work exist.")}
                  </span>
                ) : null}
              </div>
            </div>
            <div className="flex flex-wrap items-start gap-3">
              <div>
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98]">
                  {t("common.status", "Status")}
                </p>
                <StatusBadge status={order.status} />
              </div>
              <div>
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98]">
                  {t("receiving.recordStateColumn", "Record state")}
                </p>
                <InboundOrderRecordStateBadge order={order} />
              </div>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap gap-3">
            {order.status === "expected" && canReceiveInbound && !order.archived ? (
              <button
                onClick={() => {
                  persistReceivingFocus(order);
                  navigate("/receiving");
                }}
                className="rounded-full bg-[#13212c] px-5 py-2 text-sm font-semibold text-[#f4efe8]"
              >
                {t("receiving.detailOpenReceivingAction", "Start receiving")}
              </button>
            ) : order.status === "receiving" && !order.archived ? (
              <button
                onClick={() => {
                  persistReceivingFocus(order, focusedReceivingPackage ? {
                    target: "package",
                    packageId: focusedReceivingPackage.id,
                    packageNumber: focusedReceivingPackage.package_number || null,
                  } : undefined);
                  navigate("/receiving");
                }}
                className="rounded-full bg-[#13212c] px-5 py-2 text-sm font-semibold text-[#f4efe8]"
              >
                {t("receiving.tableSelectionReceivingAction", "Continue receiving")}
              </button>
            ) : null}

            {order.can_archive ? (
              <button
                onClick={() => {
                  const archived = !order.archived;
                  const confirmed = window.confirm(
                    archived
                      ? t("receiving.confirmArchive", "Archive this inbound order and hide it from the default work queue?")
                      : t("receiving.confirmRestore", "Restore this inbound order to the default work queue?"),
                  );
                  if (!confirmed) return;
                  archiveMutation.mutate({ archived });
                }}
                disabled={archiveMutation.isPending}
                className="rounded-full border border-[#13212c]/12 bg-white px-4 py-2 text-sm font-semibold text-[#13212c] disabled:opacity-50"
              >
                {order.archived ? t("receiving.restoreOrderAction", "Restore order") : t("receiving.archiveOrderAction", "Archive order")}
              </button>
            ) : null}

            {order.can_void ? (
              <button
                onClick={() => {
                  const confirmed = window.confirm(
                    t("receiving.confirmVoid", "Void this inbound order? This keeps the audit trail but removes it from active receiving work."),
                  );
                  if (!confirmed) return;
                  voidMutation.mutate();
                }}
                disabled={voidMutation.isPending}
                className="rounded-full border border-[#b98383] bg-[#fff7f7] px-4 py-2 text-sm font-semibold text-[#8d2f2f] disabled:opacity-50"
              >
                {t("receiving.voidOrderAction", "Void order")}
              </button>
            ) : null}

            {order.can_delete ? (
              <button
                onClick={() => {
                  const confirmed = window.confirm(
                    t("receiving.confirmDelete", "Delete this inbound order permanently? Only use this for clean orders that never entered receiving."),
                  );
                  if (!confirmed) return;
                  deleteMutation.mutate();
                }}
                disabled={deleteMutation.isPending}
                className="rounded-full border border-[#b98383] bg-white px-4 py-2 text-sm font-semibold text-[#8d2f2f] disabled:opacity-50"
              >
                {t("receiving.deleteOrderAction", "Delete permanently")}
              </button>
            ) : null}
          </div>
        </section>
      ) : (
        <section className="rounded-[1.6rem] border border-[#13212c]/10 bg-white/90 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
          <p className="text-sm text-[#61717d]">{t("receiving.detailOrderMissing", "This inbound order is no longer visible in the current list. It may have been deleted or moved out of tenant scope.")}</p>
        </section>
      )}

      {returnNotice ? (
        <section className="rounded-[1.4rem] border border-[#c8dfd1] bg-[#eef8f0] px-5 py-4 shadow-[0_18px_44px_rgba(19,33,44,0.04)]">
          <p className="text-[11px] uppercase tracking-[0.2em] text-[#4f7b61]">
            {t("receiving.returnNoticeEyebrow", "Returned from putaway")}
          </p>
          <p className="mt-2 text-sm font-semibold text-[#163424]">
            {returnNotice.destinationCount && returnNotice.destinationCount > 1
              ? t(
                  "receiving.returnNoticeMultiDestination",
                  "Handling unit {unit} was split across {count} final storage locations.",
                  {
                    unit: returnNotice.handlingUnitCode || "—",
                    count: String(returnNotice.destinationCount),
                  },
                )
              : t(
                  "receiving.returnNoticeSingleDestination",
                  "Handling unit {unit} was moved into {destination}.",
                  {
                    unit: returnNotice.handlingUnitCode || "—",
                    destination: returnNotice.destinationBarcode || "—",
                  },
                )}
          </p>
        </section>
      ) : null}

      <section className="grid gap-3 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div className="rounded-[1.4rem] border border-[#13212c]/8 bg-white/90 px-5 py-4 shadow-[0_18px_44px_rgba(19,33,44,0.04)]">
          <p className="text-[11px] uppercase tracking-[0.2em] text-[#7f8d98]">
            {t("receiving.detailLastChangedEyebrow", "What changed last")}
          </p>
          <p className="mt-2 text-sm font-semibold text-[#13212c]">
            {lastTimelineEvent?.title || t("receiving.detailLastChangedEmpty", "No lifecycle events recorded yet")}
          </p>
          {lastTimelineEvent?.detail ? <p className="mt-1 text-sm text-[#61717d]">{lastTimelineEvent.detail}</p> : null}
          <p className="mt-2 text-xs font-medium text-[#58718a]">
            {t("receiving.detailLastChangedWhen", "Latest activity: {timeAgo}", {
              timeAgo: formatTimelineTimeAgo(lastTimelineEvent?.occurred_at, t),
            })}
          </p>
        </div>

        <div className="rounded-[1.4rem] border border-[#13212c]/8 bg-[#f8f5ef] px-5 py-4 shadow-[0_18px_44px_rgba(19,33,44,0.04)]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-[11px] uppercase tracking-[0.2em] text-[#7f8d98]">
                {t("receiving.detailBlockedEyebrow", "What is still blocked")}
              </p>
              <p className="mt-2 text-sm font-semibold text-[#13212c]">
                {blockers.length
                  ? t("receiving.detailBlockedTitle", "This order still has package work to close")
                  : t("receiving.detailBlockedClear", "No package blockers are active right now")}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {(blockers.length ? blockers : [t("receiving.detailBlockedClearBody", "Receiving, printing, and putaway are all caught up for this inbound order.")]).map(
                  (item) => (
                    <span
                      key={item}
                      className="rounded-full border border-[#13212c]/8 bg-white px-3 py-1.5 text-xs font-medium text-[#51606b]"
                    >
                      {item}
                    </span>
                  ),
                )}
              </div>
            </div>

            {recommendedAction === "putaway" ? (
              <Link
                to="/putaway"
                onClick={() => {
                  if (typeof window === "undefined") return;
                  window.sessionStorage.setItem(
                    "putaway.focusContext",
                    JSON.stringify({
                      source: "inbound-detail-summary",
                      orderId: order?.id || null,
                      orderNumber: order?.order_number || null,
                      referenceNumber: order?.reference_number || null,
                    }),
                  );
                }}
                className="rounded-full bg-[#24507a] px-4 py-2 text-sm font-semibold text-white"
              >
                {t("receiving.detailBlockedPutawayAction", "Open putaway")}
              </Link>
            ) : recommendedAction === "receiving" || recommendedAction === "print" ? (
              <button
                type="button"
                onClick={() => {
                  if (!order) return;
                  const targetPackage = recommendedAction === "print" ? focusedPrintPackage : focusedReceivingPackage;
                  persistReceivingFocus(order, targetPackage ? {
                    target: recommendedAction === "print" ? "print" : "package",
                    packageId: targetPackage.id,
                    packageNumber: targetPackage.package_number || null,
                  } : undefined);
                  navigate("/receiving");
                }}
                className="rounded-full bg-[#24507a] px-4 py-2 text-sm font-semibold text-white"
              >
                {recommendedAction === "print"
                  ? t("receiving.detailBlockedPrintAction", "Open print-ready labels")
                  : t("receiving.detailBlockedReceivingAction", "Continue receiving")}
              </button>
            ) : (
              <a
                href="#timeline"
                className="rounded-full border border-[#13212c]/10 bg-white px-4 py-2 text-sm font-semibold text-[#13212c]"
              >
                {t("receiving.detailBlockedTimelineAction", "Review timeline")}
              </a>
            )}
          </div>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <DetailMetricCard
          label={t("receiving.packageMetricOpen", "Packages still open")}
          value={packageSummary.packages_open || 0}
        />
        <DetailMetricCard
          label={t("receiving.packageMetricPutaway", "Packages awaiting putaway")}
          value={packageSummary.packages_putaway_pending || 0}
        />
        <DetailMetricCard
          label={t("receiving.packageMetricPrint", "Internal labels to print")}
          value={packageSummary.internal_labels_print_pending || 0}
        />
        <DetailMetricCard
          label={t("receiving.packageMetricStored", "Packages in final storage")}
          value={packageSummary.packages_stored || 0}
        />
      </section>

      <div id="timeline">
        <InboundOrderLifecycleTimeline timeline={orderDetail?.timeline || []} />
      </div>

      <InboundOrderHistoryPanel detail={orderDetail} isLoading={isLoading} orderId={order?.id || null} />

      {!isLoading && orderDetail ? (
        <InboundOrderDownstreamPanel
          detail={orderDetail}
          orderId={order?.id || null}
          orderNumber={order?.order_number || null}
          referenceNumber={order?.reference_number || null}
        />
      ) : null}

      <div className="rounded-[1.4rem] border border-[#13212c]/8 bg-white/80 px-5 py-4 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.2em] text-[#7f8d98]">
              {t("receiving.detailNextEyebrow", "Next move")}
            </p>
          </div>
          <Link
            to="/receiving"
            className="inline-flex items-center gap-2 rounded-full bg-[#13212c] px-4 py-2 text-sm font-semibold text-[#f4efe8]"
          >
            {t("receiving.backToReceiving", "Back to receiving")}
            <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </div>
  );
}

function DetailMetricCard({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-white/90 px-4 py-4 shadow-[0_12px_32px_rgba(19,33,44,0.04)]">
      <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">{label}</p>
      <p className="mt-2 text-lg font-semibold text-[#13212c]">{value}</p>
    </div>
  );
}
