import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type PointerEvent as ReactPointerEvent,
  type SetStateAction,
} from "react";
import { useTranslation } from "react-i18next";

import {
  ROOT_GRID_TOOLBAR_DEFINITIONS,
  blockDataPathPrefix,
  blockShellClassForBlock,
  blockSupportsExpand,
  createGridBlock,
  initialDataPatchForBlock,
} from "./blockRegistry";
import { BlockExpandModal } from "./BlockExpandModal";
import { BlockSettingsModal } from "./BlockSettingsModal";
import { AgentUpdateBadge } from "./AgentUpdateBadge";
import type { BlockType, UiBlock, UiLayout } from "./types";
import { DashboardBlockTile } from "./DashboardBlocks";
import { MAX_BLOCKS_TOTAL } from "./gridConfig";
import {
  CANVAS_CELL_H,
  CANVAS_CELL_W,
  clampZoom,
  gridToWorldRect,
  worldToGridPos,
} from "./layoutMode";
import {
  blockTypeLabel,
  countLayoutBlocks,
  findBlockById,
  sectionHasUnreadNested,
  updateBlockById,
} from "./layoutTree";

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

function blockTitle(block: UiBlock): string {
  const custom = block.props.title?.trim();
  if (custom) return custom;
  return blockTypeLabel(block.type);
}

type DragKind = "pan" | "move" | "resize";

type DragState = {
  kind: DragKind;
  pointerId: number;
  startClientX: number;
  startClientY: number;
  originPanX: number;
  originPanY: number;
  blockId?: string;
  originLeft?: number;
  originTop?: number;
  originWidth?: number;
  originHeight?: number;
};

export type DashboardCanvasSurfaceProps = {
  layout: UiLayout;
  setLayout: Dispatch<SetStateAction<UiLayout>>;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  editMode: boolean;
  contentReadOnly?: boolean;
  interactOnly?: boolean;
  dashboardId?: string | null;
  hideToolbar?: boolean;
  onPinBlock?: (blockId: string) => void;
  onPinBlockToChat?: (blockId: string) => void;
  chatFocusedBlockId?: string | null;
  onBlockPropsSave?: (blockId: string, nextProps: UiBlock["props"]) => void | Promise<void>;
  blockSettingsAutoSave?: boolean;
  blockSettingsSaving?: boolean;
  unreadBlockIds?: Set<string>;
  highlightBlockId?: string | null;
  onBlockSeen?: (blockId: string) => void;
  /** When true, viewport fills the parent instead of a fixed vh cap. */
  fillViewport?: boolean;
};

export function DashboardCanvasSurface(props: DashboardCanvasSurfaceProps) {
  const { t } = useTranslation(["dashboard", "notifications"]);
  const {
    layout,
    setLayout,
    data,
    setData,
    editMode,
    contentReadOnly = false,
    interactOnly = false,
    dashboardId,
    hideToolbar = false,
    onPinBlock,
    onPinBlockToChat,
    chatFocusedBlockId = null,
    onBlockPropsSave,
    blockSettingsAutoSave = false,
    blockSettingsSaving = false,
    fillViewport = false,
    unreadBlockIds,
    highlightBlockId,
    onBlockSeen,
  } = props;

  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [zoom, setZoom] = useState(() => clampZoom(layout.canvas?.zoom ?? 1));
  const [panX, setPanX] = useState(() => layout.canvas?.panX ?? 0);
  const [panY, setPanY] = useState(() => layout.canvas?.panY ?? 0);
  const [spaceDown, setSpaceDown] = useState(false);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [expandedBlockId, setExpandedBlockId] = useState<string | null>(null);
  const [settingsBlockId, setSettingsBlockId] = useState<string | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    if (!dragging) return;
    const prev = document.body.style.userSelect;
    document.body.style.userSelect = "none";
    return () => {
      document.body.style.userSelect = prev;
    };
  }, [dragging]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code === "Space" && !e.repeat) setSpaceDown(true);
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code === "Space") setSpaceDown(false);
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, []);

  const persistViewport = useCallback(
    (next: { zoom?: number; panX?: number; panY?: number }) => {
      setLayout((prev) => ({
        ...prev,
        mode: "canvas",
        canvas: {
          zoom: next.zoom ?? prev.canvas?.zoom ?? zoom,
          panX: next.panX ?? prev.canvas?.panX ?? panX,
          panY: next.panY ?? prev.canvas?.panY ?? panY,
        },
      }));
    },
    [setLayout, zoom, panX, panY]
  );

  const settingsBlock = useMemo(() => {
    if (!settingsBlockId) return null;
    return findBlockById(layout, settingsBlockId);
  }, [layout, settingsBlockId]);

  const expandedBlock = useMemo(() => {
    if (!expandedBlockId) return null;
    return findBlockById(layout, expandedBlockId);
  }, [expandedBlockId, layout]);

  const acknowledgeBlock = useCallback(
    (blockId: string) => {
      if (unreadBlockIds?.has(blockId)) onBlockSeen?.(blockId);
    },
    [unreadBlockIds, onBlockSeen]
  );

  const updateBlockGrid = useCallback(
    (blockId: string, grid: UiBlock["grid"]) => {
      setLayout((prev) => ({
        ...prev,
        mode: "canvas",
        blocks: prev.blocks.map((b) => (b.id === blockId ? { ...b, grid } : b)),
      }));
    },
    [setLayout]
  );

  const addBlock = useCallback(
    (type: BlockType) => {
      if (countLayoutBlocks(layout) >= MAX_BLOCKS_TOTAL) return;
      const prefix = blockDataPathPrefix(type);
      const dp = type === "section" ? "" : uniqueDataPath(prefix, layout.blocks, data);
      const vp = viewportRef.current;
      const vw = vp?.clientWidth ?? 900;
      const vh = vp?.clientHeight ?? 560;
      const worldX = (-panX + vw / 2) / zoom - 3 * CANVAS_CELL_W;
      const worldY = (-panY + vh / 2) / zoom - 2 * CANVAS_CELL_H;
      const block = createGridBlock(type, dp, 0);
      const def = block.grid;
      block.grid = worldToGridPos(
        worldX,
        worldY,
        def.w * CANVAS_CELL_W,
        def.h * CANVAS_CELL_H
      );
      setLayout((prev) => ({
        ...prev,
        mode: "canvas",
        version: type === "section" || prev.version === 2 ? 2 : prev.version,
        blocks: [...prev.blocks, block],
      }));
      if (type !== "section") {
        setData((d) => ({ ...d, ...initialDataPatchForBlock(type, dp, t) }));
      }
    },
    [layout, data, setLayout, setData, t, panX, panY, zoom]
  );

  const removeBlock = useCallback(
    (id: string) => {
      const b = layout.blocks.find((x) => x.id === id);
      const dp = b?.props?.dataPath;
      setLayout((prev) => ({
        ...prev,
        mode: "canvas",
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

  // Native non-passive wheel: Ctrl/⌘+scroll and trackpad pinch zoom only this
  // viewport (React's onWheel is often passive, so browser page-zoom would win).
  const viewRef = useRef({ zoom, panX, panY, editMode, persistViewport });
  viewRef.current = { zoom, panX, panY, editMode, persistViewport };

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const onWheelNative = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const v = viewRef.current;
      if (e.ctrlKey || e.metaKey) {
        const factor = e.deltaY > 0 ? 0.92 : 1.08;
        const next = clampZoom(v.zoom * factor);
        setZoom(next);
        if (v.editMode) v.persistViewport({ zoom: next });
        return;
      }
      const nextPanX = v.panX - e.deltaX;
      const nextPanY = v.panY - e.deltaY;
      setPanX(nextPanX);
      setPanY(nextPanY);
      if (v.editMode) v.persistViewport({ panX: nextPanX, panY: nextPanY });
    };
    el.addEventListener("wheel", onWheelNative, { passive: false });
    return () => el.removeEventListener("wheel", onWheelNative);
  }, []);

  const nudgeZoom = (factor: number) => {
    const next = clampZoom(zoom * factor);
    setZoom(next);
    if (editMode) persistViewport({ zoom: next });
  };

  const beginPan = (e: ReactPointerEvent<HTMLDivElement>) => {
    dragRef.current = {
      kind: "pan",
      pointerId: e.pointerId,
      startClientX: e.clientX,
      startClientY: e.clientY,
      originPanX: panX,
      originPanY: panY,
    };
    setDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const beginBlockDrag = (
    e: ReactPointerEvent<HTMLElement>,
    kind: "move" | "resize",
    blockId: string,
    rect: { left: number; top: number; width: number; height: number }
  ) => {
    e.stopPropagation();
    e.preventDefault();
    setSelectedBlockId(blockId);
    dragRef.current = {
      kind,
      pointerId: e.pointerId,
      startClientX: e.clientX,
      startClientY: e.clientY,
      originPanX: panX,
      originPanY: panY,
      blockId,
      originLeft: rect.left,
      originTop: rect.top,
      originWidth: rect.width,
      originHeight: rect.height,
    };
    setDragging(true);
    viewportRef.current?.setPointerCapture(e.pointerId);
  };

  const onViewportPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button === 1 || spaceDown || e.button === 2) {
      e.preventDefault();
      beginPan(e);
      return;
    }
    if (e.button !== 0) return;
    const target = e.target as HTMLElement | null;
    // Empty board (viewport or world layer), not a block / control.
    const onEmptyBoard =
      target === e.currentTarget ||
      target?.dataset?.canvasSurface === "world" ||
      (target?.closest?.("[data-canvas-surface='world']") != null &&
        target.closest("[data-block-id]") == null);
    if (!onEmptyBoard) return;
    setSelectedBlockId(null);
    e.preventDefault();
    beginPan(e);
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    e.preventDefault();
    const dx = e.clientX - drag.startClientX;
    const dy = e.clientY - drag.startClientY;
    if (drag.kind === "pan") {
      setPanX(drag.originPanX + dx);
      setPanY(drag.originPanY + dy);
      return;
    }
    if (!editMode || !drag.blockId) return;
    if (drag.kind === "move") {
      const left = (drag.originLeft ?? 0) + dx / zoom;
      const top = (drag.originTop ?? 0) + dy / zoom;
      const width = drag.originWidth ?? CANVAS_CELL_W;
      const height = drag.originHeight ?? CANVAS_CELL_H;
      updateBlockGrid(drag.blockId, worldToGridPos(left, top, width, height));
      return;
    }
    if (drag.kind === "resize") {
      const width = Math.max(CANVAS_CELL_W, (drag.originWidth ?? CANVAS_CELL_W) + dx / zoom);
      const height = Math.max(CANVAS_CELL_H, (drag.originHeight ?? CANVAS_CELL_H) + dy / zoom);
      const left = drag.originLeft ?? 0;
      const top = drag.originTop ?? 0;
      updateBlockGrid(drag.blockId, worldToGridPos(left, top, width, height));
    }
  };

  const endPointer = (e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    if (drag.kind === "pan" && editMode) {
      persistViewport({ panX, panY });
    }
    dragRef.current = null;
    setDragging(false);
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  const fitAll = () => {
    if (!layout.blocks.length) {
      setZoom(1);
      setPanX(0);
      setPanY(0);
      if (editMode) persistViewport({ zoom: 1, panX: 0, panY: 0 });
      return;
    }
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const b of layout.blocks) {
      const r = gridToWorldRect(b.grid);
      minX = Math.min(minX, r.left);
      minY = Math.min(minY, r.top);
      maxX = Math.max(maxX, r.left + r.width);
      maxY = Math.max(maxY, r.top + r.height);
    }
    const vp = viewportRef.current;
    const vw = Math.max(320, vp?.clientWidth ?? 900);
    const vh = Math.max(240, vp?.clientHeight ?? 560);
    const pad = 48;
    const bw = Math.max(1, maxX - minX);
    const bh = Math.max(1, maxY - minY);
    const nextZoom = clampZoom(Math.min((vw - pad * 2) / bw, (vh - pad * 2) / bh));
    const nextPanX = (vw - bw * nextZoom) / 2 - minX * nextZoom;
    const nextPanY = (vh - bh * nextZoom) / 2 - minY * nextZoom;
    setZoom(nextZoom);
    setPanX(nextPanX);
    setPanY(nextPanY);
    if (editMode) persistViewport({ zoom: nextZoom, panX: nextPanX, panY: nextPanY });
  };

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col space-y-3">
      {editMode && !hideToolbar ? (
        <div className="flex flex-wrap gap-2">
          {ROOT_GRID_TOOLBAR_DEFINITIONS.map((definition) => (
            <button
              key={definition.type}
              type="button"
              className="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              onClick={() => addBlock(definition.type)}
            >
              {t(definition.addLabelKey as "dashboard:addList")}
            </button>
          ))}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2 text-[11px] text-surface-muted">
        <span>{t("dashboard:canvasHint")}</span>
        <button
          type="button"
          className="rounded border border-surface-border px-2 py-0.5 text-neutral-200 hover:bg-white/5"
          title={t("dashboard:canvasZoomOut")}
          onClick={() => nudgeZoom(0.9)}
        >
          −
        </button>
        <button
          type="button"
          className="rounded border border-surface-border px-2 py-0.5 text-neutral-200 hover:bg-white/5"
          title={t("dashboard:canvasZoomIn")}
          onClick={() => nudgeZoom(1.1)}
        >
          +
        </button>
        <button
          type="button"
          className="rounded border border-surface-border px-2 py-0.5 text-neutral-200 hover:bg-white/5"
          onClick={() => fitAll()}
        >
          {t("dashboard:canvasFit")}
        </button>
        <button
          type="button"
          className="rounded border border-surface-border px-2 py-0.5 text-neutral-200 hover:bg-white/5"
          onClick={() => {
            setZoom(1);
            if (editMode) persistViewport({ zoom: 1 });
          }}
        >
          {t("dashboard:canvasZoomReset")}
        </button>
        <span className="font-mono text-neutral-400">{Math.round(zoom * 100)}%</span>
      </div>

      {!layout.blocks.length ? (
        <p className="text-sm text-surface-muted">{t("dashboard:noBlocksInLayout")}</p>
      ) : null}

      <div
        ref={viewportRef}
        className={[
          fillViewport
            ? "relative min-h-0 h-full w-full flex-1 cursor-grab overflow-hidden rounded-xl border border-surface-border bg-[radial-gradient(circle_at_1px_1px,rgba(255,255,255,0.06)_1px,transparent_0)] bg-[length:24px_24px] bg-black/20 active:cursor-grabbing"
            : "relative h-[min(85vh,calc(100dvh-12rem))] min-h-[420px] w-full flex-1 cursor-grab overflow-hidden rounded-xl border border-surface-border bg-[radial-gradient(circle_at_1px_1px,rgba(255,255,255,0.06)_1px,transparent_0)] bg-[length:24px_24px] bg-black/20 active:cursor-grabbing",
          spaceDown ? "cursor-grab active:cursor-grabbing" : "",
          dragging ? "select-none" : "",
        ].join(" ")}
        onPointerDown={onViewportPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endPointer}
        onPointerCancel={endPointer}
        onContextMenu={(e) => e.preventDefault()}
      >
        <div
          data-canvas-surface="world"
          className="absolute left-0 top-0 origin-top-left will-change-transform"
          style={{
            // Large hit area so empty space is always draggable for pan.
            minWidth: 8000,
            minHeight: 8000,
            transform: `translate(${panX}px, ${panY}px) scale(${zoom})`,
          }}
        >
          {layout.blocks.map((b) => {
            const rect = gridToWorldRect(b.grid);
            const canExpand = blockSupportsExpand(b.type);
            const canConfigureBlock =
              Boolean(onBlockPropsSave) && b.type !== "dashboard_ref" && b.type !== "share_widget";
            const showBlockToolbar =
              editMode ||
              canExpand ||
              Boolean(onPinBlock) ||
              Boolean(onPinBlockToChat) ||
              canConfigureBlock;
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
                  "absolute cursor-auto overflow-hidden rounded-xl border bg-surface-raised/95 shadow-sm",
                  dragging ? "select-none" : "",
                  isSelected && editMode
                    ? "border-sky-500/60 ring-1 ring-sky-500/30"
                    : isHighlighted
                      ? "border-orange-500/50 ring-2 ring-orange-500/40"
                      : hasUnread
                        ? "border-orange-500/25"
                        : "border-surface-border",
                ].join(" ")}
                style={{
                  left: rect.left,
                  top: rect.top,
                  width: rect.width,
                  height: rect.height,
                }}
                onClick={(ev) => {
                  ev.stopPropagation();
                  if (editMode) setSelectedBlockId(b.id);
                  else acknowledgeBlock(b.id);
                }}
              >
                {hasUnread ? <AgentUpdateBadge title={badgeTitle} pulse={isHighlighted} /> : null}
                <div className={["flex h-full min-h-0 flex-col", blockShellClassForBlock(b)].join(" ")}>
                  {showBlockToolbar || editMode ? (
                    <div
                      className={[
                        "flex shrink-0 select-none items-center gap-2 border-b border-white/5 bg-surface-raised/95 px-2 py-1",
                        editMode
                          ? "cursor-grab active:cursor-grabbing"
                          : "",
                      ].join(" ")}
                      onPointerDown={(e) => {
                        if (!editMode || e.button !== 0 || spaceDown) return;
                        const el = e.target as HTMLElement | null;
                        if (el?.closest("button,a,input,textarea,select,label")) return;
                        beginBlockDrag(e, "move", b.id, rect);
                      }}
                    >
                      {editMode ? (
                        <span
                          className="shrink-0 cursor-grab px-0.5 text-xs leading-none text-surface-muted active:cursor-grabbing"
                          title={t("dashboard:canvasDragHandle")}
                          aria-hidden="true"
                        >
                          ⋮⋮
                        </span>
                      ) : null}
                      <span className="min-w-0 flex-1 truncate text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                        {blockTitle(b)}
                      </span>
                      <div className="flex shrink-0 gap-1">
                        {canExpand ? (
                          <button
                            type="button"
                            className="rounded px-2 py-0.5 text-xs text-sky-200 hover:bg-sky-950/50"
                            title={t("dashboard:blockExpand")}
                            onClick={() => {
                              acknowledgeBlock(b.id);
                              setExpandedBlockId(b.id);
                            }}
                          >
                            {t("dashboard:blockExpand")}
                          </button>
                        ) : null}
                        {onPinBlockToChat && b.type !== "dashboard_ref" ? (
                          <button
                            type="button"
                            className={[
                              "rounded px-2 py-0.5 text-xs",
                              chatFocusedBlockId === b.id
                                ? "bg-emerald-900/60 text-emerald-100"
                                : "text-emerald-200 hover:bg-emerald-950/50",
                            ].join(" ")}
                            title={t("dashboard:pinBlockToChatHint")}
                            onClick={() => onPinBlockToChat(b.id)}
                          >
                            {chatFocusedBlockId === b.id
                              ? t("dashboard:pinBlockToChatActive")
                              : t("dashboard:pinBlockToChat")}
                          </button>
                        ) : null}
                        {canConfigureBlock ? (
                          <button
                            type="button"
                            className="rounded px-2 py-0.5 text-xs text-amber-200 hover:bg-amber-950/50"
                            title={t("dashboard:blockSettingsTitle")}
                            onClick={() => setSettingsBlockId(b.id)}
                          >
                            ⚙
                          </button>
                        ) : null}
                        {onPinBlock && b.type !== "dashboard_ref" ? (
                          <button
                            type="button"
                            className="rounded px-2 py-0.5 text-xs text-violet-200 hover:bg-violet-950/50"
                            title={t("dashboard:pinBlockHint")}
                            onClick={() => onPinBlock(b.id)}
                          >
                            {t("dashboard:pinBlock")}
                          </button>
                        ) : null}
                        {editMode ? (
                          <button
                            type="button"
                            className="rounded px-2 py-0.5 text-xs text-red-300 hover:bg-red-950/40"
                            onClick={() => removeBlock(b.id)}
                          >
                            {t("dashboard:gridRemoveBlock")}
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                  <div className="min-h-0 flex-1 overflow-auto p-2">
                    <DashboardBlockTile
                      block={b}
                      data={data}
                      setData={setData}
                      readOnly={contentReadOnly}
                      interactOnly={interactOnly}
                      dashboardId={dashboardId ?? null}
                      rootLayout={layout}
                      setRootLayout={setLayout}
                      gridEditMode={editMode}
                      gridContentReadOnly={contentReadOnly}
                      gridDashboardId={dashboardId ?? null}
                      unreadBlockIds={unreadBlockIds}
                      highlightBlockId={highlightBlockId}
                      onBlockSeen={onBlockSeen}
                    />
                  </div>
                </div>
                {editMode ? (
                  <button
                    type="button"
                    aria-label={t("dashboard:canvasResize")}
                    className="absolute bottom-0 right-0 z-20 h-3.5 w-3.5 cursor-se-resize select-none rounded-tl bg-sky-500/80"
                    onPointerDown={(e) => {
                      if (e.button !== 0) return;
                      beginBlockDrag(e, "resize", b.id, rect);
                    }}
                  />
                ) : null}
              </div>
            );
          })}
        </div>
      </div>

      {expandedBlock ? (
        <BlockExpandModal
          block={expandedBlock}
          data={data}
          setData={setData}
          readOnly={contentReadOnly}
          interactOnly={interactOnly}
          dashboardId={dashboardId ?? null}
          onClose={() => setExpandedBlockId(null)}
        />
      ) : null}
      {settingsBlock ? (
        <BlockSettingsModal
          block={settingsBlock}
          data={data}
          autoSave={blockSettingsAutoSave}
          saving={blockSettingsSaving}
          onClose={() => setSettingsBlockId(null)}
          onSave={async (nextProps) => {
            if (onBlockPropsSave) {
              await onBlockPropsSave(settingsBlock.id, nextProps);
            } else {
              setLayout((prev) =>
                updateBlockById(prev, settingsBlock.id, (b) => ({
                  ...b,
                  props: { ...b.props, ...nextProps },
                }))
              );
            }
          }}
        />
      ) : null}
    </div>
  );
}
