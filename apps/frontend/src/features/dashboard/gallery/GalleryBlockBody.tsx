import type { ChangeEvent, Dispatch, DragEvent, SetStateAction } from "react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../auth/AuthContext";
import { GalleryImage } from "../GalleryImage";
import { getPath, setPath } from "../dashboardDataPaths";
import { GalleryLightbox } from "./GalleryLightbox";
import {
  galleryAspectClass,
  galleryGridClass,
  photosForLightbox,
  resolveGalleryLayout,
  type GalleryLayoutOptions,
  type GalleryPhoto,
} from "./galleryLayout";
import { GALLERY_IMAGE_ACCEPT, uploadDashboardGalleryFile } from "./galleryUpload";
import type { UiBlock } from "../types";

type Row = Record<string, unknown>;

function newRowId(): string {
  return `r_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function rowToPhoto(row: Row, index: number): GalleryPhoto {
  return {
    id: String(row.id ?? index),
    url: String(row.url ?? "").trim(),
    caption: String(row.caption ?? ""),
  };
}

export function GalleryBlockBody(props: {
  block?: UiBlock;
  dp: string;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  sectionTitle: string;
  dashboardId: string | null;
  readOnly: boolean;
}) {
  const { t } = useTranslation(["dashboard"]);
  const { block, dp, data, setData, sectionTitle, dashboardId, readOnly } = props;
  const auth = useAuth();
  const layout = useMemo(() => resolveGalleryLayout(block), [block]);
  const rowsUnknown = dp ? getPath(data, dp) : [];
  const photos: Row[] = Array.isArray(rowsUnknown) ? (rowsUnknown as Row[]) : [];
  const viewable = useMemo(
    () => photosForLightbox(photos.map((row, i) => rowToPhoto(row, i))),
    [photos]
  );

  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState<number | null>(null);
  const [bulkUploading, setBulkUploading] = useState(false);
  const [bulkUploadErr, setBulkUploadErr] = useState<string | null>(null);

  const updatePhoto = (index: number, field: string, value: unknown) => {
    setData((d) => {
      const list = [...((getPath(d, dp) as Row[]) || [])];
      const row = { ...(list[index] || {}) };
      row[field] = value;
      list[index] = row;
      return setPath(d, dp, list);
    });
  };

  const addPhoto = () => {
    setData((d) => {
      const list = [...((getPath(d, dp) as Row[]) || [])];
      list.push({ id: newRowId(), url: "", caption: "" });
      return setPath(d, dp, list);
    });
  };

  const removePhoto = (index: number) => {
    setData((d) => {
      const list = [...((getPath(d, dp) as Row[]) || [])];
      list.splice(index, 1);
      return setPath(d, dp, list);
    });
  };

  const reorderPhotos = (from: number, to: number) => {
    if (from === to || from < 0 || to < 0) return;
    setData((d) => {
      const list = [...((getPath(d, dp) as Row[]) || [])];
      if (from >= list.length || to >= list.length) return d;
      const [item] = list.splice(from, 1);
      list.splice(to, 0, item);
      return setPath(d, dp, list);
    });
  };

  const openLightboxForRow = (rowIndex: number) => {
    const photo = rowToPhoto(photos[rowIndex] ?? {}, rowIndex);
    if (!photo.url) return;
    const idx = viewable.findIndex((p) => p.id === photo.id);
    if (idx >= 0) setLightboxIndex(idx);
  };

  const onPickMultiple = (e: ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    e.target.value = "";
    if (!fileList?.length) return;
    if (!dashboardId) {
      setBulkUploadErr(t("dashboard:dashboardSaveBeforeUpload"));
      return;
    }
    void (async () => {
      setBulkUploading(true);
      setBulkUploadErr(null);
      const added: Row[] = [];
      for (const file of Array.from(fileList)) {
        const result = await uploadDashboardGalleryFile(dashboardId, file, auth, t);
        if (!result.ok) {
          setBulkUploadErr(result.error);
          break;
        }
        added.push({ id: newRowId(), url: result.galleryRef, caption: "" });
      }
      if (added.length > 0) {
        setData((d) => {
          const list = [...((getPath(d, dp) as Row[]) || [])];
          list.push(...added);
          return setPath(d, dp, list);
        });
      }
      setBulkUploading(false);
    })();
  };

  return (
    <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-white">{sectionTitle}</h3>
        {!readOnly ? (
          <div className="flex flex-wrap items-center gap-2">
            <label className="dashboard-grid-no-drag cursor-pointer rounded-md bg-white/10 px-3 py-1.5 text-xs font-medium text-white hover:bg-white/15">
              {bulkUploading ? "…" : t("dashboard:photosUploadMultiple")}
              <input
                type="file"
                accept={GALLERY_IMAGE_ACCEPT}
                multiple
                className="hidden"
                disabled={bulkUploading || !dashboardId}
                onChange={onPickMultiple}
              />
            </label>
            <button
              type="button"
              className="dashboard-grid-no-drag rounded-md bg-violet-600/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-500"
              onClick={addPhoto}
            >
              {t("dashboard:photosAdd")}
            </button>
          </div>
        ) : null}
      </div>
      {bulkUploadErr ? <p className="mb-2 text-xs text-red-400">{bulkUploadErr}</p> : null}
      {!readOnly && !dashboardId ? (
        <p className="mb-2 text-[10px] text-amber-200/90">{t("dashboard:saveForUpload")}</p>
      ) : null}
      {!readOnly ? (
        <p className="mb-3 text-[10px] text-surface-muted">{t("dashboard:photosDragHint")}</p>
      ) : null}

      {photos.length === 0 ? (
        <p className="rounded-lg border border-dashed border-white/15 py-10 text-center text-sm text-surface-muted">
          {readOnly
            ? t("dashboard:photosEmptyReadOnly")
            : t("dashboard:photosEmptyEditable")}
        </p>
      ) : (
        <div className={galleryGridClass(layout.columns)}>
          {photos.map((row, ri) => (
            <GalleryPhotoCard
              key={String(row.id ?? ri)}
              ri={ri}
              photo={rowToPhoto(row, ri)}
              layout={layout}
              dashboardId={dashboardId}
              auth={auth}
              readOnly={readOnly}
              isDragOver={dragOver === ri}
              updatePhoto={updatePhoto}
              removePhoto={removePhoto}
              onOpenLightbox={() => openLightboxForRow(ri)}
              onDragStart={() => setDragFrom(ri)}
              onDragEnd={() => {
                setDragFrom(null);
                setDragOver(null);
              }}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(ri);
              }}
              onDragLeave={() => setDragOver((prev) => (prev === ri ? null : prev))}
              onDrop={() => {
                if (dragFrom !== null) reorderPhotos(dragFrom, ri);
                setDragFrom(null);
                setDragOver(null);
              }}
            />
          ))}
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

function GalleryPhotoCard(props: {
  ri: number;
  photo: GalleryPhoto;
  layout: GalleryLayoutOptions;
  dashboardId: string | null;
  auth: ReturnType<typeof useAuth>;
  readOnly: boolean;
  isDragOver: boolean;
  updatePhoto: (index: number, field: string, value: unknown) => void;
  removePhoto: (index: number) => void;
  onOpenLightbox: () => void;
  onDragStart: () => void;
  onDragEnd: () => void;
  onDragOver: (e: DragEvent) => void;
  onDragLeave: () => void;
  onDrop: () => void;
}) {
  const { t } = useTranslation(["dashboard"]);
  const {
    ri,
    photo,
    layout,
    dashboardId,
    auth,
    readOnly,
    isDragOver,
    updatePhoto,
    removePhoto,
    onOpenLightbox,
    onDragStart,
    onDragEnd,
    onDragOver,
    onDragLeave,
    onDrop,
  } = props;
  const { url, caption } = photo;
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const aspectCls = galleryAspectClass(layout.aspect);

  const onPickFile = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f || !dashboardId) {
      if (!dashboardId) setUploadErr(t("dashboard:dashboardSaveBeforeUpload"));
      return;
    }
    setUploading(true);
    setUploadErr(null);
    void (async () => {
      const result = await uploadDashboardGalleryFile(dashboardId, f, auth, t);
      if (result.ok) updatePhoto(ri, "url", result.galleryRef);
      else setUploadErr(result.error);
      setUploading(false);
    })();
  };

  const imageArea = (
    <div
      className={`relative w-full overflow-hidden bg-gradient-to-br from-white/5 to-black/40 ${aspectCls} ${
        url ? "cursor-zoom-in" : ""
      }`}
    >
      {url ? (
        <button
          type="button"
          className="block h-full w-full text-left"
          onClick={onOpenLightbox}
          aria-label={t("dashboard:galleryOpenLightbox")}
        >
          <GalleryImage url={url} alt={caption} />
        </button>
      ) : (
        <div className="flex h-full min-h-[80px] items-center justify-center text-xs text-surface-muted">
          {readOnly ? t("dashboard:noImage") : t("dashboard:urlOrUpload")}
        </div>
      )}
    </div>
  );

  if (readOnly) {
    return (
      <div className="overflow-hidden rounded-xl border border-surface-border bg-black/25 shadow-sm">
        {imageArea}
        {caption ? (
          <p className="border-t border-white/5 p-3 text-xs text-neutral-200">{caption}</p>
        ) : null}
      </div>
    );
  }

  return (
    <div
      className={`overflow-hidden rounded-xl border bg-black/25 shadow-sm transition-colors ${
        isDragOver ? "border-violet-400/70 ring-1 ring-violet-400/40" : "border-surface-border"
      }`}
      draggable
      onDragStart={(e) => {
        e.stopPropagation();
        e.dataTransfer.effectAllowed = "move";
        onDragStart();
      }}
      onDragEnd={(e) => {
        e.stopPropagation();
        onDragEnd();
      }}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={(e) => {
        e.preventDefault();
        onDrop();
      }}
    >
      <div className="flex items-center gap-1 border-b border-white/5 bg-white/[0.03] px-2 py-1">
        <span
          className="dashboard-grid-no-drag cursor-grab select-none px-1 text-xs text-surface-muted active:cursor-grabbing"
          title={t("dashboard:photosDragHandle")}
          aria-hidden
        >
          ⋮⋮
        </span>
        <span className="text-[10px] text-surface-muted">{t("dashboard:photosDragHandle")}</span>
      </div>
      {imageArea}
      <div className="space-y-2 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <label className="dashboard-grid-no-drag cursor-pointer rounded-md bg-white/10 px-2 py-1 text-xs text-white hover:bg-white/15">
            {uploading ? "…" : t("dashboard:upload")}
            <input
              type="file"
              accept={GALLERY_IMAGE_ACCEPT}
              className="hidden"
              disabled={uploading || !dashboardId}
              onChange={onPickFile}
            />
          </label>
        </div>
        {uploadErr ? <p className="text-[10px] text-red-400">{uploadErr}</p> : null}
        <input
          type="url"
          placeholder={t("dashboard:fileUrlPlaceholder")}
          className="dashboard-grid-no-drag w-full rounded-md border border-surface-border bg-black/40 px-2 py-1.5 text-xs text-neutral-100 placeholder:text-white/25"
          value={url}
          onChange={(e) => updatePhoto(ri, "url", e.target.value)}
        />
        <input
          type="text"
          placeholder={t("dashboard:captionPlaceholder")}
          className="dashboard-grid-no-drag w-full rounded-md border border-surface-border bg-black/40 px-2 py-1.5 text-xs text-neutral-100"
          value={caption}
          onChange={(e) => updatePhoto(ri, "caption", e.target.value)}
        />
        <button
          type="button"
          className="dashboard-grid-no-drag w-full rounded-md py-1 text-xs text-red-400 hover:bg-red-950/30"
          onClick={() => removePhoto(ri)}
        >
          {t("dashboard:remove")}
        </button>
      </div>
    </div>
  );
}
