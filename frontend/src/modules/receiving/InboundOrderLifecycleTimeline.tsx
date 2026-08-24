import { useMemo, useState } from "react";
import { Clock3, PackageCheck, PackageSearch, Printer, Archive, Ban, ArrowRightLeft, PlayCircle } from "lucide-react";
import { useI18n } from "../../shared/i18n";

const EVENT_ICON_MAP: Record<string, any> = {
  order_created: Clock3,
  expected_arrival: Clock3,
  receiving_started: PlayCircle,
  external_code_captured: PackageSearch,
  internal_label_issued: PackageCheck,
  internal_label_printed: Printer,
  receiving_completed: PackageCheck,
  putaway_task_created: ArrowRightLeft,
  putaway_task_started: ArrowRightLeft,
  putaway_task_completed: PackageCheck,
  order_archived: Archive,
  order_voided: Ban,
};

export default function InboundOrderLifecycleTimeline({ timeline = [] }: { timeline?: any[] }) {
  const { t } = useI18n();
  const [activeFilter, setActiveFilter] = useState<"all" | "dock" | "labels" | "downstream" | "lifecycle">("all");

  const filterDefinitions = useMemo(
    () => [
      {
        id: "all" as const,
        label: t("receiving.detailTimelineFilterAll", "All events"),
        match: (_event: any) => true,
      },
      {
        id: "dock" as const,
        label: t("receiving.detailTimelineFilterDock", "Dock intake"),
        match: (event: any) =>
          ["expected_arrival", "receiving_started", "external_code_captured", "receiving_completed"].includes(event.event_type),
      },
      {
        id: "labels" as const,
        label: t("receiving.detailTimelineFilterLabels", "Internal labels"),
        match: (event: any) => ["internal_label_issued", "internal_label_printed"].includes(event.event_type),
      },
      {
        id: "downstream" as const,
        label: t("receiving.detailTimelineFilterDownstream", "Downstream work"),
        match: (event: any) =>
          ["putaway_task_created", "putaway_task_started", "putaway_task_completed"].includes(event.event_type),
      },
      {
        id: "lifecycle" as const,
        label: t("receiving.detailTimelineFilterLifecycle", "Lifecycle status"),
        match: (event: any) => ["order_created", "order_archived", "order_voided"].includes(event.event_type),
      },
    ],
    [t]
  );

  const filteredTimeline = useMemo(() => {
    const current = filterDefinitions.find((filter) => filter.id === activeFilter);
    return current ? timeline.filter(current.match) : timeline;
  }, [activeFilter, filterDefinitions, timeline]);

  return (
    <section className="rounded-[1.6rem] border border-[#13212c]/10 bg-white/90 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
            {t("receiving.detailTimelineEyebrow", "Lifecycle timeline")}
          </p>
          <h2 className="mt-2 text-lg font-semibold text-[#13212c]">
            {t("receiving.detailTimelineTitle", "See the inbound order move from dock intake into downstream work")}
          </h2>
        </div>
        {timeline.length ? (
          <div className="flex flex-wrap items-center gap-2">
            {filterDefinitions.map((filter) => {
              const count = timeline.filter(filter.match).length;
              const active = filter.id === activeFilter;
              return (
                <button
                  key={filter.id}
                  type="button"
                  onClick={() => setActiveFilter(filter.id)}
                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                    active
                      ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                      : "border-[#13212c]/10 bg-white text-[#51606b]"
                  }`}
                >
                  {filter.label} · {count}
                </button>
              );
            })}
          </div>
        ) : null}
      </div>

      {filteredTimeline.length ? (
        <div className="mt-5 space-y-3">
          {filteredTimeline.map((event, index) => {
            const Icon = EVENT_ICON_MAP[event.event_type] || Clock3;
            return (
              <div key={`${event.event_type}-${event.occurred_at}-${index}`} className="flex gap-3 rounded-[1.2rem] border border-[#13212c]/8 bg-[#faf7f2] px-4 py-4">
                <div className="mt-0.5 rounded-2xl border border-[#13212c]/10 bg-white p-2 text-[#51606b]">
                  <Icon size={16} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-[#13212c]">{event.title}</p>
                    <span className="rounded-full bg-[#f0ebe2] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#6c7a86]">
                      {event.occurred_at || "—"}
                    </span>
                  </div>
                  {event.detail ? <p className="mt-1.5 text-sm leading-6 text-[#61717d]">{event.detail}</p> : null}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="mt-4 text-sm text-[#61717d]">
          {timeline.length
            ? t("receiving.detailTimelineEmptyFiltered", "No events match this filter yet.")
            : t("receiving.detailTimelineEmpty", "No lifecycle events have been recorded for this inbound order yet.")}
        </p>
      )}
    </section>
  );
}
