import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AuthContextValue } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

export type GithubRepoRow = {
  full_name: string;
  name: string;
  html_url: string;
  clone_url: string;
  default_branch: string;
  description: string;
  private: boolean;
  updated_at?: string | null;
};

type Props = {
  open: boolean;
  onClose: () => void;
  auth: Pick<AuthContextValue, "accessToken" | "refresh">;
  dashboardId: string;
  onImported: (dashboardData: Record<string, unknown>) => void;
};

export function ProjectsImportModal({ open, onClose, auth, dashboardId, onImported }: Props) {
  const { t } = useTranslation(["dashboard", "errors", "admin"]);
  const [repos, setRepos] = useState<GithubRepoRow[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [createWorkspaces, setCreateWorkspaces] = useState(false);
  const [skipExisting, setSkipExisting] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resultMsg, setResultMsg] = useState<string | null>(null);

  const loadRepos = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await apiFetch("/v1/integrations/github/repos?per_page=100", auth);
      const j = (await r.json().catch(() => null)) as {
        ok?: boolean;
        repos?: GithubRepoRow[];
        detail?: string;
      };
      if (!r.ok || !j?.ok) {
        setError(String(j?.detail ?? r.status));
        setRepos([]);
        return;
      }
      setRepos(Array.isArray(j.repos) ? j.repos : []);
    } catch (e) {
      setError(String(e));
      setRepos([]);
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    if (!open) return;
    setSelected({});
    setQuery("");
    setResultMsg(null);
    void loadRepos();
  }, [open, loadRepos]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return repos;
    return repos.filter(
      (r) =>
        r.full_name.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        r.clone_url.toLowerCase().includes(q)
    );
  }, [repos, query]);

  const selectedCount = useMemo(
    () => Object.values(selected).filter(Boolean).length,
    [selected]
  );

  const toggleAllVisible = (on: boolean) => {
    setSelected((prev) => {
      const next = { ...prev };
      for (const r of filtered) next[r.full_name] = on;
      return next;
    });
  };

  const runImport = async () => {
    const picked = repos.filter((r) => selected[r.full_name]);
    if (!picked.length) return;
    setImporting(true);
    setError(null);
    setResultMsg(null);
    try {
      const r = await apiFetch(`/v1/dashboards/${encodeURIComponent(dashboardId)}/import-projects`, auth, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repos: picked,
          create_workspaces: createWorkspaces,
          skip_existing: skipExisting,
        }),
      });
      const j = (await r.json().catch(() => null)) as {
        ok?: boolean;
        added_count?: number;
        skipped_count?: number;
        workspace_errors?: Array<{ repo: string; error: string }>;
        dashboard?: { data?: Record<string, unknown> };
        detail?: string;
      };
      if (!r.ok || !j?.ok) {
        setError(String(j?.detail ?? r.status));
        return;
      }
      const added = Number(j.added_count ?? 0);
      const skipped = Number(j.skipped_count ?? 0);
      setResultMsg(
        t("dashboard:importResult", { added, skipped })
      );
      if (j.dashboard?.data && typeof j.dashboard.data === "object") {
        onImported(j.dashboard.data);
      }
      if (Array.isArray(j.workspace_errors) && j.workspace_errors.length > 0) {
        setError(
          j.workspace_errors.map((e) => `${e.repo}: ${e.error}`).join("; ")
        );
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setImporting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="presentation">
      <div
        className="absolute inset-0 bg-black/70"
        role="button"
        tabIndex={0}
        aria-label={t("dashboard:close")}
        onClick={onClose}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onClose();
          }
        }}
      />
      <div
        role="dialog"
        aria-modal="true"
        className="relative flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-surface-border bg-surface-raised shadow-2xl"
      >
        <div className="border-b border-surface-border px-5 py-4">
          <h2 className="text-lg font-semibold text-white">{t("dashboard:importFromGithub")}</h2>
          <p className="mt-1 text-xs text-surface-muted">{t("dashboard:importFromGithubHint")}</p>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-b border-surface-border px-5 py-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("dashboard:importSearchRepos")}
            className="min-w-[200px] flex-1 rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-sky-500/50"
          />
          <label className="flex items-center gap-2 text-xs text-neutral-200">
            <input
              type="checkbox"
              checked={skipExisting}
              onChange={(e) => setSkipExisting(e.target.checked)}
            />
            {t("dashboard:importSkipExisting")}
          </label>
          <label className="flex items-center gap-2 text-xs text-neutral-200">
            <input
              type="checkbox"
              checked={createWorkspaces}
              onChange={(e) => setCreateWorkspaces(e.target.checked)}
            />
            {t("dashboard:importCreateWorkspaces")}
          </label>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3">
          {loading ? (
            <p className="text-sm text-surface-muted">{t("dashboard:loading")}</p>
          ) : error && repos.length === 0 ? (
            <div className="space-y-2 text-sm">
              <p className="text-red-300">{error}</p>
              <p className="text-surface-muted">{t("dashboard:importGithubTokenHint")}</p>
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-surface-muted">{t("dashboard:importNoRepos")}</p>
          ) : (
            <ul className="space-y-1">
              {filtered.map((r) => (
                <li
                  key={r.full_name}
                  className="flex items-start gap-2 rounded-lg border border-white/5 px-3 py-2 hover:bg-white/[0.03]"
                >
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={!!selected[r.full_name]}
                    onChange={(e) =>
                      setSelected((prev) => ({ ...prev, [r.full_name]: e.target.checked }))
                    }
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-neutral-100">{r.full_name}</div>
                    {r.description ? (
                      <div className="truncate text-xs text-surface-muted">{r.description}</div>
                    ) : null}
                  </div>
                  {r.private ? (
                    <span className="shrink-0 rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-surface-muted">
                      private
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-surface-border px-5 py-4">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-lg border border-surface-border px-3 py-1.5 text-xs text-neutral-200 hover:bg-white/5"
              onClick={() => toggleAllVisible(true)}
            >
              {t("dashboard:importSelectAll")}
            </button>
            <button
              type="button"
              className="rounded-lg border border-surface-border px-3 py-1.5 text-xs text-neutral-200 hover:bg-white/5"
              onClick={() => toggleAllVisible(false)}
            >
              {t("dashboard:importSelectNone")}
            </button>
            <span className="self-center text-xs text-surface-muted">
              {t("dashboard:importSelectedCount", { count: selectedCount })}
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {resultMsg ? <span className="self-center text-xs text-emerald-300">{resultMsg}</span> : null}
            {error && repos.length > 0 ? (
              <span className="self-center text-xs text-amber-300">{error}</span>
            ) : null}
            <button
              type="button"
              className="rounded-lg border border-surface-border px-4 py-2 text-sm text-neutral-200 hover:bg-white/5"
              onClick={onClose}
            >
              {t("admin:cancel")}
            </button>
            <button
              type="button"
              disabled={importing || selectedCount === 0}
              className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              onClick={() => void runImport()}
            >
              {importing ? t("dashboard:importing") : t("dashboard:importRun")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
