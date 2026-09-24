import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthContext";
import { SchemaForm } from "../components/SchemaForm";
import { CollapsibleSidebarShell } from "../layout/CollapsibleSidebarShell";

type CatalogPreset = {
  run_key: string;
  title: string;
  description?: string;
  kind?: string;
  engine?: string;
  workflow_file?: string;
  inputs_schema: {
    type?: string;
    properties?: Record<string, Record<string, unknown>>;
    required?: string[];
  };
};

type CatalogPayload = {
  studio_version?: number;
  engine_default?: string;
  presets?: CatalogPreset[];
};

function buildInitialValues(
  preset: CatalogPreset | undefined
): Record<string, unknown> {
  if (!preset?.inputs_schema?.properties) return {};
  const out: Record<string, unknown> = {};
  const props = preset.inputs_schema.properties;
  for (const key of Object.keys(props)) {
    const p = props[key] as { default?: unknown; enum?: string[] };
    if (p.enum && p.enum.length > 0 && p.enum[0] === "") out[key] = "";
    else if (p.default !== undefined) out[key] = p.default;
  }
  return out;
}

export function StudioPage() {
  const { t } = useTranslation(["common"]);
  const { accessToken } = useAuth();
  const [catalog, setCatalog] = useState<CatalogPayload | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [selectedRunKey, setSelectedRunKey] = useState<string>("comfy_txt2img_default");
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [jobLoading, setJobLoading] = useState(false);
  const [jobError, setJobError] = useState<string | null>(null);
  const [jobResult, setJobResult] = useState<unknown>(null);
  const [presetSidebarOpen, setPresetSidebarOpen] = useState(false);

  const preset = useMemo(
    () => catalog?.presets?.find((p) => p.run_key === selectedRunKey),
    [catalog, selectedRunKey]
  );

  const txt2img = catalog?.presets?.find((p) => p.kind === "txt2img");
  const inpaint = catalog?.presets?.find((p) => p.kind === "inpaint");

  const selectPreset = useCallback((runKey: string) => {
    setSelectedRunKey(runKey);
    setPresetSidebarOpen(false);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const hdr: Record<string, string> = {};
        if (accessToken) hdr.Authorization = `Bearer ${accessToken}`;
        const r = await fetch("/v1/studio/catalog", { credentials: "include", headers: hdr });
        if (!r.ok) throw new Error(`catalog ${r.status}`);
        const data = (await r.json()) as CatalogPayload;
        if (!cancelled) {
          setCatalog(data);
          setCatalogError(null);
        }
      } catch (e) {
        if (!cancelled)
          setCatalogError(e instanceof Error ? e.message : t("common:studio.catalogLoadFailed"));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accessToken, t]);

  useEffect(() => {
    if (!preset) return;
    setValues(buildInitialValues(preset));
  }, [preset?.run_key, catalog?.studio_version]);

  const onFieldChange = useCallback((key: string, value: unknown) => {
    setValues((prev) => ({ ...prev, [key]: value }));
  }, []);

  const runJob = async () => {
    if (!preset) return;
    setJobLoading(true);
    setJobError(null);
    setJobResult(null);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

      const body = { run_key: preset.run_key, inputs: values };
      const r = await fetch("/v1/studio/jobs", {
        method: "POST",
        credentials: "include",
        headers,
        body: JSON.stringify(body),
      });
      const text = await r.text();
      let data: unknown;
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
      if (!r.ok) {
        setJobError(typeof data === "object" && data && "detail" in (data as object)
          ? String((data as { detail: unknown }).detail)
          : text || `HTTP ${r.status}`);
        return;
      }
      setJobResult(data);
    } catch (e) {
      setJobError(e instanceof Error ? e.message : t("common:studio.requestFailed"));
    } finally {
      setJobLoading(false);
    }
  };

  const schemaProps = preset?.inputs_schema?.properties as
    | Record<string, Record<string, unknown>>
    | undefined;
  const required = preset?.inputs_schema?.required ?? [];

  const previewUrlRaw =
    jobResult &&
    typeof jobResult === "object" &&
    jobResult !== null &&
    "primary_image" in jobResult &&
    (jobResult as { primary_image?: { data_url?: string } }).primary_image?.data_url;
  const previewUrl = typeof previewUrlRaw === "string" && previewUrlRaw ? previewUrlRaw : undefined;

  const presetButtonClass = (runKey: string, extra = "") =>
    [
      "w-full rounded-card border px-soft py-base text-left text-sm",
      selectedRunKey === runKey
        ? "border-white/30 bg-white/10 text-ink-primary"
        : "border-transparent text-ink-muted hover:bg-white/5",
      extra,
    ]
      .filter(Boolean)
      .join(" ");

  return (
    <CollapsibleSidebarShell
      className="bg-canvas"
      mobileOpen={presetSidebarOpen}
      onMobileOpenChange={setPresetSidebarOpen}
      sidebarAriaLabel={t("common:studio.presetsSidebarAria")}
      closeSidebarAriaLabel={t("common:studio.closePresetsSidebar")}
      desktopWidthClass="md:w-56"
      sidebar={
        <div className="flex h-full min-h-0 flex-col overflow-y-auto p-soft">
          <p className="mb-base text-xs font-semibold uppercase tracking-wide text-ink-muted">
            {t("common:studio.title")}
          </p>
          {txt2img ? (
            <button
              type="button"
              onClick={() => selectPreset(txt2img.run_key)}
              className={presetButtonClass(txt2img.run_key, "mb-tight")}
            >
              <div className="font-medium">{txt2img.title}</div>
              <div className="text-xs text-ink-muted">{txt2img.engine ?? "comfyui"}</div>
            </button>
          ) : null}

          <p className="mb-base mt-broad text-xs font-semibold uppercase tracking-wide text-ink-muted">
            {t("common:studio.inpaint")}
          </p>
          {inpaint ? (
            <button
              type="button"
              onClick={() => selectPreset(inpaint.run_key)}
              className={presetButtonClass(inpaint.run_key)}
            >
              <div className="font-medium">{inpaint.title}</div>
              <div className="text-xs text-ink-muted">{inpaint.engine ?? "comfyui"}</div>
            </button>
          ) : null}
        </div>
      }
    >
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto p-wide md:p-deep">
        <div className="flex flex-wrap items-start gap-base">
          <button
            type="button"
            className="shrink-0 rounded-card border border-line bg-black/30 px-firm py-snug text-meta font-medium text-ink-secondary hover:bg-white/10 md:hidden"
            aria-expanded={presetSidebarOpen}
            aria-label={t("common:studio.openPresetsSidebar")}
            onClick={() => setPresetSidebarOpen(true)}
          >
            {t("common:studio.openPresetsSidebarShort")}
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-semibold text-ink-primary">{t("common:studio.title")}</h1>
            <p className="mt-tight max-w-measure text-sm text-ink-muted">{t("common:studio.subtitle")}</p>
          </div>
        </div>

        {catalogError ? (
          <p className="mt-wide rounded-card border border-red-900/50 bg-red-950/40 px-soft py-base text-sm text-red-200">
            {catalogError}
          </p>
        ) : null}

        {catalog && !catalogError ? (
          <div className="mt-wide flex flex-wrap items-center gap-base text-sm">
            <span className="rounded-pill bg-emerald-950/80 px-base py-hair text-emerald-300">
              {t("common:studio.catalogFromServer")}
            </span>
            <span className="text-ink-muted">v{catalog.studio_version ?? "?"}</span>
            <span className="text-ink-muted">
              Default engine: {catalog.engine_default ?? "—"}
            </span>
            <button
              type="button"
              className="text-sky-400 underline hover:text-sky-300"
              onClick={() => window.location.reload()}
            >
              {t("common:studio.reloadCatalog")}
            </button>
          </div>
        ) : null}

        {preset ? (
          <div className="mt-deep max-w-measure">
            <h2 className="text-lg font-medium text-ink-primary">{preset.title}</h2>
            <p className="mt-base whitespace-pre-wrap text-sm text-ink-muted">
              {preset.description}
            </p>
            <p className="mt-base font-mono text-xs text-ink-muted">
              run_key: {preset.run_key}
              {preset.workflow_file ? ` · ${preset.workflow_file}` : ""}
            </p>

            {schemaProps ? (
              <div className="mt-broad">
                <SchemaForm
                  properties={schemaProps}
                  required={required}
                  values={values}
                  onChange={onFieldChange}
                />
              </div>
            ) : null}

            <div className="mt-deep flex flex-wrap items-center gap-soft">
              <button
                type="button"
                disabled={jobLoading}
                onClick={() => void runJob()}
                className="rounded-sheet bg-white px-roomy py-firm text-sm font-semibold text-black hover:bg-neutral-200 disabled:opacity-50"
              >
                {jobLoading ? t("common:studio.running") : t("common:studio.run")}
              </button>
              <code className="text-xs text-ink-muted">POST /v1/studio/jobs</code>
            </div>

            {jobError ? (
              <p className="mt-wide rounded-card border border-red-900/50 bg-red-950/40 px-soft py-base text-sm text-red-200">
                {jobError}
              </p>
            ) : null}

            {previewUrl ? (
              <div className="mt-broad">
                <p className="mb-base text-sm text-ink-secondary">{t("common:studio.result")}</p>
                <img
                  src={previewUrl}
                  alt={t("common:studio.generatedImageAlt")}
                  className="max-h-[480px] max-w-full rounded-card border border-line"
                />
              </div>
            ) : jobResult ? (
              <pre className="mt-wide max-h-64 overflow-auto rounded-card border border-line bg-[#111] p-soft text-xs text-ink-secondary">
                {JSON.stringify(jobResult, null, 2)}
              </pre>
            ) : null}
          </div>
        ) : catalog && !catalogError ? (
          <p className="mt-deep text-ink-muted">{t("common:studio.noPresetSelected")}</p>
        ) : null}
      </div>
    </CollapsibleSidebarShell>
  );
}
