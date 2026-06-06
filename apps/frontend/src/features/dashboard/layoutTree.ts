import type { UiBlock, UiLayout } from "./types";

export function emptyNestedLayout(): UiLayout {
  return { version: 2, blocks: [] };
}

export function normalizeNestedLayout(raw: unknown): UiLayout {
  if (!raw || typeof raw !== "object") return emptyNestedLayout();
  const o = raw as { version?: number; blocks?: unknown };
  if (!Array.isArray(o.blocks)) return emptyNestedLayout();
  return { version: 2, blocks: o.blocks as UiBlock[] };
}

export function flattenBlockIds(layout: UiLayout | null | undefined): string[] {
  if (!layout?.blocks?.length) return [];
  const out: string[] = [];
  for (const b of layout.blocks) {
    out.push(b.id);
    if (b.type === "section") {
      const nested = normalizeNestedLayout(b.props.nested);
      for (const nb of nested.blocks) out.push(nb.id);
    }
  }
  return out;
}

/** All blocks with optional dataPath (root + nested sections). */
/** True when layout has a table or card_grid block (GitHub import target). */
/** First table/card_grid dataPath in layout (matches backend primary_list_data_path). */
export function primaryListDataPath(layout: UiLayout | null | undefined): string | null {
  if (!layout?.blocks?.length) return null;
  const walk = (blocks: UiBlock[]): string | null => {
    for (const b of blocks) {
      if (b.type === "table" || b.type === "card_grid") {
        const dp = b.props.dataPath?.trim();
        if (dp) return dp;
      }
      if (b.type === "section") {
        const nested = normalizeNestedLayout(b.props.nested);
        const inner = walk(nested.blocks);
        if (inner) return inner;
      }
    }
    return null;
  };
  return walk(layout.blocks);
}

export function layoutHasImportableList(layout: UiLayout | null | undefined): boolean {
  if (!layout?.blocks?.length) return false;
  const walk = (blocks: UiBlock[]): boolean => {
    for (const b of blocks) {
      if (b.type === "table" || b.type === "card_grid") return true;
      if (b.type === "section") {
        const nested = normalizeNestedLayout(b.props.nested);
        if (walk(nested.blocks)) return true;
      }
    }
    return false;
  };
  return walk(layout.blocks);
}

export function flattenBlocksWithDataPath(
  layout: UiLayout | null | undefined
): { id: string; dataPath: string }[] {
  if (!layout?.blocks?.length) return [];
  const out: { id: string; dataPath: string }[] = [];
  const walk = (blocks: UiBlock[]) => {
    for (const b of blocks) {
      const dp = b.props.dataPath?.trim() ?? "";
      if (dp) out.push({ id: b.id, dataPath: dp });
      if (b.type === "section") {
        walk(normalizeNestedLayout(b.props.nested).blocks);
      }
    }
  };
  walk(layout.blocks);
  return out;
}

export function sectionHasUnreadNested(
  block: UiBlock,
  unreadBlockIds: Set<string> | undefined
): boolean {
  if (!unreadBlockIds?.size) return false;
  if (block.type !== "section") return false;
  const nested = normalizeNestedLayout(block.props.nested);
  return nested.blocks.some((nb) => unreadBlockIds.has(nb.id));
}

export function countLayoutBlocks(layout: UiLayout | null | undefined): number {
  return flattenBlockIds(layout).length;
}

export function findBlockById(
  layout: UiLayout | null | undefined,
  blockId: string
): UiBlock | null {
  const bid = blockId.trim();
  if (!bid || !layout?.blocks?.length) return null;
  for (const b of layout.blocks) {
    if (b.id === bid) return b;
    if (b.type === "section") {
      const nested = normalizeNestedLayout(b.props.nested);
      const hit = nested.blocks.find((nb) => nb.id === bid);
      if (hit) return hit;
    }
  }
  return null;
}

export function updateBlockById(
  layout: UiLayout,
  blockId: string,
  patch: (block: UiBlock) => UiBlock
): UiLayout {
  const bid = blockId.trim();
  if (!bid) return layout;
  let changed = false;
  const mapBlocks = (blocks: UiBlock[]): UiBlock[] =>
    blocks.map((b) => {
      if (b.id === bid) {
        changed = true;
        return patch(b);
      }
      if (b.type === "section") {
        const nested = normalizeNestedLayout(b.props.nested);
        const nextNestedBlocks = mapBlocks(nested.blocks);
        if (nextNestedBlocks !== nested.blocks) {
          changed = true;
          return {
            ...b,
            props: { ...b.props, nested: { ...nested, blocks: nextNestedBlocks } },
          };
        }
      }
      return b;
    });
  const blocks = mapBlocks(layout.blocks);
  return changed ? { ...layout, blocks } : layout;
}

export function blockTypeLabel(type: string): string {
  if (type === "rich_markdown") return "Rich MD";
  if (type === "section") return "Section";
  if (type === "card_grid") return "Cards";
  return type.replace(/_/g, " ");
}
