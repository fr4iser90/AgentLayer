import type { ChangeEvent, Dispatch, SetStateAction } from "react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import { GalleryImage } from "./GalleryImage";
import { GalleryBlockBody } from "./gallery/GalleryBlockBody";
import { formatDateTimeLocal } from "../../lib/formatDateTime";
import type { UiBlock, UiLayout } from "./types";
import { EmbedBlockBody } from "./EmbedBlock";
import { MediaPlayerBlockBody } from "./MediaPlayerBlock";
import { KanbanBlockBody, RichMarkdownBlockBody } from "./KanbanRichMarkdownBlocks";
import { ChartBlockBody, SparklineBlockBody } from "./chart/ChartBlockViews";
import { CardGridBlockBody } from "./CardGridBlock";
import { ProjectRowDetailDrawer } from "./ProjectRowDetailDrawer";
import { DashboardRefBlockBody } from "./DashboardRefBlock";
import { ShareWidgetBlockBody } from "./ShareWidgetBlock";
import { SectionBlockBody } from "./SectionBlock";
import { FormulaCalcBlockBody } from "./FormulaCalcBlock";
import { getPath, setPath } from "./dashboardDataPaths";
import {
  EXECUTION_TARGET_OPTIONS,
  labelForExecutionTarget,
  parseSchedulesBlockExecutionTargetFilter,
  type ExecutionTargetCatalogRow,
} from "../../lib/schedulerExecutionTarget";

type Row = Record<string, unknown>;

function newRowId(): string {
  return `r_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

export function DashboardBlocks(props: {
  uiLayout: UiLayout | null | undefined;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
}) {
  const { t } = useTranslation(["dashboard"]);
  const { uiLayout, data, setData } = props;
  if (!uiLayout?.blocks?.length) {
    return <p className="text-sm text-surface-muted">{t("dashboard:noBlocksInLayout")}</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      {uiLayout.blocks.map((block) => (
        <DashboardBlockTile key={block.id} block={block} data={data} setData={setData} />
      ))}
    </div>
  );
}

function normText(v: unknown): string {
  return String(v ?? "").trim().toLowerCase();
}

/** Single block (used by list view and by the drag grid). */
export function DashboardBlockTile(props: {
  block: UiBlock;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  readOnly?: boolean;
  /** When true with readOnly, allow formula inputs / checklist toggles (use mode). */
  interactOnly?: boolean;
  dashboardId?: string | null;
  displayMode?: "grid" | "expanded";
  rootLayout?: UiLayout;
  setRootLayout?: Dispatch<SetStateAction<UiLayout>>;
  gridEditMode?: boolean;
  gridContentReadOnly?: boolean;
  gridDashboardId?: string | null;
  unreadBlockIds?: Set<string>;
  highlightBlockId?: string | null;
  onBlockSeen?: (blockId: string) => void;
}) {
  return (
    <BlockView
      block={props.block}
      data={props.data}
      setData={props.setData}
      readOnly={props.readOnly === true}
      interactOnly={props.interactOnly === true}
      dashboardId={props.dashboardId ?? null}
      displayMode={props.displayMode ?? "grid"}
      rootLayout={props.rootLayout}
      setRootLayout={props.setRootLayout}
      gridEditMode={props.gridEditMode}
      gridContentReadOnly={props.gridContentReadOnly}
      gridDashboardId={props.gridDashboardId}
      unreadBlockIds={props.unreadBlockIds}
      highlightBlockId={props.highlightBlockId}
      onBlockSeen={props.onBlockSeen}
    />
  );
}

type SchedulerJobRowLite = {
  id: string;
  dashboard_id: string | null;
  execution_target: string;
  title: string | null;
  interval_minutes: number;
  enabled: boolean;
  last_run_at: string | null;
  created_at: string;
};

type HeroState = { url: string; caption: string; headline: string };

function readHero(raw: unknown): HeroState {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const o = raw as Record<string, unknown>;
    return {
      url: String(o.url ?? "").trim(),
      caption: String(o.caption ?? ""),
      headline: String(o.headline ?? ""),
    };
  }
  return { url: "", caption: "", headline: "" };
}

function HeroBlockBody(props: {
  dp: string;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  sectionTitle: string;
  dashboardId: string | null;
  readOnly: boolean;
}) {
  const { dp, data, setData, sectionTitle, dashboardId, readOnly } = props;
  const { t } = useTranslation(["dashboard"]);
  const auth = useAuth();
  const hero = readHero(dp ? getPath(data, dp) : undefined);
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState<string | null>(null);

  const patchHero = (partial: Partial<HeroState>) => {
    setData((d) => {
      const cur = readHero(dp ? getPath(d, dp) : undefined);
      return setPath(d, dp, { ...cur, ...partial });
    });
  };

  const onPickFile = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f || !dashboardId) {
      if (!dashboardId) setUploadErr(t("dashboard:dashboardSaveBeforeUpload"));
      return;
    }
    setUploading(true);
    setUploadErr(null);
    const fd = new FormData();
    fd.append("file", f);
    void (async () => {
      try {
        const res = await apiFetch(`/v1/dashboards/${dashboardId}/files`, auth, {
          method: "POST",
          body: fd,
        });
        const raw = await res.text();
        let j: { file?: { gallery_ref?: string }; detail?: unknown } = {};
        try {
          j = JSON.parse(raw) as typeof j;
        } catch {
          j = {};
        }
        if (!res.ok) {
          const msg =
            typeof j.detail === "string"
              ? j.detail
              : t("dashboard:uploadFailed", { status: res.status });
          setUploadErr(msg);
          return;
        }
        const ref = j.file?.gallery_ref;
        if (ref) patchHero({ url: ref });
      } catch (err) {
        setUploadErr(err instanceof Error ? err.message : String(err));
      } finally {
        setUploading(false);
      }
    })();
  };

  const imageArea = (
    <div className="relative isolate min-h-[200px] w-full overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-sky-950/40 via-black/50 to-violet-950/30 aspect-[2.2/1] max-h-[min(420px,55vh)]">
      {hero.url ? (
        <>
          <div className="absolute inset-0">
            <GalleryImage url={hero.url} alt={hero.headline || hero.caption || "Hero"} />
          </div>
          {hero.headline ? (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent px-5 pb-4 pt-16">
              <p className="text-lg font-semibold tracking-tight text-white drop-shadow-md md:text-xl">
                {hero.headline}
              </p>
            </div>
          ) : null}
        </>
      ) : (
        <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-2 px-6 text-center">
          <p className="text-sm text-surface-muted">
            {readOnly ? t("dashboard:heroEmptyReadOnly") : t("dashboard:heroEmptyEditable")}
          </p>
        </div>
      )}
    </div>
  );

  if (readOnly) {
    return (
      <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-3 md:p-4">
        <h3 className="mb-3 text-xs font-medium uppercase tracking-wide text-surface-muted">
          {sectionTitle}
        </h3>
        {imageArea}
        {hero.caption ? (
          <p className="mt-3 text-sm leading-relaxed text-neutral-200">{hero.caption}</p>
        ) : null}
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-3 md:p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-white">{sectionTitle}</h3>
        <label className="dashboard-grid-no-drag cursor-pointer rounded-md bg-violet-600/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-500">
          {uploading ? "…" : t("dashboard:heroUpload")}
          <input
            type="file"
            accept="image/jpeg,image/png,image/gif,image/webp"
            className="hidden"
            disabled={uploading || !dashboardId}
            onChange={onPickFile}
          />
        </label>
      </div>
      {!dashboardId ? (
        <p className="mb-2 text-[10px] text-amber-200/90">{t("dashboard:heroSaveBeforeUploadHint")}</p>
      ) : null}
      {uploadErr ? <p className="mb-2 text-xs text-red-400">{uploadErr}</p> : null}
      {imageArea}
      <div className="mt-4 space-y-3">
        <div>
          <label className="mb-1 block text-[10px] uppercase tracking-wide text-surface-muted">
            {t("dashboard:heroImageUrlLabel")}
          </label>
          <input
            type="url"
            placeholder={t("dashboard:fileUrlPlaceholder")}
            className="dashboard-grid-no-drag w-full rounded-lg border border-surface-border bg-black/40 px-3 py-2 text-sm text-neutral-100 placeholder:text-white/25"
            value={hero.url}
            onChange={(e) => patchHero({ url: e.target.value })}
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] uppercase tracking-wide text-surface-muted">
            {t("dashboard:heroHeadlineLabel")}
          </label>
          <input
            type="text"
            placeholder={t("dashboard:heroHeadlinePlaceholder")}
            className="dashboard-grid-no-drag w-full rounded-lg border border-surface-border bg-black/40 px-3 py-2 text-sm text-neutral-100"
            value={hero.headline}
            onChange={(e) => patchHero({ headline: e.target.value })}
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] uppercase tracking-wide text-surface-muted">
            {t("dashboard:heroCaptionLabel")}
          </label>
          <textarea
            className="dashboard-grid-no-drag min-h-[72px] w-full resize-y rounded-lg border border-surface-border bg-black/40 px-3 py-2 text-sm text-neutral-100"
            placeholder={t("dashboard:heroCaptionPlaceholder")}
            value={hero.caption}
            onChange={(e) => patchHero({ caption: e.target.value })}
          />
        </div>
      </div>
    </section>
  );
}

type StatTrend = "" | "up" | "down";

type StatState = { value: string; label: string; suffix: string; trend: StatTrend };

function readStat(raw: unknown): StatState {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const o = raw as Record<string, unknown>;
    const tr = String(o.trend ?? "").trim().toLowerCase();
    const trend: StatTrend =
      tr === "up" || tr === "down" ? tr : "";
    return {
      value: o.value == null ? "" : String(o.value),
      label: String(o.label ?? ""),
      suffix: String(o.suffix ?? ""),
      trend,
    };
  }
  return { value: "", label: "", suffix: "", trend: "" };
}

function StatBlockBody(props: {
  dp: string;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  sectionTitle: string;
  readOnly: boolean;
}) {
  const { dp, data, setData, sectionTitle, readOnly } = props;
  const { t } = useTranslation(["dashboard"]);
  const stat = readStat(dp ? getPath(data, dp) : undefined);

  const patchStat = (partial: Partial<StatState>) => {
    setData((d) => {
      const cur = readStat(dp ? getPath(d, dp) : undefined);
      return setPath(d, dp, { ...cur, ...partial });
    });
  };

  const trendGlyph =
    stat.trend === "up" ? (
      <span className="text-emerald-400" title={t("dashboard:trendUpTitle")}>
        ↑
      </span>
    ) : stat.trend === "down" ? (
      <span className="text-rose-400" title={t("dashboard:trendDownTitle")}>
        ↓
      </span>
    ) : null;

  return (
    <section className="flex h-full min-h-[140px] flex-col rounded-xl border border-surface-border bg-gradient-to-br from-slate-900/80 to-black/50 p-4">
      <p className="text-[10px] font-medium uppercase tracking-wide text-surface-muted">
        {sectionTitle}
      </p>
      {stat.label ? (
        <p className="mt-1 line-clamp-2 text-xs text-neutral-300">{stat.label}</p>
      ) : null}
      <div className="mt-auto flex flex-wrap items-end gap-2 pt-3">
        <div className="flex min-w-0 items-baseline gap-2">
          <span className="truncate text-3xl font-semibold tabular-nums tracking-tight text-white">
            {stat.value || "—"}
          </span>
          {stat.suffix ? (
            <span className="shrink-0 text-sm text-surface-muted">{stat.suffix}</span>
          ) : null}
          {trendGlyph ? <span className="text-xl leading-none">{trendGlyph}</span> : null}
        </div>
      </div>
      {!readOnly ? (
        <div className="mt-4 space-y-2 border-t border-white/5 pt-3">
          <input
            type="text"
            placeholder={t("dashboard:kpiLabelOptional")}
            className="dashboard-grid-no-drag w-full rounded-md border border-surface-border bg-black/40 px-2 py-1.5 text-xs text-neutral-100"
            value={stat.label}
            onChange={(e) => patchStat({ label: e.target.value })}
          />
          <div className="flex gap-2">
            <input
              type="text"
              placeholder={t("dashboard:kpiValuePlaceholder")}
              className="dashboard-grid-no-drag min-w-0 flex-1 rounded-md border border-surface-border bg-black/40 px-2 py-1.5 text-xs text-neutral-100"
              value={stat.value}
              onChange={(e) => patchStat({ value: e.target.value })}
            />
            <input
              type="text"
              placeholder={t("dashboard:kpiSuffixPlaceholder")}
              className="dashboard-grid-no-drag w-20 shrink-0 rounded-md border border-surface-border bg-black/40 px-2 py-1.5 text-xs text-neutral-100"
              value={stat.suffix}
              onChange={(e) => patchStat({ suffix: e.target.value })}
            />
          </div>
          <select
            className="dashboard-grid-no-drag w-full rounded-md border border-surface-border bg-black/40 px-2 py-1.5 text-xs text-neutral-100"
            value={stat.trend}
            onChange={(e) => patchStat({ trend: e.target.value as StatTrend })}
          >
            <option value="">{t("dashboard:kpiNoTrend")}</option>
            <option value="up">{t("dashboard:kpiTrendUp")}</option>
            <option value="down">{t("dashboard:kpiTrendDown")}</option>
          </select>
        </div>
      ) : null}
    </section>
  );
}

function parseEventDateMs(raw: string): number {
  const s = raw.trim();
  if (!s) return Number.POSITIVE_INFINITY;
  const t = Date.parse(s);
  return Number.isFinite(t) ? t : Number.POSITIVE_INFINITY;
}

function formatEventDate(raw: string): string {
  const s = raw.trim();
  if (!s) return "—";
  const t = Date.parse(s);
  if (!Number.isFinite(t)) return s;
  try {
    return new Date(t).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return s;
  }
}

function TimelineBlockBody(props: {
  dp: string;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  sectionTitle: string;
  readOnly: boolean;
}) {
  const { dp, data, setData, sectionTitle, readOnly } = props;
  const { t } = useTranslation(["dashboard"]);

  const sorted = useMemo(() => {
    const rowsUnknown = dp ? getPath(data, dp) : [];
    const rows: Row[] = Array.isArray(rowsUnknown) ? (rowsUnknown as Row[]) : [];
    return [...rows].sort(
      (a, b) =>
        parseEventDateMs(String(a.date ?? "")) - parseEventDateMs(String(b.date ?? ""))
    );
  }, [dp, data]);

  const updateRow = (indexInSorted: number, field: string, value: unknown) => {
    const id = sorted[indexInSorted]?.id;
    setData((d) => {
      const list = [...((getPath(d, dp) as Row[]) || [])];
      const ix = id != null ? list.findIndex((r) => r.id === id) : -1;
      if (ix < 0) return d;
      const row = { ...(list[ix] || {}) };
      row[field] = value;
      list[ix] = row;
      return setPath(d, dp, list);
    });
  };

  const addEvent = () => {
    setData((d) => {
      const list = [...((getPath(d, dp) as Row[]) || [])];
      const day = new Date().toISOString().slice(0, 10);
      list.push({
        id: newRowId(),
        title: "",
        date: day,
        note: "",
      });
      return setPath(d, dp, list);
    });
  };

  const removeRow = (indexInSorted: number) => {
    const id = sorted[indexInSorted]?.id;
    setData((d) => {
      const list = [...((getPath(d, dp) as Row[]) || [])];
      const ix = id != null ? list.findIndex((r) => r.id === id) : -1;
      if (ix < 0) return d;
      list.splice(ix, 1);
      return setPath(d, dp, list);
    });
  };

  return (
    <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-4">
      <div className="mb-4 flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-white">{sectionTitle}</h3>
        {!readOnly ? (
          <button
            type="button"
            className="rounded-md bg-sky-600/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            onClick={addEvent}
          >
            {t("dashboard:timelineAddEntry")}
          </button>
        ) : null}
      </div>
      {sorted.length === 0 ? (
        <p className="rounded-lg border border-dashed border-white/15 py-8 text-center text-sm text-surface-muted">
          {readOnly ? t("dashboard:timelineEmptyReadOnly") : t("dashboard:timelineEmptyEditable")}
        </p>
      ) : (
        <div className="relative pl-1">
          <div
            className="absolute bottom-2 left-[7px] top-2 w-px bg-gradient-to-b from-sky-500/50 via-white/15 to-violet-500/40"
            aria-hidden
          />
          <ul className="space-y-0">
          {sorted.map((row, si) => (
            <li key={String(row.id ?? si)} className="relative flex gap-3 pb-6 last:pb-0">
              <div className="relative z-[1] mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full border-2 border-sky-500/80 bg-black shadow-[0_0_12px_rgba(56,189,248,0.35)]" />
              <div className="min-w-0 flex-1 rounded-lg border border-white/5 bg-black/20 px-3 py-2">
                <p className="text-[11px] font-medium uppercase tracking-wide text-sky-400/90">
                  {formatEventDate(String(row.date ?? ""))}
                </p>
                {readOnly ? (
                  <>
                    <p className="mt-1 text-sm font-medium text-white">
                      {String(row.title ?? "").trim() || "—"}
                    </p>
                    {String(row.note ?? "").trim() ? (
                      <p className="mt-1 text-xs text-surface-muted">{String(row.note)}</p>
                    ) : null}
                  </>
                ) : (
                  <div className="mt-2 space-y-2">
                    <input
                      type="text"
                      placeholder={t("dashboard:timelineTitlePlaceholder")}
                      className="dashboard-grid-no-drag w-full rounded-md border border-surface-border bg-black/40 px-2 py-1.5 text-sm text-white"
                      value={String(row.title ?? "")}
                      onChange={(e) => updateRow(si, "title", e.target.value)}
                    />
                    <div className="flex flex-wrap gap-2">
                      <input
                        type="date"
                        className="dashboard-grid-no-drag rounded-md border border-surface-border bg-black/40 px-2 py-1.5 text-xs text-neutral-100"
                        value={String(row.date ?? "").slice(0, 10)}
                        onChange={(e) => updateRow(si, "date", e.target.value)}
                      />
                      <button
                        type="button"
                        className="ml-auto rounded px-2 py-1 text-xs text-red-400 hover:bg-white/5"
                        onClick={() => removeRow(si)}
                      >
                        {t("dashboard:remove")}
                      </button>
                    </div>
                    <textarea
                      placeholder={t("dashboard:timelineNoteOptional")}
                      className="dashboard-grid-no-drag min-h-[56px] w-full resize-y rounded-md border border-surface-border bg-black/40 px-2 py-1.5 text-xs text-neutral-200"
                      value={String(row.note ?? "")}
                      onChange={(e) => updateRow(si, "note", e.target.value)}
                    />
                  </div>
                )}
              </div>
            </li>
          ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function BlockView(props: {
  block: UiBlock;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  dashboardId: string | null;
  readOnly: boolean;
  interactOnly?: boolean;
  displayMode?: "grid" | "expanded";
  rootLayout?: UiLayout;
  setRootLayout?: Dispatch<SetStateAction<UiLayout>>;
  gridEditMode?: boolean;
  gridContentReadOnly?: boolean;
  gridDashboardId?: string | null;
  unreadBlockIds?: Set<string>;
  highlightBlockId?: string | null;
  onBlockSeen?: (blockId: string) => void;
}) {
  const {
    block,
    data,
    setData,
    dashboardId,
    readOnly,
    interactOnly = false,
    displayMode = "grid",
    rootLayout,
    setRootLayout,
    gridEditMode,
    gridContentReadOnly,
    gridDashboardId,
    unreadBlockIds,
    highlightBlockId,
    onBlockSeen,
  } = props;
  const structureLocked = readOnly;
  const allowInteract = interactOnly || !readOnly;
  const { t } = useTranslation(["dashboard", "admin"]);
  const dp = block.props.dataPath || "";

  if (block.type === "section") {
    if (!rootLayout || !setRootLayout) {
      return (
        <p className="text-xs text-surface-muted">{t("dashboard:sectionUnavailable")}</p>
      );
    }
    return (
      <SectionBlockBody
        block={block}
        rootLayout={rootLayout}
        setRootLayout={setRootLayout}
        data={data}
        setData={setData}
        editMode={gridEditMode && !readOnly}
        contentReadOnly={gridContentReadOnly || readOnly}
        dashboardId={gridDashboardId ?? dashboardId}
        unreadBlockIds={unreadBlockIds}
        highlightBlockId={highlightBlockId}
        onBlockSeen={onBlockSeen}
      />
    );
  }

  if (block.type === "hero") {
    return (
      <HeroBlockBody
        dp={dp}
        data={data}
        setData={setData}
        sectionTitle={block.props.title || t("dashboard:heroFallback")}
        dashboardId={dashboardId}
        readOnly={readOnly}
      />
    );
  }

  if (block.type === "stat") {
    return (
      <StatBlockBody
        dp={dp}
        data={data}
        setData={setData}
        sectionTitle={block.props.title || "KPI"}
        readOnly={readOnly}
      />
    );
  }

  if (block.type === "timeline") {
    return (
      <TimelineBlockBody
        dp={dp}
        data={data}
        setData={setData}
        sectionTitle={block.props.title || t("dashboard:timelineFallback")}
        readOnly={readOnly}
      />
    );
  }

  if (block.type === "chart") {
    return (
      <ChartBlockBody
        dp={dp}
        data={data}
        setData={setData}
        sectionTitle={block.props.title || t("dashboard:chartFallback")}
        readOnly={readOnly}
        displayMode={displayMode}
      />
    );
  }

  if (block.type === "sparkline") {
    return (
      <SparklineBlockBody
        dp={dp}
        data={data}
        setData={setData}
        sectionTitle={block.props.title || t("dashboard:sparklineFallback")}
        readOnly={readOnly}
      />
    );
  }

  if (block.type === "kanban") {
    return (
      <KanbanBlockBody
        dp={dp}
        data={data}
        setData={setData}
        sectionTitle={block.props.title || t("dashboard:kanbanFallback")}
        readOnly={readOnly}
        displayMode={displayMode}
      />
    );
  }

  if (block.type === "rich_markdown") {
    return (
      <RichMarkdownBlockBody
        dp={dp}
        data={data}
        setData={setData}
        sectionTitle={block.props.title || t("dashboard:richMarkdownFallback")}
        placeholder={block.props.placeholder || ""}
        readOnly={readOnly}
      />
    );
  }

  if (block.type === "embed") {
    return (
      <EmbedBlockBody
        dp={dp}
        data={data}
        setData={setData}
        sectionTitle={block.props.title || "Embed"}
        readOnly={readOnly}
      />
    );
  }

  if (block.type === "media_player") {
    return (
      <MediaPlayerBlockBody
        dp={dp}
        data={data}
        setData={setData}
        sectionTitle={block.props.title || t("dashboard:mediaPlayerFallback")}
        readOnly={readOnly}
        dashboardId={dashboardId}
      />
    );
  }

  if (block.type === "markdown") {
    const raw = getPath(data, dp);
    const text = typeof raw === "string" ? raw : "";
    return (
      <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-4">
        <label className="mb-2 block text-xs font-medium uppercase tracking-wide text-surface-muted">
          {block.props.placeholder || dp || "Text"}
        </label>
        <textarea
          readOnly={readOnly}
          className="min-h-[120px] w-full resize-y rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-sky-500/50 read-only:cursor-default read-only:opacity-90"
          value={text}
          placeholder={block.props.placeholder || ""}
          onChange={(e) =>
            setData((d) => setPath(d, dp, e.target.value))
          }
        />
      </section>
    );
  }

  if (block.type === "card_grid") {
    return (
      <CardGridBlockBody
        block={block}
        dp={dp}
        data={data}
        setData={setData}
        readOnly={readOnly}
        dashboardId={dashboardId}
      />
    );
  }

  if (block.type === "dashboard_ref") {
    return <DashboardRefBlockBody block={block} readOnly={readOnly} />;
  }

  if (block.type === "share_widget") {
    return <ShareWidgetBlockBody block={block} />;
  }

    if (block.type === "formula_calc") {
    const inputs = Array.isArray(block.props.formulaInputs)
      ? (block.props.formulaInputs as {
          key: string;
          label: string;
          optional?: boolean;
          control?: "number" | "select" | "percent";
          options?: { label: string; value: number }[];
          defaultValue?: number;
          step?: number;
          placeholder?: string;
        }[])
      : [];
    const outputs = Array.isArray(block.props.formulaOutputs)
      ? (block.props.formulaOutputs as { key: string; label: string; expr: string }[])
      : [];
    return (
      <FormulaCalcBlockBody
        title={typeof block.props.title === "string" ? block.props.title : undefined}
        disclaimer={typeof block.props.disclaimer === "string" ? block.props.disclaimer : undefined}
        formulaNote={typeof block.props.formulaNote === "string" ? block.props.formulaNote : undefined}
        inputs={inputs}
        outputs={outputs}
        readOnly={structureLocked && !allowInteract}
      />
    );
  }

  if (block.type === "gallery") {
    return (
      <GalleryBlockBody
        block={block}
        dp={dp}
        data={data}
        setData={setData}
        sectionTitle={block.props.title || t("dashboard:photosTitleFallback")}
        dashboardId={dashboardId}
        readOnly={readOnly}
      />
    );
  }

  if (block.type === "table") {
    const rowsUnknown = dp ? getPath(data, dp) : [];
    const rows: Row[] = Array.isArray(rowsUnknown)
      ? (rowsUnknown as Row[])
      : [];
    const cols = (block.props.columns || []).filter(
      (c: { field?: string }) => c?.field !== "workspace_id"
    );
    const enableRowDetail = block.props.enableRowDetail === true;
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
        ? searchFieldsRaw.filter((x) => typeof x === "string" && x.trim())?.map((x) => String(x))
        : cols
            .filter((c: any) => c?.field && c?.kind !== "checkbox")
            .map((c: any) => String(c.field));

    const [query, setQuery] = useState("");
    const [detailRowId, setDetailRowId] = useState<string | null>(null);

    const filteredRows = useMemo(() => {
      const q = normText(query);
      if (!q) return rows;
      return rows.filter((r) => {
        for (const f of searchFields) {
          const t = normText((r as any)?.[f]);
          if (t && t.includes(q)) return true;
        }
        return false;
      });
    }, [rows, query, searchFields]);

    const detailRow = useMemo(() => {
      if (!detailRowId) return null;
      const found = rows.find((r) => String((r as any)?.id ?? "") === detailRowId);
      return found ?? null;
    }, [rows, detailRowId]);

    const updateRow = (index: number, field: string, value: unknown) => {
      setData((d) => {
        const list = [...((getPath(d, dp) as Row[]) || [])];
        const row = { ...(list[index] || {}) };
        row[field] = value;
        list[index] = row;
        return setPath(d, dp, list);
      });
    };

    const addRow = () => {
      setData((d) => {
        const list = [...((getPath(d, dp) as Row[]) || [])];
        const base: Row = { id: newRowId() };
        for (const c of cols) {
          if (c.kind === "checkbox") base[c.field] = false;
          else if (c.kind === "number") base[c.field] = 1;
          else if (c.kind === "select") base[c.field] = c.options?.[0] ?? "";
          else base[c.field] = "";
        }
        list.push(base);
        return setPath(d, dp, list);
      });
    };

    const removeRow = (index: number) => {
      setData((d) => {
        const list = [...((getPath(d, dp) as Row[]) || [])];
        list.splice(index, 1);
        return setPath(d, dp, list);
      });
    };

    return (
      <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-surface-muted">
            {t("dashboard:tableTitle", { path: dp })}
          </span>
          <div className="flex items-center gap-2">
            {searchEnabled ? (
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={searchPlaceholder}
                className="w-56 rounded-md border border-surface-border bg-black/30 px-3 py-1.5 text-xs text-neutral-100 outline-none focus:border-sky-500/50"
              />
            ) : null}
            {!structureLocked ? (
              <button
                type="button"
                className="rounded-md bg-sky-600/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
                onClick={addRow}
              >
                {t("dashboard:tableAddRow")}
              </button>
            ) : null}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-surface-border text-surface-muted">
                {cols.map((c) => (
                  <th key={c.field} className="px-2 py-2 font-medium">
                    {c.label || c.field}
                  </th>
                ))}
                {enableRowDetail ? <th className="w-12 px-2 py-2" /> : null}
                {!structureLocked ? <th className="w-10 px-2 py-2" /> : null}
              </tr>
            </thead>
            <tbody>
              {filteredRows.length === 0 ? (
                <tr>
                  <td
                    colSpan={cols.length + (enableRowDetail ? 1 : 0) + (structureLocked ? 0 : 1)}
                    className="px-2 py-6 text-center text-surface-muted"
                  >
                    {rows.length === 0
                      ? structureLocked
                        ? t("dashboard:tableEmptyReadOnly")
                        : t("dashboard:tableEmptyEditable")
                      : t("dashboard:tableNoMatches")}
                  </td>
                </tr>
              ) : (
                filteredRows.map((row, ri) => (
                  <tr key={String(row.id ?? ri)} className="border-b border-white/5">
                    {cols.map((c) => (
                      <td key={c.field} className="px-2 py-1 align-middle">
                        <CellInput
                          col={c}
                          value={row[c.field]}
                          readOnly={c.kind === "checkbox" ? !allowInteract : structureLocked}
                          onChange={(v) => {
                            const rowId = String(row.id ?? "");
                            if (!rowId) return updateRow(ri, c.field, v);
                            const realIndex = rows.findIndex((x) => String((x as any)?.id ?? "") === rowId);
                            updateRow(realIndex >= 0 ? realIndex : ri, c.field, v);
                          }}
                        />
                      </td>
                    ))}
                    {enableRowDetail ? (
                      <td className="px-1">
                        <button
                          type="button"
                          className="rounded px-2 py-1 text-xs text-sky-200 hover:bg-white/5"
                          onClick={() => setDetailRowId(String(row.id ?? ""))}
                          title={t("dashboard:details")}
                        >
                          ↗
                        </button>
                      </td>
                    ) : null}
                    {!structureLocked ? (
                      <td className="px-1">
                        <button
                          type="button"
                          className="rounded p-1 text-xs text-red-400 hover:bg-white/5"
                          onClick={() => {
                            const rowId = String(row.id ?? "");
                            const realIndex = rowId
                              ? rows.findIndex((x) => String((x as any)?.id ?? "") === rowId)
                              : ri;
                            removeRow(realIndex >= 0 ? realIndex : ri);
                          }}
                          title={t("dashboard:deleteRow")}
                        >
                          ✕
                        </button>
                      </td>
                    ) : null}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
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

  if (block.type === "schedules") {
    const auth = useAuth();
    const scopeRaw = String(block.props.scope ?? "dashboard").trim().toLowerCase();
    const scope = scopeRaw === "both" || scopeRaw === "global" || scopeRaw === "dashboard" ? scopeRaw : "dashboard";
    const [targetCatalog, setTargetCatalog] = useState<readonly ExecutionTargetCatalogRow[]>(
      EXECUTION_TARGET_OPTIONS
    );
    const knownTargets = useMemo(
      () => new Set(targetCatalog.map((o) => o.value)),
      [targetCatalog]
    );
    const executionTarget = parseSchedulesBlockExecutionTargetFilter(
      block.props.executionTarget as string | undefined,
      knownTargets
    );
    const [jobs, setJobs] = useState<SchedulerJobRowLite[] | null>(null);
    const [loading, setLoading] = useState(false);
    const [err, setErr] = useState<string | null>(null);
    const includeArchived = block.props.includeArchived === true;

    const refresh = async () => {
      setLoading(true);
      setErr(null);
      try {
        const q = new URLSearchParams();
        q.set("limit", "100");
        if (scope === "dashboard" && dashboardId) {
          q.set("dashboard_id", String(dashboardId));
        }
        const res = await apiFetch(`/v1/user/scheduler-jobs?${q.toString()}`, auth);
        const j = (await res.json().catch(() => null)) as any;
        if (!res.ok || !j?.ok) {
          setErr(String(j?.detail ?? j?.error ?? res.status));
          setJobs(null);
        } else {
          const dashKey = dashboardId ? String(dashboardId) : "";
          let rows: SchedulerJobRowLite[] = Array.isArray(j.jobs)
            ? (j.jobs as SchedulerJobRowLite[])
            : [];
          if (scope === "global") {
            rows = rows.filter((row) => !row.dashboard_id);
          } else if (scope === "dashboard" && dashKey) {
            rows = rows.filter((row) => String(row.dashboard_id || "") === dashKey);
          } else if (scope === "both" && dashKey) {
            rows = rows.filter(
              (row) => !row.dashboard_id || String(row.dashboard_id) === dashKey
            );
          }
          if (executionTarget !== "all") {
            rows = rows.filter(
              (row) =>
                String(row.execution_target || "").trim().toLowerCase() === executionTarget
            );
          }
          if (!includeArchived) {
            rows = rows.filter((row) => !(row as { deleted_at?: string | null }).deleted_at);
          }
          setJobs(rows);
        }
      } catch (e) {
        setErr(String(e));
        setJobs(null);
      } finally {
        setLoading(false);
      }
    };

    useEffect(() => {
      void (async () => {
        const res = await apiFetch("/v1/user/scheduler-jobs/execution-targets", auth);
        const j = (await res.json().catch(() => null)) as {
          ok?: boolean;
          targets?: ExecutionTargetCatalogRow[];
        };
        if (res.ok && j?.ok && Array.isArray(j.targets) && j.targets.length > 0) {
          setTargetCatalog(j.targets);
        }
      })();
    }, [auth, auth.accessToken]);

    useEffect(() => {
      void refresh();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [scope, executionTarget, dashboardId]);

    const toggleEnabled = async (jobId: string, next: boolean) => {
      const res = await apiFetch(`/v1/user/scheduler-jobs/${jobId}/enabled`, auth, {
        method: "PATCH",
        body: JSON.stringify({ enabled: next }),
      });
      const j = (await res.json().catch(() => null)) as any;
      if (!res.ok || !j?.ok) {
        setErr(String(j?.detail ?? j?.error ?? res.status));
        return;
      }
      await refresh();
    };

    return (
      <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-surface-muted">
            {t("admin:schedulesTitle")}
          </span>
          <button
            type="button"
            className="rounded-md border border-surface-border px-2 py-1 text-[11px] text-neutral-100 hover:bg-white/5"
            onClick={() => void refresh()}
            disabled={loading}
          >
            {loading ? t("admin:loading") : t("admin:schedulesRefresh")}
          </button>
        </div>
        {err ? <div className="mb-3 text-xs text-red-200/90">{err}</div> : null}
        {!jobs ? (
          <div className="text-sm text-surface-muted">
            {loading ? t("admin:loading") : t("admin:schedulesNoDataYet")}
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-sm text-surface-muted">{t("admin:schedulesNone")}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-surface-border text-surface-muted">
                  <th className="px-2 py-2 font-medium">{t("admin:schedulesEnabledFilter")}</th>
                  <th className="px-2 py-2 font-medium">{t("admin:schedulesTarget")}</th>
                  <th className="px-2 py-2 font-medium">{t("admin:schedulesColTitle")}</th>
                  <th className="px-2 py-2 font-medium">{t("admin:schedulesColInterval")}</th>
                  <th className="px-2 py-2 font-medium">{t("admin:schedulesColScope")}</th>
                  <th className="px-2 py-2 font-medium">{t("admin:schedulesColLastRun")}</th>
                  <th className="px-2 py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id} className="border-b border-white/5">
                    <td className="px-2 py-2">
                      <span className={`rounded-md border px-2 py-0.5 text-xs ${pill(j.enabled)}`}>
                        {j.enabled ? t("admin:schedulesEnabledLabel") : t("admin:schedulesDisabledLabel")}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-xs text-neutral-100">
                      <div>{labelForExecutionTarget(j.execution_target, targetCatalog)}</div>
                      <div className="font-mono text-[10px] text-surface-muted">
                        {j.execution_target}
                      </div>
                    </td>
                    <td className="px-2 py-2 text-neutral-100">{j.title || "—"}</td>
                    <td className="px-2 py-2 text-surface-muted">
                      {t("admin:schedulesIntervalMin", { minutes: j.interval_minutes })}
                    </td>
                    <td className="px-2 py-2 text-surface-muted">
                      {j.dashboard_id
                        ? t("admin:schedulesScopeDashboardShort")
                        : t("admin:schedulesScopeGlobal")}
                    </td>
                    <td className="px-2 py-2 text-surface-muted">{formatDateTimeLocal(j.last_run_at)}</td>
                    <td className="px-2 py-2">
                      {!readOnly ? (
                        <button
                          type="button"
                          className="rounded-md border border-surface-border px-2 py-1 text-xs text-neutral-100 hover:bg-white/5"
                          onClick={() => void toggleEnabled(j.id, !j.enabled)}
                        >
                          {j.enabled ? t("admin:schedulesDisable") : t("admin:schedulesEnable")}
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    );
  }

  return (
    <p className="text-sm text-amber-200/90">
      Unbekannter Block-Typ: {(block as UiBlock).type}
    </p>
  );
}

function CellInput(props: {
  col: { field: string; kind: string; options?: string[] };
  value: unknown;
  readOnly?: boolean;
  onChange: (v: unknown) => void;
}) {
  const { col, value, readOnly = false, onChange } = props;
  if (col.kind === "checkbox") {
    return (
      <input
        type="checkbox"
        disabled={readOnly}
        className="h-4 w-4 rounded border-surface-border disabled:cursor-not-allowed disabled:opacity-60"
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }
  if (col.kind === "number") {
    return (
      <input
        type="number"
        readOnly={readOnly}
        className="w-full min-w-[4rem] rounded border border-surface-border bg-black/30 px-2 py-1 text-neutral-100 read-only:cursor-default read-only:opacity-90"
        value={typeof value === "number" ? value : Number(value) || 0}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    );
  }
  if (col.kind === "select" && col.options?.length) {
    return (
      <select
        disabled={readOnly}
        className="w-full rounded border border-surface-border bg-black/30 px-2 py-1 text-neutral-100 disabled:cursor-not-allowed disabled:opacity-60"
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      >
        {col.options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    );
  }
  return (
    <input
      type="text"
      readOnly={readOnly}
      className="w-full rounded border border-surface-border bg-black/30 px-2 py-1 text-neutral-100 read-only:cursor-default read-only:opacity-90"
      value={value == null ? "" : String(value)}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}
