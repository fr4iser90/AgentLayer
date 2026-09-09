import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthContext";
import { apiFetch, type WorkspaceApiRecord } from "../lib/api";
import { deleteWorkspaceApi, isAgentlayerSelfWorkspace } from "../lib/workspacesApi";

type FsEntry = {
  name: string;
  path: string;
  is_dir: boolean;
  is_symlink?: boolean;
};

function parentPath(p: string): string {
  const parts = p.replace(/\\/g, "/").split("/").filter(Boolean);
  if (parts.length <= 1) return "";
  return parts.slice(0, -1).join("/");
}

export function ProjectsPage() {
  const { t } = useTranslation(["workspace", "errors", "common"]);
  const auth = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("id")?.trim() || null;

  const [workspaces, setWorkspaces] = useState<WorkspaceApiRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [browsePath, setBrowsePath] = useState("");
  const [entries, setEntries] = useState<FsEntry[]>([]);
  const [treeLoading, setTreeLoading] = useState(false);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [treeTruncated, setTreeTruncated] = useState(false);

  const selected = useMemo(
    () => workspaces.find((w) => w.id === selectedId) ?? null,
    [workspaces, selectedId]
  );

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await apiFetch("/v1/workspaces", auth);
      const j = (await r.json().catch(() => ({}))) as {
        workspaces?: WorkspaceApiRecord[];
        detail?: string;
      };
      if (!r.ok) {
        setError(
          typeof j.detail === "string" ? j.detail : t("workspace:projectsLoadFailed", { status: r.status })
        );
        setWorkspaces([]);
        return;
      }
      setWorkspaces(Array.isArray(j.workspaces) ? j.workspaces : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("workspace:projectsLoadFailed", { status: "?" }));
      setWorkspaces([]);
    } finally {
      setLoading(false);
    }
  }, [auth, t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!selectedId && workspaces.length > 0) {
      setSearchParams({ id: workspaces[0]!.id }, { replace: true });
    }
  }, [selectedId, workspaces, setSearchParams]);

  const loadTree = useCallback(async () => {
    if (!selectedId) {
      setEntries([]);
      setTreeError(null);
      return;
    }
    setTreeLoading(true);
    setTreeError(null);
    try {
      const q = browsePath ? `?path=${encodeURIComponent(browsePath)}` : "";
      const r = await apiFetch(`/v1/workspaces/${encodeURIComponent(selectedId)}/fs/list${q}`, auth);
      const j = (await r.json().catch(() => ({}))) as {
        entries?: FsEntry[];
        truncated?: boolean;
        detail?: string;
      };
      if (!r.ok) {
        setTreeError(
          typeof j.detail === "string" ? j.detail : t("workspace:projectsTreeFailed", { status: r.status })
        );
        setEntries([]);
        return;
      }
      setEntries(Array.isArray(j.entries) ? j.entries : []);
      setTreeTruncated(Boolean(j.truncated));
    } catch (e) {
      setTreeError(e instanceof Error ? e.message : t("workspace:projectsTreeFailed", { status: "?" }));
      setEntries([]);
    } finally {
      setTreeLoading(false);
    }
  }, [auth, browsePath, selectedId, t]);

  useEffect(() => {
    setBrowsePath("");
  }, [selectedId]);

  useEffect(() => {
    void loadTree();
  }, [loadTree]);

  const selectWorkspace = (id: string) => {
    setSearchParams({ id });
  };

  const onDelete = async (ws: WorkspaceApiRecord) => {
    const self = isAgentlayerSelfWorkspace(ws);
    const ok = window.confirm(
      self
        ? t("workspace:projectsDeleteSelfConfirm", { name: ws.name })
        : t("workspace:projectsDeleteConfirm", { name: ws.name })
    );
    if (!ok) return;
    setBusyId(ws.id);
    setError(null);
    try {
      await deleteWorkspaceApi(auth, ws.id);
      setWorkspaces((prev) => prev.filter((w) => w.id !== ws.id));
      if (selectedId === ws.id) {
        setSearchParams({});
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("workspace:projectsDeleteFailed"));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col gap-4 overflow-hidden p-4 md:p-6">
      <header className="shrink-0">
        <h1 className="text-lg font-semibold text-white">{t("workspace:projectsTitle")}</h1>
        <p className="mt-1 max-w-2xl text-sm text-surface-muted">{t("workspace:projectsIntro")}</p>
        <p className="mt-1 text-xs text-surface-muted">{t("workspace:projectsOwnerScopeNote")}</p>
      </header>

      {error ? (
        <p className="shrink-0 rounded-lg border border-rose-500/30 bg-rose-950/30 px-3 py-2 text-sm text-rose-200">
          {error}
        </p>
      ) : null}

      <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[minmax(14rem,20rem)_1fr]">
        <section className="flex min-h-0 flex-col rounded-xl border border-surface-border bg-surface-raised/40">
          <div className="flex items-center justify-between gap-2 border-b border-surface-border px-3 py-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-surface-muted">
              {t("workspace:projectsListTitle")}
            </h2>
            <button
              type="button"
              className="rounded-md border border-white/10 px-2 py-1 text-[10px] text-neutral-300 hover:bg-white/5 disabled:opacity-40"
              disabled={loading}
              onClick={() => void reload()}
            >
              {t("workspace:projectsRefresh")}
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {loading ? (
              <p className="px-2 py-2 text-xs text-surface-muted">{t("common:nav.loading")}</p>
            ) : workspaces.length === 0 ? (
              <p className="px-2 py-2 text-xs text-surface-muted">{t("workspace:projectsEmpty")}</p>
            ) : (
              <ul className="space-y-1">
                {workspaces.map((w) => {
                  const active = w.id === selectedId;
                  return (
                    <li key={w.id}>
                      <button
                        type="button"
                        className={[
                          "w-full rounded-lg px-2.5 py-2 text-left transition-colors",
                          active
                            ? "border border-sky-500/40 bg-sky-950/30"
                            : "border border-transparent hover:bg-white/5",
                        ].join(" ")}
                        onClick={() => selectWorkspace(w.id)}
                      >
                        <span className="block truncate text-sm text-neutral-100">{w.name}</span>
                        <span className="mt-0.5 block truncate text-[10px] text-surface-muted">
                          {w.source}
                          {w.git_url ? ` · ${w.git_url}` : ""}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </section>

        <section className="flex min-h-0 flex-col rounded-xl border border-surface-border bg-surface-raised/40">
          {!selected ? (
            <p className="p-4 text-sm text-surface-muted">{t("workspace:selectProjectBrowseFiles")}</p>
          ) : (
            <>
              <div className="shrink-0 space-y-3 border-b border-surface-border p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="truncate text-base font-medium text-white">{selected.name}</h2>
                    <p className="mt-1 break-all font-mono text-[11px] text-surface-muted">
                      {selected.path || "—"}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link
                      to={`/chat?workspace=${encodeURIComponent(selected.id)}`}
                      className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-neutral-200 hover:bg-white/5"
                    >
                      {t("workspace:projectsOpenChat")}
                    </Link>
                    <button
                      type="button"
                      disabled={busyId === selected.id}
                      className="rounded-lg border border-rose-500/40 px-3 py-1.5 text-xs text-rose-200 hover:bg-rose-950/40 disabled:opacity-40"
                      onClick={() => void onDelete(selected)}
                    >
                      {busyId === selected.id
                        ? t("workspace:projectsDeleting")
                        : t("workspace:projectsDeleteClean")}
                    </button>
                  </div>
                </div>
                <dl className="grid gap-2 text-xs sm:grid-cols-2">
                  <div>
                    <dt className="text-surface-muted">{t("workspace:projectsFieldSource")}</dt>
                    <dd className="text-neutral-200">{selected.source}</dd>
                  </div>
                  <div>
                    <dt className="text-surface-muted">{t("workspace:projectsFieldBranch")}</dt>
                    <dd className="text-neutral-200">{selected.git_branch || "—"}</dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="text-surface-muted">{t("workspace:projectsFieldGit")}</dt>
                    <dd className="break-all text-neutral-200">{selected.git_url || "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-surface-muted">{t("workspace:projectsFieldUpdated")}</dt>
                    <dd className="text-neutral-200">{selected.updated_at || "—"}</dd>
                  </div>
                </dl>
              </div>

              <div className="flex min-h-0 flex-1 flex-col">
                <div className="flex shrink-0 items-center justify-between gap-2 border-b border-surface-border px-3 py-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-surface-muted">
                    {t("workspace:projectFilesTitle")}
                  </h3>
                  <div className="flex items-center gap-2">
                    {browsePath ? (
                      <button
                        type="button"
                        className="rounded border border-white/10 px-2 py-0.5 text-[10px] text-neutral-300 hover:bg-white/5"
                        onClick={() => setBrowsePath(parentPath(browsePath))}
                      >
                        {t("workspace:projectsTreeUp")}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="rounded border border-white/10 px-2 py-0.5 text-[10px] text-neutral-300 hover:bg-white/5"
                      disabled={treeLoading}
                      onClick={() => void loadTree()}
                    >
                      {t("workspace:projectsRefresh")}
                    </button>
                  </div>
                </div>
                <p className="shrink-0 truncate border-b border-white/5 px-3 py-1 font-mono text-[10px] text-surface-muted">
                  {browsePath || "."}
                </p>
                <div className="min-h-0 flex-1 overflow-y-auto p-2">
                  {treeError ? (
                    <p className="px-2 py-2 text-xs text-rose-300">{treeError}</p>
                  ) : treeLoading ? (
                    <p className="px-2 py-2 text-xs text-surface-muted">{t("common:nav.loading")}</p>
                  ) : entries.length === 0 ? (
                    <p className="px-2 py-2 text-xs text-surface-muted">{t("workspace:projectsTreeEmpty")}</p>
                  ) : (
                    <ul className="space-y-0.5">
                      {entries.map((e) => (
                        <li key={e.path}>
                          {e.is_dir ? (
                            <button
                              type="button"
                              className="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs text-sky-200 hover:bg-white/5"
                              onClick={() => setBrowsePath(e.path)}
                            >
                              <span className="text-surface-muted">/</span>
                              <span className="truncate">{e.name}</span>
                              {e.is_symlink ? (
                                <span className="text-[9px] text-surface-muted">
                                  {t("workspace:treeEntrySymlink")}
                                </span>
                              ) : null}
                            </button>
                          ) : (
                            <div className="flex items-center gap-2 rounded px-2 py-1 text-xs text-neutral-300">
                              <span className="text-surface-muted">·</span>
                              <span className="truncate">{e.name}</span>
                              {e.is_symlink ? (
                                <span className="text-[9px] text-surface-muted">
                                  {t("workspace:treeEntrySymlink")}
                                </span>
                              ) : null}
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                  {treeTruncated ? (
                    <p className="mt-2 px-2 text-[10px] text-amber-300/90">
                      {t("workspace:projectsTreeTruncated")}
                    </p>
                  ) : null}
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
