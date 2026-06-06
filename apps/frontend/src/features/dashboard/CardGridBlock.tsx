import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import { getPath } from "./dashboardDataPaths";
import { ProjectRowDetailDrawer } from "./ProjectRowDetailDrawer";
import type { ColumnDef, UiBlock } from "./types";

type Row = Record<string, unknown>;

function normText(v: unknown): string {
  return String(v ?? "").trim().toLowerCase();
}

function badgeClass(status: string): string {
  const s = normText(status);
  if (s === "ok" || s === "secure" || s === "pass") {
    return "bg-emerald-600/25 text-emerald-200 border-emerald-500/30";
  }
  if (s === "warn" || s === "warning" || s === "outdated") {
    return "bg-amber-600/25 text-amber-200 border-amber-500/30";
  }
  if (s === "fail" || s === "critical" || s === "vulnerable") {
    return "bg-red-600/25 text-red-200 border-red-500/30";
  }
  return "bg-white/10 text-surface-muted border-white/10";
}

function gridColsClass(n: number): string {
  if (n <= 1) return "grid-cols-1";
  if (n === 2) return "grid-cols-1 sm:grid-cols-2";
  if (n >= 4) return "grid-cols-1 sm:grid-cols-2 xl:grid-cols-4";
  return "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3";
}

const DEFAULT_CARD_FIELDS = ["title", "remote_url", "tags", "status", "security"];

const DEFAULT_COLUMNS: ColumnDef[] = [
  { field: "pinned", kind: "checkbox", label: "" },
  { field: "title", kind: "text", label: "Project" },
  { field: "remote_url", kind: "text", label: "Remote" },
  { field: "project_path", kind: "text", label: "Local path" },
  { field: "tags", kind: "text", label: "Tags" },
  { field: "status", kind: "text", label: "Status" },
  { field: "security", kind: "text", label: "Security" },
];

export function CardGridBlockBody(props: {
  block: UiBlock;
  dp: string;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  readOnly: boolean;
  dashboardId: string | null;
}) {
  const { block, dp, data, setData, readOnly, dashboardId } = props;
  const { t } = useTranslation(["dashboard"]);

  const rowsUnknown = dp ? getPath(data, dp) : [];
  const rows: Row[] = Array.isArray(rowsUnknown) ? (rowsUnknown as Row[]) : [];

  const cols = (block.props.columns as ColumnDef[] | undefined)?.length
    ? (block.props.columns as ColumnDef[]).filter((c) => c?.field !== "workspace_id")
    : DEFAULT_COLUMNS;

  const cardFieldsRaw = Array.isArray(block.props.cardFields)
    ? (block.props.cardFields as unknown[])
    : DEFAULT_CARD_FIELDS;
  const cardFields = cardFieldsRaw
    .filter((x) => typeof x === "string" && x.trim())
    .map((x) => String(x));

  const gridColumns = Math.min(4, Math.max(1, Number(block.props.gridColumns) || 3));
  const enableRowDetail = block.props.enableRowDetail !== false;
  const enableRunNow = block.props.enableRunNow === true;
  const enableWorkspaceLink = enableRunNow && block.props.enableWorkspaceLink !== false;
  const defaultWorkspaceId =
    typeof block.props.workspaceId === "string" ? block.props.workspaceId.trim() : "";
  const searchEnabled = block.props.enableSearch === true;
  const searchPlaceholder =
    typeof block.props.searchPlaceholder === "string" && block.props.searchPlaceholder.trim()
      ? block.props.searchPlaceholder.trim()
      : t("dashboard:tableSearchPlaceholder");

  const searchFieldsRaw = Array.isArray(block.props.searchFields)
    ? (block.props.searchFields as unknown[])
    : [];
  const searchFields =
    searchFieldsRaw.length > 0
      ? searchFieldsRaw.filter((x) => typeof x === "string" && x.trim()).map((x) => String(x))
      : cols.filter((c) => c?.field && c.kind !== "checkbox").map((c) => String(c.field));

  const [query, setQuery] = useState("");
  const [detailRowId, setDetailRowId] = useState<string | null>(null);

  const sortedRows = useMemo(() => {
    return [...rows].sort((a, b) => {
      const ap = (a as any)?.pinned === true ? 1 : 0;
      const bp = (b as any)?.pinned === true ? 1 : 0;
      return bp - ap;
    });
  }, [rows]);

  const filteredRows = useMemo(() => {
    const q = normText(query);
    if (!q) return sortedRows;
    return sortedRows.filter((r) => {
      for (const f of searchFields) {
        const val = normText((r as any)?.[f]);
        if (val && val.includes(q)) return true;
      }
      return false;
    });
  }, [sortedRows, query, searchFields]);

  const detailRow = useMemo(() => {
    if (!detailRowId) return null;
    return rows.find((r) => String((r as any)?.id ?? "") === detailRowId) ?? null;
  }, [rows, detailRowId]);

  const sectionTitle = block.props.title?.trim() || t("dashboard:cardGridFallback");

  return (
    <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-surface-muted">
          {sectionTitle}
        </span>
        {searchEnabled ? (
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={searchPlaceholder}
            className="w-full min-w-[12rem] max-w-xs rounded-md border border-surface-border bg-black/30 px-3 py-1.5 text-xs text-neutral-100 outline-none focus:border-sky-500/50 sm:w-56"
          />
        ) : null}
      </div>

      {filteredRows.length === 0 ? (
        <p className="py-8 text-center text-sm text-surface-muted">{t("dashboard:cardGridEmpty")}</p>
      ) : (
        <div className={`grid gap-3 ${gridColsClass(gridColumns)}`}>
          {filteredRows.map((row) => {
            const id = String((row as any)?.id ?? "");
            const title = String((row as any)?.title ?? "").trim() || t("dashboard:untitled");
            const pinned = (row as any)?.pinned === true;
            const status = String((row as any)?.status ?? "").trim();
            const security = String((row as any)?.security ?? "").trim();
            const remote = String((row as any)?.remote_url ?? "").trim();
            const tags = String((row as any)?.tags ?? "").trim();

            return (
              <button
                key={id || title}
                type="button"
                disabled={!enableRowDetail}
                className={[
                  "dashboard-grid-no-drag flex min-h-[120px] flex-col rounded-xl border border-surface-border bg-gradient-to-br from-slate-900/90 to-black/60 p-4 text-left shadow-sm transition-colors",
                  enableRowDetail ? "hover:border-sky-500/40 hover:bg-slate-900" : "cursor-default",
                ].join(" ")}
                onClick={() => {
                  if (enableRowDetail && id) setDetailRowId(id);
                }}
              >
                <div className="mb-2 flex items-start justify-between gap-2">
                  <h4 className="line-clamp-2 text-sm font-semibold text-white">{title}</h4>
                  {pinned ? (
                    <span className="shrink-0 text-[10px] text-amber-300" title={t("dashboard:pinned")}>
                      ★
                    </span>
                  ) : null}
                </div>
                {cardFields.includes("remote_url") && remote ? (
                  <p className="mb-2 truncate font-mono text-[10px] text-sky-300/90">{remote}</p>
                ) : null}
                {cardFields.includes("tags") && tags ? (
                  <p className="mb-2 line-clamp-2 text-xs text-surface-muted">{tags}</p>
                ) : null}
                <div className="mt-auto flex flex-wrap gap-1.5 pt-2">
                  {cardFields.includes("status") && status ? (
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase ${badgeClass(status)}`}
                    >
                      {status}
                    </span>
                  ) : null}
                  {cardFields.includes("security") && security ? (
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase ${badgeClass(security)}`}
                    >
                      {security}
                    </span>
                  ) : null}
                  {enableRunNow && String((row as any)?.workspace_id ?? "").trim() ? (
                    <span className="rounded-full border border-violet-500/30 bg-violet-600/20 px-2 py-0.5 text-[10px] text-violet-200">
                      {t("dashboard:workspaceLinked")}
                    </span>
                  ) : null}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {enableRowDetail && detailRowId && detailRow ? (
        <ProjectRowDetailDrawer
          detailRow={detailRow}
          detailRowId={detailRowId}
          onClose={() => setDetailRowId(null)}
          cols={cols}
          dp={dp}
          data={data}
          setData={setData}
          enableRunNow={enableRunNow}
          enableWorkspaceLink={enableWorkspaceLink}
          readOnly={readOnly}
          dashboardId={dashboardId}
          defaultWorkspaceId={defaultWorkspaceId}
        />
      ) : null}
    </section>
  );
}
