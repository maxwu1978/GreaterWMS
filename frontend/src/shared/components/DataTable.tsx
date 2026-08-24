import { type ReactNode } from "react";
import { useI18n } from "../i18n";
import EmptyStatePanel from "./EmptyStatePanel";

interface Column<T> {
  key: string;
  header: string;
  render?: (row: T, index: number) => ReactNode;
  className?: string;
  sortable?: boolean;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  loading?: boolean;
  emptyMessage?: string;
  emptyTitle?: string;
  emptyHint?: string;
  emptyActionLabel?: string;
  emptyActionHref?: string;
  onRowClick?: (row: T) => void;
  onHeaderClick?: (key: string) => void;
  rowClassName?: (row: T, index: number) => string;
  sortField?: string | null;
  sortDirection?: "asc" | "desc";
  mobileDetailLimit?: number;
}

export default function DataTable<T extends Record<string, any>>({
  columns,
  data,
  loading = false,
  emptyMessage,
  emptyTitle,
  emptyHint,
  emptyActionLabel,
  emptyActionHref,
  onRowClick,
  onHeaderClick,
  rowClassName,
  sortField,
  sortDirection = "asc",
  mobileDetailLimit = 4,
}: DataTableProps<T>) {
  const { t } = useI18n();
  const resolvedEmptyMessage = emptyMessage || t("common.noDataFound", "No data found");
  const resolvedEmptyTitle = emptyTitle || t("common.emptyState", "Empty state");
  const mobileColumns = columns.filter((column) => column.key !== "__row_number");
  const mobileTitleColumn = mobileColumns[0] ?? columns[0];
  const mobileDetailColumns = mobileColumns.slice(1);
  const primaryMobileDetailColumns = mobileDetailColumns.slice(0, Math.max(0, mobileDetailLimit));
  const secondaryMobileDetailColumns = mobileDetailColumns.slice(Math.max(0, mobileDetailLimit));
  const sortableColumns = columns.filter((column) => column.sortable);
  const renderCell = (row: T, col: Column<T>, index: number) => (col.render ? col.render(row, index) : row[col.key]);
  const emptyContent = (
    <EmptyStatePanel
      title={resolvedEmptyTitle}
      message={resolvedEmptyMessage}
      hint={emptyHint}
      actionLabel={emptyActionLabel}
      actionHref={emptyActionHref}
    />
  );

  if (loading) {
    return (
      <div className="overflow-hidden rounded-[1.8rem] border border-[#13212c]/10 bg-white/80 p-8 text-center text-[#7f8e98] shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
        {t("common.loading", "Loading...")}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[1.8rem] border border-[#13212c]/10 bg-white/80 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
      {sortableColumns.length > 0 && onHeaderClick ? (
        <div className="border-b border-[#13212c]/8 bg-[#f7f4ee] px-3 py-3 md:hidden">
          <div className="flex flex-wrap gap-2">
            {sortableColumns.map((col) => (
              <button
                key={col.key}
                type="button"
                onClick={() => onHeaderClick(col.key)}
                className={`inline-flex shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] transition ${
                  sortField === col.key
                    ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                    : "border-[#13212c]/10 bg-white text-[#61717d]"
                }`}
              >
                <span>{col.header}</span>
                <span>{sortField === col.key ? (sortDirection === "asc" ? "↑" : "↓") : "↕"}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="md:hidden">
        {data.length === 0 ? (
          <div className="px-4 py-8">{emptyContent}</div>
        ) : (
          <div className="divide-y divide-[#13212c]/8">
            {data.map((row, index) => (
              <div
                key={index}
                onClick={() => onRowClick?.(row)}
                onKeyDown={(event) => {
                  if (!onRowClick) return;
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onRowClick(row);
                  }
                }}
                role={onRowClick ? "button" : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                className={`w-full px-4 py-4 text-left transition ${
                  onRowClick ? "hover:bg-[#f9f5ed]" : "cursor-default"
                } ${rowClassName?.(row, index) || ""}`}
              >
                <div className="flex items-start gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[0.9rem] border border-[#13212c]/10 bg-[#f7f4ee] text-sm font-semibold text-[#61717d]">
                    {index + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="break-words text-base font-semibold text-[#13212c]">
                      {renderCell(row, mobileTitleColumn, index)}
                    </div>
                    {mobileDetailColumns.length > 0 ? (
                      <div className="mt-3 grid gap-2">
                        {primaryMobileDetailColumns.map((col) => (
                          <div
                            key={col.key}
                            className="rounded-[0.9rem] border border-[#13212c]/8 bg-[#fbf8f2] px-3 py-2"
                          >
                            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98]">{col.header}</p>
                            <div className="mt-1 break-words text-sm text-[#253441]">{renderCell(row, col, index) ?? "—"}</div>
                          </div>
                        ))}
                        {secondaryMobileDetailColumns.length > 0 ? (
                          <details
                            className="rounded-[0.9rem] border border-[#13212c]/8 bg-white px-3 py-2"
                            onClick={(event) => event.stopPropagation()}
                            onKeyDown={(event) => event.stopPropagation()}
                          >
                            <summary className="cursor-pointer list-none text-[10px] font-semibold uppercase tracking-[0.16em] text-[#61717d]">
                              {t("common.moreDetails", "More details")}
                            </summary>
                            <div className="mt-2 grid gap-2">
                              {secondaryMobileDetailColumns.map((col) => (
                                <div
                                  key={col.key}
                                  className="rounded-[0.8rem] border border-[#13212c]/8 bg-[#fbf8f2] px-3 py-2"
                                >
                                  <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98]">{col.header}</p>
                                  <div className="mt-1 break-words text-sm text-[#253441]">{renderCell(row, col, index) ?? "—"}</div>
                                </div>
                              ))}
                            </div>
                          </details>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="hidden overflow-x-auto md:block">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[#13212c]/10 bg-[#f7f4ee]">
              {columns.map((col) => (
                <th
                  key={col.key}
                  aria-sort={
                    col.sortable && sortField === col.key
                      ? sortDirection === "asc"
                        ? "ascending"
                        : "descending"
                      : undefined
                  }
                  className="whitespace-nowrap px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.18em] text-[#71808c]"
                >
                  {col.sortable && onHeaderClick ? (
                    <button
                      type="button"
                      onClick={() => onHeaderClick(col.key)}
                      className="inline-flex items-center gap-2 rounded-full px-1 py-0.5 text-left transition hover:text-[#13212c]"
                    >
                      <span>{col.header}</span>
                      <span className={sortField === col.key ? "text-[10px] text-[#13212c]" : "text-[10px] text-[#a3adb5]"}>
                        {sortField === col.key ? (sortDirection === "asc" ? "↑" : "↓") : "↕"}
                      </span>
                    </button>
                  ) : (
                    col.header
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[#13212c]/8">
            {data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-10">
                  {emptyContent}
                </td>
              </tr>
            ) : (
              data.map((row, i) => (
                <tr
                  key={i}
                  onClick={() => onRowClick?.(row)}
                  className={`${onRowClick ? "cursor-pointer transition hover:bg-[#f9f5ed]" : "transition hover:bg-[#fcfaf6]"} ${rowClassName?.(row, i) || ""}`}
                >
                  {columns.map((col) => (
                    <td key={col.key} className={`px-4 py-3.5 text-sm text-[#253441] ${col.className || ""}`}>
                      {renderCell(row, col, i)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
