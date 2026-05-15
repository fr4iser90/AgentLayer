import { useCallback, useEffect, useState } from "react";
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

type Props = {
  auth: Pick<AuthContextValue, "accessToken" | "refresh">;
  workspaceId: string | null;
};

export function CodingWorkspacePanels({ auth, workspaceId }: Props) {
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
        setListError(typeof j.detail === "string" ? j.detail : `List failed (${r.status})`);
        setEntries([]);
        return;
      }
      setEntries(Array.isArray(j.entries) ? j.entries : []);
      setListTruncated(Boolean(j.truncated));
    } catch (e) {
      setListError(e instanceof Error ? e.message : "List failed");
      setEntries([]);
    } finally {
      setListLoading(false);
    }
  }, [auth, workspaceId, browsePath]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (!workspaceId) {
      setBrowsePath("");
      setSelectedFile(null);
      setFileContent(null);
      setFileMeta(null);
      setFileError(null);
    }
  }, [workspaceId]);

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
          setFileError(typeof j.detail === "string" ? j.detail : `Open failed (${r.status})`);
          return;
        }
        setFileContent(typeof j.content === "string" ? j.content : "");
        const sz = j.size != null ? ` · ${j.size} bytes` : "";
        setFileMeta(`${j.path ?? relPath}${sz}`);
      } catch (e) {
        setFileError(e instanceof Error ? e.message : "Open failed");
      } finally {
        setFileLoading(false);
      }
    },
    [auth, workspaceId]
  );

  const crumbs = browsePath
    ? browsePath.split("/").filter(Boolean)
    : [];

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

  if (!workspaceId) {
    return (
      <div className="flex min-h-[120px] flex-col items-center justify-center border-b border-surface-border bg-black/20 px-3 py-6 text-center text-xs text-surface-muted lg:h-full lg:min-h-0 lg:w-[min(100%,420px)] lg:shrink-0 lg:flex-row lg:border-b-0 lg:border-r">
        <p>Select a workspace to browse files.</p>
      </div>
    );
  }

  return (
    <div className="flex max-h-[40vh] min-h-0 shrink-0 flex-col border-b border-surface-border bg-[#0a0a0a] lg:h-full lg:max-h-none lg:w-[min(100%,480px)] lg:shrink-0 lg:flex-row lg:border-b-0 lg:border-r">
      <div className="flex min-h-0 w-full flex-col border-surface-border lg:w-52 lg:shrink-0 lg:border-r">
        <div className="shrink-0 border-b border-surface-border px-2 py-2">
          <p className="text-[10px] font-medium uppercase tracking-wide text-surface-muted">Workspace files</p>
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
              Up
            </button>
            <button
              type="button"
              className="rounded border border-surface-border px-2 py-0.5 text-[10px] text-neutral-300 hover:bg-white/5 disabled:opacity-40"
              onClick={() => void loadList()}
              disabled={listLoading}
            >
              {listLoading ? "…" : "Refresh"}
            </button>
          </div>
        </div>
        <ul className="min-h-0 flex-1 overflow-y-auto px-1 py-1 text-xs">
          {listError ? (
            <li className="px-2 py-2 text-red-300/90">{listError}</li>
          ) : entries.length === 0 && !listLoading ? (
            <li className="px-2 py-2 text-surface-muted">Empty</li>
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
                  {e.is_symlink ? <span className="text-[9px] text-amber-400/80">link</span> : null}
                </button>
              </li>
            ))
          )}
        </ul>
        {listTruncated ? (
          <p className="shrink-0 border-t border-surface-border px-2 py-1 text-[9px] text-amber-300/80">
            List truncated (server cap).
          </p>
        ) : null}
      </div>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col border-t border-surface-border lg:border-t-0">
        <div className="shrink-0 border-b border-surface-border px-3 py-2">
          <p className="text-[10px] font-medium uppercase tracking-wide text-surface-muted">Preview</p>
          {fileMeta ? <p className="mt-0.5 truncate font-mono text-[10px] text-neutral-500">{fileMeta}</p> : null}
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-2">
          {fileLoading ? (
            <p className="text-xs text-surface-muted">Loading…</p>
          ) : fileError ? (
            <p className="text-xs text-red-300/90">{fileError}</p>
          ) : fileContent != null ? (
            <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-neutral-200">
              {fileContent}
            </pre>
          ) : (
            <p className="text-xs text-surface-muted">Pick a file in the tree (read-only preview).</p>
          )}
        </div>
      </div>
    </div>
  );
}
