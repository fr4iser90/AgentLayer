import { useCallback, useMemo, useState, type RefObject } from "react";
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
  NESTED_GRID_BLOCK_DEFINITIONS,
  ROOT_GRID_TOOLBAR_DEFINITIONS,
  blockDataPathPrefix,
  blockShellClassForType,
  blockSupportsExpand,
  createGridBlock,
  initialDataPatchForBlock,
  layoutFromBlocks,
  type GridBlockDefinition,
} from "./blockRegistry";
import { BlockExpandModal } from "./BlockExpandModal";
import { AgentUpdateBadge } from "./AgentUpdateBadge";
import type { BlockType, UiBlock, UiLayout } from "./types";
import { DashboardBlockTile } from "./DashboardBlocks";
import {
  GRID_COLS,
  GRID_CONTAINER_PADDING,
  GRID_MARGIN,
  GRID_MOBILE_STACK_MAX_WIDTH,
  GRID_ROW_HEIGHT,
  MAX_BLOCKS_TOTAL,
} from "./gridConfig";
import { blockTypeLabel, countLayoutBlocks, sectionHasUnreadNested } from "./layoutTree";

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
    version: prev.version === 2 ? 2 : 1,
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

function blockTitle(block: UiBlock): string {
  const custom = block.props.title?.trim();
  if (custom) return custom;
  return blockTypeLabel(block.type);
}

function AddBlockToolbar(props: {
  definitions: GridBlockDefinition[];
  onAdd: (type: BlockType) => void;
  compact?: boolean;
}) {
  const { t } = useTranslation(["dashboard"]);
  const { definitions, onAdd, compact } = props;
  return (
    <div className={`flex flex-wrap gap-2 ${compact ? "" : "mb-1"}`}>
      {definitions.map((definition) => (
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

export type DashboardGridInnerProps = {
  layout: UiLayout;
  setLayout: Dispatch<SetStateAction<UiLayout>>;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  editMode: boolean;
  contentReadOnly?: boolean;
  dashboardId?: string | null;
  /** 0 = root dashboard grid; 1 = inside a section block */
  depth?: 0 | 1;
  /** Root layout + setter — required for section blocks at depth 0 */
  rootLayout?: UiLayout;
  setRootLayout?: Dispatch<SetStateAction<UiLayout>>;
  /** Hide outer toolbar (section provides its own) */
  hideToolbar?: boolean;
  /** Nested grid uses containerRef from parent section */
  embedded?: boolean;
  /** Pin block to another dashboard (live dashboard_ref) */
  onPinBlock?: (blockId: string) => void;
  /** Block ids with unread agent-update notifications */
  unreadBlockIds?: Set<string>;
  /** Pulse/highlight one block (e.g. from ?block= deep link) */
  highlightBlockId?: string | null;
  /** Mark block notifications read (per block) */
  onBlockSeen?: (blockId: string) => void;
};

export function DashboardGridInner(props: DashboardGridInnerProps) {
  const { t } = useTranslation(["dashboard", "notifications"]);
  const {
    layout,
    setLayout,
    data,
    setData,
    editMode,
    contentReadOnly = false,
    dashboardId,
    depth = 0,
    rootLayout,
    setRootLayout,
    hideToolbar = false,
    embedded = false,
    onPinBlock,
    unreadBlockIds,
    highlightBlockId,
    onBlockSeen,
  } = props;
  const { width, containerRef, mounted } = useContainerWidth();
  const [expandedBlockId, setExpandedBlockId] = useState<string | null>(null);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);

  const toolbarDefinitions =
    depth === 0 ? ROOT_GRID_TOOLBAR_DEFINITIONS : NESTED_GRID_BLOCK_DEFINITIONS;
  const effectiveRootLayout = rootLayout ?? layout;
  const effectiveSetRootLayout = setRootLayout ?? setLayout;

  const expandedBlock = useMemo(() => {
    if (!expandedBlockId) return null;
    if (expandedBlockId && depth === 0) {
      const root = layout.blocks.find((b) => b.id === expandedBlockId);
      if (root) return root;
    }
    for (const b of layout.blocks) {
      if (b.id === expandedBlockId) return b;
      if (b.type === "section") {
        const nested = b.props.nested;
        const found = nested?.blocks?.find((nb) => nb.id === expandedBlockId);
        if (found) return found;
      }
    }
    return null;
  }, [expandedBlockId, layout.blocks, depth]);

  const mobileStack = mounted && width > 0 && width < GRID_MOBILE_STACK_MAX_WIDTH;
  const layoutInteractive = editMode && !mobileStack;

  const acknowledgeBlock = useCallback(
    (blockId: string) => {
      if (unreadBlockIds?.has(blockId)) onBlockSeen?.(blockId);
    },
    [unreadBlockIds, onBlockSeen]
  );

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
      if (countLayoutBlocks(effectiveRootLayout) >= MAX_BLOCKS_TOTAL) return;
      const prefix = blockDataPathPrefix(type);
      const dp = type === "section" ? "" : uniqueDataPath(prefix, layout.blocks, data);
      const y =
        layout.blocks.length === 0
          ? 0
          : layout.blocks.reduce((m, b) => Math.max(m, b.grid.y + b.grid.h), 0);
      const block = createGridBlock(type, dp, y);
      setLayout((prev) => ({
        version: type === "section" || prev.version === 2 ? 2 : prev.version,
        blocks: [...prev.blocks, block],
      }));
      if (type !== "section") {
        setData((d) => ({ ...d, ...initialDataPatchForBlock(type, dp, t) }));
      }
    },
    [layout.blocks, data, setLayout, setData, t, effectiveRootLayout]
  );

  const removeBlock = useCallback(
    (id: string) => {
      const b = layout.blocks.find((x) => x.id === id);
      const dp = b?.props?.dataPath;
      setLayout((prev) => ({
        version: prev.version,
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
        {editMode && !hideToolbar ? <AddBlockToolbar definitions={toolbarDefinitions} onAdd={addBlock} /> : null}
        <p className="text-sm text-surface-muted">{t("dashboard:noBlocksInLayout")}</p>
      </div>
    );
  }

  const gridBody = (
    <>
      {mounted && width > 0 ? (
        <ReactGridLayout
          width={width}
          layout={rglLayout}
          gridConfig={{
            cols: GRID_COLS,
            rowHeight: GRID_ROW_HEIGHT,
            margin: GRID_MARGIN,
            containerPadding: GRID_CONTAINER_PADDING,
          }}
          dragConfig={{
            enabled: layoutInteractive,
            bounded: true,
            cancel: ".dashboard-grid-no-drag",
            handle: ".dashboard-grid-drag-handle",
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
            const showBlockToolbar = editMode || canExpand || Boolean(onPinBlock);
            const isSelected = selectedBlockId === b.id;
            const hasUnread =
              (unreadBlockIds?.has(b.id) ?? false) ||
              (b.type === "section" && sectionHasUnreadNested(b, unreadBlockIds));
            const isHighlighted = highlightBlockId === b.id;
            const badgeTitle = t("notifications:agentUpdateBadge");
            return (
              <div
                key={b.id}
                data-block-id={b.id}
                className={[
                  "relative overflow-hidden rounded-xl border bg-surface-raised/90 shadow-sm transition-colors",
                  isSelected && editMode
                    ? "border-sky-500/60 ring-1 ring-sky-500/30"
                    : isHighlighted
                      ? "border-orange-500/50 ring-2 ring-orange-500/40"
                      : hasUnread
                        ? "border-orange-500/25"
                        : "border-surface-border",
                ].join(" ")}
                onClick={() => {
                  if (editMode) setSelectedBlockId(b.id);
                  else acknowledgeBlock(b.id);
                }}
              >
                {hasUnread ? <AgentUpdateBadge title={badgeTitle} pulse={isHighlighted} /> : null}
                <div className={blockShellClassForType(b.type)}>
                  {showBlockToolbar || editMode ? (
                    <div className="dashboard-grid-drag-handle sticky top-0 z-10 flex cursor-grab items-center gap-2 border-b border-white/5 bg-surface-raised/95 px-2 py-1 active:cursor-grabbing">
                      <span className="min-w-0 flex-1 truncate text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                        {blockTitle(b)}
                      </span>
                      <div className="flex shrink-0 gap-1">
                        {canExpand ? (
                          <button
                            type="button"
                            className="dashboard-grid-no-drag rounded px-2 py-0.5 text-xs text-sky-200 hover:bg-sky-950/50"
                            title={t("dashboard:blockExpand")}
                            aria-label={t("dashboard:blockExpand")}
                            onClick={() => {
                              acknowledgeBlock(b.id);
                              setExpandedBlockId(b.id);
                            }}
                          >
                            {t("dashboard:blockExpand")}
                          </button>
                        ) : null}
                        {onPinBlock && b.type !== "dashboard_ref" ? (
                          <button
                            type="button"
                            className="dashboard-grid-no-drag rounded px-2 py-0.5 text-xs text-violet-200 hover:bg-violet-950/50"
                            onClick={() => onPinBlock(b.id)}
                          >
                            {t("dashboard:pinBlock")}
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
                    </div>
                  ) : null}
                  <div className="min-h-0 flex-1 p-2">
                    <DashboardBlockTile
                      block={b}
                      data={data}
                      setData={setData}
                      readOnly={contentReadOnly}
                      dashboardId={dashboardId ?? null}
                      rootLayout={effectiveRootLayout}
                      setRootLayout={effectiveSetRootLayout}
                      gridEditMode={editMode}
                      gridContentReadOnly={contentReadOnly}
                      gridDashboardId={dashboardId ?? null}
                      unreadBlockIds={unreadBlockIds}
                      highlightBlockId={highlightBlockId}
                      onBlockSeen={onBlockSeen}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </ReactGridLayout>
      ) : null}
    </>
  );

  return (
    <div className={`min-w-0 space-y-3 ${embedded ? "" : ""}`}>
      {editMode && !hideToolbar ? (
        <AddBlockToolbar definitions={toolbarDefinitions} onAdd={addBlock} />
      ) : null}
      {mobileStack ? (
        <p className="text-[11px] text-surface-muted">{t("dashboard:gridMobileStackHint")}</p>
      ) : null}

      <div ref={containerRef as RefObject<HTMLDivElement>} className="min-h-[200px] min-w-0">
        {gridBody}
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

export function DashboardGridCanvas(props: {
  layout: UiLayout;
  setLayout: Dispatch<SetStateAction<UiLayout>>;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  editMode: boolean;
  contentReadOnly?: boolean;
  dashboardId?: string | null;
  hideToolbar?: boolean;
  onPinBlock?: (blockId: string) => void;
  unreadBlockIds?: Set<string>;
  highlightBlockId?: string | null;
  onBlockSeen?: (blockId: string) => void;
}) {
  return <DashboardGridInner {...props} depth={0} rootLayout={props.layout} setRootLayout={props.setLayout} />;
}
