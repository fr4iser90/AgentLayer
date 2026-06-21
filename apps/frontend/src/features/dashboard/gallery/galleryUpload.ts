import type { useAuth } from "../../../auth/AuthContext";
import { apiFetch } from "../../../lib/api";

type Auth = ReturnType<typeof useAuth>;
type TranslateFn = (key: string, opts?: Record<string, unknown>) => string;

export async function uploadDashboardGalleryFile(
  dashboardId: string,
  file: File,
  auth: Auth,
  t: TranslateFn,
  opts?: { appendListPath?: string; caption?: string }
): Promise<{ ok: true; galleryRef: string } | { ok: false; error: string }> {
  const fd = new FormData();
  fd.append("file", file);
  if (opts?.appendListPath?.trim()) fd.append("append_list_path", opts.appendListPath.trim());
  if (opts?.caption?.trim()) fd.append("caption", opts.caption.trim());
  try {
    const res = await apiFetch(`/v1/dashboards/${dashboardId}/files`, auth, {
      method: "POST",
      body: fd,
    });
    const raw = await res.text();
    let j: { file?: { gallery_ref?: string }; detail?: unknown; gallery_append_error?: unknown } = {};
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
    const ref = j.file?.gallery_ref;
    if (!ref) return { ok: false, error: t("dashboard:uploadNoRef") };
    return { ok: true, galleryRef: ref };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

export const GALLERY_IMAGE_ACCEPT = "image/jpeg,image/png,image/gif,image/webp";
