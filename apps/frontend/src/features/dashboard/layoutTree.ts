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

export function blockTypeLabel(type: string): string {
  if (type === "rich_markdown") return "Rich MD";
  if (type === "section") return "Section";
  if (type === "card_grid") return "Cards";
  return type.replace(/_/g, " ");
}
