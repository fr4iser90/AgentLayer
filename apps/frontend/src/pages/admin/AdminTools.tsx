import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import { Badge, type BadgeTone } from "../../ui/Badge";

type ToolMeta = {
  id?: string;
  version?: string;
  source?: string;
  tools?: string[];
  tags?: string[];
  capabilities?: string[];
  secrets_required?: string[];
  requires?: string[];
  min_role?: string;
  allowed_tenant_ids?: number[] | null;
  families?: string[];
  domain?: string;
  admin_bucket?: string;
  admin_tags?: string[];
  execution_context?: string;
  os_support?: string[];
  risk_level?: string;
  tool_effective?: Record<
    string,
    {
      enabled: boolean;
      min_role: string;
      allowed_tenant_ids?: number[] | null;
      execution_context?: string;
    }
  >;
  policy_row?: {
    enabled?: boolean;
    min_role?: string;
    allowed_tenant_ids?: number[] | null;
    execution_context?: string | null;
  };
};

type PolicyRow = {
  package_id: string;
  tool_name: string;
  enabled: boolean;
  min_role: "user" | "admin";
  allowed_tenant_ids: number[] | null;
  execution_context: string | null;
};

type ImportCandidate = {
  kind: string;
  name: string;
  title: string;
  summary?: string;
  confidence?: number;
  risk?: string;
  source_paths?: string[];
  target_dir?: string;
  inputs_schema?: unknown;
  side_effects?: Record<string, unknown>;
  determinism_notes?: string[];
};

type ImportAnalyzeResult = {
  source_type: string;
  source_type_confidence: number;
  source_count: number;
  sources: Array<{ path: string; chars: number }>;
  candidates: ImportCandidate[];
};

function parseTenantIdsInput(s: string): number[] | null {
  const trimmed = s.trim();
  if (!trimmed) return null;
  const ids = [
    ...new Set(
      trimmed
        .split(/[\s,;]+/)
        .filter(Boolean)
        .map((p) => parseInt(p, 10))
        .filter((n) => Number.isFinite(n) && n >= 1),
    ),
  ].sort((a, b) => a - b);
  return ids.length ? ids : null;
}

function formatTenantIds(t: number[] | null | undefined): string {
  if (!t?.length) return "";
  return t.join(", ");
}

function sortPackagesById(pkgs: ToolMeta[]): ToolMeta[] {
  return [...pkgs].sort((a, b) =>
    (a.id || "").localeCompare(b.id || "", undefined, { sensitivity: "base" }),
  );
}

const ADMIN_BUCKET_ORDER = [
  "files",
  "network",
  "knowledge",
  "secrets",
  "comms",
  "verticals",
  "meta",
  "media",
  "unsorted",
] as const;

const ADMIN_BUCKET_SET = new Set<string>(ADMIN_BUCKET_ORDER);

const ADMIN_BUCKET_LABEL_KEYS = {
  files: "admin:toolsBucketFiles",
  network: "admin:toolsBucketNetwork",
  knowledge: "admin:toolsBucketKnowledge",
  secrets: "admin:toolsBucketSecrets",
  comms: "admin:toolsBucketComms",
  verticals: "admin:toolsBucketVerticals",
  meta: "admin:toolsBucketMeta",
  media: "admin:toolsBucketMedia",
  unsorted: "admin:toolsBucketUnsorted",
} as const;

function shouldSubdivideByDomain(pkgs: ToolMeta[]): boolean {
  const keys = new Set(pkgs.map((p) => (p.domain || "").trim().toLowerCase() || "—"));
  return keys.size > 1;
}

function partitionByDomain(pkgs: ToolMeta[]): { domain: string; items: ToolMeta[] }[] {
  return sectionsByDomain(pkgs).map((s) => ({ domain: s.domain, items: s.items }));
}

/** One section per ``TOOL_DOMAIN`` (router category), A–Z; missing domain → „—“. */
function sectionsByDomain(pkgs: ToolMeta[]): { key: string; domain: string; items: ToolMeta[] }[] {
  const map = new Map<string, ToolMeta[]>();
  for (const p of pkgs) {
    const raw = (p.domain || "").trim();
    const key = raw.toLowerCase() || "—";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(p);
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([domainKey, items]) => ({
      key: domainKey,
      domain: items[0]?.domain?.trim() || (domainKey === "—" ? "—" : domainKey),
      items: sortPackagesById(items),
    }));
}

/**
 * Risk tier -> ``Badge`` tone.
 *
 * `l3` was previously `rose`, which the app also uses for live-mic and
 * trend-down. A risk escalation's top tier means "harmful", and that is what
 * `danger` already says — so `l3` lands there and rose is freed to mean
 * recording only. Keeping a bespoke chip to avoid a hue collision preserves the
 * collision instead of resolving it.
 */
function riskBadgeTone(rl: string | undefined): BadgeTone {
  switch (rl) {
    case "l3":
      return "danger";
    case "l2":
      return "warning";
    case "l1":
      return "accent";
    case "l0":
      return "neutral";
    default:
      return "neutral";
  }
}

export function AdminTools() {
  const { t } = useTranslation(["admin"]);
  const auth = useAuth();
  const [meta, setMeta] = useState<ToolMeta[]>([]);
  const [policyByPkg, setPolicyByPkg] = useState<Record<string, PolicyRow>>({});
  const [tenantInputByPkg, setTenantInputByPkg] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [importSourceType, setImportSourceType] = useState("auto");
  const [importMarkdown, setImportMarkdown] = useState("");
  const [importFiles, setImportFiles] = useState<FileList | null>(null);
  const [importBusy, setImportBusy] = useState(false);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<ImportAnalyzeResult | null>(null);

  const loadAdmin = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const res = await apiFetch("/v1/admin/tools", auth);
      const data = (await res.json()) as { tools?: ToolMeta[]; policy_rows?: PolicyRow[] };
      if (!res.ok) {
        setMsg(t("admin:toolsRegistryLoadFailed"));
        return;
      }
      const list = data.tools ?? [];
      setMeta(list);
      const rows = data.policy_rows ?? [];
      const map: Record<string, PolicyRow> = {};
      const tin: Record<string, string> = {};
      for (const r of rows) {
        if (r.tool_name === "*" || !r.tool_name) {
          const mr = r.min_role === "admin" ? "admin" : "user";
          const at = r.allowed_tenant_ids ?? null;
          map[r.package_id] = {
            ...r,
            tool_name: "*",
            min_role: mr,
            allowed_tenant_ids: at,
            execution_context: r.execution_context ?? null,
          };
          tin[r.package_id] = formatTenantIds(at);
        }
      }
      for (const t of list) {
        const pid = t.id ?? "";
        if (!pid || map[pid]) continue;
        const te = t.tool_effective?.[t.tools?.[0] ?? ""];
        map[pid] = {
          package_id: pid,
          tool_name: "*",
          enabled: te?.enabled ?? true,
          min_role: te?.min_role === "admin" ? "admin" : "user",
          allowed_tenant_ids: te?.allowed_tenant_ids ?? null,
          execution_context: null,
        };
        tin[pid] = formatTenantIds(te?.allowed_tenant_ids ?? null);
      }
      setPolicyByPkg(map);
      setTenantInputByPkg(tin);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [auth, t]);

  useEffect(() => {
    void loadAdmin();
  }, [loadAdmin]);

  async function reloadRegistry() {
    setBusy(true);
    setMsg(null);
    try {
      const res = await apiFetch("/v1/admin/reload-tools", auth, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail =
          data && typeof data === "object" && "detail" in data
            ? String((data as { detail: unknown }).detail)
            : res.statusText;
        setMsg(detail);
        return;
      }
      await loadAdmin();
      setMsg(t("admin:toolsRegistryReloaded"));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function savePolicies() {
    setBusy(true);
    setMsg(null);
    try {
      const policies = packages.map((p) => {
        const pid = p.id ?? "";
        const pol = policyByPkg[pid];
        const row = pol?.package_id
          ? pol
          : {
              package_id: pid,
              tool_name: "*" as const,
              enabled: true,
              min_role: "user" as const,
              allowed_tenant_ids: null,
              execution_context: null,
            };
        const rawTenants = tenantInputByPkg[pid] ?? "";
        const parsed = parseTenantIdsInput(rawTenants);
        return {
          ...row,
          allowed_tenant_ids: parsed,
          execution_context: null,
        };
      });
      const res = await apiFetch("/v1/admin/tool-policies", auth, {
        method: "PUT",
        body: JSON.stringify({ policies }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const detail =
          data && typeof data === "object" && "detail" in data
            ? String((data as { detail: unknown }).detail)
            : res.statusText;
        setMsg(detail);
        return;
      }
      setMsg(t("admin:toolsPolicySaved"));
      await loadAdmin();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function analyzeImport() {
    setImportBusy(true);
    setImportMsg(null);
    setImportResult(null);
    try {
      const fd = new FormData();
      fd.set("source_type", importSourceType);
      fd.set("markdown", importMarkdown);
      for (const f of Array.from(importFiles ?? [])) {
        fd.append("files", f, f.name);
      }
      const res = await apiFetch("/v1/admin/tools/import/analyze", auth, {
        method: "POST",
        body: fd,
      });
      const data = (await res.json().catch(() => ({}))) as ImportAnalyzeResult & { detail?: unknown };
      if (!res.ok) {
        setImportMsg(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
        return;
      }
      setImportResult(data);
      setImportMsg(t("admin:toolsImportAnalyzed", { sources: data.source_count, candidates: data.candidates.length }));
    } catch (e) {
      setImportMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setImportBusy(false);
    }
  }

  const packages = useMemo(() => meta.filter((m) => m.id), [meta]);

  const groupedPackages = useMemo(() => {
    const buckets: Record<string, ToolMeta[]> = {};
    for (const b of ADMIN_BUCKET_ORDER) buckets[b] = [];
    for (const p of packages) {
      const raw = (p.admin_bucket || "unsorted").trim().toLowerCase() || "unsorted";
      const b = ADMIN_BUCKET_SET.has(raw) ? raw : "unsorted";
      if (!buckets[b]) buckets[b] = [];
      buckets[b].push(p);
    }
    return buckets;
  }, [packages]);

  const totalPackages = packages.length;

  function updatePolicy(pid: string, patch: Partial<PolicyRow>) {
    setPolicyByPkg((prev) => {
      const base: PolicyRow =
        prev[pid] ??
        ({
          package_id: pid,
          tool_name: "*",
          enabled: true,
          min_role: "user",
          allowed_tenant_ids: null,
          execution_context: null,
        } as PolicyRow);
      return {
        ...prev,
        [pid]: {
          ...base,
          ...patch,
          package_id: pid,
          execution_context: null,
        },
      };
    });
  }

  function renderCard(p: ToolMeta) {
    const pid = p.id ?? "";
    const pol = policyByPkg[pid] ?? {
      package_id: pid,
      tool_name: "*",
      enabled: true,
      min_role: "user",
      allowed_tenant_ids: null,
      execution_context: null,
    };
    const sec = p.secrets_required;
    const req = p.requires;
    const firstTool = p.tools?.[0] ?? "";
    const manCtx = p.execution_context || "container";
    const effCtx =
      (firstTool && p.tool_effective?.[firstTool]?.execution_context) || manCtx;
    const effMr = firstTool && p.tool_effective?.[firstTool]?.min_role;
    const effTenants = firstTool ? p.tool_effective?.[firstTool]?.allowed_tenant_ids : null;
    const riskLevel = p.risk_level;
    const riskLabel = riskLevel ? t("admin:toolsBadgeRisk", { level: riskLevel }) : null;
    // `null` tone means the tier is reserved (rose) and keeps its bespoke chip.
    const riskTone = riskLevel ? riskBadgeTone(riskLevel) : null;

    return (
      <li
        key={pid}
        className="rounded-card border border-line bg-card p-soft text-xs text-ink-primary"
      >
        <div className="flex flex-col gap-base sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1 space-y-base">
            <div className="flex flex-wrap items-center gap-x-base gap-y-tight">
              <span className="font-mono text-sm font-semibold text-ink-primary">{pid}</span>
              {p.version ? <span className="text-meta text-ink-muted">v{p.version}</span> : null}
              {p.admin_bucket ? (
                <Badge tone="success">
                  {t("admin:toolsBadgeBucket", { name: p.admin_bucket })}
                </Badge>
              ) : null}
              {p.domain ? (
                <Badge tone="neutral">
                  {t("admin:toolsBadgeDomain", { name: p.domain })}
                </Badge>
              ) : null}
              <span
                className="rounded-tile bg-violet-900/50 px-snug py-hair text-meta text-violet-100"
                title={t("admin:effectiveRunContextTitle")}
              >
                {t("admin:toolsBadgeRun", { ctx: effCtx })}
                {effCtx !== manCtx ? (
                  <span className="text-violet-200/80">
                    {t("admin:toolsBadgeRunManifest", { ctx: manCtx })}
                  </span>
                ) : null}
              </span>
              {effMr ? (
                <Badge tone="warning" title={t("admin:effectiveMinRoleTitle")}>
                  {t("admin:toolsBadgeAccess", { role: effMr })}
                </Badge>
              ) : null}
              {effTenants?.length ? (
                <Badge tone="neutral">
                  {t("admin:toolsBadgeTenants", { ids: effTenants.join(",") })}
                </Badge>
              ) : null}
              {p.os_support?.length ? (
                <Badge tone="neutral">
                  {t("admin:toolsBadgeOs", { list: p.os_support.join(",") })}
                </Badge>
              ) : null}
              {riskLevel ? <Badge tone={riskTone}>{riskLabel}</Badge> : null}
            </div>
            <p className="truncate font-mono text-meta text-ink-muted" title={p.source}>
              {p.source}
            </p>
            <div className="grid gap-snug sm:grid-cols-2">
              <div>
                <span className="text-ink-muted">{t("admin:toolsColTools")}</span>{" "}
                <span className="break-all font-mono text-meta text-ink-secondary">
                  {(p.tools ?? []).join(", ")}
                </span>
              </div>
              {p.tags?.length ? (
                <div>
                  <span className="text-ink-muted">{t("admin:toolsColManifestTags")}</span>{" "}
                  <span className="text-ink-secondary">{p.tags.join(", ")}</span>
                </div>
              ) : null}
              {p.admin_tags?.length ? (
                <div>
                  <span className="text-ink-muted">{t("admin:toolsColRegistryTags")}</span>{" "}
                  <span className="text-ink-secondary">{p.admin_tags.join(", ")}</span>
                </div>
              ) : null}
              {p.capabilities?.length ? (
                <div>
                  <span className="text-ink-muted">{t("admin:toolsColCapabilities")}</span>{" "}
                  <span className="text-ink-secondary">{p.capabilities.join(", ")}</span>
                </div>
              ) : null}
              {req?.length ? (
                <div>
                  <span className="text-ink-muted">{t("admin:toolsColToolRequires")}</span>{" "}
                  <span className="text-ink-secondary">{req.join(", ")}</span>
                </div>
              ) : null}
              {sec?.length ? (
                <div>
                  <span className="text-ink-muted">{t("admin:toolsColSecrets")}</span>{" "}
                  <span className="text-badge-warning">{sec.join(", ")}</span>
                </div>
              ) : null}
              {p.families?.length ? (
                <div>
                  <span className="text-ink-muted">{t("admin:toolsColFamilies")}</span>{" "}
                  <span className="text-ink-secondary">{p.families.join(", ")}</span>
                </div>
              ) : null}
              <div className="sm:col-span-2">
                <span className="text-ink-muted">{t("admin:adminToolsManifestAccess")}</span>{" "}
                <span className="font-mono text-ink-secondary">
                  TOOL_MIN_ROLE={p.min_role ?? "user"}
                  {p.allowed_tenant_ids?.length
                    ? ` · TOOL_ALLOWED_TENANT_IDS=[${p.allowed_tenant_ids.join(", ")}]`
                    : ""}
                </span>
              </div>
            </div>
          </div>
          <label className="flex shrink-0 cursor-pointer items-center gap-base whitespace-nowrap text-meta text-ink-primary">
            <input
              type="checkbox"
              checked={pol.enabled}
              onChange={(e) => updatePolicy(pid, { enabled: e.target.checked })}
            />
            {t("admin:toolsPolicyEnabled")}
          </label>
        </div>
        <div className="mt-soft grid grid-cols-1 gap-soft border-t border-line pt-soft sm:grid-cols-2">
          <label className="flex min-w-0 flex-col gap-tight text-meta text-ink-muted">
            <span className="text-ink-muted">{t("admin:toolsPolicyMinRole")}</span>
            <select
              className="w-full rounded-tile border border-line bg-field px-base py-snug text-xs text-ink-primary"
              value={pol.min_role}
              onChange={(e) =>
                updatePolicy(pid, { min_role: e.target.value === "admin" ? "admin" : "user" })
              }
            >
              <option value="user">{t("admin:toolsMinRoleUser")}</option>
              <option value="admin">{t("admin:toolsMinRoleAdmin")}</option>
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-tight text-meta text-ink-muted">
            <span className="text-ink-muted">
              {t("admin:toolsPolicyTenantIds")} (<span className="font-mono">tenants.id</span>)
            </span>
            <input
              type="text"
              className="w-full rounded-tile border border-line bg-field px-base py-snug font-mono text-xs text-ink-primary placeholder:text-neutral-500"
              placeholder={t("admin:toolsPolicyTenantIdsPlaceholder")}
              value={tenantInputByPkg[pid] ?? ""}
              onChange={(e) => {
                const v = e.target.value;
                setTenantInputByPkg((prev) => ({ ...prev, [pid]: v }));
              }}
            />
          </label>
        </div>
      </li>
    );
  }

  return (
    <div className="mx-auto max-w-pageWide px-wide py-deep sm:px-broad">
      <h1 className="text-2xl font-semibold text-ink-primary">{t("admin:toolsRegistryTitle")}</h1>
      <p className="mt-base max-w-measure text-sm text-ink-muted">
        {t("admin:toolsRegistryIntro")}{" "}
        <span className="text-ink-muted">{t("admin:toolsRegistryAssignUsers")}</span>
      </p>

      <section className="mt-broad rounded-sheet border border-line bg-card p-wide">
        <div className="flex flex-col gap-base sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-ink-primary">{t("admin:toolsImportTitle")}</h2>
            <p className="mt-tight max-w-measure text-xs text-ink-muted">
              {t("admin:toolsImportIntro")}
            </p>
          </div>
          <label className="sr-only" htmlFor="tools-import-source-type">
            {t("admin:toolsImportSourceType")}
          </label>
          <select
            id="tools-import-source-type"
            className="w-full rounded-tile border border-line bg-field px-base py-snug text-xs text-ink-primary sm:w-56"
            value={importSourceType}
            onChange={(e) => setImportSourceType(e.target.value)}
          >
            <option value="auto">{t("admin:toolsImportAuto")}</option>
            <option value="openclaw_skill">{t("admin:toolsImportOpenClaw")}</option>
            <option value="cursor_skill">{t("admin:toolsImportCursor")}</option>
            <option value="claude_command">{t("admin:toolsImportClaude")}</option>
            <option value="generic_markdown">{t("admin:toolsImportGeneric")}</option>
          </select>
        </div>
        <div className="mt-wide grid gap-soft lg:grid-cols-2">
          <label className="flex flex-col gap-tight text-xs text-ink-muted">
            <span>{t("admin:toolsImportPaste")}</span>
            <textarea
              className="min-h-40 rounded-tile border border-line bg-field px-soft py-base font-mono text-xs text-ink-primary placeholder:text-neutral-500"
              value={importMarkdown}
              onChange={(e) => setImportMarkdown(e.target.value)}
              placeholder={t("admin:toolsImportPastePlaceholder")}
            />
          </label>
          <div className="rounded-tile border border-line bg-black/20 p-soft text-xs text-ink-muted">
            <label className="block">
              <span>{t("admin:toolsImportUpload")}</span>
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
              <li>{t("admin:toolsImportAnalyzeOnly")}</li>
            </ul>
            <button
              type="button"
              disabled={importBusy || (!importMarkdown.trim() && !(importFiles?.length))}
              className="mt-wide rounded-tile bg-accent px-wide py-base text-sm font-medium text-ink-on-fill hover:bg-accent-hover disabled:opacity-50"
              onClick={() => void analyzeImport()}
            >
              {importBusy ? t("admin:toolsImportAnalyzing") : t("admin:toolsImportAnalyze")}
            </button>
          </div>
        </div>
        {importMsg ? <p className="mt-soft text-sm text-ink-muted">{importMsg}</p> : null}
        {importResult ? (
          <div className="mt-wide space-y-soft">
            <div className="rounded-tile border border-line bg-black/20 p-soft text-xs text-ink-secondary">
              {t("admin:toolsImportDetected")}: <span className="font-mono text-ink-primary">{importResult.source_type}</span>{" "}
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
              {importResult.candidates.map((c) => (
                <article key={`${c.kind}:${c.name}`} className="rounded-card border border-line bg-black/20 p-soft text-xs text-ink-primary">
                  <div className="flex flex-wrap items-center gap-base">
                    <span className="font-mono text-sm font-semibold text-ink-primary">{c.name}</span>
                    <Badge tone="accent">{c.kind}</Badge>
                    <Badge tone="warning">
                      {t("admin:toolsImportRisk", { risk: c.risk ?? t("admin:toolsImportUnknown") })}
                    </Badge>
                    {typeof c.confidence === "number" ? (
                      <Badge tone="neutral">
                        {Math.round(c.confidence * 100)}%
                      </Badge>
                    ) : null}
                  </div>
                  <p className="mt-base text-ink-secondary">{c.title}</p>
                  {c.summary ? <p className="mt-tight text-ink-muted">{c.summary}</p> : null}
                  <p className="mt-base font-mono text-meta text-ink-muted">{c.target_dir}</p>
                  {c.determinism_notes?.length ? (
                    <ul className="mt-base list-disc space-y-tight pl-wide text-meta text-ink-muted">
                      {c.determinism_notes.map((n) => <li key={n}>{n}</li>)}
                    </ul>
                  ) : null}
                </article>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      <div className="mt-wide flex flex-wrap gap-base">
        <button
          type="button"
          disabled={busy}
          className="rounded-tile bg-accent px-wide py-base text-sm font-medium text-ink-on-fill hover:bg-accent-hover disabled:opacity-50"
          onClick={() => void loadAdmin()}
        >
          {t("admin:toolsRegistryRefresh")}
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded-tile bg-white/10 px-wide py-base text-sm font-medium text-ink-primary hover:bg-white/15 disabled:opacity-50"
          onClick={() => void reloadRegistry()}
        >
          {t("admin:toolsRegistryReload")}
        </button>
        <button
          type="button"
          disabled={busy || loading}
          className="rounded-tile bg-success px-wide py-base text-sm font-medium text-ink-on-fill hover:bg-success-hover disabled:opacity-50"
          onClick={() => void savePolicies()}
        >
          {t("admin:toolsRegistrySavePolicy")}
        </button>
      </div>

      {msg ? <p className="mt-soft text-sm text-ink-muted">{msg}</p> : null}

      {loading ? (
        <p className="mt-deep text-sm text-ink-muted">{t("admin:toolsRegistryLoading")}</p>
      ) : (
        <div className="mt-broad max-h-[min(72vh,calc(100dvh-11rem))] overflow-y-auto overscroll-contain rounded-card border border-line bg-black/20 pr-tight">
          <div className="flex flex-col divide-y divide-line">
            {ADMIN_BUCKET_ORDER.map((bucket) => {
              const raw = groupedPackages[bucket] ?? [];
              const sectionPkgs = sortPackagesById(raw);
              if (!sectionPkgs.length) return null;
              const subdiv = shouldSubdivideByDomain(sectionPkgs);
              const blocks = subdiv
                ? partitionByDomain(sectionPkgs)
                : [{ domain: "", items: sectionPkgs }];

              return (
                <details key={bucket} className="group px-base py-hair open:bg-white/[0.03]">
                  <summary className="cursor-pointer list-none py-firm pl-tight [&::-webkit-details-marker]:hidden">
                    <div className="flex flex-wrap items-baseline justify-between gap-base pr-tight">
                      <span className="text-sm font-medium text-ink-primary">
                        <span className="font-mono text-ink-muted">{bucket}</span> ·{" "}
                        {t(ADMIN_BUCKET_LABEL_KEYS[bucket])}
                      </span>
                      <span className="font-mono text-xs text-ink-muted">
                        {t("admin:toolsPackagesCount", { count: sectionPkgs.length })}
                      </span>
                    </div>
                  </summary>
                  <div className="space-y-wide pb-wide pl-tight">
                    {blocks.map((block) => (
                      <div key={block.domain || "_"}>
                        {subdiv ? (
                          <h3 className="mb-base border-l-2 border-accent/60 pl-base text-meta font-semibold uppercase tracking-wide text-badge-accent">
                            {t("admin:toolsDomainHeader", {
                              domain: block.domain,
                              count: block.items.length,
                            })}
                          </h3>
                        ) : null}
                        <ul className="flex flex-col gap-base">{block.items.map((p) => renderCard(p))}</ul>
                      </div>
                    ))}
                  </div>
                </details>
              );
            })}
          </div>
        </div>
      )}

      {!loading && totalPackages === 0 ? (
        <p className="mt-deep text-sm text-ink-muted">{t("admin:toolsRegistryNoneLoaded")}</p>
      ) : null}
    </div>
  );
}
