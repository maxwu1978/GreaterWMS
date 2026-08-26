import type { CSSProperties, ReactNode } from "react";

/**
 * Shared visual contract for GreaterWMS operational tables.
 *
 * The colors, row rhythm, horizontal scrolling, and zebra/hover states mirror
 * the production Quasar operations board. The existing Warehouse Operations
 * page remains the canonical reference; new operational tables should use
 * these primitives instead of copying its table chrome into each page.
 */
export const GREATER_WMS_TABLE_SPEC = {
  headerBackground: "#3f4b69",
  rowEvenBackground: "#f7f8fb",
  rowHoverBackground: "#eaf0f8",
  headerHeight: 38,
  rowMinimumHeight: 48,
  divider: "#dedede",
  horizontalScroll: true,
} as const;

type GreaterWmsTableFrameProps = {
  children?: ReactNode;
  className?: string;
};

type GreaterWmsTableGridProps = GreaterWmsTableFrameProps & {
  columns: string;
  minWidth: number;
};

type GreaterWmsTableRowProps = GreaterWmsTableGridProps & {
  stripe?: "base" | "alternate";
};

function gridStyle(columns: string, minWidth: number): CSSProperties {
  return { gridTemplateColumns: columns, minWidth: `${minWidth}px` };
}

export function GreaterWmsTable({ children, className = "" }: GreaterWmsTableFrameProps) {
  return (
    <div
      className={`w-full overflow-x-auto ${className}`}
      style={{
        "--greater-wms-table-header-bg": GREATER_WMS_TABLE_SPEC.headerBackground,
        "--greater-wms-table-row-even-bg": GREATER_WMS_TABLE_SPEC.rowEvenBackground,
        "--greater-wms-table-row-hover-bg": GREATER_WMS_TABLE_SPEC.rowHoverBackground,
        "--greater-wms-table-divider": GREATER_WMS_TABLE_SPEC.divider,
      } as CSSProperties}
    >
      {children}
    </div>
  );
}

export function GreaterWmsTableHeader({ children, columns, minWidth, className = "" }: GreaterWmsTableGridProps) {
  return (
    <div
      role="row"
      className={`hidden items-center bg-[var(--greater-wms-table-header-bg)] text-[12px] font-bold uppercase tracking-[0.04em] text-white sm:grid ${className}`}
      style={{ ...gridStyle(columns, minWidth), minHeight: `${GREATER_WMS_TABLE_SPEC.headerHeight}px` }}
    >
      {children}
    </div>
  );
}

export function GreaterWmsTableHeaderCell({ children, className = "" }: GreaterWmsTableFrameProps) {
  return <span className={`flex items-center px-3 py-2 ${className}`} style={{ minHeight: `${GREATER_WMS_TABLE_SPEC.headerHeight}px` }}>{children}</span>;
}

export function GreaterWmsTableRow({ children, columns, minWidth, stripe = "base", className = "" }: GreaterWmsTableRowProps) {
  return (
    <div
      role="row"
      className={`hidden items-stretch border-t border-[var(--greater-wms-table-divider)] text-[13px] ${stripe === "alternate" ? "bg-[var(--greater-wms-table-row-even-bg)]" : "bg-white"} hover:bg-[var(--greater-wms-table-row-hover-bg)] sm:grid ${className}`}
      style={{ ...gridStyle(columns, minWidth), minHeight: `${GREATER_WMS_TABLE_SPEC.rowMinimumHeight}px` }}
    >
      {children}
    </div>
  );
}

export function GreaterWmsTableCell({ children, className = "" }: GreaterWmsTableFrameProps) {
  return <div className={`min-w-0 px-3 py-3 ${className}`}>{children}</div>;
}

export function GreaterWmsTableMobileHeader({ children, columns, minWidth, className = "" }: GreaterWmsTableGridProps) {
  return (
    <div
      role="row"
      className={`grid items-center bg-[#eef0f4] text-[9px] font-bold uppercase tracking-[0.1em] text-[#626a77] sm:hidden ${className}`}
      style={{ ...gridStyle(columns, minWidth), minHeight: `${GREATER_WMS_TABLE_SPEC.headerHeight}px` }}
    >
      {children}
    </div>
  );
}
