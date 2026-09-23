import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import { isPackageEnabledForChat, setPackageEnabledForChat } from "../../features/settings/toolPrefs";

type ToolPackageUi = {
  category: string;
  display_name: string;
  order: number;
  icon?: string;
  tagline?: string;
};

type ToolsMeta = {
  id?: string;
  domain?: string;
  admin_bucket?: string;
  tools?: string[];
  TOOL_LABEL?: string;
  TOOL_DESCRIPTION?: string;
  secrets_required?: string[];
  requires?: string[];
  risk_level?: string | number;
  ui?: ToolPackageUi;
};

type ChatToolFunction = {
  name?: string;
  description?: string;
  TOOL_DESCRIPTION?: string;
  parameters?: unknown;
};

const CATEGORY_ORDER = [
  "productivity",
  "knowledge",
  "developer",
  "creative",
  "outdoor",
  "system",
] as const;

const CATEGORY_LABEL_KEY: Record<string, string> = {
  productivity: "settings:toolsCategoryProductivity",
  knowledge: "settings:toolsCategoryKnowledge",
  developer: "settings:toolsCategoryDeveloper",
  creative: "settings:toolsCategoryCreative",
  outdoor: "settings:toolsCategoryOutdoor",
  system: "settings:toolsCategorySystem",
};

const SETUP_HINT_KEY: Record<string, string> = {
  gmail: "settings:toolsHintGmail",
  github: "settings:toolsHintGithub",
  google_calendar: "settings:toolsHintGoogleCalendar",
  openweather: "settings:toolsHintOpenweather",
};

type TabId = "all" | "enabled" | "needs_setup" | "high_risk";

function secretKeysForPackage(m: ToolsMeta): string[] {
  const raw = m.secrets_required ?? [];
  if (!Array.isArray(raw)) return [];
  return [...new Set(raw.map((x) => String(x).trim().toLowerCase()).filter(Boolean))];
}

function riskLabel(m: ToolsMeta): string {
  const r = m.risk_level;
  if (r == null || r === "") return "";
  return String(r).toLowerCase();
}

function isHighRisk(m: ToolsMeta): boolean {
  const s = riskLabel(m);
  return s === "l2" || s === "l3" || s === "2" || s === "3";
}

function matchesSearch(m: ToolsMeta, q: string): boolean {
  if (!q.trim()) return true;
  const needle = q.trim().toLowerCase();
  const id = (m.id || "").toLowerCase();
  const dn = (m.ui?.display_name || m.TOOL_LABEL || "").toLowerCase();
  const tg = (m.ui?.tagline || m.TOOL_DESCRIPTION || "").toLowerCase();
  const tools = (m.tools ?? []).join(" ").toLowerCase();
  return id.includes(needle) || dn.includes(needle) || tg.includes(needle) || tools.includes(needle);
}

function buildFunctionIndex(chatTools: unknown[]): Map<string, ChatToolFunction> {
  const map = new Map<string, ChatToolFunction>();
  for (const spec of chatTools) {
    if (!spec || typeof spec !== "object") continue;
    const fn = (spec as { function?: ChatToolFunction }).function;
    if (!fn || typeof fn !== "object") continue;
    const n = fn.name;
    if (typeof n === "string" && n.trim()) map.set(n.trim(), fn);
  }
  return map;
}

function summarizeParams(params: unknown): string {
  if (!params || typeof params !== "object") return "";
  try {
    const s = JSON.stringify(params, null, 2);
    return s.length > 1200 ? `${s.slice(0, 1200)}…` : s;
  } catch {
    return "";
  }
}

function categoryAnalytics(items: ToolsMeta[], services: string[]) {
  let ready = 0;
  let needSetup = 0;
  let enabled = 0;
  for (const m of items) {
    const names = (m.tools ?? []).filter((x): x is string => typeof x === "string" && !!x.trim());
    const reqs = secretKeysForPackage(m);
    const missing = reqs.filter((k) => !services.includes(k));
    if (missing.length) needSetup += 1;
    else ready += 1;
    if (names.length && isPackageEnabledForChat(names)) enabled += 1;
  }
  return { total: items.length, ready, needSetup, enabled };
}

function recommendationForPackage(
  m: ToolsMeta,
  missing: string[],
  display: string,
  tr: (key: string, opts?: Record<string, unknown>) => string
): string {
  const mid = (m.id || "").trim();
  for (const k of missing) {
    const hintKey = SETUP_HINT_KEY[k];
    if (hintKey) return tr(hintKey);
  }
  if (mid && SETUP_HINT_KEY[mid]) return tr(SETUP_HINT_KEY[mid]);
  return tr("settings:toolsRecommendationMissing", { keys: missing.join(", "), display });
}

export function ToolsSettings() {
  const { t } = useTranslation(["settings"]);
  const auth = useAuth();
  const [meta, setMeta] = useState<ToolsMeta[]>([]);
  const [chatSpecs, setChatSpecs] = useState<unknown[]>([]);
  const [services, setServices] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [, bump] = useState(0);
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<TabId>("all");
  const [openCats, setOpenCats] = useState<Record<string, boolean>>({});
  const [drawerPkg, setDrawerPkg] = useState<ToolsMeta | null>(null);

  const fnIndex = useMemo(() => buildFunctionIndex(chatSpecs), [chatSpecs]);

  const load = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const res = await apiFetch("/v1/tools", auth);
      const data = (await res.json()) as {
        tools?: unknown[];
        tools_meta?: ToolsMeta[];
        detail?: unknown;
      };
      if (!res.ok) {
        setMeta([]);
        setChatSpecs([]);
        setMsg(typeof data.detail === "string" ? data.detail : t("settings:toolsLoadFailed"));
        return;
      }
      setMeta(Array.isArray(data.tools_meta) ? data.tools_meta : []);
      setChatSpecs(Array.isArray(data.tools) ? data.tools : []);

      const sres = await apiFetch("/v1/user/secrets", auth);
      const sdata = (await sres.json()) as { services?: string[] };
      if (sres.ok) {
        setServices((sdata.services ?? []).map((k) => String(k).toLowerCase()));
      } else {
        setServices([]);
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    void load();
  }, [load]);

  const filteredByTab = useMemo(() => {
    return meta.filter((m) => {
      if (!(m.id || "").trim()) return false;
      const names = (m.tools ?? []).filter((x): x is string => typeof x === "string" && !!x.trim());
      const reqs = secretKeysForPackage(m);
      const missing = reqs.filter((k) => !services.includes(k));
      const enabled = names.length ? isPackageEnabledForChat(names) : true;

      if (tab === "enabled") return enabled && names.length > 0;
      if (tab === "needs_setup") return missing.length > 0;
      if (tab === "high_risk") return isHighRisk(m);
      return true;
    });
  }, [meta, services, tab]);

  const searched = useMemo(() => {
    return filteredByTab.filter((m) => matchesSearch(m, search));
  }, [filteredByTab, search]);

  const grouped = useMemo(() => {
    const map = new Map<string, ToolsMeta[]>();
    for (const m of searched) {
      const cat = (m.ui?.category || "system").toLowerCase();
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(m);
    }
    for (const g of map.values()) {
      g.sort((a, b) => {
        const oa = a.ui?.order ?? 500;
        const ob = b.ui?.order ?? 500;
        if (oa !== ob) return oa - ob;
        return (a.ui?.display_name || a.id || "").localeCompare(b.ui?.display_name || b.id || "", undefined, {
          sensitivity: "base",
        });
      });
    }
    const ordered: { cat: string; label: string; items: ToolsMeta[] }[] = [];
    for (const c of CATEGORY_ORDER) {
      const items = map.get(c);
      if (items?.length) {
        const key = CATEGORY_LABEL_KEY[c];
        ordered.push({ cat: c, label: key ? t(key) : c, items });
      }
    }
    const orderSet = new Set<string>(CATEGORY_ORDER);
    for (const [c, items] of map.entries()) {
      if (!orderSet.has(c) && items.length) {
        const key = CATEGORY_LABEL_KEY[c];
        ordered.push({ cat: c, label: key ? t(key) : c, items });
      }
    }
    return ordered;
  }, [searched, t]);

  const recommendations = useMemo(() => {
    const out: { id: string; title: string; body: string }[] = [];
    for (const m of meta) {
      if (!(m.id || "").trim()) continue;
      const reqs = secretKeysForPackage(m);
      const missing = reqs.filter((k) => !services.includes(k));
      if (!missing.length) continue;
      const title = (m.ui?.display_name || m.TOOL_LABEL || m.id || "").trim();
      out.push({
        id: (m.id || "").trim(),
        title,
        body: recommendationForPackage(m, missing, title, t),
      });
    }
    return out.slice(0, 6);
  }, [meta, services]);

  useEffect(() => {
    setOpenCats((prev) => {
      const next = { ...prev };
      for (const g of grouped) {
        if (next[g.cat] === undefined) next[g.cat] = true;
      }
      return next;
    });
  }, [grouped]);

  useEffect(() => {
    function onKey(ev: KeyboardEvent) {
      if (ev.key === "Escape") setDrawerPkg(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function refreshToggles() {
    bump((n) => n + 1);
  }

  function toggleCat(cat: string) {
    setOpenCats((p) => ({ ...p, [cat]: !p[cat] }));
  }

  function tryPromptForPackage(m: ToolsMeta): string {
    const names = (m.tools ?? []).filter((x): x is string => typeof x === "string" && !!x.trim());
    const first = names[0] || "tools";
    const title = (m.ui?.display_name || m.id || "").trim();
    return t("settings:toolsTryPromptVerify", { tool: first, title });
  }

  return (
    <div className="mx-auto max-w-4xl space-y-deep pb-grand">
      <div>
        <h1 className="text-lg font-semibold text-ink-primary">{t("settings:toolsTitle")}</h1>
        <p className="mt-base text-sm text-ink-muted">
          {t("settings:toolsIntro")}{" "}
          <Link to="/settings/connections" className="text-sky-400 hover:text-sky-300 hover:underline">
            {t("settings:toolsConnectionsLink")}
          </Link>
          .
        </p>
      </div>

      {msg ? <p className="text-sm text-amber-400">{msg}</p> : null}
      {loading ? <p className="text-sm text-ink-muted">{t("settings:toolsLoading")}</p> : null}

      {!loading && recommendations.length > 0 ? (
        <section
          className="rounded-sheet border border-sky-500/25 bg-sky-500/5 px-wide py-soft"
          aria-label={t("settings:toolsSetupSuggestionsAria")}
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-sky-200/90">
            {t("settings:toolsSuggestedNextSteps")}
          </p>
          <ul className="mt-base space-y-base text-sm text-ink-primary">
            {recommendations.map((r) => (
              <li key={r.id} className="flex flex-col gap-hair sm:flex-row sm:items-center sm:justify-between">
                <span>{r.body}</span>
                <Link
                  to="/settings/connections"
                  className="shrink-0 text-xs font-medium text-sky-400 hover:text-sky-300 hover:underline"
                >
                  {t("settings:toolsOpenConnections")}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {!loading && meta.length > 0 ? (
        <div className="flex flex-col gap-wide sm:flex-row sm:items-center sm:justify-between">
          <label className="block max-w-md flex-1 text-sm text-ink-muted">
            {t("settings:toolsSearchLabel")}
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("settings:toolsSearchPlaceholder")}
              className="mt-tight w-full rounded-card border border-line bg-field px-soft py-base text-sm text-ink-primary placeholder:text-neutral-600"
            />
          </label>
          <div
            className="flex flex-wrap gap-tight"
            role="tablist"
            aria-label={t("settings:toolsFilterPackagesAria")}
          >
            {(
              [
                ["all", t("settings:toolsTabAll")],
                ["enabled", t("settings:toolsTabEnabled")],
                ["needs_setup", t("settings:toolsTabNeedsSetup")],
                ["high_risk", t("settings:toolsTabHighRisk")],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={`rounded-pill px-soft py-snug text-xs font-medium transition ${
                  tab === id ? "bg-sky-600 text-ink-on-fill" : "bg-white/5 text-ink-muted hover:bg-white/10"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="space-y-wide">
        {grouped.map((g) => {
          const open = openCats[g.cat] !== false;
          const stats = categoryAnalytics(g.items, services);
          return (
            <section key={g.cat} className="overflow-hidden rounded-sheet border border-line bg-card">
              <button
                type="button"
                onClick={() => toggleCat(g.cat)}
                className="flex w-full items-center justify-between gap-soft px-wide py-soft text-left transition hover:bg-white/[0.04]"
              >
                <div>
                  <h2 className="text-sm font-semibold text-ink-primary">{g.label}</h2>
                  <p className="text-meta text-ink-muted">
                    {t("settings:toolsCategoryStats", {
                      total: stats.total,
                      ready: stats.ready,
                      enabled: stats.enabled,
                      needSetup: stats.needSetup,
                    })}
                  </p>
                </div>
                <span className="text-ink-muted">{open ? "▲" : "▼"}</span>
              </button>
              {open ? (
                <div className="border-t border-line-subtle px-soft pb-wide pt-base">
                  <div className="grid gap-soft sm:grid-cols-2">
                    {g.items.map((m) => {
                      const pid = (m.id || "").trim();
                      const names = (m.tools ?? []).filter((x): x is string => typeof x === "string" && !!x.trim());
                      const enabled = names.length ? isPackageEnabledForChat(names) : true;
                      const reqs = secretKeysForPackage(m);
                      const missing = reqs.filter((k) => !services.includes(k));
                      const title = (m.ui?.display_name || m.TOOL_LABEL || pid).trim();
                      const tagline = (m.ui?.tagline || m.TOOL_DESCRIPTION || "").trim().slice(0, 200);
                      const risk = riskLabel(m);
                      const high = isHighRisk(m);
                      const tryEnc = encodeURIComponent(tryPromptForPackage(m));
                      return (
                        <div
                          key={pid}
                          className="flex flex-col rounded-sheet border border-line bg-black/25 p-wide shadow-sm shadow-black/20"
                        >
                          <div className="mb-base flex flex-wrap items-start justify-between gap-base">
                            <div className="min-w-0">
                              {m.domain ? (
                                <p className="text-meta uppercase tracking-wide text-ink-muted">{m.domain}</p>
                              ) : null}
                              <h3 className="font-semibold text-ink-primary">{title}</h3>
                              <p className="font-mono text-meta text-ink-muted">{pid}</p>
                            </div>
                            <div className="flex flex-wrap justify-end gap-tight">
                              {enabled ? (
                                <span className="rounded-tile bg-emerald-500/15 px-snug py-hair text-meta text-emerald-200">
                                  {t("settings:toolsBadgeOn")}
                                </span>
                              ) : (
                                <span className="rounded-tile bg-neutral-500/20 px-snug py-hair text-meta text-ink-muted">
                                  {t("settings:toolsBadgeOff")}
                                </span>
                              )}
                              {missing.length ? (
                                <span className="rounded-tile bg-amber-500/20 px-snug py-hair text-meta text-amber-200">
                                  {t("settings:toolsBadgeNeedsSecret")}
                                </span>
                              ) : reqs.length ? (
                                <span className="rounded-tile bg-emerald-500/10 px-snug py-hair text-meta text-emerald-200/90">
                                  {t("settings:toolsBadgeReady")}
                                </span>
                              ) : (
                                <span className="rounded-tile bg-white/5 px-snug py-hair text-meta text-ink-muted">
                                  {t("settings:toolsBadgeNoSecrets")}
                                </span>
                              )}
                              {high ? (
                                <span className="rounded-tile bg-orange-500/20 px-snug py-hair text-meta text-orange-200">
                                  {t("settings:toolsRiskHigh", { level: risk || "high" })}
                                </span>
                              ) : risk ? (
                                <span className="rounded-tile bg-white/10 px-snug py-hair text-meta text-ink-muted">
                                  {t("settings:toolsRiskLevel", { level: risk })}
                                </span>
                              ) : null}
                            </div>
                          </div>
                          {tagline ? <p className="mb-soft text-xs leading-relaxed text-ink-muted">{tagline}</p> : null}
                          <p className="mb-soft text-meta text-ink-muted">
                            <span className="text-ink-muted">{t("settings:toolsToolsCount", { count: names.length })}</span>{" "}
                            <span className="font-mono text-meta text-ink-muted">{names.join(", ")}</span>
                          </p>
                          <div className="mb-soft flex flex-wrap gap-base border-t border-line-subtle pt-soft">
                            <Link
                              to={`/chat?try=${tryEnc}`}
                              className="rounded-tile bg-white/10 px-firm py-tight text-meta font-medium text-ink-primary hover:bg-white/15"
                            >
                              {t("settings:toolsTest")}
                            </Link>
                            <Link
                              to="/docs"
                              className="rounded-tile bg-white/5 px-firm py-tight text-meta text-ink-muted hover:bg-white/10 hover:text-neutral-200"
                            >
                              {t("settings:toolsDocs")}
                            </Link>
                            {reqs.length ? (
                              <Link
                                to="/settings/connections"
                                className="rounded-tile bg-white/5 px-firm py-tight text-meta text-sky-400 hover:bg-white/10"
                              >
                                {t("settings:toolsConfigure")}
                              </Link>
                            ) : null}
                            <button
                              type="button"
                              disabled={!names.length}
                              className="rounded-tile bg-white/5 px-firm py-tight text-meta text-amber-200/90 hover:bg-white/10 disabled:opacity-40"
                              onClick={() => {
                                setPackageEnabledForChat(names, false);
                                refreshToggles();
                              }}
                            >
                              {t("settings:toolsDisable")}
                            </button>
                            <button
                              type="button"
                              className="rounded-tile border border-line-strong px-firm py-tight text-meta text-ink-primary hover:bg-white/10"
                              onClick={() => setDrawerPkg(m)}
                            >
                              {t("settings:toolsDetails")}
                            </button>
                          </div>
                          <div className="flex flex-wrap items-center gap-soft border-t border-line-subtle pt-soft">
                            <label className="flex cursor-pointer items-center gap-base text-xs text-ink-primary">
                              <input
                                type="checkbox"
                                className="h-4 w-4 rounded-tile border-line bg-field"
                                checked={enabled}
                                disabled={!names.length}
                                onChange={(e) => {
                                  setPackageEnabledForChat(names, e.target.checked);
                                  refreshToggles();
                                }}
                              />
                              {t("settings:toolsEnableBrowser")}
                            </label>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </section>
          );
        })}
      </div>

      {!loading && meta.length === 0 ? (
        <p className="text-sm text-ink-muted">{t("settings:toolsNoPackages")}</p>
      ) : null}

      {!loading && meta.length > 0 && searched.length === 0 ? (
        <p className="text-sm text-ink-muted">{t("settings:toolsNoMatchFilter")}</p>
      ) : null}

      <button
        type="button"
        className="text-xs text-sky-400 hover:text-sky-300 hover:underline"
        onClick={() => void load()}
      >
        {t("settings:toolsRefreshCatalog")}
      </button>

      {drawerPkg ? (
        <PackageDrawer
          pkg={drawerPkg}
          fnIndex={fnIndex}
          onClose={() => setDrawerPkg(null)}
        />
      ) : null}
    </div>
  );
}

function PackageDrawer({
  pkg,
  fnIndex,
  onClose,
}: {
  pkg: ToolsMeta;
  fnIndex: Map<string, ChatToolFunction>;
  onClose: () => void;
}) {
  const { t } = useTranslation(["settings", "common"]);
  const pid = (pkg.id || "").trim();
  const title = (pkg.ui?.display_name || pkg.TOOL_LABEL || pid).trim();
  const names = (pkg.tools ?? []).filter((x): x is string => typeof x === "string" && !!x.trim());
  const first = names[0] || "tool";
  const example = t("settings:toolsTryExample", { tool: first });

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 p-0 sm:p-wide" role="dialog" aria-modal="true">
      <button
        type="button"
        className="absolute inset-0 h-full w-full cursor-default"
        aria-label={t("settings:close")}
        onClick={onClose}
      />
      <div className="relative flex h-full w-full max-w-lg flex-col border-l border-line bg-[#141414] shadow-2xl sm:h-auto sm:max-h-[90vh] sm:rounded-sheet">
        <div className="flex items-start justify-between gap-soft border-b border-line px-roomy py-wide">
          <div>
            <p className="text-meta uppercase text-ink-muted">{pid}</p>
            <h2 className="text-lg font-semibold text-ink-primary">{title}</h2>
            {(pkg.ui?.tagline || pkg.TOOL_DESCRIPTION) && (
              <p className="mt-tight text-sm text-ink-muted">{(pkg.ui?.tagline || pkg.TOOL_DESCRIPTION || "").slice(0, 400)}</p>
            )}
          </div>
          <button
            type="button"
            className="rounded-card px-base py-tight text-sm text-ink-muted hover:bg-white/10 hover:text-white"
            onClick={onClose}
          >
            <X aria-hidden className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-broad overflow-y-auto px-roomy py-wide">
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-sky-200/80">{t("settings:toolsExamplePrompt")}</h3>
            <p className="mt-tight text-sm text-ink-secondary">{example}</p>
          </section>
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-sky-200/80">{t("settings:toolsFunctionsInPackage")}</h3>
            <ul className="mt-base space-y-wide">
              {names.map((n) => {
                const fn = fnIndex.get(n);
                const desc = (fn?.description || fn?.TOOL_DESCRIPTION || "").trim() || "—";
                const params = summarizeParams(fn?.parameters);
                return (
                  <li key={n} className="rounded-card border border-line bg-black/30 p-soft">
                    <p className="font-mono text-sm font-medium text-sky-200">{n}</p>
                    <p className="mt-tight text-xs text-ink-muted">{desc}</p>
                    {params ? (
                      <pre className="mt-base max-h-40 overflow-auto rounded-tile border border-line-subtle bg-black/40 p-base text-meta text-ink-muted">
                        {params}
                      </pre>
                    ) : (
                      <p className="mt-tight text-meta text-ink-faint">{t("settings:toolsNoParamSchema")}</p>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
          <section className="rounded-card border border-dashed border-line-strong bg-white/[0.02] p-soft">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{t("settings:toolsLogsLastUsed")}</h3>
            <p className="mt-tight text-xs text-ink-muted">{t("settings:toolsLogsNotExposed")}</p>
          </section>
        </div>
        <div className="flex gap-base border-t border-line px-roomy py-wide">
          <Link
            to="/settings/connections"
            className="rounded-card bg-sky-600 px-wide py-base text-sm font-medium text-ink-on-fill hover:bg-sky-500"
            onClick={onClose}
          >
            {t("settings:connectionsTitle")}
          </Link>
          <button
            type="button"
            className="rounded-card border border-line-strong px-wide py-base text-sm text-ink-primary hover:bg-white/10"
            onClick={onClose}
          >
            {t("settings:toolsDrawerClose")}
          </button>
        </div>
      </div>
    </div>
  );
}
