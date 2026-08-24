import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CalendarClock, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { fetchOperationsBoard, type OperationsBoardItem, type OperationsBoardLane } from "../../shared/api/operationsBoard";
import { queryKeys } from "../../shared/api/queryKeys";

type BoardFilter = "all" | OperationsBoardLane;

const laneOrder: OperationsBoardLane[] = ["blocked", "delayed", "now", "next"];

const operationLabels: Record<string, string> = {
  receiving: "Receiving",
  unload: "Unload",
  putaway: "Putaway",
  picking: "Picking",
  shipping: "Shipping",
  load: "Load",
  move: "Move",
  replenish: "Replenish",
  cycle_count: "Cycle count",
};

const laneMeta: Record<OperationsBoardLane, { label: string; shortLabel: string; className: string; dotClassName: string }> = {
  blocked: {
    label: "Blocked",
    shortLabel: "HOLD",
    className: "border-[#d69a93] bg-[#fff1ef] text-[#9a3f38]",
    dotClassName: "bg-[#c9574f]",
  },
  delayed: {
    label: "Delayed",
    shortLabel: "LATE",
    className: "border-[#e3bd73] bg-[#fff8e8] text-[#99651d]",
    dotClassName: "bg-[#d79828]",
  },
  now: {
    label: "Now",
    shortLabel: "NOW",
    className: "border-[#9db7d6] bg-[#eef4fc] text-[#345d8e]",
    dotClassName: "bg-[#4b83bd]",
  },
  next: {
    label: "Next",
    shortLabel: "NEXT",
    className: "border-[#b7b7b7] bg-[#f5f5f5] text-[#555]",
    dotClassName: "bg-[#828282]",
  },
};

function formatDueAt(value: string | null | undefined): string {
  if (!value) return "ASAP";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "ASAP";
  return date.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function formatUpdatedAt(value: string | undefined): string {
  if (!value) return "--:--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return date.toLocaleTimeString(undefined, { hour12: false });
}

function quantityLabel(item: OperationsBoardItem): string {
  if (item.quantity_progress === null || item.quantity_progress === undefined) {
    return item.quantity ? item.quantity.toLocaleString() : "-";
  }
  return `${item.quantity_progress.toLocaleString()} / ${item.quantity.toLocaleString()}`;
}

function BoardRow({ item }: { item: OperationsBoardItem }) {
  const meta = laneMeta[item.lane];
  return (
    <>
      <div className="hidden min-w-[940px] grid-cols-[132px_112px_148px_minmax(220px,1.3fr)_minmax(200px,1fr)_128px_100px] items-center border-t border-[#dedede] text-[13px] odd:bg-white even:bg-[#fafafa] hover:bg-[#f1f4f8] sm:grid">
        <div className="flex items-center gap-2 px-3 py-4">
          <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${meta.dotClassName}`} />
          <span className={`inline-flex border px-2 py-1 text-[10px] font-bold tracking-[0.12em] ${meta.className}`}>
            {meta.shortLabel}
          </span>
        </div>
        <div className="border-l border-[#e6e6e6] px-3 py-4 font-mono text-xs text-[#444]">
          <p className="font-semibold">{formatDueAt(item.due_at)}</p>
        </div>
        <div className="border-l border-[#e6e6e6] px-3 py-4 font-semibold text-[#252525]">
          {operationLabels[item.operation] || item.operation}
        </div>
        <div className="min-w-0 border-l border-[#e6e6e6] px-3 py-4">
          <p className="truncate font-mono font-semibold text-[#202020]">{item.reference_number}</p>
        </div>
        <div className="min-w-0 border-l border-[#e6e6e6] px-3 py-4">
          <p className="truncate text-[#383838]">{item.location_label || "Location not assigned"}</p>
        </div>
        <p className="whitespace-nowrap border-l border-[#e6e6e6] px-3 py-4 font-mono text-xs text-[#444]">{quantityLabel(item)}</p>
        <Link
          to={item.action_route}
          className="mx-3 inline-flex min-h-8 items-center justify-center gap-1 border border-[#9aa4bb] bg-white px-2 text-[11px] font-semibold text-[#4c5d82] transition hover:border-[#5d6b8b] hover:bg-[#5d6b8b] hover:text-white"
        >
          Open
          <ArrowRight size={12} />
        </Link>
      </div>

      <div className="border-t border-[#dedede] bg-white text-[12px] sm:hidden">
        <div className="grid grid-cols-[76px_70px_minmax(0,1fr)_54px] items-center">
          <div className="flex items-center gap-1.5 px-2 py-3">
            <span className={`h-2 w-2 shrink-0 rounded-full ${meta.dotClassName}`} />
            <span className={`border px-1 py-1 text-[9px] font-bold tracking-[0.08em] ${meta.className}`}>
              {meta.shortLabel}
            </span>
          </div>
          <p className="border-l border-[#e6e6e6] px-2 py-3 font-mono text-[10px] font-semibold text-[#444]">{formatDueAt(item.due_at)}</p>
          <div className="min-w-0 border-l border-[#e6e6e6] px-2 py-3">
            <p className="font-semibold text-[#252525]">{operationLabels[item.operation] || item.operation}</p>
            <p className="truncate font-mono text-[10px] text-[#777]">{item.reference_number}</p>
          </div>
          <Link
            to={item.action_route}
            aria-label={`Open ${operationLabels[item.operation] || item.operation}`}
            className="mx-1 inline-flex min-h-7 items-center justify-center border border-[#9aa4bb] bg-white text-[#4c5d82]"
          >
            <ArrowRight size={13} />
          </Link>
        </div>
        <div className="flex items-center justify-between border-t border-[#eeeeee] px-3 py-2 text-[10px] text-[#777]">
          <span className="truncate">{item.location_label || "Location not assigned"}</span>
          <span className="ml-3 shrink-0 font-mono">{quantityLabel(item)}</span>
        </div>
      </div>
    </>
  );
}

export default function OperationsBoard() {
  const [filter, setFilter] = useState<BoardFilter>("all");
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: queryKeys.operationsBoard(),
    queryFn: fetchOperationsBoard,
    refetchInterval: 30_000,
  });

  const items = data?.items || [];
  const visibleItems = filter === "all" ? items : items.filter((item) => item.lane === filter);
  const filterItems: Array<{ key: BoardFilter; label: string; count: number }> = [
    { key: "all", label: "All work", count: data?.counts.total || 0 },
    { key: "now", label: "Now", count: data?.counts.now || 0 },
    { key: "next", label: "Next", count: data?.counts.next || 0 },
    { key: "delayed", label: "Delayed", count: data?.counts.delayed || 0 },
    { key: "blocked", label: "Blocked", count: data?.counts.blocked || 0 },
  ];

  return (
    <section className="block border border-[#cfcfcf] bg-white shadow-[0_4px_14px_rgba(0,0,0,0.08)]" data-testid="operations-board" aria-label="Live warehouse operations board">
      <div className="bg-[#303b5b] text-white">
        <div className="flex flex-wrap items-end justify-between gap-5 px-5 py-5 sm:px-6">
          <div>
            <div className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-[#c9d1e0]">
              <span className="h-2 w-2 animate-pulse rounded-full bg-[#70d19a]" />
              Live operations board
            </div>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">Warehouse Operations</h2>
          </div>
          <div className="grid grid-cols-4 divide-x divide-white/20 border border-white/20 bg-white/5">
            {laneOrder.map((lane) => (
              <div key={lane} className="min-w-[74px] px-3 py-2 text-center">
                <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-[#cbd3df]">{laneMeta[lane].label}</p>
                <p className="mt-1 font-mono text-xl font-bold">{data?.counts[lane] || 0}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/15 px-5 py-2.5 text-[11px] sm:px-6">
          <span className="font-mono uppercase tracking-[0.14em] text-[#cbd3df]">Queue / {data?.counts.total || 0}</span>
          <span className="font-mono text-[#cbd3df]">LAST UPDATE {formatUpdatedAt(data?.generated_at)}</span>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#d6d6d6] bg-[#f7f7f7] px-4 py-3 sm:px-5">
        <div className="flex flex-wrap items-center gap-1.5">
          {filterItems.map((item) => (
            <button
              key={item.key}
              type="button"
              aria-pressed={filter === item.key}
              onClick={() => setFilter(item.key)}
              className={`inline-flex items-center gap-2 border px-3 py-1.5 text-xs font-semibold transition ${filter === item.key ? "border-[#5d6b8b] bg-[#5d6b8b] text-white" : "border-[#d0d0d0] bg-white text-[#555] hover:border-[#9aa4bb]"}`}
            >
              {item.label.replace("All work", "All")}
              <span className={`font-mono text-[10px] ${filter === item.key ? "text-white/80" : "text-[#888]"}`}>{item.count}</span>
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => void refetch()}
          className="inline-flex items-center gap-2 border border-[#d0d0d0] bg-white px-3 py-1.5 text-xs font-semibold text-[#555] transition hover:border-[#9aa4bb] hover:text-[#304060]"
        >
          <RefreshCw size={13} className={isFetching ? "animate-spin" : undefined} />
          Refresh
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-3 px-6 py-12 text-sm text-[#777]">
          <RefreshCw size={16} className="animate-spin" />
          Loading operational queue...
        </div>
      ) : isError ? (
        <div className="flex items-center gap-3 px-6 py-12 text-sm text-[#9a3f38]">
          <AlertTriangle size={17} />
          The operational queue is temporarily unavailable.
        </div>
      ) : visibleItems.length === 0 ? (
        <div className="flex items-center gap-3 px-6 py-12 text-sm text-[#777]">
          <CalendarClock size={17} />
          No work matches this board filter.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <div className="hidden min-w-[940px] grid-cols-[132px_112px_148px_minmax(220px,1.3fr)_minmax(200px,1fr)_128px_100px] bg-[#eef0f4] text-[10px] font-bold uppercase tracking-[0.12em] text-[#626a77] sm:grid">
            <span className="px-3 py-3">Status</span>
            <span className="border-l border-[#d7dbe2] px-3 py-3">Time</span>
            <span className="border-l border-[#d7dbe2] px-3 py-3">Operation</span>
            <span className="border-l border-[#d7dbe2] px-3 py-3">Reference</span>
            <span className="border-l border-[#d7dbe2] px-3 py-3">Location</span>
            <span className="border-l border-[#d7dbe2] px-3 py-3">Qty</span>
            <span className="border-l border-[#d7dbe2] px-3 py-3">Action</span>
          </div>
          <div className="grid grid-cols-[76px_70px_minmax(0,1fr)_54px] bg-[#eef0f4] text-[9px] font-bold uppercase tracking-[0.1em] text-[#626a77] sm:hidden">
            <span className="px-2 py-2.5">Status</span>
            <span className="border-l border-[#d7dbe2] px-2 py-2.5">Time</span>
            <span className="border-l border-[#d7dbe2] px-2 py-2.5">Work</span>
            <span className="border-l border-[#d7dbe2] px-2 py-2.5">Go</span>
          </div>
          {visibleItems.map((item) => <BoardRow key={item.id} item={item} />)}
        </div>
      )}

      <div className="border-t border-[#d6d6d6] bg-[#fafafa] px-4 py-2.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#888] sm:px-5">
        Auto refresh 30s
      </div>
    </section>
  );
}
