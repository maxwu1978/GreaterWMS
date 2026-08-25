import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CalendarClock, Maximize2, Minus, Plus, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { fetchOperationsBoard, type OperationsBoardItem, type OperationsBoardLane, type OperationsBoardResponse } from "../../shared/api/operationsBoard";
import { GreaterWmsTable, GreaterWmsTableCell, GreaterWmsTableHeader, GreaterWmsTableHeaderCell, GreaterWmsTableMobileHeader, GreaterWmsTableRow } from "../../shared/components/GreaterWmsTable";
import { queryKeys } from "../../shared/api/queryKeys";
import { isGreaterWmsPreviewMode } from "../../shared/previewMode";

type BoardFilter = "all" | "urgent" | OperationsBoardLane;

const OPERATIONS_TABLE_COLUMNS = "218px 190px 220px minmax(190px,1fr) 165px 200px 100px 170px 48px";
const OPERATIONS_TABLE_MIN_WIDTH = 1180;

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

function quantityLabel(item: OperationsBoardItem): string {
  if (item.quantity_progress === null || item.quantity_progress === undefined) {
    return item.quantity ? item.quantity.toLocaleString() : "-";
  }
  return `${item.quantity_progress.toLocaleString()} / ${item.quantity.toLocaleString()}`;
}

function BoardRow({ item, rowIndex }: { item: OperationsBoardItem; rowIndex: number }) {
  const meta = laneMeta[item.lane];
  const category = String(item.category || item.reference_type || "Work").toUpperCase();
  const nextAction = operationLabels[item.operation] || item.operation || "Review";
  const urgency = item.lane === "delayed" ? "Overdue" : meta.shortLabel;
  return (
    <>
      <GreaterWmsTableRow columns={OPERATIONS_TABLE_COLUMNS} minWidth={OPERATIONS_TABLE_MIN_WIDTH} stripe={rowIndex % 2 === 1 ? "alternate" : "base"}>
        <GreaterWmsTableCell>
          <div className="flex items-center gap-2 whitespace-nowrap">
            <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${meta.dotClassName}`} />
            <span className="font-semibold">{formatDueAt(item.due_at)}</span>
            <span className={`inline-flex border px-1.5 py-0.5 text-[10px] font-semibold ${meta.className}`}>{urgency}</span>
          </div>
          {item.lane === "delayed" ? <p className="mt-1 text-[11px] font-semibold text-[#9a3f38]">Action overdue</p> : null}
        </GreaterWmsTableCell>
        <GreaterWmsTableCell>
          <p className="truncate font-semibold" title={item.client_name || item.client_id || "Warehouse"}>{item.client_name || item.client_id || "Warehouse"}</p>
        </GreaterWmsTableCell>
        <GreaterWmsTableCell>
          <div className="flex min-w-0 items-center gap-2">
            <span className="shrink-0 border border-[#9db7d6] bg-[#eef4fc] px-1.5 py-0.5 text-[10px] font-semibold text-[#345d8e]">{category}</span>
            <span className="truncate font-mono font-semibold text-[#202020]" title={item.reference_number}>{item.reference_number || item.reference_id}</span>
          </div>
        </GreaterWmsTableCell>
        <GreaterWmsTableCell>
          <p className="truncate font-semibold" title={nextAction}>{nextAction}</p>
        </GreaterWmsTableCell>
        <GreaterWmsTableCell>
          <p className="truncate" title={item.assigned_to || item.assigned_type || "Warehouse"}>{item.assigned_to || item.assigned_type || "Warehouse"}</p>
        </GreaterWmsTableCell>
        <GreaterWmsTableCell><p className="truncate" title={item.location_label || "Location not assigned"}>{item.location_label || "Location not assigned"}</p></GreaterWmsTableCell>
        <GreaterWmsTableCell className="whitespace-nowrap text-right font-mono text-xs text-[#444]">{quantityLabel(item)}</GreaterWmsTableCell>
        <GreaterWmsTableCell><span className={`inline-flex border px-2 py-1 text-[11px] font-semibold ${meta.className}`}>{meta.label}</span></GreaterWmsTableCell>
        <GreaterWmsTableCell className="flex items-center justify-center px-2"><Link to={item.action_route} aria-label={`Open ${item.reference_number || item.reference_id}`} className="inline-flex min-h-8 items-center justify-center text-[#4c5d82] hover:text-[#1976d2]"><ArrowRight size={16} /></Link></GreaterWmsTableCell>
      </GreaterWmsTableRow>

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

const previewOperationsData: OperationsBoardResponse = {
  generated_at: "2026-08-25T11:44:00Z",
  warehouse_id: "PEAK SMART LOGISTICS",
  counts: { total: 1, now: 0, next: 0, delayed: 1, blocked: 0, by_operation: { receiving: 1 } },
  items: [{
    id: "preview-inbound-001",
    category: "Inbound",
    operation: "receiving",
    lane: "delayed",
    source_status: "awaiting_arrival",
    reference_type: "ASN",
    reference_id: "preview-asn-240824-01",
    reference_number: "ASN2...8191",
    client_id: "delta",
    client_name: "Delta",
    priority: 1,
    due_at: "2026-08-25T05:00:00Z",
    created_at: "2026-08-24T11:38:00Z",
    quantity: 18,
    quantity_progress: 0,
    location_label: "DOCK → STG",
    assigned_type: "Warehouse",
    assigned_to: "Warehouse",
    action_key: "receiving",
    action_route: "/receiving",
    blocker_code: null,
  }],
};

export default function OperationsBoard() {
  const [filter, setFilter] = useState<BoardFilter>("all");
  const previewMode = isGreaterWmsPreviewMode();
  const { data: fetchedData, isLoading: fetchedLoading, isError, refetch, isFetching } = useQuery({
    queryKey: queryKeys.operationsBoard(),
    queryFn: fetchOperationsBoard,
    enabled: !previewMode,
    refetchInterval: previewMode ? false : 30_000,
  });
  const data = previewMode ? previewOperationsData : fetchedData;
  const isLoading = !previewMode && fetchedLoading;

  const items = data?.items || [];
  const visibleItems = filter === "all"
    ? items
    : filter === "urgent"
      ? items.filter((item) => item.lane === "delayed")
      : items.filter((item) => item.lane === filter);
  const filterItems: Array<{ key: BoardFilter; label: string; count: number }> = [
    { key: "all", label: "All", count: data?.counts.total || 0 },
    { key: "urgent", label: "Urgent", count: data?.counts.delayed || 0 },
    { key: "now", label: "In Progress", count: data?.counts.now || 0 },
    { key: "next", label: "Pending", count: data?.counts.next || 0 },
    { key: "delayed", label: "Delayed", count: data?.counts.delayed || 0 },
    { key: "blocked", label: "Exception", count: data?.counts.blocked || 0 },
  ];

  return (
    <section className="w-full border border-[#d7d7d7] bg-white shadow-[0_4px_14px_rgba(0,0,0,0.22)]" data-testid="operations-board" aria-label="Live warehouse operations board">
      <div className="flex min-h-12 items-center gap-3 bg-[#596782] px-3 text-white sm:px-4">
        <h2 className="text-[16px] font-bold uppercase tracking-[0.08em]">Warehouse Operations</h2>
        <div className="ml-auto flex items-center gap-2 text-[11px]">
          <span className="hidden text-[#e8edf7] sm:inline">{data?.warehouse_id || ""}</span>
          <span className="font-bold tracking-[0.12em] text-[#8ee3a7]">LIVE</span>
          <button type="button" aria-label="Zoom out" className="inline-flex h-7 w-7 items-center justify-center hover:bg-white/10"><Minus size={16} /></button>
          <span className="min-w-10 text-center font-bold">100%</span>
          <button type="button" aria-label="Zoom in" className="inline-flex h-7 w-7 items-center justify-center hover:bg-white/10"><Plus size={16} /></button>
          <button type="button" aria-label="Refresh" onClick={() => void refetch()} className="inline-flex h-7 w-7 items-center justify-center hover:bg-white/10"><RefreshCw size={16} className={isFetching ? "animate-spin" : undefined} /></button>
          <button type="button" aria-label="Fullscreen" className="inline-flex h-7 w-7 items-center justify-center hover:bg-white/10"><Maximize2 size={16} /></button>
        </div>
      </div>

      <div className="flex min-h-10 items-center border-b border-[#dfe3ea] px-3 sm:px-4">
        <div className="flex h-10 items-center gap-6 text-[14px] font-semibold uppercase">
          <button type="button" className="relative h-full px-1 text-[#1976d2] after:absolute after:bottom-0 after:left-0 after:right-0 after:h-[3px] after:bg-[#1976d2]">Active</button>
          <button type="button" className="h-full px-1 text-[#333]">History</button>
        </div>
        <div className="ml-auto flex items-center gap-3 text-[11px] font-bold uppercase">
          <span className="text-[#667085]">Total {data?.counts.total || 0}</span>
          <span className="text-[#b54708]">Urgent {data?.counts.delayed || 0}</span>
          <span className="text-[#b42318]">Exception {data?.counts.blocked || 0}</span>
        </div>
      </div>

      <div className="flex min-h-10 items-center overflow-x-auto border-b border-[#dfe3ea] bg-[#f5f6f8] px-3 sm:px-4">
        <div className="flex h-10 items-center gap-0">
          {filterItems.map((item) => (
            <button
              key={item.key}
              type="button"
              aria-pressed={filter === item.key}
              onClick={() => setFilter(item.key)}
              className={`relative h-full whitespace-nowrap px-3 text-[14px] font-semibold uppercase transition ${filter === item.key ? "text-[#1976d2] after:absolute after:bottom-0 after:left-0 after:right-0 after:h-[3px] after:bg-[#1976d2]" : "text-[#333] hover:text-[#1976d2]"}`}
            >
              {item.label}
            </button>
          ))}
        </div>
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
        <GreaterWmsTable>
          <GreaterWmsTableHeader columns={OPERATIONS_TABLE_COLUMNS} minWidth={OPERATIONS_TABLE_MIN_WIDTH}>
            <GreaterWmsTableHeaderCell>ETA / Urgency</GreaterWmsTableHeaderCell>
            <GreaterWmsTableHeaderCell>Owner / Customer</GreaterWmsTableHeaderCell>
            <GreaterWmsTableHeaderCell>Ref / Type</GreaterWmsTableHeaderCell>
            <GreaterWmsTableHeaderCell>Next Step</GreaterWmsTableHeaderCell>
            <GreaterWmsTableHeaderCell>Assigned To</GreaterWmsTableHeaderCell>
            <GreaterWmsTableHeaderCell>Move</GreaterWmsTableHeaderCell>
            <GreaterWmsTableHeaderCell>Qty</GreaterWmsTableHeaderCell>
            <GreaterWmsTableHeaderCell>Work Status</GreaterWmsTableHeaderCell>
            <GreaterWmsTableHeaderCell />
          </GreaterWmsTableHeader>
          <GreaterWmsTableMobileHeader columns="76px 70px minmax(0,1fr) 54px" minWidth={0}>
            <span className="px-2 py-2.5">Status</span>
            <span className="px-2 py-2.5">Time</span>
            <span className="px-2 py-2.5">Work</span>
            <span className="px-2 py-2.5">Go</span>
          </GreaterWmsTableMobileHeader>
          {visibleItems.map((item, rowIndex) => <BoardRow key={item.id} item={item} rowIndex={rowIndex} />)}
        </GreaterWmsTable>
      )}

    </section>
  );
}
