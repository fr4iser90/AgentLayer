/** Shared react-grid-layout settings for root and nested dashboard grids. */

export const GRID_COLS = 12;

export const GRID_ROW_HEIGHT = 48;

export const GRID_MARGIN: [number, number] = [12, 12];

export const GRID_CONTAINER_PADDING: [number, number] = [4, 4];

/** Below this width (px), blocks stack full width. Matches Tailwind `md`. */
export const GRID_MOBILE_STACK_MAX_WIDTH = 768;

export const MAX_LAYOUT_DEPTH = 2;

export const MAX_BLOCKS_TOTAL = 64;

/** Block types that cannot be placed inside a section (depth 1). */
export const NESTED_DISALLOWED_BLOCK_TYPES = new Set(["section"]);
