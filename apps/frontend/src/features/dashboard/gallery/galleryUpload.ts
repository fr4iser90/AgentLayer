import type { useAuth } from "../../../auth/AuthContext";
import { apiFetch } from "../../../lib/api";

type Auth = ReturnType<typeof useAuth>;
type TranslateFn = (key: string, opts?: Record<string, unknown>) => string;

export type BoardFileMeta = {
  id: string;
  file_ref: string;
  gallery_ref: string;
  content_type: string;
  size_bytes: number;
  original_name: string;
  created_at: string;
};

export type UploadBoardFileResult =
  | {
      ok: true;
      galleryRef: string;
      contentType?: string;
      textAppliedTo?: string;
      textApplyError?: string;
      galleryAppendError?: string;
    }
  | { ok: false; error: string };

export async function uploadDashboardBoardFile(
  dashboardId: string,
  file: File,
  auth: Auth,
  t: TranslateFn,
  opts?: {
    appendListPath?: string;
    appendTextPath?: string;
    caption?: string;
  }
): Promise<UploadBoardFileResult> {
  const fd = new FormData();
  fd.append("file", file);
  if (opts?.appendListPath?.trim()) fd.append("append_list_path", opts.appendListPath.trim());
  if (opts?.appendTextPath?.trim()) fd.append("append_text_path", opts.appendTextPath.trim());
  if (opts?.caption?.trim()) fd.append("caption", opts.caption.trim());
  try {
    const res = await apiFetch(`/v1/dashboards/${dashboardId}/files`, auth, {
      method: "POST",
      body: fd,
    });
    const raw = await res.text();
    let j: {
      file?: { gallery_ref?: string; file_ref?: string; content_type?: string };
      detail?: unknown;
      gallery_append_error?: unknown;
      text_apply_error?: unknown;
      text_applied_to?: string;
    } = {};
    try {
      j = JSON.parse(raw) as typeof j;
    } catch {
      j = {};
    }
    if (!res.ok) {
      const msg =
        typeof j.detail === "string"
          ? j.detail
          : t("dashboard:uploadFailed", { status: res.status });
      return { ok: false, error: msg };
    }
    if (opts?.appendListPath?.trim() && j.gallery_append_error) {
      return { ok: false, error: String(j.gallery_append_error) };
    }
    const ref = j.file?.gallery_ref || j.file?.file_ref;
    if (!ref) return { ok: false, error: t("dashboard:uploadNoRef") };
    return {
      ok: true,
      galleryRef: ref,
      contentType: j.file?.content_type,
      textAppliedTo: j.text_applied_to,
      textApplyError: j.text_apply_error ? String(j.text_apply_error) : undefined,
      galleryAppendError: j.gallery_append_error ? String(j.gallery_append_error) : undefined,
    };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

/** Gallery/hero image upload (optional list append). */
export async function uploadDashboardGalleryFile(
  dashboardId: string,
  file: File,
  auth: Auth,
  t: TranslateFn,
  opts?: { appendListPath?: string; caption?: string }
): Promise<{ ok: true; galleryRef: string } | { ok: false; error: string }> {
  const result = await uploadDashboardBoardFile(dashboardId, file, auth, t, opts);
  if (!result.ok) return result;
  return { ok: true, galleryRef: result.galleryRef };
}

export async function listDashboardBoardFiles(
  dashboardId: string,
  auth: Auth,
  t: TranslateFn
): Promise<{ ok: true; files: BoardFileMeta[] } | { ok: false; error: string }> {
  try {
    const res = await apiFetch(`/v1/dashboards/${dashboardId}/files`, auth, { method: "GET" });
    const raw = await res.text();
    let j: { files?: BoardFileMeta[]; detail?: unknown } = {};
    try {
      j = JSON.parse(raw) as typeof j;
    } catch {
      j = {};
    }
    if (!res.ok) {
      const msg =
        typeof j.detail === "string"
          ? j.detail
          : t("dashboard:boardFilesLoadFailed", { status: res.status });
      return { ok: false, error: msg };
    }
    const files = Array.isArray(j.files) ? j.files : [];
    return { ok: true, files };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

export const GALLERY_IMAGE_ACCEPT = "image/jpeg,image/png,image/gif,image/webp";

/** Board file picker: images + markdown/text family. */
export const BOARD_FILE_ACCEPT =
  "image/jpeg,image/png,image/gif,image/webp,.md,.markdown,.txt,.csv,.json,.log,.yaml,.yml";
