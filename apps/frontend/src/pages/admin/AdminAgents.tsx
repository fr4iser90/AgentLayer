import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

type AgentRow = {
  id: string;
  name: string;
  icon: string;
  description: string;
  min_role: string;
  requires_workspace: boolean;
  tool_domains: string[];
  tool_capability_any: string[];
  tool_names_count: number;
  source_kind?: string;
  source_path?: string | null;
  tool_discipline_preset?: string | null;
};

type AgentDetail = AgentRow & {
  system_prompt?: string;
  tool_names?: string[];
  effective_tool_names?: string[];
  effective_preview?: { role: string; tenant_id: number };
  execution_context?: string;
  model_profile?: string | null;
  strict_workspace?: boolean;
};

export function AdminAgents() {
  const { t } = useTranslation(["admin"]);
  const auth = useAuth();
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AgentDetail | null>(null);
  const [previewRole, setPreviewRole] = useState<"admin" | "user">("admin");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const res = await apiFetch("/v1/admin/agents", auth);
      const data = (await res.json()) as { agents?: AgentRow[] };
      if (!res.ok) {
        setMsg(t("admin:agentsLoadFailed"));
        return;
      }
      const list = data.agents ?? [];
      setAgents(list);
      if (!selectedId && list.length) setSelectedId(list[0].id);
    } catch {
      setMsg(t("admin:agentsLoadFailed"));
    } finally {
      setLoading(false);
    }
  }, [auth, t]);

  const loadDetail = useCallback(
    async (agentId: string, role: "admin" | "user") => {
      setDetailLoading(true);
      try {
        const q = new URLSearchParams({ role });
        const res = await apiFetch(`/v1/admin/agents/${encodeURIComponent(agentId)}?${q}`, auth);
        const data = (await res.json()) as AgentDetail;
        if (res.ok) setDetail(data);
      } finally {
        setDetailLoading(false);
      }
    },
    [auth],
  );

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (selectedId) void loadDetail(selectedId, previewRole);
  }, [selectedId, previewRole, loadDetail]);

  const selected = useMemo(
    () => agents.find((a) => a.id === selectedId) ?? null,
    [agents, selectedId],
  );

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-semibold text-white">{t("admin:agentsTitle")}</h1>
      <p className="mt-2 max-w-3xl text-sm text-surface-muted">{t("admin:agentsIntro")}</p>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
          onClick={() => void loadList()}
        >
          {t("admin:agentsRefresh")}
        </button>
        <Link
          to="/admin/tools"
          className="rounded-md bg-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/15"
        >
          {t("admin:agentsOpenTools")}
        </Link>
      </div>

      {msg ? <p className="mt-4 text-sm text-amber-300">{msg}</p> : null}
      {loading ? <p className="mt-6 text-sm text-surface-muted">{t("admin:agentsLoading")}</p> : null}

      {!loading && agents.length === 0 ? (
        <p className="mt-6 text-sm text-surface-muted">{t("admin:agentsNone")}</p>
      ) : null}

      {!loading && agents.length > 0 ? (
        <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          <ul className="space-y-2">
            {agents.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(a.id)}
                  className={`w-full rounded-xl border px-3 py-3 text-left transition-colors ${
                    selectedId === a.id
                      ? "border-sky-500/40 bg-sky-950/20"
                      : "border-surface-border bg-surface-raised/60 hover:border-white/15"
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <span className="text-lg" aria-hidden>
                      {a.icon}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-white">
                        {a.name}{" "}
                        <span className="font-mono text-xs text-surface-muted">({a.id})</span>
                      </p>
                      <p className="mt-1 text-xs text-surface-muted">
                        {t("admin:agentsToolsCount", { count: a.tool_names_count })} ·{" "}
                        {t("admin:agentsMinRole", { role: a.min_role })}
                      </p>
                    </div>
                  </div>
                </button>
              </li>
            ))}
          </ul>

          {selected ? (
            <div className="rounded-xl border border-surface-border bg-surface-raised/50 p-4">
              <h2 className="text-lg font-semibold text-white">
                {selected.icon} {selected.name}
              </h2>
              <p className="mt-1 text-sm text-surface-muted">{selected.description}</p>

              <dl className="mt-4 grid gap-2 text-xs sm:grid-cols-2">
                <div>
                  <dt className="text-surface-muted">{t("admin:agentsSource")}</dt>
                  <dd className="font-mono text-neutral-200">
                    {detail?.source_path ?? selected.source_path ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-surface-muted">{t("admin:agentsDiscipline")}</dt>
                  <dd className="text-neutral-200">{detail?.tool_discipline_preset ?? "—"}</dd>
                </div>
              </dl>

              <div className="mt-4">
                <p className="text-[11px] font-medium uppercase tracking-wide text-surface-muted">
                  {t("admin:agentsToolDomains")}
                </p>
                <p className="mt-1 font-mono text-xs text-neutral-300">
                  {(detail?.tool_domains ?? selected.tool_domains).join(", ") || "—"}
                </p>
              </div>

              <div className="mt-3">
                <p className="text-[11px] font-medium uppercase tracking-wide text-surface-muted">
                  {t("admin:agentsToolCapabilities")}
                </p>
                <p className="mt-1 font-mono text-xs text-neutral-300">
                  {(detail?.tool_capability_any ?? selected.tool_capability_any).join(", ") || "—"}
                </p>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                <label className="text-xs text-surface-muted">{t("admin:agentsEffectivePreview")}</label>
                <select
                  className="rounded border border-surface-border bg-black/30 px-2 py-1 text-xs text-white"
                  value={previewRole}
                  onChange={(e) => setPreviewRole(e.target.value as "admin" | "user")}
                >
                  <option value="admin">{t("admin:toolsMinRoleAdmin")}</option>
                  <option value="user">{t("admin:toolsMinRoleUser")}</option>
                </select>
              </div>

              {detailLoading ? (
                <p className="mt-3 text-xs text-surface-muted">{t("admin:agentsLoadingDetail")}</p>
              ) : (
                <>
                  <div className="mt-3">
                    <p className="text-[11px] font-medium uppercase tracking-wide text-surface-muted">
                      {t("admin:agentsResolvedTools")} ({detail?.tool_names?.length ?? 0})
                    </p>
                    <p className="mt-1 max-h-32 overflow-y-auto break-all font-mono text-[11px] text-neutral-400">
                      {(detail?.tool_names ?? []).join(", ") || "—"}
                    </p>
                  </div>
                  <div className="mt-3">
                    <p className="text-[11px] font-medium uppercase tracking-wide text-surface-muted">
                      {t("admin:agentsEffectiveTools")} ({detail?.effective_tool_names?.length ?? 0})
                    </p>
                    <p className="mt-1 max-h-32 overflow-y-auto break-all font-mono text-[11px] text-emerald-300/90">
                      {(detail?.effective_tool_names ?? []).join(", ") || "—"}
                    </p>
                  </div>
                </>
              )}

              <p className="mt-4 text-xs text-surface-muted">{t("admin:agentsEditHint")}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
