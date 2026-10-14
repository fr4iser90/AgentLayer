/**
 * Admin: install / update / uninstall / version-select / enable external coding harnesses.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { Button } from "../../ui/Button";
import { Checkbox } from "../../ui/Checkbox";
import { Select } from "../../ui/Field";
import { PageShell } from "../../layout/PageShell";

type RuntimeRow = {
  id: string;
  label: string;
  npm_package: string;
  docs_url?: string;
  installed: boolean;
  volume_installed?: boolean;
  source?: "volume" | "image" | null;
  binary_path?: string | null;
  version?: string | null;
  enabled: boolean;
  available: boolean;
  reason: string;
  last_install_log_tail?: string | null;
};

type Catalog = {
  external_runtime_enabled: boolean;
  preferred_id: string | null;
  runtimes: RuntimeRow[];
};

type VersionOption = { value: string; label: string };

type VersionsPayload = {
  ok?: boolean;
  error?: string | null;
  options?: VersionOption[];
  default?: string;
};

function authHeaders(token: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

export function AdminCodingRuntimes() {
  const { t } = useTranslation(["admin"]);
  const auth = useAuth();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [preferred, setPreferred] = useState("");
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  const [versionPick, setVersionPick] = useState<Record<string, string>>({});
  const [versionOptions, setVersionOptions] = useState<Record<string, VersionOption[]>>({});
  const [versionsLoading, setVersionsLoading] = useState<Record<string, boolean>>({});

  const applyCatalog = useCallback((data: Catalog) => {
    setCatalog(data);
    setPreferred((data.preferred_id || "").trim());
    setEnabled(new Set(data.runtimes.filter((x) => x.enabled).map((x) => x.id)));
    setVersionPick((prev) => {
      const next = { ...prev };
      for (const rt of data.runtimes) {
        if (!next[rt.id]) next[rt.id] = "latest";
      }
      return next;
    });
  }, []);

  const loadVersions = useCallback(
    async (runtimeIds: string[]) => {
      if (!auth.accessToken || runtimeIds.length === 0) return;
      setVersionsLoading((prev) => {
        const next = { ...prev };
        for (const id of runtimeIds) next[id] = true;
        return next;
      });
      await Promise.all(
        runtimeIds.map(async (id) => {
          try {
            const r = await fetch(`/v1/admin/coding-runtimes/${id}/versions`, {
              credentials: "include",
              headers: authHeaders(auth.accessToken!),
            });
            const body = (await r.json().catch(() => ({}))) as VersionsPayload;
            const options =
              r.ok && body.ok !== false && Array.isArray(body.options) && body.options.length > 0
                ? body.options
                : [{ value: "latest", label: "latest" }];
            setVersionOptions((prev) => ({ ...prev, [id]: options }));
            setVersionPick((prev) => {
              const cur = prev[id];
              const allowed = new Set(options.map((o) => o.value));
              if (cur && allowed.has(cur)) return prev;
              return { ...prev, [id]: body.default || options[0]?.value || "latest" };
            });
          } catch {
            setVersionOptions((prev) => ({
              ...prev,
              [id]: [{ value: "latest", label: "latest" }],
            }));
          } finally {
            setVersionsLoading((prev) => ({ ...prev, [id]: false }));
          }
        })
      );
    },
    [auth.accessToken]
  );

  const load = useCallback(async () => {
    if (!auth.accessToken) return;
    setLoading(true);
    setError(null);
    const r = await fetch("/v1/admin/coding-runtimes", {
      credentials: "include",
      headers: authHeaders(auth.accessToken),
    });
    setLoading(false);
    if (!r.ok) {
      setError(t("admin:codingRuntimesLoadFailed"));
      return;
    }
    const data = (await r.json()) as Catalog;
    applyCatalog(data);
    void loadVersions(data.runtimes.map((rt) => rt.id));
  }, [applyCatalog, auth.accessToken, loadVersions, t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function runAction(
    id: string,
    mode: "install" | "update" | "uninstall",
    version?: string
  ) {
    if (!auth.accessToken) return;
    setBusyId(id);
    setError(null);
    setLog(null);
    const path =
      mode === "update"
        ? `/v1/admin/coding-runtimes/${id}/update`
        : mode === "uninstall"
          ? `/v1/admin/coding-runtimes/${id}/uninstall`
          : `/v1/admin/coding-runtimes/${id}/install`;
    const r = await fetch(path, {
      method: "POST",
      credentials: "include",
      headers: authHeaders(auth.accessToken),
      body:
        mode === "install"
          ? JSON.stringify({ version: (version || "latest").trim() || "latest" })
          : undefined,
    });
    const body = (await r.json().catch(() => ({}))) as {
      ok?: boolean;
      error?: string;
      log?: string;
      catalog?: Catalog;
      detail?: string;
    };
    setBusyId(null);
    if (body.log) setLog(body.log);
    if (!r.ok || body.ok === false) {
      setError(body.error || body.detail || t("admin:codingRuntimesInstallFailed"));
      if (body.catalog) applyCatalog(body.catalog);
      return;
    }
    if (body.catalog) applyCatalog(body.catalog);
    else await load();
  }

  async function saveFlags() {
    if (!auth.accessToken) return;
    setBusyId("__save__");
    setError(null);
    const r = await fetch("/v1/admin/coding-runtimes", {
      method: "PATCH",
      credentials: "include",
      headers: authHeaders(auth.accessToken),
      body: JSON.stringify({
        enabled_ids: [...enabled],
        preferred_id: preferred && enabled.has(preferred) ? preferred : "",
      }),
    });
    setBusyId(null);
    if (!r.ok) {
      setError(t("admin:codingRuntimesSaveFailed"));
      return;
    }
    applyCatalog((await r.json()) as Catalog);
  }

  function toggleEnabled(id: string, on: boolean) {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
    if (!on && preferred === id) setPreferred("");
    if (on && !preferred) setPreferred(id);
  }

  return (
    <PageShell density="wide" className="space-y-wide">
      <div>
        <h1 className="text-2xl font-semibold text-ink-primary">{t("admin:codingRuntimesTitle")}</h1>
        <p className="mt-base text-sm text-ink-muted">{t("admin:codingRuntimesIntro")}</p>
      </div>

      {loading && !catalog ? (
        <p className="text-sm text-ink-muted">{t("admin:codingRuntimesLoading")}</p>
      ) : null}
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}

      <ul className="space-y-wide">
        {(catalog?.runtimes ?? []).map((rt) => {
          const options = versionOptions[rt.id] ?? [{ value: "latest", label: "latest" }];
          const pick = versionPick[rt.id] ?? "latest";
          const loadingVers = versionsLoading[rt.id] === true;
          return (
            <li key={rt.id} className="rounded-card border border-line bg-card px-soft py-wide">
              <div className="flex flex-wrap items-start justify-between gap-base">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-soft">
                    <span className="text-sm font-medium text-ink-primary">{rt.label}</span>
                    <span
                      className={`text-xs font-medium ${rt.available ? "text-success" : "text-warning"}`}
                    >
                      {rt.available
                        ? t("admin:codingRuntimesAvailable")
                        : t("admin:codingRuntimesUnavailable")}
                    </span>
                    {rt.source === "image" ? (
                      <span className="text-xs text-ink-muted">
                        {t("admin:codingRuntimesSourceImage")}
                      </span>
                    ) : null}
                    {rt.source === "volume" ? (
                      <span className="text-xs text-ink-muted">
                        {t("admin:codingRuntimesSourceVolume")}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-tight text-xs text-ink-muted">
                    {rt.npm_package}
                    {rt.version ? ` · v${rt.version}` : ""}
                    {rt.installed ? "" : ` · ${t("admin:codingRuntimesNotInstalled")}`}
                  </p>
                  {rt.binary_path ? (
                    <p className="mt-tight break-all text-xs text-ink-muted">{rt.binary_path}</p>
                  ) : null}
                  {!rt.available && rt.reason ? (
                    <p className="mt-tight text-xs text-warning">{rt.reason}</p>
                  ) : null}
                  {rt.docs_url ? (
                    <a
                      href={rt.docs_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-tight inline-block text-xs text-badge-accent hover:underline"
                    >
                      {t("admin:codingRuntimesDocs")}
                    </a>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-soft">
                  <Button
                    type="button"
                    className="px-soft py-tight text-xs hover:bg-white/5"
                    disabled={busyId === rt.id}
                    onClick={() =>
                      void runAction(rt.id, rt.volume_installed ? "update" : "install", "latest")
                    }
                  >
                    {rt.volume_installed
                      ? t("admin:codingRuntimesUpdate")
                      : t("admin:codingRuntimesInstall")}
                  </Button>
                  <Button
                    type="button"
                    className="px-soft py-tight text-xs hover:bg-white/5"
                    disabled={busyId === rt.id || !rt.volume_installed}
                    onClick={() => void runAction(rt.id, "uninstall")}
                    title={
                      rt.volume_installed
                        ? undefined
                        : t("admin:codingRuntimesUninstallImageOnly")
                    }
                  >
                    {t("admin:codingRuntimesUninstall")}
                  </Button>
                </div>
              </div>

              <div className="mt-wide flex flex-wrap items-end gap-soft">
                <label className="flex w-full max-w-controlWide flex-1 flex-col gap-snug text-sm">
                  <span className="text-ink-muted">{t("admin:codingRuntimesVersion")}</span>
                  <Select
                    value={pick}
                    onChange={(ev) =>
                      setVersionPick((prev) => ({ ...prev, [rt.id]: ev.target.value }))
                    }
                    disabled={busyId === rt.id || loadingVers}
                  >
                    {options.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </Select>
                </label>
                <Button
                  type="button"
                  className="px-soft py-tight text-xs hover:bg-white/5"
                  disabled={busyId === rt.id || loadingVers || !pick}
                  onClick={() => void runAction(rt.id, "install", pick)}
                >
                  {t("admin:codingRuntimesInstallVersion")}
                </Button>
              </div>
              <p className="mt-tight text-xs text-ink-muted">
                {loadingVers
                  ? t("admin:codingRuntimesVersionsLoading")
                  : t("admin:codingRuntimesVersionHint")}
              </p>

              <label className="mt-wide flex cursor-pointer items-center gap-soft text-sm">
                <Checkbox
                  checked={enabled.has(rt.id)}
                  onChange={(ev) => toggleEnabled(rt.id, ev.target.checked)}
                />
                <span>{t("admin:codingRuntimesEnable")}</span>
              </label>
            </li>
          );
        })}
      </ul>

      <label className="flex max-w-controlWide flex-col gap-snug text-sm">
        <span className="text-ink-muted">{t("admin:codingRuntimesPreferred")}</span>
        <Select value={preferred} onChange={(ev) => setPreferred(ev.target.value)}>
          <option value="">{t("admin:codingRuntimesPreferredInternal")}</option>
          {(catalog?.runtimes ?? [])
            .filter((rt) => enabled.has(rt.id))
            .map((rt) => (
              <option key={rt.id} value={rt.id}>
                {rt.label}
              </option>
            ))}
        </Select>
      </label>

      <div className="flex flex-wrap gap-soft">
        <Button
          variant="primary"
          type="button"
          disabled={busyId !== null}
          onClick={() => void saveFlags()}
          className="px-wide py-firm text-sm"
        >
          {busyId === "__save__" ? t("admin:codingRuntimesSaving") : t("admin:codingRuntimesSave")}
        </Button>
        <Button
          type="button"
          disabled={loading || busyId !== null}
          onClick={() => void load()}
          className="px-wide py-firm text-sm hover:bg-white/5"
        >
          {t("admin:codingRuntimesRefresh")}
        </Button>
      </div>

      {log ? (
        <pre className="max-h-60 overflow-auto rounded-card border border-line bg-card p-soft text-xs text-ink-muted whitespace-pre-wrap">
          {log}
        </pre>
      ) : null}
    </PageShell>
  );
}
