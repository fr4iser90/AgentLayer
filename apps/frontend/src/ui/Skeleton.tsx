/**
 * Loading placeholders that reserve the space the real content will take.
 *
 * The point is layout stability, not decoration. `/app/admin/users` measured
 * CLS 0.24 against a 0.02 budget because the loading state was one 69 px row
 * while the loaded table was 10 rows x 137 px: the table grew 1302 px and every
 * section below it moved to a new position. A placeholder that is smaller than
 * its result shifts the page exactly as much as no placeholder at all.
 *
 * So: pass the height you measured, not one you estimated. The users rows came
 * out at 137 px rather than the ~44 px they look like, because each cell holds
 * a `<select>` plus a second text line — guessing there reserved a third of the
 * space needed.
 */
import { useId } from "react";

// Both alphas are on Tailwind's opacity scale on purpose. `/6` looks harmless
// and emits no rule at all — the same trap the Badge primitive documents for
// `/8`, and a skeleton whose fill silently does not exist is an invisible
// placeholder that still reserves the height but stops reading as one.
const BAR = "relative overflow-hidden rounded-tile bg-white/10";
const HIGHLIGHT =
  "absolute inset-y-0 left-0 w-1/2 animate-shimmer bg-gradient-to-r from-transparent via-white/20 to-transparent";

function Bar({ width, height }: { width: string; height: number }) {
  return (
    <div className={BAR} style={{ width, height }}>
      <div className={HIGHLIGHT} aria-hidden />
    </div>
  );
}

export interface SkeletonTextProps {
  /** Lines of text to reserve. */
  lines?: number;
  /** Line height in px — use the rendered line height of the real text. */
  lineHeight?: number;
  className?: string;
}

/** A paragraph placeholder. The last line is short because real prose ends mid-line. */
export function SkeletonText({ lines = 3, lineHeight = 22, className }: SkeletonTextProps) {
  return (
    <div className={className} aria-hidden>
      <div className="flex flex-col gap-tight">
        {Array.from({ length: lines }, (_, index) => (
          <Bar key={index} width={index === lines - 1 ? "62%" : "100%"} height={lineHeight - 8} />
        ))}
      </div>
    </div>
  );
}

export interface SkeletonRowsProps {
  rows?: number;
  /** Measured height of one real row, including its padding. */
  rowHeight?: number;
  /** Column widths, repeated if there are more columns than entries. */
  columns?: string[];
  className?: string;
}

/**
 * A table body placeholder.
 *
 * `rowHeight` must come from the loaded table, not from a hunch — see the note
 * at the top of this file. `aria-hidden` is deliberate: the placeholder is not
 * content, and a screen reader reading twenty empty bars is worse than one
 * announcement, which the caller owns.
 */
export function SkeletonRows({
  rows = 8,
  rowHeight = 44,
  columns = ["38%", "22%", "18%", "14%"],
  className,
}: SkeletonRowsProps) {
  const id = useId();
  return (
    <div
      className={className}
      aria-hidden
      style={{ minHeight: rows * rowHeight }}
      data-skeleton-rows={id}
    >
      <div className="flex flex-col">
        {Array.from({ length: rows }, (_, rowIndex) => (
          <div
            key={rowIndex}
            className="flex items-center gap-wide border-b border-line-subtle py-soft"
            style={{ height: rowHeight }}
          >
            {Array.from({ length: columns.length }, (_, columnIndex) => (
              <Bar key={columnIndex} width={columns[columnIndex % columns.length]} height={12} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export interface SkeletonCardProps {
  /** Reserve the height of a real card, including its padding. */
  height?: number;
  lines?: number;
  className?: string;
}

/** A content-card placeholder: title, a few prose lines, one control. */
export function SkeletonCard({ height = 140, lines = 2, className }: SkeletonCardProps) {
  return (
    <div
      className={[
        "rounded-card border border-line bg-card p-roomy",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      style={{ minHeight: height }}
      aria-hidden
    >
      <Bar width="40%" height={16} />
      <div className="mt-soft">
        <SkeletonText lines={lines} />
      </div>
      <div className="mt-wide">
        <Bar width="96px" height={28} />
      </div>
    </div>
  );
}