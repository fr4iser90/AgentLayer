import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import {
  listDashboardBoardFiles,
  type BoardFileMeta,
} from "./gallery/galleryUpload";

/** Settings panel: list persistent board files (Board-Dateien). */
export function DashboardBoardFilesPanel(props: { dashboardId: string }) {
  const { t } = useTranslation(["dashboard"]);
  const auth = useAuth();
  const { dashboardId } = props;
  const [files, setFiles] = useState<BoardFileMeta[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!auth.accessToken) return;
    setBusy(true);
    setErr(null);
    const res = await listDashboardBoardFiles(dashboardId, auth, t);
    setBusy(false);
    if (!res.ok) {
      setErr(res.error);
      return;
    }
    setFiles(res.files);
  }, [auth, dashboardId, t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div className="rounded-sheet border border-line bg-black/20 p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          {t("dashboard:boardFilesLibrary")}
        </p>
        <button
          type="button"
          disabled={busy}
          className="rounded-tile border border-line px-2 py-1 text-meta text-ink-secondary hover:bg-white/5 disabled:opacity-40"
          onClick={() => void reload()}
        >
          {t("dashboard:boardFilesRefresh")}
        </button>
      </div>
      <p className="mt-1 text-xs text-ink-muted">{t("dashboard:boardFilesLibraryHint")}</p>
      {err ? <p className="mt-2 text-xs text-rose-300">{err}</p> : null}
      {busy && files.length === 0 ? (
        <p className="mt-2 text-xs text-ink-muted">{t("dashboard:loading")}</p>
      ) : files.length === 0 ? (
        <p className="mt-2 text-xs text-ink-muted">{t("dashboard:boardFilesLibraryEmpty")}</p>
      ) : (
        <ul className="mt-3 max-h-56 space-y-1 overflow-y-auto">
          {files.map((f) => (
            <li
              key={f.id}
              className="rounded-tile border border-line-subtle bg-black/30 px-2 py-1.5 text-xs text-ink-primary"
            >
              <p className="truncate font-medium">{f.original_name || f.id}</p>
              <p className="truncate text-meta text-ink-muted">
                {f.content_type || "file"} · {f.file_ref || f.gallery_ref}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
