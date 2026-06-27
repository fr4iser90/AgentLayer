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

type AgentImportResult = {
  source_type: string;
  source_type_confidence: number;
  source_count: number;
  sources: Array<{ path: string; chars: number }>;
  agent_draft: {
    target_dir: string;
    agent_yaml: Record<string, unknown>;
    system_prompt_preview: string;
    risk: string;
    notes: string[];
  };
  tool_mapping: {
    matched_existing: Array<{ package_id?: string; domain?: string; tools?: string[]; score?: number }>;
    missing_or_ambiguous: string[];
  };
  config_patches: Array<{ knob_id: string; value: unknown; reason?: string }>;
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
  const [importSourceType, setImportSourceType] = useState("auto");
  const [importText, setImportText] = useState("");
  const [importFiles, setImportFiles] = useState<FileList | null>(null);
  const [importBusy, setImportBusy] = useState(false);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<AgentImportResult | null>(null);

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

  async function analyzeImport() {
    setImportBusy(true);
    setImportMsg(null);
    setImportResult(null);
    try {
      const fd = new FormData();
      fd.set("source_type", importSourceType);
      fd.set("text", importText);
      for (const f of Array.from(importFiles ?? [])) {
        fd.append("files", f, f.name);
      }
      const res = await apiFetch("/v1/admin/agents/import/analyze", auth, {
        method: "POST",
        body: fd,
      });
      const data = (await res.json().catch(() => ({}))) as AgentImportResult & { detail?: unknown };
      if (!res.ok) {
        setImportMsg(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
        return;
      }
      setImportResult(data);
      setImportMsg(t("admin:agentsImportAnalyzed", { sources: data.source_count }));
    } catch (e) {
      setImportMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setImportBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-semibold text-white">{t("admin:agentsTitle")}</h1>
      <p className="mt-2 max-w-3xl text-sm text-surface-muted">{t("admin:agentsIntro")}</p>

      <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised/80 p-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-white">{t("admin:agentsImportTitle")}</h2>
            <p className="mt-1 max-w-3xl text-xs text-surface-muted">{t("admin:agentsImportIntro")}</p>
          </div>
          <label className="sr-only" htmlFor="agents-import-source-type">
            {t("admin:agentsImportSourceType")}
          </label>
          <select
            id="agents-import-source-type"
            className="w-full rounded-md border border-surface-border bg-black/30 px-2 py-1.5 text-xs text-white sm:w-56"
            value={importSourceType}
            onChange={(e) => setImportSourceType(e.target.value)}
          >
            <option value="auto">{t("admin:agentsImportAuto")}</option>
            <option value="openclaw_agent">{t("admin:agentsImportOpenClaw")}</option>
            <option value="hermes_agent">{t("admin:agentsImportHermes")}</option>
            <option value="langgraph_agent">{t("admin:agentsImportLangGraph")}</option>
            <option value="crewai_agent">{t("admin:agentsImportCrewAI")}</option>
            <option value="autogen_agent">{t("admin:agentsImportAutoGen")}</option>
            <option value="generic_agent">{t("admin:agentsImportGeneric")}</option>
          </select>
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs text-surface-muted">
            <span>{t("admin:agentsImportPaste")}</span>
            <textarea
              className="min-h-40 rounded-md border border-surface-border bg-black/30 px-3 py-2 font-mono text-xs text-white placeholder:text-neutral-500"
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder={t("admin:agentsImportPastePlaceholder")}
            />
          </label>
          <div className="rounded-md border border-white/10 bg-black/20 p-3 text-xs text-surface-muted">
            <label className="block">
              <span>{t("admin:agentsImportUpload")}</span>
              <input
                className="mt-2 block w-full text-xs text-neutral-200 file:mr-3 file:rounded-md file:border-0 file:bg-white/10 file:px-3 file:py-1.5 file:text-xs file:text-white hover:file:bg-white/15"
                type="file"
                multiple
                accept=".md,.markdown,.txt,.yaml,.yml,.json,.zip"
                onChange={(e) => setImportFiles(e.target.files)}
              />
            </label>
            <ul className="mt-3 list-disc space-y-1 pl-4 text-[11px]">
              <li>{t("admin:toolsImportAllowed")}</li>
              <li>{t("admin:toolsImportLimits")}</li>
              <li>{t("admin:toolsImportZipSafety")}</li>
              <li>{t("admin:agentsImportAnalyzeOnly")}</li>
            </ul>
            <button
              type="button"
              disabled={importBusy || (!importText.trim() && !(importFiles?.length))}
              className="mt-4 rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              onClick={() => void analyzeImport()}
            >
              {importBusy ? t("admin:agentsImportAnalyzing") : t("admin:agentsImportAnalyze")}
            </button>
          </div>
        </div>

        {importMsg ? <p className="mt-3 text-sm text-surface-muted">{importMsg}</p> : null}
        {importResult ? (
          <div className="mt-4 space-y-3">
            <div className="rounded-md border border-white/10 bg-black/20 p-3 text-xs text-neutral-300">
              {t("admin:toolsImportDetected")}:{" "}
              <span className="font-mono text-white">{importResult.source_type}</span>{" "}
              <span className="text-surface-muted">
                ({Math.round(importResult.source_type_confidence * 100)}%)
              </span>
              <div className="mt-2 flex flex-wrap gap-2">
                {importResult.sources.map((s) => (
                  <span key={s.path} className="rounded bg-white/5 px-2 py-1 font-mono text-[11px]">
                    {s.path} · {t("admin:toolsImportChars", { count: s.chars })}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid gap-3 lg:grid-cols-2">
              <article className="rounded-lg border border-white/10 bg-black/20 p-3 text-xs text-neutral-200">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-semibold text-white">
                    {String(importResult.agent_draft.agent_yaml.id ?? "")}
                  </span>
                  <span className="rounded bg-amber-900/60 px-1.5 py-0.5 text-[10px] text-amber-100">
                    {t("admin:toolsImportRisk", { risk: importResult.agent_draft.risk })}
                  </span>
                </div>
                <p className="mt-2 font-mono text-[11px] text-surface-muted">
                  {importResult.agent_draft.target_dir}
                </p>
                <pre className="mt-3 max-h-56 overflow-auto rounded bg-black/40 p-2 text-[11px] text-neutral-300">
                  {JSON.stringify(importResult.agent_draft.agent_yaml, null, 2)}
                </pre>
              </article>

              <article className="rounded-lg border border-white/10 bg-black/20 p-3 text-xs text-neutral-200">
                <h3 className="text-sm font-semibold text-white">{t("admin:agentsImportSystemPrompt")}</h3>
                <pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap rounded bg-black/40 p-2 text-[11px] text-neutral-300">
                  {importResult.agent_draft.system_prompt_preview || "—"}
                </pre>
              </article>
            </div>

            <div className="grid gap-3 lg:grid-cols-2">
              <article className="rounded-lg border border-white/10 bg-black/20 p-3 text-xs text-neutral-200">
                <h3 className="text-sm font-semibold text-white">{t("admin:agentsImportToolMapping")}</h3>
                <ul className="mt-2 space-y-1">
                  {importResult.tool_mapping.matched_existing.map((m) => (
                    <li key={`${m.package_id}:${m.domain}`} className="font-mono text-[11px] text-neutral-300">
                      {m.package_id} · {m.domain} · {(m.tools ?? []).join(", ")}
                    </li>
                  ))}
                </ul>
                {importResult.tool_mapping.missing_or_ambiguous.length ? (
                  <p className="mt-2 text-[11px] text-amber-200">
                    {t("admin:agentsImportMissingTools")}:{" "}
                    {importResult.tool_mapping.missing_or_ambiguous.join(", ")}
                  </p>
                ) : null}
              </article>

              <article className="rounded-lg border border-white/10 bg-black/20 p-3 text-xs text-neutral-200">
                <h3 className="text-sm font-semibold text-white">{t("admin:agentsImportConfigPatches")}</h3>
                <ul className="mt-2 space-y-2">
                  {importResult.config_patches.map((p) => (
                    <li key={p.knob_id} className="rounded bg-white/5 p-2">
                      <p className="font-mono text-[11px] text-neutral-200">
                        {p.knob_id} = {JSON.stringify(p.value)}
                      </p>
                      {p.reason ? <p className="mt-1 text-[11px] text-surface-muted">{p.reason}</p> : null}
                    </li>
                  ))}
                </ul>
                {importResult.config_patches.length === 0 ? (
                  <p className="mt-2 text-[11px] text-surface-muted">{t("admin:agentsImportNoPatches")}</p>
                ) : null}
              </article>
            </div>
          </div>
        ) : null}
      </section>

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
