import type { UiBlock } from "../types";

export type GalleryAspect = "square" | "video" | "auto";

export type GalleryLayoutOptions = {
  columns: number;
  aspect: GalleryAspect;
};

export type GalleryPhoto = {
  id: string;
  url: string;
  caption: string;
};

const ASPECTS = new Set<GalleryAspect>(["square", "video", "auto"]);

export function resolveGalleryLayout(block: UiBlock | undefined): GalleryLayoutOptions {
  const rawCols = block?.props?.galleryColumns;
  let columns = typeof rawCols === "number" && Number.isFinite(rawCols) ? Math.round(rawCols) : 0;
  if (columns < 2) columns = 3;
  if (columns > 5) columns = 5;

  const rawAspect = block?.props?.galleryAspect;
  const aspect =
    typeof rawAspect === "string" && ASPECTS.has(rawAspect as GalleryAspect)
      ? (rawAspect as GalleryAspect)
      : "square";

  return { columns, aspect };
}

export function galleryAspectClass(aspect: GalleryAspect): string {
  if (aspect === "video") return "aspect-video";
  if (aspect === "auto") return "min-h-[140px]";
  return "aspect-square";
}

/** Responsive grid classes from column count (2–5). */
export function galleryGridClass(columns: number): string {
  const base = "grid gap-3 sm:gap-4";
  switch (columns) {
    case 2:
      return `${base} grid-cols-2`;
    case 4:
      return `${base} grid-cols-2 sm:grid-cols-3 lg:grid-cols-4`;
    case 5:
      return `${base} grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5`;
    case 3:
    default:
      return `${base} grid-cols-2 lg:grid-cols-3`;
  }
}

export function photosForLightbox(photos: GalleryPhoto[]): GalleryPhoto[] {
  return photos.filter((p) => p.url.trim().length > 0);
}
