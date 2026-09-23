import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { hasOrgSurface } from "../../auth/deploymentMode";
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

/** Lucide-style keys (ascii) → initial badge; legacy emoji icons still render as-is. */
function AgentIcon({ icon, name }: { icon?: string; name: string }): ReactNode {
  const raw = (icon || "").trim();
  const isKey = raw.length > 0 && /^[a-z0-9_-]+$/i.test(raw);
  if (isKey || !raw) {
    return (
      <span
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-card bg-surface-border/60 text-xs font-medium text-ink-muted"
        aria-hidden
        title={isKey ? raw : undefined}
      >
        {(name || "?").slice(0, 1).toUpperCase()}
      </span>
    );
  }
  return (
    <span className="text-lg" aria-hidden>
      {raw}
    </span>
  );
}

type AgentDetail = AgentRow & {
  system_prompt?: string;
  tool_names?: string[];
  effective_tool_names?: string[];
  effective_preview?: { role: string; tenant_id: number; user_id?: string };
  execution_context?: string;
  model_profile?: string | null;
  strict_workspace?: boolean;
  governance?: {
    access: {
      direct_allowed: boolean;
      delegate_allowed: boolean;
      direct_reason: string;
      delegate_reason: string;
      direct_source: string;
      delegate_source: string;
    };
    policies: Array<{
      id: number;
      scope: "global" | "tenant" | "user";
      tenant_id?: number | null;
      user_id?: string | null;
      agent_id: string;
      direct_state: "inherit" | "allow" | "deny";
      delegate_state: "inherit" | "allow" | "deny";
      notes?: string | null;
      updated_at?: string;
    }>;
    prompt: {
      chars: number;
      approx_tokens: number;
      source: string;
      effective_source?: string;
      published_version?: number | null;
      published_version_id?: string | null;
      editable: boolean;
      editing_mode: string;
      note: string;
    };
  };
};

type AgentPromptVersion = {
  id: string;
  tenant_id: number;
  agent_id: string;
  version: number;
  status: "draft" | "published" | "archived";
  prompt_text: string;
  notes?: string | null;
  created_at?: string;
  created_by?: string | null;
  published_at?: string | null;
  published_by?: string | null;
  archived_at?: string | null;
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
  const [previewUserId, setPreviewUserId] = useState("");
  const [policyScope, setPolicyScope] = useState<"global" | "tenant" | "user">("tenant");
  const [policyTenantId, setPolicyTenantId] = useState("");
  const [policyUserId, setPolicyUserId] = useState("");
  // Tenant-scoped access policy is a tenant-selection surface: with no org surface
  // there is one tenant and nothing to scope against. The default scope is
  // "tenant", so it has to be coerced rather than just hidden — a select left on
  // an option it no longer offers renders blank and would still save that value.
  const showTenantScope = hasOrgSurface(auth.user);
  useEffect(() => {
    if (!showTenantScope && policyScope === "tenant") setPolicyScope("global");
  }, [showTenantScope, policyScope]);
  const [directState, setDirectState] = useState<"inherit" | "allow" | "deny">("inherit");
  const [delegateState, setDelegateState] = useState<"inherit" | "allow" | "deny">("inherit");
  const [policyBusy, setPolicyBusy] = useState(false);
  const [policyMsg, setPolicyMsg] = useState<string | null>(null);
  const [promptText, setPromptText] = useState("");
  const [promptVersions, setPromptVersions] = useState<AgentPromptVersion[]>([]);
  const [promptBusy, setPromptBusy] = useState(false);
  const [promptMsg, setPromptMsg] = useState<string | null>(null);
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
        if (previewUserId.trim()) q.set("user_id", previewUserId.trim());
        const res = await apiFetch(`/v1/admin/agents/${encodeURIComponent(agentId)}?${q}`, auth);
        const data = (await res.json()) as AgentDetail;
        if (res.ok) setDetail(data);
      } finally {
        setDetailLoading(false);
      }
    },
    [auth, previewUserId],
  );

  const loadPromptVersions = useCallback(
    async (agentId: string) => {
      try {
        const res = await apiFetch(`/v1/admin/agents/${encodeURIComponent(agentId)}/prompt-versions`, auth);
        const data = (await res.json()) as { versions?: AgentPromptVersion[] };
        if (res.ok) setPromptVersions(data.versions ?? []);
      } catch {
        setPromptVersions([]);
      }
    },
    [auth],
  );

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (selectedId) void loadDetail(selectedId, previewRole);
  }, [selectedId, previewRole, previewUserId, loadDetail]);

  useEffect(() => {
    if (selectedId) void loadPromptVersions(selectedId);
  }, [selectedId, loadPromptVersions]);

  useEffect(() => {
    setPromptText(detail?.system_prompt ?? "");
  }, [detail?.system_prompt, selectedId]);

  const selected = useMemo(
    () => agents.find((a) => a.id === selectedId) ?? null,
    [agents, selectedId],
  );

  async function saveAccessPolicy() {
    if (!selectedId) return;
    setPolicyBusy(true);
    setPolicyMsg(null);
    try {
      const body: Record<string, unknown> = {
        scope: policyScope,
        direct_state: directState,
        delegate_state: delegateState,
      };
      if (policyTenantId.trim()) body.tenant_id = Number(policyTenantId.trim());
      if (policyUserId.trim()) body.user_id = policyUserId.trim();
      const res = await apiFetch(`/v1/admin/agents/${encodeURIComponent(selectedId)}/access-policy`, auth, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setPolicyMsg(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
        return;
      }
      setPolicyMsg(t("admin:agentsPolicySaved"));
      await loadDetail(selectedId, previewRole);
    } catch (e) {
      setPolicyMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setPolicyBusy(false);
    }
  }

  async function deleteAccessPolicy() {
    if (!selectedId) return;
    setPolicyBusy(true);
    setPolicyMsg(null);
    try {
      const q = new URLSearchParams({ scope: policyScope });
      if (policyTenantId.trim()) q.set("tenant_id", policyTenantId.trim());
      if (policyUserId.trim()) q.set("user_id", policyUserId.trim());
      const res = await apiFetch(
        `/v1/admin/agents/${encodeURIComponent(selectedId)}/access-policy?${q}`,
        auth,
        { method: "DELETE" },
      );
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setPolicyMsg(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
        return;
      }
      setPolicyMsg(t("admin:agentsPolicyDeleted"));
      await loadDetail(selectedId, previewRole);
    } catch (e) {
      setPolicyMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setPolicyBusy(false);
    }
  }

  async function savePromptDraft() {
    if (!selectedId) return;
    setPromptBusy(true);
    setPromptMsg(null);
    try {
      const res = await apiFetch(`/v1/admin/agents/${encodeURIComponent(selectedId)}/prompt-drafts`, auth, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt_text: promptText }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setPromptMsg(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
        return;
      }
      setPromptMsg(t("admin:agentsPromptDraftSaved"));
      await loadPromptVersions(selectedId);
    } catch (e) {
      setPromptMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setPromptBusy(false);
    }
  }

  async function publishPromptVersion(versionId: string) {
    if (!selectedId) return;
    setPromptBusy(true);
    setPromptMsg(null);
    try {
      const res = await apiFetch(
        `/v1/admin/agents/${encodeURIComponent(selectedId)}/prompt-versions/${encodeURIComponent(versionId)}/publish`,
        auth,
        { method: "POST" },
      );
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setPromptMsg(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
        return;
      }
      setPromptMsg(t("admin:agentsPromptPublished"));
      await loadPromptVersions(selectedId);
      await loadDetail(selectedId, previewRole);
    } catch (e) {
      setPromptMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setPromptBusy(false);
    }
  }

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
    <div className="mx-auto max-w-6xl px-wide py-deep sm:px-broad">
      <h1 className="text-2xl font-semibold text-ink-primary">{t("admin:agentsTitle")}</h1>
      <p className="mt-base max-w-3xl text-sm text-ink-muted">{t("admin:agentsIntro")}</p>

      <section className="mt-broad rounded-sheet border border-line bg-card p-wide">
        <div className="flex flex-col gap-base sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-ink-primary">{t("admin:agentsImportTitle")}</h2>
            <p className="mt-tight max-w-3xl text-xs text-ink-muted">{t("admin:agentsImportIntro")}</p>
          </div>
          <label className="sr-only" htmlFor="agents-import-source-type">
            {t("admin:agentsImportSourceType")}
          </label>
          <select
            id="agents-import-source-type"
            className="w-full rounded-tile border border-line bg-field px-base py-snug text-xs text-ink-primary sm:w-56"
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

        <div className="mt-wide grid gap-soft lg:grid-cols-2">
          <label className="flex flex-col gap-tight text-xs text-ink-muted">
            <span>{t("admin:agentsImportPaste")}</span>
            <textarea
              className="min-h-40 rounded-tile border border-line bg-field px-soft py-base font-mono text-xs text-ink-primary placeholder:text-neutral-500"
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder={t("admin:agentsImportPastePlaceholder")}
            />
          </label>
          <div className="rounded-tile border border-line bg-black/20 p-soft text-xs text-ink-muted">
            <label className="block">
              <span>{t("admin:agentsImportUpload")}</span>
              <input
                className="mt-base block w-full text-xs text-ink-primary file:mr-soft file:rounded-tile file:border-0 file:bg-white/10 file:px-soft file:py-snug file:text-xs file:text-white hover:file:bg-white/15"
                type="file"
                multiple
                accept=".md,.markdown,.txt,.yaml,.yml,.json,.zip"
                onChange={(e) => setImportFiles(e.target.files)}
              />
            </label>
            <ul className="mt-soft list-disc space-y-tight pl-wide text-meta">
              <li>{t("admin:toolsImportAllowed")}</li>
              <li>{t("admin:toolsImportLimits")}</li>
              <li>{t("admin:toolsImportZipSafety")}</li>
              <li>{t("admin:agentsImportAnalyzeOnly")}</li>
            </ul>
            <button
              type="button"
              disabled={importBusy || (!importText.trim() && !(importFiles?.length))}
              className="mt-wide rounded-tile bg-sky-600 px-wide py-base text-sm font-medium text-ink-on-fill hover:bg-sky-500 disabled:opacity-50"
              onClick={() => void analyzeImport()}
            >
              {importBusy ? t("admin:agentsImportAnalyzing") : t("admin:agentsImportAnalyze")}
            </button>
          </div>
        </div>

        {importMsg ? <p className="mt-soft text-sm text-ink-muted">{importMsg}</p> : null}
        {importResult ? (
          <div className="mt-wide space-y-soft">
            <div className="rounded-tile border border-line bg-black/20 p-soft text-xs text-ink-secondary">
              {t("admin:toolsImportDetected")}:{" "}
              <span className="font-mono text-ink-primary">{importResult.source_type}</span>{" "}
              <span className="text-ink-muted">
                ({Math.round(importResult.source_type_confidence * 100)}%)
              </span>
              <div className="mt-base flex flex-wrap gap-base">
                {importResult.sources.map((s) => (
                  <span key={s.path} className="rounded-tile bg-white/5 px-base py-tight font-mono text-meta">
                    {s.path} · {t("admin:toolsImportChars", { count: s.chars })}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid gap-soft lg:grid-cols-2">
              <article className="rounded-card border border-line bg-black/20 p-soft text-xs text-ink-primary">
                <div className="flex flex-wrap items-center gap-base">
                  <span className="font-mono text-sm font-semibold text-ink-primary">
                    {String(importResult.agent_draft.agent_yaml.id ?? "")}
                  </span>
                  <span className="rounded-tile bg-amber-900/60 px-snug py-hair text-meta text-amber-100">
                    {t("admin:toolsImportRisk", { risk: importResult.agent_draft.risk })}
                  </span>
                </div>
                <p className="mt-base font-mono text-meta text-ink-muted">
                  {importResult.agent_draft.target_dir}
                </p>
                <pre className="mt-soft max-h-56 overflow-auto rounded-tile bg-black/40 p-base text-meta text-ink-secondary">
                  {JSON.stringify(importResult.agent_draft.agent_yaml, null, 2)}
                </pre>
              </article>

              <article className="rounded-card border border-line bg-black/20 p-soft text-xs text-ink-primary">
                <h3 className="text-sm font-semibold text-ink-primary">{t("admin:agentsImportSystemPrompt")}</h3>
                <pre className="mt-soft max-h-56 overflow-auto whitespace-pre-wrap rounded-tile bg-black/40 p-base text-meta text-ink-secondary">
                  {importResult.agent_draft.system_prompt_preview || "—"}
                </pre>
              </article>
            </div>

            <div className="grid gap-soft lg:grid-cols-2">
              <article className="rounded-card border border-line bg-black/20 p-soft text-xs text-ink-primary">
                <h3 className="text-sm font-semibold text-ink-primary">{t("admin:agentsImportToolMapping")}</h3>
                <ul className="mt-base space-y-tight">
                  {importResult.tool_mapping.matched_existing.map((m) => (
                    <li key={`${m.package_id}:${m.domain}`} className="font-mono text-meta text-ink-secondary">
                      {m.package_id} · {m.domain} · {(m.tools ?? []).join(", ")}
                    </li>
                  ))}
                </ul>
                {importResult.tool_mapping.missing_or_ambiguous.length ? (
                  <p className="mt-base text-meta text-amber-200">
                    {t("admin:agentsImportMissingTools")}:{" "}
                    {importResult.tool_mapping.missing_or_ambiguous.join(", ")}
                  </p>
                ) : null}
              </article>

              <article className="rounded-card border border-line bg-black/20 p-soft text-xs text-ink-primary">
                <h3 className="text-sm font-semibold text-ink-primary">{t("admin:agentsImportConfigPatches")}</h3>
                <ul className="mt-base space-y-base">
                  {importResult.config_patches.map((p) => (
                    <li key={p.knob_id} className="rounded-tile bg-white/5 p-base">
                      <p className="font-mono text-meta text-ink-primary">
                        {p.knob_id} = {JSON.stringify(p.value)}
                      </p>
                      {p.reason ? <p className="mt-tight text-meta text-ink-muted">{p.reason}</p> : null}
                    </li>
                  ))}
                </ul>
                {importResult.config_patches.length === 0 ? (
                  <p className="mt-base text-meta text-ink-muted">{t("admin:agentsImportNoPatches")}</p>
                ) : null}
              </article>
            </div>
          </div>
        ) : null}
      </section>

      <div className="mt-wide flex flex-wrap gap-base">
        <button
          type="button"
          className="rounded-tile bg-sky-600 px-wide py-base text-sm font-medium text-ink-on-fill hover:bg-sky-500"
          onClick={() => void loadList()}
        >
          {t("admin:agentsRefresh")}
        </button>
        <Link
          to="/admin/tools"
          className="rounded-tile bg-white/10 px-wide py-base text-sm font-medium text-ink-primary hover:bg-white/15"
        >
          {t("admin:agentsOpenTools")}
        </Link>
      </div>

      {msg ? <p className="mt-wide text-sm text-amber-300">{msg}</p> : null}
      {loading ? <p className="mt-broad text-sm text-ink-muted">{t("admin:agentsLoading")}</p> : null}

      {!loading && agents.length === 0 ? (
        <p className="mt-broad text-sm text-ink-muted">{t("admin:agentsNone")}</p>
      ) : null}

      {!loading && agents.length > 0 ? (
        <div className="mt-broad grid gap-wide lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          <ul className="space-y-base">
            {agents.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(a.id)}
                  className={`w-full rounded-sheet border px-soft py-soft text-left transition-colors ${
                    selectedId === a.id
                      ? "border-sky-500/40 bg-sky-950/20"
                      : "border-line bg-card hover:border-line-strong"
                  }`}
                >
                  <div className="flex items-start gap-base">
                    <AgentIcon icon={a.icon} name={a.name} />
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-ink-primary">
                        {a.name}{" "}
                        <span className="font-mono text-xs text-ink-muted">({a.id})</span>
                      </p>
                      <p className="mt-tight text-xs text-ink-muted">
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
            <div className="rounded-sheet border border-line bg-card p-wide">
              <h2 className="flex items-center gap-base text-lg font-semibold text-ink-primary">
                <AgentIcon icon={selected.icon} name={selected.name} />
                {selected.name}
              </h2>
              <p className="mt-tight text-sm text-ink-muted">{selected.description}</p>

              <dl className="mt-wide grid gap-base text-xs sm:grid-cols-2">
                <div>
                  <dt className="text-ink-muted">{t("admin:agentsSource")}</dt>
                  <dd className="font-mono text-ink-primary">
                    {detail?.source_path ?? selected.source_path ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-muted">{t("admin:agentsDiscipline")}</dt>
                  <dd className="text-ink-primary">{detail?.tool_discipline_preset ?? "—"}</dd>
                </div>
              </dl>

              <div className="mt-wide">
                <p className="text-meta font-medium uppercase tracking-wide text-ink-muted">
                  {t("admin:agentsToolDomains")}
                </p>
                <p className="mt-tight font-mono text-xs text-ink-secondary">
                  {(detail?.tool_domains ?? selected.tool_domains).join(", ") || "—"}
                </p>
              </div>

              <div className="mt-soft">
                <p className="text-meta font-medium uppercase tracking-wide text-ink-muted">
                  {t("admin:agentsToolCapabilities")}
                </p>
                <p className="mt-tight font-mono text-xs text-ink-secondary">
                  {(detail?.tool_capability_any ?? selected.tool_capability_any).join(", ") || "—"}
                </p>
              </div>

              <div className="mt-wide flex flex-wrap items-center gap-base">
                <label className="text-xs text-ink-muted">{t("admin:agentsEffectivePreview")}</label>
                <select
                  className="rounded-tile border border-line bg-field px-base py-tight text-xs text-ink-primary"
                  value={previewRole}
                  onChange={(e) => setPreviewRole(e.target.value as "admin" | "user")}
                >
                  <option value="admin">{t("admin:toolsMinRoleAdmin")}</option>
                  <option value="user">{t("admin:toolsMinRoleUser")}</option>
                </select>
                <input
                  className="w-72 rounded-tile border border-line bg-field px-base py-tight text-xs text-ink-primary placeholder:text-neutral-500"
                  value={previewUserId}
                  onChange={(e) => setPreviewUserId(e.target.value)}
                  placeholder={t("admin:agentsPreviewUserIdPlaceholder")}
                />
              </div>

              {detailLoading ? (
                <p className="mt-soft text-xs text-ink-muted">{t("admin:agentsLoadingDetail")}</p>
              ) : (
                <>
                  <div className="mt-wide rounded-card border border-line bg-black/20 p-soft">
                    <div className="flex flex-wrap items-start justify-between gap-soft">
                      <div>
                        <p className="text-meta font-medium uppercase tracking-wide text-ink-muted">
                          {t("admin:agentsAccessGovernance")}
                        </p>
                        <p className="mt-tight text-xs text-ink-secondary">
                          {t("admin:agentsDirectAccess")}:{" "}
                          <span className={detail?.governance?.access.direct_allowed ? "text-emerald-300" : "text-rose-300"}>
                            {detail?.governance?.access.direct_allowed ? t("admin:agentsAllowed") : t("admin:agentsDenied")}
                          </span>{" "}
                          <span className="text-ink-muted">
                            ({detail?.governance?.access.direct_source ?? "—"})
                          </span>
                        </p>
                        <p className="mt-tight text-xs text-ink-secondary">
                          {t("admin:agentsDelegateAccess")}:{" "}
                          <span className={detail?.governance?.access.delegate_allowed ? "text-emerald-300" : "text-rose-300"}>
                            {detail?.governance?.access.delegate_allowed ? t("admin:agentsAllowed") : t("admin:agentsDenied")}
                          </span>{" "}
                          <span className="text-ink-muted">
                            ({detail?.governance?.access.delegate_source ?? "—"})
                          </span>
                        </p>
                      </div>
                      <div className="min-w-64 flex-1">
                        <p className="text-meta font-medium uppercase tracking-wide text-ink-muted">
                          {t("admin:agentsPromptBudget")}
                        </p>
                        <p className="mt-tight text-xs text-ink-secondary">
                          {detail?.governance?.prompt.chars ?? 0} {t("admin:agentsChars")} · ~
                          {detail?.governance?.prompt.approx_tokens ?? 0} {t("admin:agentsTokens")}
                        </p>
                        <p className="mt-tight text-meta text-ink-muted">
                          {detail?.governance?.prompt.note ?? "—"}
                        </p>
                      </div>
                    </div>

                    <div className="mt-wide grid gap-base md:grid-cols-5">
                      <label className="text-xs text-ink-muted">
                        {t("admin:agentsPolicyScope")}
                        <select
                          className="mt-tight w-full rounded-tile border border-line bg-field px-base py-tight text-xs text-ink-primary"
                          value={policyScope}
                          onChange={(e) => setPolicyScope(e.target.value as "global" | "tenant" | "user")}
                        >
                          <option value="global">{t("admin:agentsScopeGlobal")}</option>
                          {showTenantScope ? (
                            <option value="tenant">{t("admin:agentsScopeTenant")}</option>
                          ) : null}
                          <option value="user">{t("admin:agentsScopeUser")}</option>
                        </select>
                      </label>
                      {showTenantScope ? (
                        <label className="text-xs text-ink-muted">
                          {t("admin:agentsTenantId")}
                          <input
                            className="mt-tight w-full rounded-tile border border-line bg-field px-base py-tight text-xs text-ink-primary placeholder:text-neutral-500"
                            value={policyTenantId}
                            onChange={(e) => setPolicyTenantId(e.target.value)}
                            placeholder={t("admin:agentsTenantIdPlaceholder")}
                          />
                        </label>
                      ) : null}
                      <label className="text-xs text-ink-muted">
                        {t("admin:agentsUserId")}
                        <input
                          className="mt-tight w-full rounded-tile border border-line bg-field px-base py-tight text-xs text-ink-primary placeholder:text-neutral-500"
                          value={policyUserId}
                          onChange={(e) => setPolicyUserId(e.target.value)}
                          placeholder={t("admin:agentsUserIdPlaceholder")}
                        />
                      </label>
                      <label className="text-xs text-ink-muted">
                        {t("admin:agentsDirectAccess")}
                        <select
                          className="mt-tight w-full rounded-tile border border-line bg-field px-base py-tight text-xs text-ink-primary"
                          value={directState}
                          onChange={(e) => setDirectState(e.target.value as "inherit" | "allow" | "deny")}
                        >
                          <option value="inherit">{t("admin:agentsInherit")}</option>
                          <option value="allow">{t("admin:agentsAllow")}</option>
                          <option value="deny">{t("admin:agentsDeny")}</option>
                        </select>
                      </label>
                      <label className="text-xs text-ink-muted">
                        {t("admin:agentsDelegateAccess")}
                        <select
                          className="mt-tight w-full rounded-tile border border-line bg-field px-base py-tight text-xs text-ink-primary"
                          value={delegateState}
                          onChange={(e) => setDelegateState(e.target.value as "inherit" | "allow" | "deny")}
                        >
                          <option value="inherit">{t("admin:agentsInherit")}</option>
                          <option value="allow">{t("admin:agentsAllow")}</option>
                          <option value="deny">{t("admin:agentsDeny")}</option>
                        </select>
                      </label>
                    </div>
                    <div className="mt-soft flex flex-wrap items-center gap-base">
                      <button
                        type="button"
                        disabled={policyBusy}
                        className="rounded-tile bg-sky-600 px-soft py-snug text-xs font-medium text-ink-on-fill hover:bg-sky-500 disabled:opacity-50"
                        onClick={() => void saveAccessPolicy()}
                      >
                        {t("admin:agentsSavePolicy")}
                      </button>
                      <button
                        type="button"
                        disabled={policyBusy}
                        className="rounded-tile bg-white/10 px-soft py-snug text-xs font-medium text-ink-primary hover:bg-white/15 disabled:opacity-50"
                        onClick={() => void deleteAccessPolicy()}
                      >
                        {t("admin:agentsDeletePolicy")}
                      </button>
                      {policyMsg ? <span className="text-xs text-ink-muted">{policyMsg}</span> : null}
                    </div>
                    <div className="mt-soft">
                      <p className="text-meta font-medium uppercase tracking-wide text-ink-muted">
                        {t("admin:agentsActivePolicies")}
                      </p>
                      <div className="mt-tight space-y-tight">
                        {(detail?.governance?.policies ?? []).length === 0 ? (
                          <p className="text-xs text-ink-muted">—</p>
                        ) : (
                          (detail?.governance?.policies ?? []).map((p) => (
                            <p key={p.id} className="font-mono text-meta text-ink-secondary">
                              {p.scope} {p.tenant_id ?? ""} {p.user_id ?? ""} · direct={p.direct_state} · delegate=
                              {p.delegate_state}
                            </p>
                          ))
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="mt-wide rounded-card border border-line bg-black/20 p-soft">
                    <div className="flex flex-wrap items-start justify-between gap-soft">
                      <div>
                        <p className="text-meta font-medium uppercase tracking-wide text-ink-muted">
                          {t("admin:agentsPromptEditor")}
                        </p>
                        <p className="mt-tight text-xs text-ink-muted">
                          {t("admin:agentsPromptEditorHint")}
                        </p>
                      </div>
                      <p className="font-mono text-meta text-ink-muted">
                        {t("admin:agentsPromptSource")}: {detail?.governance?.prompt.effective_source ?? "file_default"}
                        {detail?.governance?.prompt.published_version
                          ? ` · v${detail.governance.prompt.published_version}`
                          : ""}
                      </p>
                    </div>
                    <textarea
                      className="mt-soft min-h-52 w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-xs text-ink-primary placeholder:text-neutral-500"
                      value={promptText}
                      onChange={(e) => setPromptText(e.target.value)}
                      maxLength={12000}
                    />
                    <div className="mt-base flex flex-wrap items-center justify-between gap-base">
                      <p className="text-meta text-ink-muted">
                        {promptText.length} / 12000 {t("admin:agentsChars")} · ~{Math.max(1, Math.floor(promptText.length / 4))}{" "}
                        {t("admin:agentsTokens")}
                      </p>
                      <div className="flex flex-wrap items-center gap-base">
                        <button
                          type="button"
                          disabled={promptBusy || !promptText.trim()}
                          className="rounded-tile bg-sky-600 px-soft py-snug text-xs font-medium text-ink-on-fill hover:bg-sky-500 disabled:opacity-50"
                          onClick={() => void savePromptDraft()}
                        >
                          {t("admin:agentsSavePromptDraft")}
                        </button>
                        {promptMsg ? <span className="text-xs text-ink-muted">{promptMsg}</span> : null}
                      </div>
                    </div>
                    <div className="mt-wide">
                      <p className="text-meta font-medium uppercase tracking-wide text-ink-muted">
                        {t("admin:agentsPromptVersions")}
                      </p>
                      <div className="mt-base space-y-base">
                        {promptVersions.length === 0 ? (
                          <p className="text-xs text-ink-muted">—</p>
                        ) : (
                          promptVersions.map((v) => (
                            <div
                              key={v.id}
                              className="flex flex-wrap items-center justify-between gap-base rounded-tile border border-line bg-white/[0.03] px-base py-base"
                            >
                              <div>
                                <p className="font-mono text-xs text-ink-primary">
                                  v{v.version} · {v.status} · {v.prompt_text.length} {t("admin:agentsChars")}
                                </p>
                                <p className="mt-hair text-meta text-ink-muted">
                                  {v.created_at ?? "—"}
                                  {v.published_at ? ` · ${t("admin:agentsPublishedAt")} ${v.published_at}` : ""}
                                </p>
                              </div>
                              <button
                                type="button"
                                disabled={promptBusy || v.status === "published"}
                                className="rounded-tile bg-white/10 px-soft py-snug text-xs font-medium text-ink-primary hover:bg-white/15 disabled:opacity-50"
                                onClick={() => void publishPromptVersion(v.id)}
                              >
                                {t("admin:agentsPublishPrompt")}
                              </button>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="mt-soft">
                    <p className="text-meta font-medium uppercase tracking-wide text-ink-muted">
                      {t("admin:agentsResolvedTools")} ({detail?.tool_names?.length ?? 0})
                    </p>
                    <p className="mt-tight max-h-32 overflow-y-auto break-all font-mono text-meta text-ink-muted">
                      {(detail?.tool_names ?? []).join(", ") || "—"}
                    </p>
                  </div>
                  <div className="mt-soft">
                    <p className="text-meta font-medium uppercase tracking-wide text-ink-muted">
                      {t("admin:agentsEffectiveTools")} ({detail?.effective_tool_names?.length ?? 0})
                    </p>
                    <p className="mt-tight max-h-32 overflow-y-auto break-all font-mono text-meta text-emerald-300/90">
                      {(detail?.effective_tool_names ?? []).join(", ") || "—"}
                    </p>
                  </div>
                </>
              )}

              <p className="mt-wide text-xs text-ink-muted">{t("admin:agentsEditHint")}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
