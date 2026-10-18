/** Layout mode helpers for dashboard ``ui_layout`` (grid vs infinite canvas). */

import type {
  DashboardCanvasViewport,
  DashboardLayoutMode,
  UiBlock,
  UiLayout,
  UiLayoutModeSnapshot,
} from "./types";
import { GRID_COLS } from "./gridConfig";

/** World cell size for canvas rendering (maps grid units → px). */
export const CANVAS_CELL_W = 80;
export const CANVAS_CELL_H = 48;

export const CANVAS_ZOOM_MIN = 0.35;
export const CANVAS_ZOOM_MAX = 2.5;

export function normalizeLayoutMode(raw: unknown): DashboardLayoutMode {
  return String(raw || "").trim().toLowerCase() === "canvas" ? "canvas" : "grid";
}

export function parseCanvasViewport(raw: unknown): DashboardCanvasViewport | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  const zoom = typeof o.zoom === "number" && Number.isFinite(o.zoom) ? o.zoom : undefined;
  const panX = typeof o.panX === "number" && Number.isFinite(o.panX) ? o.panX : undefined;
  const panY = typeof o.panY === "number" && Number.isFinite(o.panY) ? o.panY : undefined;
  if (zoom === undefined && panX === undefined && panY === undefined) return undefined;
  return { zoom, panX, panY };
}

function cloneBlocks(blocks: UiBlock[]): UiBlock[] {
  return JSON.parse(JSON.stringify(blocks)) as UiBlock[];
}

function parseModeSnapshot(raw: unknown): UiLayoutModeSnapshot | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const o = raw as { blocks?: unknown; canvas?: unknown };
  if (!Array.isArray(o.blocks)) return undefined;
  const canvas = parseCanvasViewport(o.canvas);
  return {
    blocks: o.blocks as UiBlock[],
    ...(canvas ? { canvas } : {}),
  };
}

export function parseUiLayout(raw: unknown): UiLayout | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as {
    version?: number;
    blocks?: unknown;
    mode?: unknown;
    canvas?: unknown;
    mode_layouts?: unknown;
  };
  if (!Array.isArray(o.blocks)) return null;
  const mode = normalizeLayoutMode(o.mode);
  const canvas = parseCanvasViewport(o.canvas);
  let mode_layouts: UiLayout["mode_layouts"];
  if (o.mode_layouts && typeof o.mode_layouts === "object") {
    const ml = o.mode_layouts as { grid?: unknown; canvas?: unknown };
    const grid = parseModeSnapshot(ml.grid);
    const canvasSnap = parseModeSnapshot(ml.canvas);
    if (grid || canvasSnap) {
      mode_layouts = {
        ...(grid ? { grid } : {}),
        ...(canvasSnap ? { canvas: canvasSnap } : {}),
      };
    }
  }
  return {
    version: Number(o.version) === 2 ? 2 : 1,
    mode,
    ...(canvas ? { canvas } : {}),
    blocks: o.blocks as UiLayout["blocks"],
    ...(mode_layouts ? { mode_layouts } : {}),
  };
}

export function layoutModeOf(layout: UiLayout | null | undefined): DashboardLayoutMode {
  return normalizeLayoutMode(layout?.mode);
}

/** Clamp canvas free positions into a valid 12-col grid (may leave vertical gaps). */
export function snapBlocksToGrid(blocks: UiBlock[]): UiBlock[] {
  return blocks.map((b) => {
    const w = Math.max(1, Math.min(GRID_COLS, Math.round(b.grid.w) || 1));
    const h = Math.max(1, Math.round(b.grid.h) || 1);
    const x = Math.max(0, Math.min(GRID_COLS - w, Math.round(b.grid.x) || 0));
    const y = Math.max(0, Math.round(b.grid.y) || 0);
    return { ...b, grid: { x, y, w, h } };
  });
}

function snapshotOf(layout: UiLayout): UiLayoutModeSnapshot {
  return {
    blocks: cloneBlocks(layout.blocks),
    ...(layout.canvas ? { canvas: { ...layout.canvas } } : {}),
  };
}

/**
 * Apply a mode snapshot's positions onto the current block set (by id).
 * Blocks that only exist now keep a derived placement for the target mode.
 */
function applySnapshotPositions(
  liveBlocks: UiBlock[],
  saved: UiLayoutModeSnapshot | undefined,
  targetMode: DashboardLayoutMode
): UiBlock[] {
  const byId = new Map(
    (saved?.blocks ?? []).map((b) => [b.id, b] as const).filter(([id]) => !!id)
  );
  const merged = liveBlocks.map((b) => {
    const prev = byId.get(b.id);
    if (prev?.grid) {
      return { ...b, grid: { ...prev.grid } };
    }
    return b;
  });
  return targetMode === "grid" ? snapBlocksToGrid(merged) : merged;
}

/**
 * Switch placement engine while keeping the other mode's last positions.
 * Active ``blocks`` (identity/props) always win; only ``grid`` coords + canvas
 * viewport are restored from ``mode_layouts``.
 */
export function withLayoutMode(layout: UiLayout, mode: DashboardLayoutMode): UiLayout {
  const current = layoutModeOf(layout);
  if (current === mode) {
    return layout;
  }

  const mode_layouts: NonNullable<UiLayout["mode_layouts"]> = {
    ...(layout.mode_layouts ?? {}),
    [current]: snapshotOf(layout),
  };

  const saved = mode_layouts[mode];
  const blocks = applySnapshotPositions(layout.blocks, saved, mode);

  if (mode === "canvas") {
    return {
      ...layout,
      mode: "canvas",
      version: layout.version === 2 ? 2 : 1,
      blocks,
      canvas: saved?.canvas ?? layout.canvas ?? { zoom: 1, panX: 0, panY: 0 },
      mode_layouts,
    };
  }

  return {
    ...layout,
    mode: "grid",
    version: layout.version === 2 ? 2 : 1,
    blocks,
    canvas: undefined,
    mode_layouts,
  };
}

export function clampZoom(z: number): number {
  if (!Number.isFinite(z)) return 1;
  return Math.min(CANVAS_ZOOM_MAX, Math.max(CANVAS_ZOOM_MIN, z));
}

export function gridToWorldRect(grid: { x: number; y: number; w: number; h: number }): {
  left: number;
  top: number;
  width: number;
  height: number;
} {
  return {
    left: grid.x * CANVAS_CELL_W,
    top: grid.y * CANVAS_CELL_H,
    width: Math.max(CANVAS_CELL_W, grid.w * CANVAS_CELL_W),
    height: Math.max(CANVAS_CELL_H, grid.h * CANVAS_CELL_H),
  };
}

export function worldToGridPos(
  left: number,
  top: number,
  width: number,
  height: number
): { x: number; y: number; w: number; h: number } {
  return {
    x: Math.round(left / CANVAS_CELL_W),
    y: Math.round(top / CANVAS_CELL_H),
    w: Math.max(1, Math.round(width / CANVAS_CELL_W)),
    h: Math.max(1, Math.round(height / CANVAS_CELL_H)),
  };
}
