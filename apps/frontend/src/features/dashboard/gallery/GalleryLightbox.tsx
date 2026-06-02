import { useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { GalleryImage } from "../GalleryImage";
import type { GalleryPhoto } from "./galleryLayout";

export function GalleryLightbox(props: {
  photos: GalleryPhoto[];
  index: number;
  onClose: () => void;
  onIndexChange: (index: number) => void;
}) {
  const { t } = useTranslation(["dashboard"]);
  const { photos, index, onClose, onIndexChange } = props;
  const current = photos[index];
  const hasPrev = index > 0;
  const hasNext = index < photos.length - 1;

  const goPrev = useCallback(() => {
    if (hasPrev) onIndexChange(index - 1);
  }, [hasPrev, index, onIndexChange]);

  const goNext = useCallback(() => {
    if (hasNext) onIndexChange(index + 1);
  }, [hasNext, index, onIndexChange]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft") goPrev();
      else if (e.key === "ArrowRight") goNext();
    };
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose, goPrev, goNext]);

  if (!current) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex flex-col bg-black/95"
      role="dialog"
      aria-modal="true"
      aria-label={t("dashboard:galleryLightboxLabel")}
    >
      <button
        type="button"
        className="absolute right-3 top-3 z-10 rounded-lg bg-white/10 px-3 py-1.5 text-sm text-white hover:bg-white/20 sm:right-4 sm:top-4"
        onClick={onClose}
      >
        {t("dashboard:galleryLightboxClose")}
      </button>

      <div
        className="flex min-h-0 flex-1 items-center justify-center px-2 py-14 sm:px-16"
        onClick={onClose}
      >
        <div
          className="relative max-h-full max-w-full"
          onClick={(e) => e.stopPropagation()}
        >
          <GalleryImage
            url={current.url}
            alt={current.caption || t("dashboard:photosTitleFallback")}
            className="max-h-[min(80vh,900px)] max-w-[min(96vw,1400px)] object-contain"
          />
        </div>
      </div>

      {hasPrev ? (
        <button
          type="button"
          className="absolute left-2 top-1/2 z-10 -translate-y-1/2 rounded-full bg-white/10 p-2 text-white hover:bg-white/20 sm:left-4"
          onClick={(e) => {
            e.stopPropagation();
            goPrev();
          }}
          aria-label={t("dashboard:galleryLightboxPrev")}
        >
          ‹
        </button>
      ) : null}

      {hasNext ? (
        <button
          type="button"
          className="absolute right-2 top-1/2 z-10 -translate-y-1/2 rounded-full bg-white/10 p-2 text-white hover:bg-white/20 sm:right-4"
          onClick={(e) => {
            e.stopPropagation();
            goNext();
          }}
          aria-label={t("dashboard:galleryLightboxNext")}
        >
          ›
        </button>
      ) : null}

      <footer className="shrink-0 border-t border-white/10 px-4 py-3 text-center sm:px-6">
        {current.caption ? (
          <p className="text-sm text-neutral-200">{current.caption}</p>
        ) : null}
        <p className="mt-1 text-xs text-neutral-500">
          {t("dashboard:galleryLightboxCounter", {
            current: index + 1,
            total: photos.length,
          })}
        </p>
      </footer>
    </div>
  );
}
