export type SortDirection = "asc" | "desc";

export function compareTableValues(left: unknown, right: unknown, direction: SortDirection) {
  const multiplier = direction === "asc" ? 1 : -1;
  const leftValue = normalizeComparable(left);
  const rightValue = normalizeComparable(right);

  if (leftValue < rightValue) return -1 * multiplier;
  if (leftValue > rightValue) return 1 * multiplier;
  return 0;
}

export function sortTableRows<T>(
  rows: T[],
  getComparable: (row: T) => unknown,
  direction: SortDirection,
) {
  return rows
    .map((row, index) => ({ row, index }))
    .sort((left, right) => {
      const valueDiff = compareTableValues(getComparable(left.row), getComparable(right.row), direction);
      return valueDiff || left.index - right.index;
    })
    .map(({ row }) => row);
}

function normalizeComparable(value: unknown): string | number {
  if (value === null || value === undefined) return "";
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? "" : value.getTime();
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  if (typeof value === "boolean") return value ? 1 : 0;
  const asNumber = Number(value);
  if (typeof value !== "string" && Number.isFinite(asNumber)) return asNumber;
  return String(value).toLowerCase();
}
