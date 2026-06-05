import { useCallback, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import ReactGridLayout, {
  useContainerWidth,
  verticalCompactor,
  type Layout,
} from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

import {
  GRID_BLOCK_DEFINITIONS,
  GRID_MOBILE_STACK_MAX_WIDTH,
  blockDataPathPrefix,
  blockShellClassForType,
  blockSupportsExpand,
  createGridBlock,
  initialDataPatchForBlock,
  layoutFromBlocks,
} from "./blockRegistry";
import { BlockExpandModal } from "./BlockExpandModal";
import type { BlockType, UiBlock, UiLayout } from "./types";
import { DashboardBlockTile } from "./DashboardBlocks";

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

function AddBlockToolbar(props: { onAdd: (type: BlockType) => void }) {
  const { t } = useTranslation(["dashboard"]);
  const { onAdd } = props;
  return (
    <div className="flex flex-wrap gap-2">
      {GRID_BLOCK_DEFINITIONS.map((definition) => (
        <button
          key={definition.type}
          type="button"
          className="dashboard-grid-no-drag rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
          onClick={() => onAdd(definition.type)}
        >
          {t(definition.addLabelKey as "dashboard:addList")}
        </button>
      ))}
    </div>
  );
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
  const [expandedBlockId, setExpandedBlockId] = useState<string | null>(null);

  const expandedBlock = useMemo(
    () => (expandedBlockId ? layout.blocks.find((b) => b.id === expandedBlockId) ?? null : null),
    [expandedBlockId, layout.blocks]
  );

  const mobileStack = mounted && width > 0 && width < GRID_MOBILE_STACK_MAX_WIDTH;
  const layoutInteractive = editMode && !mobileStack;

  const rglLayout = useMemo(
    () => layoutFromBlocks(layout.blocks, { editMode: layoutInteractive, mobileStack }),
    [layout.blocks, layoutInteractive, mobileStack]
  );

  const onLayoutChange = useCallback(
    (next: Layout) => {
      if (!layoutInteractive) return;
      setLayout((prev) => mergeRglIntoBlocks(prev, next));
    },
    [layoutInteractive, setLayout]
  );

  const addBlock = useCallback(
    (type: BlockType) => {
      const prefix = blockDataPathPrefix(type);
      const dp = uniqueDataPath(prefix, layout.blocks, data);
      const y =
        layout.blocks.length === 0
          ? 0
          : layout.blocks.reduce((m, b) => Math.max(m, b.grid.y + b.grid.h), 0);
      const block = createGridBlock(type, dp, y);
      setLayout((prev) => ({ version: 1, blocks: [...prev.blocks, block] }));
      setData((d) => ({ ...d, ...initialDataPatchForBlock(type, dp, t) }));
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
        {editMode ? <AddBlockToolbar onAdd={addBlock} /> : null}
        <p className="text-sm text-surface-muted">{t("dashboard:noBlocksInLayout")}</p>
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-3">
      {editMode ? <AddBlockToolbar onAdd={addBlock} /> : null}
      {mobileStack ? (
        <p className="text-[11px] text-surface-muted">{t("dashboard:gridMobileStackHint")}</p>
      ) : null}

      <div ref={containerRef} className="min-h-[200px] min-w-0">
        {mounted && width > 0 ? (
          <ReactGridLayout
            width={width}
            layout={rglLayout}
            gridConfig={{ cols: 12, rowHeight: 44, margin: [8, 8], containerPadding: [4, 4] }}
            dragConfig={{
              enabled: layoutInteractive,
              bounded: true,
              cancel: ".dashboard-grid-no-drag",
              threshold: 4,
            }}
            resizeConfig={{
              enabled: layoutInteractive,
              handles: ["se", "sw", "ne", "nw", "e", "w", "n", "s"],
            }}
            compactor={verticalCompactor}
            onLayoutChange={onLayoutChange}
          >
            {layout.blocks.map((b) => {
              const canExpand = blockSupportsExpand(b.type);
              const showBlockToolbar = editMode || canExpand;
              return (
              <div
                key={b.id}
                className="overflow-hidden rounded-xl border border-surface-border bg-surface-raised/90 shadow-sm"
              >
                <div className={blockShellClassForType(b.type)}>
                  {showBlockToolbar ? (
                    <div className="sticky top-0 z-10 flex justify-end gap-1 border-b border-white/5 bg-surface-raised/95 px-1 py-1">
                      {canExpand ? (
                        <button
                          type="button"
                          className="dashboard-grid-no-drag rounded px-2 py-0.5 text-xs text-sky-200 hover:bg-sky-950/50"
                          title={t("dashboard:blockExpand")}
                          aria-label={t("dashboard:blockExpand")}
                          onClick={() => setExpandedBlockId(b.id)}
                        >
                          {t("dashboard:blockExpand")}
                        </button>
                      ) : null}
                      {editMode ? (
                        <button
                          type="button"
                          className="dashboard-grid-no-drag rounded px-2 py-0.5 text-xs text-red-300 hover:bg-red-950/50"
                          onClick={() => removeBlock(b.id)}
                        >
                          {t("dashboard:gridRemoveBlock")}
                        </button>
                      ) : null}
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
            );
            })}
          </ReactGridLayout>
        ) : null}
      </div>

      {expandedBlock ? (
        <BlockExpandModal
          block={expandedBlock}
          data={data}
          setData={setData}
          readOnly={contentReadOnly}
          dashboardId={dashboardId ?? null}
          onClose={() => setExpandedBlockId(null)}
        />
      ) : null}
    </div>
  );
}
