import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { File, Folder } from "lucide-react";
import type { AuthContextValue } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import { Tooltip } from "../../ui/Tooltip";

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
  "flex max-h-[40vh] min-h-0 shrink-0 flex-col border-b border-line bg-[#0a0a0a] lg:h-full lg:max-h-none lg:w-[min(100%,480px)] lg:shrink-0 lg:flex-row lg:border-b-0 lg:border-r";

const SHELL_CLASS_CHAT =
  "fixed inset-0 z-docked flex min-h-0 flex-col bg-[#0a0a0a] md:static md:z-auto md:h-full md:w-[min(100%,300px)] md:shrink-0 md:border-r md:border-line";

function diffLineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "text-ink-muted";
  if (line.startsWith("@@")) return "text-accent";
  if (line.startsWith("+")) return "text-badge-success";
  if (line.startsWith("-")) return "text-badge-danger";
  return "text-ink-secondary";
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
    `rounded-tile px-firm py-tight text-meta font-medium transition-colors ${
      active ? "bg-white/15 text-ink-primary" : "text-ink-muted hover:bg-white/10 hover:text-neutral-200"
    }`;

  return (
    <div className="flex gap-tight">
      <button type="button" className={tabClass(panelTab === "files")} onClick={() => onTab("files")}>
        Files
      </button>
      {showChanges ? (
        <button type="button" className={tabClass(panelTab === "changes")} onClick={() => onTab("changes")}>
          Changes
          {changesBadge ? (
            <span className="ml-tight rounded-tile bg-warning-subtle px-tight py-px text-meta text-badge-warning">{changesBadge}</span>
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
      <div className="font-mono text-meta leading-relaxed">
        {lines.map((line, i) => (
          <div key={`${i}-${line.slice(0, 24)}`} className={`whitespace-pre ${diffLineClass(line)}`}>
            {line || " "}
          </div>
        ))}
      </div>
      {truncated ? (
        <p className="mt-base text-meta text-badge-warning">{t("dashboard:diffTruncated")}</p>
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
      <div className={`${shellClass} items-center justify-center px-soft py-broad text-center text-xs text-ink-muted`}>
        <p>{t("workspace:selectProjectBrowseFiles")}</p>
      </div>
    );
  }

  return (
    <div className={shellClass}>
      {variant === "chat" && onMobileClose ? (
        <div className="flex shrink-0 items-center justify-between gap-base border-b border-line px-soft py-base md:hidden">
          <p className="min-w-0 truncate text-sm font-medium text-ink-primary">{t("workspace:projectFilesTitle")}</p>
          <button
            type="button"
            className="shrink-0 rounded-tile px-base py-tight text-xs text-ink-muted hover:bg-white/5 hover:text-neutral-200"
            onClick={onMobileClose}
          >
            {t("dashboard:close")}
          </button>
        </div>
      ) : null}
      <div className="flex min-h-0 w-full flex-1 flex-col border-line lg:w-52 lg:shrink-0 lg:border-r">
        <div className="shrink-0 border-b border-line px-base py-base">
          <PanelTabs
            panelTab={panelTab}
            onTab={setPanelTab}
            changesBadge={changesBadge}
            showChanges={!readOnly}
          />
          {panelTab === "files" ? (
            <>
              <p className="mt-base text-meta font-medium uppercase tracking-wide text-ink-muted">
                Workspace files
              </p>
              <div className="mt-tight flex flex-wrap items-center gap-tight text-meta text-ink-muted">
                <button
                  type="button"
                  className="rounded-tile px-snug py-hair hover:bg-white/10 disabled:opacity-40"
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
                    <span key={prefix} className="flex items-center gap-tight">
                      <span className="text-white/20">/</span>
                      <Tooltip label={prefix}>
                      <button
                          type="button"
                          className="max-w-chip truncate rounded-tile px-snug py-hair hover:bg-white/10"
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
                      </Tooltip>
                    </span>
                  );
                })}
              </div>
              <div className="mt-tight flex items-center gap-base">
                <button
                  type="button"
                  className="rounded-tile border border-line px-base py-hair text-meta text-ink-secondary hover:bg-white/5 disabled:opacity-40"
                  onClick={goUp}
                  disabled={!browsePath}
                >
                  {t("dashboard:up")}
                </button>
                <button
                  type="button"
                  className="rounded-tile border border-line px-base py-hair text-meta text-ink-secondary hover:bg-white/5 disabled:opacity-40"
                  onClick={() => void loadList()}
                  disabled={listLoading}
                >
                  {listLoading ? "…" : t("dashboard:refresh")}
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="mt-base text-meta font-medium uppercase tracking-wide text-ink-muted">
                {t("dashboard:gitChanges")}
              </p>
              <p className="mt-hair text-meta text-ink-muted">
                {changesSummary?.branch ? `branch: ${changesSummary.branch}` : t("dashboard:workingTree")}
              </p>
              <div className="mt-tight">
                <button
                  type="button"
                  className="rounded-tile border border-line px-base py-hair text-meta text-ink-secondary hover:bg-white/5 disabled:opacity-40"
                  onClick={() => void loadChangesSummary()}
                  disabled={changesLoading}
                >
                  {changesLoading ? "…" : t("dashboard:refresh")}
                </button>
              </div>
            </>
          )}
        </div>

        <ul className="min-h-0 flex-1 overflow-y-auto px-tight py-tight text-xs">
          {panelTab === "files" ? (
            <>
              {listError ? (
                <li className="px-base py-base text-badge-danger">{listError}</li>
              ) : entries.length === 0 && !listLoading ? (
                <li className="px-base py-base text-ink-muted">{t("dashboard:filesEmpty")}</li>
              ) : (
                entries.map((e) => (
                  <li key={e.path}>
                    <button
                      type="button"
                      className={`flex w-full items-center gap-tight rounded-tile px-base py-tight text-left hover:bg-white/10 ${
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
                      {e.is_dir ? (
                        <Folder aria-hidden className="h-3.5 w-3.5 shrink-0 text-ink-muted" />
                      ) : (
                        <File aria-hidden className="h-3.5 w-3.5 shrink-0 text-ink-muted" />
                      )}
                      <span className="min-w-0 flex-1 truncate text-ink-primary">{e.name}</span>
                      {e.is_symlink ? (
                        <span className="text-meta text-warning">{t("workspace:treeEntrySymlink")}</span>
                      ) : null}
                    </button>
                  </li>
                ))
              )}
            </>
          ) : changesLoading && !changesSummary ? (
            <li className="px-base py-base text-ink-muted">{t("dashboard:loading")}</li>
          ) : changesError ? (
            <li className="px-base py-base text-badge-danger">{changesError}</li>
          ) : !changesSummary?.has_changes ? (
            <li className="px-base py-base text-ink-muted">{t("dashboard:noUncommittedChanges")}</li>
          ) : (changesSummary.files ?? []).length === 0 ? (
            <li className="px-base py-base text-ink-muted">{t("dashboard:changesDetected")}</li>
          ) : (
            (changesSummary.files ?? []).map((f) => (
              <li key={f.path}>
                <button
                  type="button"
                  className={`flex w-full flex-col rounded-tile px-base py-tight text-left hover:bg-white/10 ${
                    selectedChangePath === f.path ? "bg-white/10" : ""
                  }`}
                  onClick={() => void loadChangeDiff(f.path)}
                >
                  <span className="truncate font-mono text-meta text-ink-primary">{f.path}</span>
                  <span className="text-meta text-ink-muted">{f.stat}</span>
                </button>
              </li>
            ))
          )}
        </ul>
        {panelTab === "files" && listTruncated ? (
          <p className="shrink-0 border-t border-line px-base py-tight text-meta text-badge-warning">
            {t("dashboard:listTruncated")}
          </p>
        ) : null}
      </div>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col border-t border-line lg:border-t-0">
        <div className="shrink-0 border-b border-line px-soft py-base">
          <p className="text-meta font-medium uppercase tracking-wide text-ink-muted">
            {panelTab === "files" ? t("dashboard:preview") : t("dashboard:diff")}
          </p>
          {panelTab === "files" && fileMeta ? (
            <p className="mt-hair truncate font-mono text-meta text-ink-muted">{fileMeta}</p>
          ) : null}
          {panelTab === "changes" && selectedChangePath ? (
            <p className="mt-hair truncate font-mono text-meta text-ink-muted">{selectedChangePath}</p>
          ) : null}
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-base">
          {panelTab === "files" ? (
            <>
              {fileLoading ? (
                <p className="text-xs text-ink-muted">{t("dashboard:loading")}</p>
              ) : fileError ? (
                <p className="text-xs text-badge-danger">{fileError}</p>
              ) : fileContent != null ? (
                <pre className="whitespace-pre-wrap break-words font-mono text-meta leading-relaxed text-ink-primary">
                  {fileContent}
                </pre>
              ) : (
                <p className="text-xs text-ink-muted">{t("dashboard:pickFileHint")}</p>
              )}
            </>
          ) : changeDiffLoading ? (
            <p className="text-xs text-ink-muted">{t("dashboard:loadingDiff")}</p>
          ) : changeDiffError ? (
            <p className="text-xs text-badge-danger">{changeDiffError}</p>
          ) : changeDiff != null ? (
            <DiffView text={changeDiff} truncated={changeDiffTruncated} />
          ) : changesSummary?.stat && !selectedChangePath ? (
            <pre className="whitespace-pre-wrap font-mono text-meta leading-relaxed text-ink-muted">
              {changesSummary.stat}
              {changesSummary.stat_truncated ? "\n…[truncated]" : ""}
            </pre>
          ) : changesSummary?.has_changes ? (
            <p className="text-xs text-ink-muted">{t("dashboard:selectChangedFileHint")}</p>
          ) : changesError ? null : (
            <p className="text-xs text-ink-muted">{t("dashboard:noChangesToReview")}</p>
          )}
          {panelTab === "changes" && selectedChangePath ? (
            <button
              type="button"
              className="mt-soft text-meta text-accent hover:underline"
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
