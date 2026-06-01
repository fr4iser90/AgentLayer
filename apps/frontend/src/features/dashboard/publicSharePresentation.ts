import type { UiLayout } from "./types";

const GALLERY_PRESENTATION_TYPES = new Set([
  "gallery",
  "markdown",
  "rich_markdown",
  "hero",
]);

/** True when public share should use the immersive gallery layout (not dashboard grid). */
export function publicShareUsesGalleryPresentation(layout: UiLayout | null): boolean {
  if (!layout?.blocks?.length) return false;
  const types = layout.blocks.map((b) => b.type);
  if (!types.some((t) => t === "gallery" || t === "hero")) return false;
  return types.every((t) => GALLERY_PRESENTATION_TYPES.has(t));
}
