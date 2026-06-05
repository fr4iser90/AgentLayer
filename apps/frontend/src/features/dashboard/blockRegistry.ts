import type { TFunction } from "i18next";
import type { BlockType, ColumnDef, UiBlock } from "./types";

/** Below this container width (px), grid blocks stack full width. Matches Tailwind `md`. */
export const GRID_MOBILE_STACK_MAX_WIDTH = 768;

const DEFAULT_TABLE_COLUMNS: ColumnDef[] = [
  { field: "done", kind: "checkbox", label: "" },
  { field: "name", kind: "text", label: "" },
];

export type BlockShellHeight = "default" | "tall" | "hero" | "timeline";

export type GridBlockDefinition = {
  type: BlockType;
  dataPathPrefix: string;
  addLabelKey: string;
  defaultGrid: { w: number; h: number };
  minGrid: { minW: number; minH: number };
  mobileStack: boolean;
  shellHeight: BlockShellHeight;
  /** Show fullscreen expand control in the grid shell. */
  supportsExpand?: boolean;
  /** i18n key when block.props.title is empty. */
  expandTitleFallbackKey?: string;
  createProps: (dataPath: string) => UiBlock["props"];
  createInitialData: (t: TFunction<["dashboard"]>) => unknown;
};

const SHELL_HEIGHT_CLASS: Record<BlockShellHeight, string> = {
  default: "flex max-h-[min(520px,65vh)] flex-col overflow-auto",
  tall: "flex max-h-[min(720px,90vh)] flex-col overflow-auto",
  hero: "flex max-h-[min(720px,88vh)] flex-col overflow-auto",
  timeline: "flex max-h-[min(640px,82vh)] flex-col overflow-auto",
};

function gridDef(definition: GridBlockDefinition): GridBlockDefinition {
  return definition;
}

/** Block types that can be added from the grid editor toolbar. */
export const GRID_BLOCK_DEFINITIONS: GridBlockDefinition[] = [
  gridDef({
    type: "table",
    dataPathPrefix: "items",
    addLabelKey: "dashboard:addList",
    defaultGrid: { w: 6, h: 6 },
    minGrid: { minW: 2, minH: 3 },
    mobileStack: true,
    shellHeight: "default",
    supportsExpand: true,
    expandTitleFallbackKey: "dashboard:tableTitle",
    createProps: (dataPath) => ({ dataPath, columns: [...DEFAULT_TABLE_COLUMNS] }),
    createInitialData: () => [],
  }),
  gridDef({
    type: "markdown",
    dataPathPrefix: "notes",
    addLabelKey: "dashboard:addNotes",
    defaultGrid: { w: 6, h: 6 },
    minGrid: { minW: 2, minH: 3 },
    mobileStack: true,
    shellHeight: "default",
    createProps: (dataPath) => ({ dataPath, placeholder: "" }),
    createInitialData: () => "",
  }),
  gridDef({
    type: "gallery",
    dataPathPrefix: "photos",
    addLabelKey: "dashboard:addPhotos",
    defaultGrid: { w: 6, h: 6 },
    minGrid: { minW: 2, minH: 3 },
    mobileStack: true,
    shellHeight: "default",
    createProps: (dataPath) => ({ dataPath, title: "Photos" }),
    createInitialData: () => [],
  }),
  gridDef({
    type: "hero",
    dataPathPrefix: "hero",
    addLabelKey: "dashboard:addHero",
    defaultGrid: { w: 12, h: 8 },
    minGrid: { minW: 4, minH: 4 },
    mobileStack: true,
    shellHeight: "hero",
    createProps: (dataPath) => ({ dataPath, title: "" }),
    createInitialData: () => ({ url: "", caption: "", headline: "" }),
  }),
  gridDef({
    type: "timeline",
    dataPathPrefix: "timeline",
    addLabelKey: "dashboard:addTimeline",
    defaultGrid: { w: 12, h: 9 },
    minGrid: { minW: 4, minH: 5 },
    mobileStack: true,
    shellHeight: "timeline",
    createProps: (dataPath) => ({ dataPath, title: "" }),
    createInitialData: () => [],
  }),
  gridDef({
    type: "stat",
    dataPathPrefix: "stat",
    addLabelKey: "dashboard:addKpi",
    defaultGrid: { w: 4, h: 5 },
    minGrid: { minW: 2, minH: 3 },
    mobileStack: true,
    shellHeight: "default",
    createProps: (dataPath) => ({ dataPath, title: "" }),
    createInitialData: () => ({ value: "", label: "", suffix: "", trend: "" }),
  }),
  gridDef({
    type: "chart",
    dataPathPrefix: "chart",
    addLabelKey: "dashboard:addChart",
    defaultGrid: { w: 12, h: 10 },
    minGrid: { minW: 4, minH: 6 },
    mobileStack: true,
    shellHeight: "tall",
    supportsExpand: true,
    expandTitleFallbackKey: "dashboard:chartFallback",
    createProps: (dataPath) => ({ dataPath, title: "" }),
    createInitialData: (t) => ({
      chartType: "line",
      labels: ["Q1", "Q2", "Q3"],
      series: [{ label: t("dashboard:chartSeriesN", { n: 1 }), data: [12, 19, 3] }],
    }),
  }),
  gridDef({
    type: "sparkline",
    dataPathPrefix: "sparkline",
    addLabelKey: "dashboard:addSpark",
    defaultGrid: { w: 6, h: 4 },
    minGrid: { minW: 2, minH: 3 },
    mobileStack: true,
    shellHeight: "default",
    createProps: (dataPath) => ({ dataPath, title: "" }),
    createInitialData: () => ({ values: [2, 5, 3, 8, 6, 4, 7] }),
  }),
  gridDef({
    type: "kanban",
    dataPathPrefix: "kanban",
    addLabelKey: "dashboard:addKanban",
    defaultGrid: { w: 12, h: 12 },
    minGrid: { minW: 6, minH: 6 },
    mobileStack: true,
    shellHeight: "tall",
    supportsExpand: true,
    expandTitleFallbackKey: "dashboard:kanbanFallback",
    createProps: (dataPath) => ({ dataPath, title: "" }),
    createInitialData: (t) => {
      const tms = Date.now();
      return {
        columns: [
          { id: `col_${tms}_a`, title: t("dashboard:kanbanTodo"), cards: [] },
          { id: `col_${tms}_b`, title: t("dashboard:kanbanDoing"), cards: [] },
          { id: `col_${tms}_c`, title: t("dashboard:kanbanDone"), cards: [] },
        ],
      };
    },
  }),
  gridDef({
    type: "rich_markdown",
    dataPathPrefix: "rich_md",
    addLabelKey: "dashboard:addRichMarkdown",
    defaultGrid: { w: 12, h: 9 },
    minGrid: { minW: 4, minH: 6 },
    mobileStack: true,
    shellHeight: "tall",
    createProps: (dataPath) => ({ dataPath, placeholder: "", title: "" }),
    createInitialData: () => "",
  }),
  gridDef({
    type: "embed",
    dataPathPrefix: "embed",
    addLabelKey: "dashboard:addEmbed",
    defaultGrid: { w: 12, h: 10 },
    minGrid: { minW: 4, minH: 6 },
    mobileStack: true,
    shellHeight: "tall",
    createProps: (dataPath) => ({ dataPath, title: "" }),
    createInitialData: () => ({ url: "", title: "", height: 480 }),
  }),
];

const GRID_BLOCK_REGISTRY = Object.fromEntries(
  GRID_BLOCK_DEFINITIONS.map((d) => [d.type, d])
) as Record<BlockType, GridBlockDefinition>;

export function getGridBlockDefinition(type: BlockType): GridBlockDefinition | undefined {
  return GRID_BLOCK_REGISTRY[type as keyof typeof GRID_BLOCK_REGISTRY];
}

export function blockMinDimsForType(type: BlockType): { minW: number; minH: number } {
  return getGridBlockDefinition(type)?.minGrid ?? { minW: 2, minH: 3 };
}

export function blockShellClassForType(type: BlockType): string {
  const shellHeight = getGridBlockDefinition(type)?.shellHeight ?? "default";
  return SHELL_HEIGHT_CLASS[shellHeight];
}

export function blockSupportsExpand(type: BlockType): boolean {
  return getGridBlockDefinition(type)?.supportsExpand === true;
}

export function blockExpandTitle(block: UiBlock, t: TFunction<["dashboard"]>): string {
  const custom = block.props.title?.trim();
  if (custom) return custom;
  if (block.type === "table") {
    const path = block.props.dataPath?.trim() || "—";
    return t("dashboard:tableTitle", { path });
  }
  const fallbackKey = getGridBlockDefinition(block.type)?.expandTitleFallbackKey;
  if (fallbackKey) {
    return t(fallbackKey as "dashboard:chartFallback");
  }
  return block.type;
}

export function blockDataPathPrefix(type: BlockType): string {
  const definition = getGridBlockDefinition(type);
  if (!definition) throw new Error(`Unknown grid block type: ${type}`);
  return definition.dataPathPrefix;
}

export function newBlockId(): string {
  return `blk_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function createGridBlock(type: BlockType, dataPath: string, y: number): UiBlock {
  const definition = getGridBlockDefinition(type);
  if (!definition) throw new Error(`Unknown grid block type: ${type}`);
  return {
    id: newBlockId(),
    type,
    grid: { x: 0, y, w: definition.defaultGrid.w, h: definition.defaultGrid.h },
    props: definition.createProps(dataPath),
  };
}

export function initialDataPatchForBlock(
  type: BlockType,
  dataPath: string,
  t: TFunction<["dashboard"]>
): Record<string, unknown> {
  const definition = getGridBlockDefinition(type);
  if (!definition) return { [dataPath]: "" };
  return { [dataPath]: definition.createInitialData(t) };
}

export type GridLayoutItem = {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  static?: boolean;
  minW?: number;
  minH?: number;
  maxW?: number;
};

function sortBlocksForStack(blocks: UiBlock[]): UiBlock[] {
  return [...blocks].sort((a, b) => a.grid.y - b.grid.y || a.grid.x - b.grid.x);
}

export function layoutFromBlocks(
  blocks: UiBlock[],
  opts: { editMode: boolean; mobileStack: boolean }
): GridLayoutItem[] {
  if (opts.mobileStack) {
    let y = 0;
    return sortBlocksForStack(blocks).map((block) => {
      const { minW, minH } = blockMinDimsForType(block.type);
      const h = Math.max(minH, block.grid.h);
      const item: GridLayoutItem = {
        i: block.id,
        x: 0,
        y,
        w: 12,
        h,
        static: true,
        minW: 12,
        minH,
        maxW: 12,
      };
      y += h;
      return item;
    });
  }

  return blocks.map((block) => {
    const { minW, minH } = blockMinDimsForType(block.type);
    return {
      i: block.id,
      x: Math.min(11, Math.max(0, block.grid.x)),
      y: Math.max(0, block.grid.y),
      w: Math.min(12, Math.max(minW, block.grid.w)),
      h: Math.max(minH, block.grid.h),
      static: !opts.editMode,
      minW,
      minH,
      maxW: 12,
    };
  });
}
