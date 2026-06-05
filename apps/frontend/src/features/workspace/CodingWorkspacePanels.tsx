import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AuthContextValue } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

type FsEntry = { name: string; path: string; is_dir: boolean; is_symlink: boolean };

type ListPayload = {
  ok?: boolean;
  path?: string;
  entries?: FsEntry[];
  truncated?: boolean;
  detail?: string;
};

type ReadPayload = {
  ok?: boolean;
  path?: string;
  content?: string;
  size?: number;
  detail?: string;
};

type GitChangeFile = { path: string; stat: string };

type GitChangesSummary = {
  ok?: boolean;
  is_git_repo?: boolean;
  branch?: string | null;
  has_changes?: boolean;
  stat?: string;
  stat_truncated?: boolean;
  files?: GitChangeFile[];
  path?: string;
  diff?: string;
  diff_truncated?: boolean;
  detail?: string;
};

type PanelTab = "files" | "changes";

type Props = {
  auth: Pick<AuthContextValue, "accessToken" | "refresh">;
  workspaceId: string | null;
  /** Increment after agent run completes to refresh the changes tab. */
  changesRefreshKey?: number;
  /** ``chat`` = narrow sidebar beside Chat; ``build`` = full Build page layout. */
  variant?: "build" | "chat";
  /** When true, hide git Changes tab (e.g. viewer-only projects). */
  readOnly?: boolean;
  /** Mobile chat overlay: close handler for the full-screen project panel. */
  onMobileClose?: () => void;
};

const SHELL_CLASS_BUILD =
  "flex max-h-[40vh] min-h-0 shrink-0 flex-col border-b border-surface-border bg-[#0a0a0a] lg:h-full lg:max-h-none lg:w-[min(100%,480px)] lg:shrink-0 lg:flex-row lg:border-b-0 lg:border-r";

const SHELL_CLASS_CHAT =
  "fixed inset-0 z-30 flex min-h-0 flex-col bg-[#0a0a0a] md:static md:z-auto md:h-full md:w-[min(100%,300px)] md:shrink-0 md:border-r md:border-surface-border";

function diffLineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "text-neutral-500";
  if (line.startsWith("@@")) return "text-sky-400/90";
  if (line.startsWith("+")) return "text-emerald-300/95";
  if (line.startsWith("-")) return "text-red-300/95";
  return "text-neutral-300";
}

function PanelTabs({
  panelTab,
  onTab,
  changesBadge,
  showChanges = true,
}: {
  panelTab: PanelTab;
  onTab: (t: PanelTab) => void;
  changesBadge: string | null;
  showChanges?: boolean;
}) {
  const { t } = useTranslation(["dashboard", "errors"]);
  const tabClass = (active: boolean) =>
    `rounded-md px-2.5 py-1 text-[10px] font-medium transition-colors ${
      active ? "bg-white/15 text-white" : "text-surface-muted hover:bg-white/10 hover:text-neutral-200"
    }`;

  return (
    <div className="flex gap-1">
      <button type="button" className={tabClass(panelTab === "files")} onClick={() => onTab("files")}>
        Files
      </button>
      {showChanges ? (
        <button type="button" className={tabClass(panelTab === "changes")} onClick={() => onTab("changes")}>
          Changes
          {changesBadge ? (
            <span className="ml-1 rounded bg-amber-600/40 px-1 py-px text-[9px] text-amber-100">{changesBadge}</span>
          ) : null}
        </button>
      ) : null}
    </div>
  );
}

function DiffView({ text, truncated }: { text: string; truncated: boolean }) {
  const { t } = useTranslation(["dashboard"]);
  const lines = text.split("\n");
  return (
    <>
      <div className="font-mono text-[10px] leading-relaxed">
        {lines.map((line, i) => (
          <div key={`${i}-${line.slice(0, 24)}`} className={`whitespace-pre ${diffLineClass(line)}`}>
            {line || " "}
          </div>
        ))}
      </div>
      {truncated ? (
        <p className="mt-2 text-[9px] text-amber-300/80">{t("dashboard:diffTruncated")}</p>
      ) : null}
    </>
  );
}

export function CodingWorkspacePanels({
  auth,
  workspaceId,
  changesRefreshKey = 0,
  variant = "build",
  readOnly = false,
  onMobileClose,
}: Props) {
  const { t } = useTranslation(["dashboard", "workspace"]);
  const shellClass = variant === "chat" ? SHELL_CLASS_CHAT : SHELL_CLASS_BUILD;
  const [panelTab, setPanelTab] = useState<PanelTab>("files");

  const [browsePath, setBrowsePath] = useState("");
  const [entries, setEntries] = useState<FsEntry[]>([]);
  const [listTruncated, setListTruncated] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileMeta, setFileMeta] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);

  const [changesSummary, setChangesSummary] = useState<GitChangesSummary | null>(null);
  const [changesLoading, setChangesLoading] = useState(false);
  const [changesError, setChangesError] = useState<string | null>(null);
  const [selectedChangePath, setSelectedChangePath] = useState<string | null>(null);
  const [changeDiff, setChangeDiff] = useState<string | null>(null);
  const [changeDiffTruncated, setChangeDiffTruncated] = useState(false);
  const [changeDiffLoading, setChangeDiffLoading] = useState(false);
  const [changeDiffError, setChangeDiffError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    if (!workspaceId) {
      setEntries([]);
      setListError(null);
      return;
    }
    setListLoading(true);
    setListError(null);
    try {
      const q = browsePath ? `?path=${encodeURIComponent(browsePath)}` : "";
      const r = await apiFetch(`/v1/workspaces/${workspaceId}/fs/list${q}`, auth);
      const j = (await r.json().catch(() => ({}))) as ListPayload;
      if (!r.ok) {
        setListError(
          typeof j.detail === "string" ? j.detail : `${t("errors:readFileFailed")} (${r.status})`
        );
        setEntries([]);
        return;
      }
      setEntries(Array.isArray(j.entries) ? j.entries : []);
      setListTruncated(Boolean(j.truncated));
    } catch (e) {
      setListError(e instanceof Error ? e.message : t("errors:readFileFailed"));
      setEntries([]);
    } finally {
      setListLoading(false);
    }
  }, [auth, workspaceId, browsePath]);

  const loadChangesSummary = useCallback(async () => {
    if (!workspaceId) {
      setChangesSummary(null);
      setChangesError(null);
      return;
    }
    setChangesLoading(true);
    setChangesError(null);
    try {
      const r = await apiFetch(`/v1/workspaces/${workspaceId}/git/changes`, auth);
      const j = (await r.json().catch(() => ({}))) as GitChangesSummary & { detail?: string };
      if (!r.ok) {
        setChangesError(
          typeof j.detail === "string" ? j.detail : `${t("errors:loadChatsServerSyncFailed")} (${r.status})`
        );
        setChangesSummary(null);
        return;
      }
      setChangesSummary(j);
    } catch (e) {
      setChangesError(e instanceof Error ? e.message : t("errors:loadChatsServerSyncFailed"));
      setChangesSummary(null);
    } finally {
      setChangesLoading(false);
    }
  }, [auth, workspaceId]);

  const loadChangeDiff = useCallback(
    async (relPath: string) => {
      if (!workspaceId) return;
      setSelectedChangePath(relPath);
      setChangeDiffLoading(true);
      setChangeDiffError(null);
      setChangeDiff(null);
      try {
        const q = `?path=${encodeURIComponent(relPath)}`;
        const r = await apiFetch(`/v1/workspaces/${workspaceId}/git/changes${q}`, auth);
        const j = (await r.json().catch(() => ({}))) as GitChangesSummary & { detail?: string };
        if (!r.ok) {
          setChangeDiffError(
            typeof j.detail === "string" ? j.detail : `${t("dashboard:diffFailed")} (${r.status})`
          );
          return;
        }
        setChangeDiff(typeof j.diff === "string" ? j.diff : "");
        setChangeDiffTruncated(Boolean(j.diff_truncated));
      } catch (e) {
        setChangeDiffError(e instanceof Error ? e.message : t("dashboard:diffFailed"));
      } finally {
        setChangeDiffLoading(false);
      }
    },
    [auth, workspaceId]
  );

  const loadFile = useCallback(
    async (relPath: string) => {
      if (!workspaceId) return;
      setSelectedFile(relPath);
      setFileLoading(true);
      setFileError(null);
      setFileContent(null);
      setFileMeta(null);
      try {
        const q = `?path=${encodeURIComponent(relPath)}`;
        const r = await apiFetch(`/v1/workspaces/${workspaceId}/fs/read${q}`, auth);
        const j = (await r.json().catch(() => ({}))) as ReadPayload;
        if (!r.ok) {
          setFileError(typeof j.detail === "string" ? j.detail : `${t("errors:readFileFailed")} (${r.status})`);
          return;
        }
        setFileContent(typeof j.content === "string" ? j.content : "");
        const sz = j.size != null ? ` · ${j.size} bytes` : "";
        setFileMeta(`${j.path ?? relPath}${sz}`);
      } catch (e) {
        setFileError(e instanceof Error ? e.message : t("errors:readFileFailed"));
      } finally {
        setFileLoading(false);
      }
    },
    [auth, workspaceId]
  );

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (panelTab === "changes" || changesRefreshKey > 0) {
      void loadChangesSummary();
    }
  }, [panelTab, changesRefreshKey, loadChangesSummary]);

  useEffect(() => {
    if (!workspaceId) {
      setBrowsePath("");
      setSelectedFile(null);
      setFileContent(null);
      setFileMeta(null);
      setFileError(null);
      setChangesSummary(null);
      setChangesError(null);
      setSelectedChangePath(null);
      setChangeDiff(null);
      setPanelTab("files");
    }
  }, [workspaceId]);

  const crumbs = browsePath ? browsePath.split("/").filter(Boolean) : [];

  const goUp = () => {
    if (!browsePath) return;
    const parts = browsePath.split("/").filter(Boolean);
    parts.pop();
    setBrowsePath(parts.join("/"));
    setSelectedFile(null);
    setFileContent(null);
    setFileMeta(null);
    setFileError(null);
  };

  const changeFileCount = changesSummary?.files?.length ?? 0;
  const changesBadge =
    changesSummary?.has_changes && changeFileCount > 0
      ? String(changeFileCount)
      : changesSummary?.has_changes
        ? "•"
        : null;

  if (!workspaceId) {
    return (
      <div className={`${shellClass} items-center justify-center px-3 py-6 text-center text-xs text-surface-muted`}>
        <p>{t("workspace:selectProjectBrowseFiles")}</p>
      </div>
    );
  }

  return (
    <div className={shellClass}>
      {variant === "chat" && onMobileClose ? (
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-surface-border px-3 py-2 md:hidden">
          <p className="min-w-0 truncate text-sm font-medium text-white">{t("workspace:projectFilesTitle")}</p>
          <button
            type="button"
            className="shrink-0 rounded-md px-2 py-1 text-xs text-surface-muted hover:bg-white/5 hover:text-neutral-200"
            onClick={onMobileClose}
          >
            {t("dashboard:close")}
          </button>
        </div>
      ) : null}
      <div className="flex min-h-0 w-full flex-1 flex-col border-surface-border lg:w-52 lg:shrink-0 lg:border-r">
        <div className="shrink-0 border-b border-surface-border px-2 py-2">
          <PanelTabs
            panelTab={panelTab}
            onTab={setPanelTab}
            changesBadge={changesBadge}
            showChanges={!readOnly}
          />
          {panelTab === "files" ? (
            <>
              <p className="mt-2 text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                Workspace files
              </p>
              <div className="mt-1 flex flex-wrap items-center gap-1 text-[10px] text-neutral-400">
                <button
                  type="button"
                  className="rounded px-1.5 py-0.5 hover:bg-white/10 disabled:opacity-40"
                  onClick={() => {
                    setBrowsePath("");
                    setSelectedFile(null);
                    setFileContent(null);
                    setFileMeta(null);
                    setFileError(null);
                  }}
                  disabled={!browsePath && !selectedFile}
                >
                  root
                </button>
                {crumbs.map((seg, i) => {
                  const prefix = crumbs.slice(0, i + 1).join("/");
                  return (
                    <span key={prefix} className="flex items-center gap-1">
                      <span className="text-white/20">/</span>
                      <button
                        type="button"
                        className="max-w-[5rem] truncate rounded px-1.5 py-0.5 hover:bg-white/10"
                        title={prefix}
                        onClick={() => {
                          setBrowsePath(prefix);
                          setSelectedFile(null);
                          setFileContent(null);
                          setFileMeta(null);
                          setFileError(null);
                        }}
                      >
                        {seg}
                      </button>
                    </span>
                  );
                })}
              </div>
              <div className="mt-1 flex items-center gap-2">
                <button
                  type="button"
                  className="rounded border border-surface-border px-2 py-0.5 text-[10px] text-neutral-300 hover:bg-white/5 disabled:opacity-40"
                  onClick={goUp}
                  disabled={!browsePath}
                >
                  {t("dashboard:up")}
                </button>
                <button
                  type="button"
                  className="rounded border border-surface-border px-2 py-0.5 text-[10px] text-neutral-300 hover:bg-white/5 disabled:opacity-40"
                  onClick={() => void loadList()}
                  disabled={listLoading}
                >
                  {listLoading ? "…" : t("dashboard:refresh")}
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="mt-2 text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                {t("dashboard:gitChanges")}
              </p>
              <p className="mt-0.5 text-[10px] text-neutral-500">
                {changesSummary?.branch ? `branch: ${changesSummary.branch}` : t("dashboard:workingTree")}
              </p>
              <div className="mt-1">
                <button
                  type="button"
                  className="rounded border border-surface-border px-2 py-0.5 text-[10px] text-neutral-300 hover:bg-white/5 disabled:opacity-40"
                  onClick={() => void loadChangesSummary()}
                  disabled={changesLoading}
                >
                  {changesLoading ? "…" : t("dashboard:refresh")}
                </button>
              </div>
            </>
          )}
        </div>

        <ul className="min-h-0 flex-1 overflow-y-auto px-1 py-1 text-xs">
          {panelTab === "files" ? (
            <>
              {listError ? (
                <li className="px-2 py-2 text-red-300/90">{listError}</li>
              ) : entries.length === 0 && !listLoading ? (
                <li className="px-2 py-2 text-surface-muted">{t("dashboard:filesEmpty")}</li>
              ) : (
                entries.map((e) => (
                  <li key={e.path}>
                    <button
                      type="button"
                      className={`flex w-full items-center gap-1 rounded px-2 py-1 text-left hover:bg-white/10 ${
                        selectedFile === e.path && !e.is_dir ? "bg-white/10" : ""
                      }`}
                      onClick={() => {
                        if (e.is_dir) {
                          setBrowsePath(e.path);
                          setSelectedFile(null);
                          setFileContent(null);
                          setFileMeta(null);
                          setFileError(null);
                        } else {
                          void loadFile(e.path);
                        }
                      }}
                    >
                      <span className="text-surface-muted">{e.is_dir ? "📁" : "📄"}</span>
                      <span className="min-w-0 flex-1 truncate text-neutral-200">{e.name}</span>
                      {e.is_symlink ? (
                        <span className="text-[9px] text-amber-400/80">{t("workspace:treeEntrySymlink")}</span>
                      ) : null}
                    </button>
                  </li>
                ))
              )}
            </>
          ) : changesLoading && !changesSummary ? (
            <li className="px-2 py-2 text-surface-muted">{t("dashboard:loading")}</li>
          ) : changesError ? (
            <li className="px-2 py-2 text-red-300/90">{changesError}</li>
          ) : !changesSummary?.has_changes ? (
            <li className="px-2 py-2 text-surface-muted">{t("dashboard:noUncommittedChanges")}</li>
          ) : (changesSummary.files ?? []).length === 0 ? (
            <li className="px-2 py-2 text-surface-muted">{t("dashboard:changesDetected")}</li>
          ) : (
            (changesSummary.files ?? []).map((f) => (
              <li key={f.path}>
                <button
                  type="button"
                  className={`flex w-full flex-col rounded px-2 py-1 text-left hover:bg-white/10 ${
                    selectedChangePath === f.path ? "bg-white/10" : ""
                  }`}
                  onClick={() => void loadChangeDiff(f.path)}
                >
                  <span className="truncate font-mono text-[10px] text-neutral-200">{f.path}</span>
                  <span className="text-[9px] text-neutral-500">{f.stat}</span>
                </button>
              </li>
            ))
          )}
        </ul>
        {panelTab === "files" && listTruncated ? (
          <p className="shrink-0 border-t border-surface-border px-2 py-1 text-[9px] text-amber-300/80">
            {t("dashboard:listTruncated")}
          </p>
        ) : null}
      </div>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col border-t border-surface-border lg:border-t-0">
        <div className="shrink-0 border-b border-surface-border px-3 py-2">
          <p className="text-[10px] font-medium uppercase tracking-wide text-surface-muted">
            {panelTab === "files" ? t("dashboard:preview") : t("dashboard:diff")}
          </p>
          {panelTab === "files" && fileMeta ? (
            <p className="mt-0.5 truncate font-mono text-[10px] text-neutral-500">{fileMeta}</p>
          ) : null}
          {panelTab === "changes" && selectedChangePath ? (
            <p className="mt-0.5 truncate font-mono text-[10px] text-neutral-500">{selectedChangePath}</p>
          ) : null}
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-2">
          {panelTab === "files" ? (
            <>
              {fileLoading ? (
                <p className="text-xs text-surface-muted">{t("dashboard:loading")}</p>
              ) : fileError ? (
                <p className="text-xs text-red-300/90">{fileError}</p>
              ) : fileContent != null ? (
                <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-neutral-200">
                  {fileContent}
                </pre>
              ) : (
                <p className="text-xs text-surface-muted">{t("dashboard:pickFileHint")}</p>
              )}
            </>
          ) : changeDiffLoading ? (
            <p className="text-xs text-surface-muted">{t("dashboard:loadingDiff")}</p>
          ) : changeDiffError ? (
            <p className="text-xs text-red-300/90">{changeDiffError}</p>
          ) : changeDiff != null ? (
            <DiffView text={changeDiff} truncated={changeDiffTruncated} />
          ) : changesSummary?.stat && !selectedChangePath ? (
            <pre className="whitespace-pre-wrap font-mono text-[10px] leading-relaxed text-neutral-400">
              {changesSummary.stat}
              {changesSummary.stat_truncated ? "\n…[truncated]" : ""}
            </pre>
          ) : changesSummary?.has_changes ? (
            <p className="text-xs text-surface-muted">{t("dashboard:selectChangedFileHint")}</p>
          ) : changesError ? null : (
            <p className="text-xs text-surface-muted">{t("dashboard:noChangesToReview")}</p>
          )}
          {panelTab === "changes" && selectedChangePath ? (
            <button
              type="button"
              className="mt-3 text-[10px] text-sky-400/90 hover:underline"
              onClick={() => {
                const parts = selectedChangePath.split("/").filter(Boolean);
                parts.pop();
                setPanelTab("files");
                setBrowsePath(parts.join("/"));
                void loadFile(selectedChangePath);
              }}
            >
              Open current file in Files
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
