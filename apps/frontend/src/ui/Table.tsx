import type { ReactNode } from "react";
import { SkeletonRows } from "./Skeleton";

/**
 * The one table.
 *
 * Eleven files drew their own `<table>`: three different cell paddings, four
 * different empty-row texts (one of them a bare "—" in a single centered cell),
 * two different loading rows, and no header that stayed put once a list grew
 * past the viewport. A list you cannot read while scrolling is a list that
 * loses its column names, so the sticky header is the primitive's default and
 * not an option.
 *
 * `empty` and `loading` exist because the ad-hoc version of both was the bug:
 * an empty table that says nothing and a loading table that looks like an empty
 * one. Loading draws real skeleton rows (SkeletonRows), so the row rhythm while
 * loading matches the row rhythm after — the page does not jump when data lands.
 */

export interface TableColumn<T> {
  /** Stable identity for the column; also used for `key` on cells. */
  key: string;
  header: ReactNode;
  /** Right-align numeric columns so magnitudes compare by column, not by string. */
  align?: "left" | "right" | "center";
  /**
   * Fixed track width as a CSS length (`"9rem"`). A column that only the
   * content widths would resize on every re-render — quota columns did exactly
   * that while typing.
   */
  width?: string;
  render: (row: T, index: number) => ReactNode;
}

export type TableDensity = "compact" | "normal";

const CELL: Record<TableDensity, string> = {
  compact: "px-soft py-tight text-label",
  normal: "px-soft py-base text-body",
};

const HEAD: Record<TableDensity, string> = {
  compact: "px-soft py-tight text-meta",
  normal: "px-soft py-base text-label",
};

const ALIGN = {
  left: "text-left",
  right: "text-right",
  center: "text-center",
} as const;

export interface TableProps<T> {
  columns: Array<TableColumn<T>>;
  rows: T[];
  /** Defaults to the row index. Pass a real id when rows can be reordered. */
  rowKey?: (row: T, index: number) => string | number;
  density?: TableDensity;
  /** Rendered instead of rows, spanning the full width. */
  empty?: ReactNode;
  /** Draws skeleton rows in the current density. Wins over `empty`. */
  loading?: boolean;
  /** Row height the skeleton uses; defaults to the density's own rhythm. */
  rowHeight?: number;
  /** Keeps the header pinned while the wrapper scrolls. Default true. */
  stickyHeader?: boolean;
  /**
   * CSS minimum width for the table itself (`"840px"`). A table with eight
   * columns and no floor does not scroll — it squeezes the title column to
   * three characters and wraps every date.
   */
  minWidth?: string;
  className?: string;
}

export function Table<T>({
  columns,
  rows,
  rowKey,
  density = "normal",
  empty,
  loading = false,
  rowHeight,
  stickyHeader = true,
  className,
}: TableProps<T>) {
  const span = columns.length;
  const headCell = [
    HEAD[density],
    "font-medium text-ink-muted",
    stickyHeader && "sticky top-0 z-lift bg-panel",
  ];

  return (
    <div
      className={["overflow-x-auto", className].filter(Boolean).join(" ")}
      role="region"
      aria-busy={loading || undefined}
    >
      <table className="w-full border-collapse border-line text-left">
        <thead className="border-b border-line">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                style={col.width ? { width: col.width } : undefined}
                className={[...headCell, ALIGN[col.align ?? "left"]]
                  .filter(Boolean)
                  .join(" ")}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={span} className="p-0">
                <SkeletonRows
                  rows={5}
                  rowHeight={rowHeight ?? (density === "compact" ? 32 : 44)}
                  columns={columns.map(() => "100%")}
                />
              </td>
            </tr>
          ) : rows.length === 0 ? (
            <tr>
              <td
                colSpan={span}
                className="px-soft py-broad text-center text-body text-ink-muted"
              >
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr
                key={rowKey ? rowKey(row, i) : i}
                className="border-b border-line-subtle last:border-b-0 hover:bg-white/[0.03]"
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    style={col.width ? { width: col.width } : undefined}
                    className={[CELL[density], ALIGN[col.align ?? "left"]]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    {col.render(row, i)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}