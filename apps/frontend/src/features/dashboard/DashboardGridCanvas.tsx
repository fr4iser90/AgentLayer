import { useCallback, useMemo } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import ReactGridLayout, {
  useContainerWidth,
  verticalCompactor,
  type Layout,
} from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

import type { BlockType, ColumnDef, UiBlock, UiLayout } from "./types";
import { DashboardBlockTile } from "./DashboardBlocks";

const BLOCK_PREFIX: Record<BlockType, string> = {
  table: "items",
  markdown: "notes",
  gallery: "photos",
  hero: "hero",
  timeline: "timeline",
  stat: "stat",
  chart: "chart",
  sparkline: "sparkline",
  kanban: "kanban",
  rich_markdown: "rich_md",
  embed: "embed",
};

function newBlockId(): string {
  return `blk_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function usedDataPaths(blocks: UiBlock[]): Set<string> {
  const s = new Set<string>();
  for (const b of blocks) {
    const p = b.props.dataPath?.trim();
    if (p) s.add(p);
  }
  return s;
}

function uniqueDataPath(prefix: string, blocks: UiBlock[], data: Record<string, unknown>): string {
  const used = usedDataPaths(blocks);
  for (const k of Object.keys(data)) used.add(k);
  for (let i = 0; i < 80; i++) {
    const p = `${prefix}_${Math.random().toString(36).slice(2, 8)}`;
    if (!used.has(p)) return p;
  }
  return `${prefix}_${Date.now()}`;
}

const defaultTableColumns: ColumnDef[] = [
  { field: "done", kind: "checkbox", label: "" },
  { field: "name", kind: "text", label: "" },
];

function makeBlock(type: BlockType, dp: string, y: number): UiBlock {
  if (type === "hero") {
    return {
      id: newBlockId(),
      type: "hero",
      grid: { x: 0, y, w: 12, h: 8 },
      props: { dataPath: dp, title: "" },
    };
  }
  if (type === "timeline") {
    return {
      id: newBlockId(),
      type: "timeline",
      grid: { x: 0, y, w: 12, h: 9 },
      props: { dataPath: dp, title: "" },
    };
  }
  if (type === "stat") {
    return {
      id: newBlockId(),
      type: "stat",
      grid: { x: 0, y, w: 4, h: 5 },
      props: { dataPath: dp, title: "" },
    };
  }
  if (type === "chart") {
    return {
      id: newBlockId(),
      type: "chart",
      grid: { x: 0, y, w: 12, h: 10 },
      props: { dataPath: dp, title: "" },
    };
  }
  if (type === "sparkline") {
    return {
      id: newBlockId(),
      type: "sparkline",
      grid: { x: 0, y, w: 6, h: 4 },
      props: { dataPath: dp, title: "" },
    };
  }
  if (type === "kanban") {
    return {
      id: newBlockId(),
      type: "kanban",
      grid: { x: 0, y, w: 12, h: 12 },
      props: { dataPath: dp, title: "" },
    };
  }
  if (type === "rich_markdown") {
    return {
      id: newBlockId(),
      type: "rich_markdown",
      grid: { x: 0, y, w: 12, h: 9 },
      props: { dataPath: dp, placeholder: "", title: "" },
    };
  }
  if (type === "embed") {
    return {
      id: newBlockId(),
      type: "embed",
      grid: { x: 0, y, w: 12, h: 10 },
      props: { dataPath: dp, title: "" },
    };
  }
  const grid = { x: 0, y, w: 6, h: 6 };
  if (type === "table") {
    return {
      id: newBlockId(),
      type: "table",
      grid,
      props: { dataPath: dp, columns: [...defaultTableColumns] },
    };
  }
  if (type === "markdown") {
    return {
      id: newBlockId(),
      type: "markdown",
      grid,
      props: { dataPath: dp, placeholder: "" },
    };
  }
  return {
    id: newBlockId(),
    type: "gallery",
    grid,
    props: { dataPath: dp, title: "Photos" },
  };
}

function blockMinDims(b: UiBlock): { minW: number; minH: number } {
  if (b.type === "hero") return { minW: 4, minH: 4 };
  if (b.type === "stat") return { minW: 2, minH: 3 };
  if (b.type === "timeline") return { minW: 4, minH: 5 };
  if (b.type === "chart") return { minW: 4, minH: 6 };
  if (b.type === "sparkline") return { minW: 2, minH: 3 };
  if (b.type === "kanban") return { minW: 6, minH: 6 };
  if (b.type === "rich_markdown") return { minW: 4, minH: 6 };
  if (b.type === "embed") return { minW: 4, minH: 6 };
  return { minW: 2, minH: 3 };
}

function layoutFromBlocks(blocks: UiBlock[], editMode: boolean): Layout {
  return blocks.map((b) => {
    const { minW, minH } = blockMinDims(b);
    return {
      i: b.id,
      x: Math.min(11, Math.max(0, b.grid.x)),
      y: Math.max(0, b.grid.y),
      w: Math.min(12, Math.max(minW, b.grid.w)),
      h: Math.max(minH, b.grid.h),
      static: !editMode,
      minW,
      minH,
      maxW: 12,
    };
  });
}

function mergeRglIntoBlocks(prev: UiLayout, rgl: Layout): UiLayout {
  const pos = new Map(rgl.map((it) => [it.i, it]));
  return {
    version: 1,
    blocks: prev.blocks.map((b) => {
      const L = pos.get(b.id);
      if (!L) return b;
      return {
        ...b,
        grid: { x: L.x, y: L.y, w: L.w, h: L.h },
      };
    }),
  };
}

export function DashboardGridCanvas(props: {
  layout: UiLayout;
  setLayout: Dispatch<SetStateAction<UiLayout>>;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  editMode: boolean;
  /** When true, block content is not editable (layout may still use editMode for owner/editor). */
  contentReadOnly?: boolean;
  dashboardId?: string | null;
}) {
  const { t } = useTranslation(["dashboard"]);
  const { layout, setLayout, data, setData, editMode, contentReadOnly = false, dashboardId } = props;
  const { width, containerRef, mounted } = useContainerWidth();

  const rglLayout = useMemo(
    () => layoutFromBlocks(layout.blocks, editMode),
    [layout.blocks, editMode]
  );

  const onLayoutChange = useCallback(
    (next: Layout) => {
      if (!editMode) return;
      setLayout((prev) => mergeRglIntoBlocks(prev, next));
    },
    [editMode, setLayout]
  );

  const addBlock = useCallback(
    (type: BlockType) => {
      const prefix = BLOCK_PREFIX[type];
      const dp = uniqueDataPath(prefix, layout.blocks, data);
      const y =
        layout.blocks.length === 0
          ? 0
          : layout.blocks.reduce((m, b) => Math.max(m, b.grid.y + b.grid.h), 0);
      const block = makeBlock(type, dp, y);
      setLayout((prev) => ({ version: 1, blocks: [...prev.blocks, block] }));
      setData((d) => {
        const n = { ...d };
        if (type === "table" || type === "gallery" || type === "timeline") n[dp] = [];
        else if (type === "hero")
          n[dp] = { url: "", caption: "", headline: "" };
        else if (type === "stat")
          n[dp] = { value: "", label: "", suffix: "", trend: "" };
        else if (type === "chart")
          n[dp] = {
            chartType: "line",
            labels: ["Q1", "Q2", "Q3"],
            series: [{ label: t("dashboard:chartSeriesN", { n: 1 }), data: [12, 19, 3] }],
          };
        else if (type === "sparkline") n[dp] = { values: [2, 5, 3, 8, 6, 4, 7] };
        else if (type === "kanban") {
          const tms = Date.now();
          n[dp] = {
            columns: [
              { id: `col_${tms}_a`, title: t("dashboard:kanbanTodo"), cards: [] },
              { id: `col_${tms}_b`, title: t("dashboard:kanbanDoing"), cards: [] },
              { id: `col_${tms}_c`, title: t("dashboard:kanbanDone"), cards: [] },
            ],
          };
        } else if (type === "rich_markdown") n[dp] = "";
        else if (type === "embed")
          n[dp] = { url: "", title: "", height: 480 };
        else n[dp] = "";
        return n;
      });
    },
    [layout.blocks, data, setLayout, setData, t]
  );

  const removeBlock = useCallback(
    (id: string) => {
      const b = layout.blocks.find((x) => x.id === id);
      const dp = b?.props?.dataPath;
      setLayout((prev) => ({
        version: 1,
        blocks: prev.blocks.filter((x) => x.id !== id),
      }));
      if (dp && !dp.includes(".")) {
        setData((d) => {
          const n = { ...d };
          delete n[dp];
          return n;
        });
      }
    },
    [layout.blocks, setLayout, setData]
  );

  if (!layout.blocks.length) {
    return (
      <div className="space-y-3">
        {editMode ? (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              onClick={() => addBlock("table")}
            >
              {t("dashboard:addList")}
            </button>
            <button
              type="button"
              className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              onClick={() => addBlock("markdown")}
            >
              {t("dashboard:addNotes")}
            </button>
            <button
              type="button"
              className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              onClick={() => addBlock("gallery")}
            >
              {t("dashboard:addPhotos")}
            </button>
            <button
              type="button"
              className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              onClick={() => addBlock("hero")}
            >
              {t("dashboard:addHero")}
            </button>
            <button
              type="button"
              className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              onClick={() => addBlock("timeline")}
            >
              {t("dashboard:addTimeline")}
            </button>
            <button
              type="button"
              className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              onClick={() => addBlock("stat")}
            >
              {t("dashboard:addKpi")}
            </button>
            <button
              type="button"
              className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              onClick={() => addBlock("chart")}
            >
              {t("dashboard:addChart")}
            </button>
            <button
              type="button"
              className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              onClick={() => addBlock("sparkline")}
            >
              {t("dashboard:addSpark")}
            </button>
            <button
              type="button"
              className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              onClick={() => addBlock("kanban")}
            >
              {t("dashboard:addKanban")}
            </button>
            <button
              type="button"
              className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              onClick={() => addBlock("rich_markdown")}
            >
              {t("dashboard:addRichMarkdown")}
            </button>
            <button
              type="button"
              className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              onClick={() => addBlock("embed")}
            >
              {t("dashboard:addEmbed")}
            </button>
          </div>
        ) : null}
        <p className="text-sm text-surface-muted">{t("dashboard:noBlocksInLayout")}</p>
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-3">
      {editMode ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            onClick={() => addBlock("table")}
          >
            {t("dashboard:addList")}
          </button>
          <button
            type="button"
            className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            onClick={() => addBlock("markdown")}
          >
            {t("dashboard:addNotes")}
          </button>
          <button
            type="button"
            className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            onClick={() => addBlock("gallery")}
          >
            {t("dashboard:addPhotos")}
          </button>
          <button
            type="button"
            className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            onClick={() => addBlock("hero")}
          >
            {t("dashboard:addHero")}
          </button>
          <button
            type="button"
            className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            onClick={() => addBlock("timeline")}
          >
            {t("dashboard:addTimeline")}
          </button>
          <button
            type="button"
            className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            onClick={() => addBlock("stat")}
          >
            {t("dashboard:addKpi")}
          </button>
          <button
            type="button"
            className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            onClick={() => addBlock("chart")}
          >
            {t("dashboard:addChart")}
          </button>
          <button
            type="button"
            className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            onClick={() => addBlock("sparkline")}
          >
            {t("dashboard:addSpark")}
          </button>
          <button
            type="button"
            className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            onClick={() => addBlock("kanban")}
          >
            {t("dashboard:addKanban")}
          </button>
          <button
            type="button"
            className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            onClick={() => addBlock("rich_markdown")}
          >
            {t("dashboard:addRichMarkdown")}
          </button>
          <button
            type="button"
            className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            onClick={() => addBlock("embed")}
          >
            {t("dashboard:addEmbed")}
          </button>
        </div>
      ) : null}

      <div ref={containerRef} className="min-h-[200px] min-w-0">
        {mounted && width > 0 ? (
          <ReactGridLayout
            width={width}
            layout={rglLayout}
            gridConfig={{ cols: 12, rowHeight: 44, margin: [8, 8], containerPadding: [4, 4] }}
            dragConfig={{
              enabled: editMode,
              bounded: true,
              cancel: ".dashboard-grid-no-drag",
              threshold: 4,
            }}
            resizeConfig={{
              enabled: editMode,
              handles: ["se", "sw", "ne", "nw", "e", "w", "n", "s"],
            }}
            compactor={verticalCompactor}
            onLayoutChange={onLayoutChange}
          >
            {layout.blocks.map((b) => (
              <div
                key={b.id}
                className="overflow-hidden rounded-xl border border-surface-border bg-surface-raised/90 shadow-sm"
              >
                <div
                  className={
                    b.type === "hero"
                      ? "flex max-h-[min(720px,88vh)] flex-col overflow-auto"
                      : b.type === "timeline"
                        ? "flex max-h-[min(640px,82vh)] flex-col overflow-auto"
                        : b.type === "chart" ||
                            b.type === "kanban" ||
                            b.type === "rich_markdown" ||
                            b.type === "embed"
                          ? "flex max-h-[min(720px,90vh)] flex-col overflow-auto"
                          : "flex max-h-[min(520px,65vh)] flex-col overflow-auto"
                  }
                >
                  {editMode ? (
                    <div className="sticky top-0 z-10 flex justify-end border-b border-white/5 bg-surface-raised/95 px-1 py-1">
                      <button
                        type="button"
                        className="dashboard-grid-no-drag rounded px-2 py-0.5 text-xs text-red-300 hover:bg-red-950/50"
                        onClick={() => removeBlock(b.id)}
                      >
                        {t("dashboard:gridRemoveBlock")}
                      </button>
                    </div>
                  ) : null}
                  <div className="min-h-0 flex-1 p-2">
                    <DashboardBlockTile
                      block={b}
                      data={data}
                      setData={setData}
                      readOnly={contentReadOnly}
                      dashboardId={dashboardId ?? null}
                    />
                  </div>
                </div>
              </div>
            ))}
          </ReactGridLayout>
        ) : null}
      </div>
    </div>
  );
}
