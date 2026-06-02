import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { GalleryImage } from "../GalleryImage";
import { getPath } from "../dashboardDataPaths";
import type { UiBlock } from "../types";
import { GalleryLightbox } from "./GalleryLightbox";
import {
  galleryAspectClass,
  galleryGridClass,
  photosForLightbox,
  resolveGalleryLayout,
  type GalleryPhoto,
} from "./galleryLayout";

type PhotoRow = { id?: unknown; url?: unknown; caption?: unknown };

function galleryPhotos(block: UiBlock, data: Record<string, unknown>): PhotoRow[] {
  const dp = block.props.dataPath || "";
  if (!dp) return [];
  const raw = getPath(data, dp);
  if (!Array.isArray(raw)) return [];
  return raw as PhotoRow[];
}

function PublicPhotoTile(props: {
  photo: GalleryPhoto;
  aspectCls: string;
  onOpen: () => void;
}) {
  const { photo, aspectCls, onOpen } = props;
  const { url, caption } = photo;
  if (!url) return null;
  return (
    <figure className="group overflow-hidden rounded-lg bg-black/40 sm:rounded-xl">
      <button
        type="button"
        className={`block w-full overflow-hidden bg-neutral-900 ${aspectCls} cursor-zoom-in`}
        onClick={onOpen}
      >
        <GalleryImage
          url={url}
          alt={caption || "Photo"}
          className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.02]"
        />
      </button>
      {caption ? (
        <figcaption className="border-t border-white/5 px-3 py-2 text-xs leading-relaxed text-neutral-300">
          {caption}
        </figcaption>
      ) : null}
    </figure>
  );
}

export function GalleryPublicSection(props: {
  block: UiBlock;
  sectionTitle: string;
  data: Record<string, unknown>;
}) {
  const { t } = useTranslation(["dashboard"]);
  const { block, sectionTitle, data } = props;
  const layout = useMemo(() => resolveGalleryLayout(block), [block]);
  const aspectCls = galleryAspectClass(layout.aspect);

  const photos = useMemo(() => {
    return galleryPhotos(block, data)
      .map((row, i) => ({
        id: String(row.id ?? i),
        url: String(row.url ?? "").trim(),
        caption: String(row.caption ?? ""),
      }))
      .filter((p) => p.url.length > 0);
  }, [block, data]);

  const viewable = useMemo(() => photosForLightbox(photos), [photos]);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  return (
    <section className="mb-8 last:mb-4 sm:mb-12">
      {sectionTitle ? (
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-neutral-400 sm:mb-4">
          {sectionTitle}
        </h2>
      ) : null}
      {photos.length === 0 ? (
        <p className="py-16 text-center text-sm text-neutral-500">
          {t("dashboard:photosEmptyReadOnly")}
        </p>
      ) : (
        <div className={galleryGridClass(layout.columns)}>
          {photos.map((photo) => {
            const lbIdx = viewable.findIndex((p) => p.id === photo.id);
            return (
              <PublicPhotoTile
                key={photo.id}
                photo={photo}
                aspectCls={aspectCls}
                onOpen={() => {
                  if (lbIdx >= 0) setLightboxIndex(lbIdx);
                }}
              />
            );
          })}
        </div>
      )}
      {lightboxIndex !== null && viewable.length > 0 ? (
        <GalleryLightbox
          photos={viewable}
          index={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onIndexChange={setLightboxIndex}
        />
      ) : null}
    </section>
  );
}
