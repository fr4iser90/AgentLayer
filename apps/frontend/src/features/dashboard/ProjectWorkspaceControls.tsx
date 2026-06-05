import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AuthContextValue } from "../../auth/AuthContext";
import { apiFetch, type WorkspaceApiRecord } from "../../lib/api";

type Props = {
  auth: Pick<AuthContextValue, "accessToken" | "refresh">;
  workspaceId: string;
  remoteUrl: string;
  defaultBranch?: string;
  readOnly?: boolean;
  onWorkspaceChange: (workspaceId: string, projectPath?: string) => void;
};

export function ProjectWorkspaceControls({
  auth,
  workspaceId,
  remoteUrl,
  defaultBranch = "main",
  readOnly = false,
  onWorkspaceChange,
}: Props) {
  const { t } = useTranslation(["dashboard", "errors"]);
  const [workspaces, setWorkspaces] = useState<WorkspaceApiRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const loadWorkspaces = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiFetch("/v1/workspaces", auth);
      if (!r.ok) {
        setWorkspaces([]);
        return;
      }
      const j = (await r.json()) as { workspaces?: WorkspaceApiRecord[] };
      setWorkspaces(j.workspaces ?? []);
    } catch {
      setWorkspaces([]);
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    void loadWorkspaces();
  }, [loadWorkspaces]);

  const matched = workspaces.find((w) => w.id === workspaceId.trim());
  const remote = remoteUrl.trim();

  const createFromRemote = async () => {
    if (!remote || readOnly) return;
    setCreating(true);
    setMsg(null);
    try {
      const slug = remote
        .replace(/\.git$/i, "")
        .split("/")
        .pop()
        ?.replace(/[^a-zA-Z0-9_.-]+/g, "-")
        .slice(0, 48);
      const name = slug || "repo";
      const r = await apiFetch("/v1/workspaces", auth, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          source: "git",
          git_url: remote,
          git_branch: defaultBranch || "main",
        }),
      });
      const j = (await r.json().catch(() => null)) as {
        workspace?: WorkspaceApiRecord;
        detail?: string;
      };
      if (!r.ok || !j?.workspace?.id) {
        setMsg(`${t("errors:generic")}: ${String(j?.detail ?? r.status)}`);
        return;
      }
      await loadWorkspaces();
      onWorkspaceChange(j.workspace.id, j.workspace.path);
      setMsg(t("dashboard:workspaceCreatedLinked"));
    } catch (e) {
      setMsg(`${t("errors:generic")}: ${String(e)}`);
    } finally {
      setCreating(false);
    }
  };

  const linkExisting = (id: string) => {
    const ws = workspaces.find((w) => w.id === id);
    onWorkspaceChange(id, ws?.path);
    setMsg(null);
  };

  return (
    <div className="mb-4 rounded-xl border border-surface-border bg-black/15 p-3">
      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-surface-muted">
        {t("dashboard:linkedWorkspace")}
      </div>
      {loading ? (
        <p className="text-xs text-surface-muted">{t("dashboard:loading")}</p>
      ) : (
        <>
          <label className="mb-2 block text-[11px] text-surface-muted">
            {t("dashboard:workspacePickerLabel")}
            <select
              value={workspaceId}
              disabled={readOnly}
              onChange={(e) => linkExisting(e.target.value)}
              className="mt-1 w-full rounded-lg border border-surface-border bg-black/30 px-3 py-1.5 text-xs text-neutral-100 outline-none focus:border-violet-400/60 disabled:opacity-70"
            >
              <option value="">{t("dashboard:workspacePickerNone")}</option>
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                  {w.git_url ? ` · ${w.git_url.replace(/^https?:\/\//, "")}` : ""}
                </option>
              ))}
            </select>
          </label>
          {matched ? (
            <p className="mb-2 truncate font-mono text-[10px] text-surface-muted">{matched.path}</p>
          ) : workspaceId ? (
            <p className="mb-2 text-[10px] text-amber-300/90">{t("dashboard:workspaceNotFound")}</p>
          ) : null}
          {!readOnly && remote ? (
            <button
              type="button"
              disabled={creating}
              onClick={() => void createFromRemote()}
              className="rounded-md border border-violet-500/40 bg-violet-950/30 px-3 py-1.5 text-xs text-violet-100 hover:bg-violet-900/40 disabled:opacity-60"
            >
              {creating ? t("dashboard:workspaceCreating") : t("dashboard:workspaceCreateFromRemote")}
            </button>
          ) : null}
        </>
      )}
      {msg ? <p className="mt-2 text-xs text-surface-muted">{msg}</p> : null}
    </div>
  );
}
