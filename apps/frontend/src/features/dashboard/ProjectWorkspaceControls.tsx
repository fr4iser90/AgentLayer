import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { hasOrgSurface } from "../../auth/deploymentMode";
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
  const { t } = useTranslation(["dashboard", "errors", "workspace"]);
  const { user } = useAuth();
  const [workspaces, setWorkspaces] = useState<WorkspaceApiRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [shareWithCompany, setShareWithCompany] = useState(false);
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
          visibility: shareWithCompany ? "tenant" : "private",
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
    <div className="mb-wide rounded-sheet border border-line bg-black/15 p-soft">
      <div className="mb-base text-xs font-medium uppercase tracking-wide text-ink-muted">
        {t("dashboard:linkedWorkspace")}
      </div>
      {loading ? (
        <p className="text-xs text-ink-muted">{t("dashboard:loading")}</p>
      ) : (
        <>
          <label className="mb-base block text-meta text-ink-muted">
            {t("dashboard:workspacePickerLabel")}
            <select
              value={workspaceId}
              disabled={readOnly}
              onChange={(e) => linkExisting(e.target.value)}
              className="mt-tight w-full rounded-card border border-line bg-field px-soft py-snug text-xs text-ink-primary outline-none focus:border-violet-400/60 disabled:opacity-70"
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
            <p className="mb-base truncate font-mono text-meta text-ink-muted">{matched.path}</p>
          ) : workspaceId ? (
            <p className="mb-base text-meta text-badge-warning">{t("dashboard:workspaceNotFound")}</p>
          ) : null}
          {!readOnly && remote ? (
            <>
              {hasOrgSurface(user) ? (
                <label className="mb-base flex items-start gap-base text-meta text-ink-muted">
                  <input
                    type="checkbox"
                    className="mt-hair"
                    checked={shareWithCompany}
                    onChange={(e) => setShareWithCompany(e.target.checked)}
                  />
                  <span>{t("workspace:createShareWithCompany")}</span>
                </label>
              ) : null}
              <button
                type="button"
                disabled={creating}
                onClick={() => void createFromRemote()}
                className="rounded-tile border border-violet-500/40 bg-violet-950/30 px-soft py-snug text-xs text-violet-100 hover:bg-violet-900/40 disabled:opacity-60"
              >
                {creating ? t("dashboard:workspaceCreating") : t("dashboard:workspaceCreateFromRemote")}
              </button>
            </>
          ) : null}
        </>
      )}
      {msg ? <p className="mt-base text-xs text-ink-muted">{msg}</p> : null}
    </div>
  );
}
