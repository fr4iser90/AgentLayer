import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AuthContextValue } from "../../../auth/AuthContext";
import {
  applyAgentConfigPatches,
  fetchAgentConfigFingerprint,
  fetchAgentConfigKnobs,
  initializeAgentConfigDefaults,
  isHarnessKnob,
  type AgentConfigKnob,
} from "../agentConfig/agentConfigApi";

const PREFLIGHT_KNOB_IDS = [
  "agent.max_tool_rounds",
  "agent.subagent_max_tool_rounds",
  "tool_forward.ranking_enabled",
  "tool_forward.catalog_after_first_round",
  "agent.tool_choice_required_retry",
  "tool_routing.router_strict_default",
  "operator.delegate_enabled",
  "agent.general.pinned_tools",
] as const;

function formatEffective(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "boolean") return value ? "on" : "off";
  if (Array.isArray(value)) {
    const parts = value.map((x) => String(x));
    if (parts.length <= 4) return parts.join(", ");
    return `${parts.slice(0, 4).join(", ")} +${parts.length - 4}`;
  }
  const s = String(value);
  return s.length > 80 ? `${s.slice(0, 77)}…` : s;
}

function sourceLabel(
  source: string | undefined,
  t: (key: string) => string,
): string {
  switch (source) {
    case "db_override":
      return t("admin:benchConfigSourceDb");
    case "registry_default":
      return t("admin:benchConfigSourceRegistry");
    case "file_default":
      return t("admin:benchConfigSourceFile");
    case "operator_settings":
      return t("admin:benchConfigSourceOperator");
    default:
      return source || "—";
  }
}

function valueForEdit(knob: AgentConfigKnob | undefined): string {
  if (!knob) return "";
  const v = knob.effective ?? knob.default ?? "";
  if (typeof v === "string") return v;
  return JSON.stringify(v, null, 2);
}

type Props = {
  auth: AuthContextValue;
};

export function BenchmarkConfigPreflightPanel({ auth }: Props) {
  const { t } = useTranslation(["admin"]);
  const [knobs, setKnobs] = useState<AgentConfigKnob[]>([]);
  const [fingerprint, setFingerprint] = useState("");
  const [gitSha, setGitSha] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [initBusy, setInitBusy] = useState(false);
  const [editKnobId, setEditKnobId] = useState("");
  const [editValue, setEditValue] = useState("");
  const [applyBusy, setApplyBusy] = useState(false);

  const writableKnobs = useMemo(
    () => knobs.filter((k) => isHarnessKnob(k) && k.writable !== false),
    [knobs],
  );

  const reload = useCallback(async () => {
    if (!auth.accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const [k, fp] = await Promise.all([
        fetchAgentConfigKnobs(auth),
        fetchAgentConfigFingerprint(auth),
      ]);
      setKnobs(k.knobs || []);
      setFingerprint(String(fp.fingerprint || ""));
      setGitSha(String(fp.git_sha || ""));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const byId = new Map(knobs.map((k) => [k.id, k]));
  const summaryKnobs = PREFLIGHT_KNOB_IDS.map((id) => byId.get(id)).filter(
    (k): k is AgentConfigKnob => Boolean(k),
  );
  const moreKnobs = writableKnobs.filter(
    (k) => !PREFLIGHT_KNOB_IDS.includes(k.id as (typeof PREFLIGHT_KNOB_IDS)[number]),
  );

  const selectedKnob = writableKnobs.find((k) => k.id === editKnobId);

  useEffect(() => {
    setEditValue(valueForEdit(selectedKnob));
  }, [selectedKnob]);

  async function onInitialize() {
    setInitBusy(true);
    setError(null);
    try {
      await initializeAgentConfigDefaults(auth, false);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setInitBusy(false);
    }
  }

  async function onApplyKnob() {
    if (!editKnobId || !selectedKnob) return;
    setApplyBusy(true);
    setError(null);
    try {
      let value: unknown = editValue;
      if (selectedKnob.type === "integer") value = parseInt(editValue, 10);
      else if (selectedKnob.type === "boolean") value = editValue === "true";
      else if (selectedKnob.type === "string_list") value = JSON.parse(editValue || "[]");
      else if (selectedKnob.type === "json") value = JSON.parse(editValue || "{}");
      await applyAgentConfigPatches(auth, { patches: [{ knob_id: editKnobId, value }] });
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setApplyBusy(false);
    }
  }

  const needsDbInit = summaryKnobs.some((k) => k.source !== "db_override" && k.source !== "operator_settings");

  return (
    <section className="rounded-xl border border-indigo-500/25 bg-indigo-950/20 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-xs font-medium uppercase text-indigo-200/90">
            {t("admin:benchConfigPreflightTitle")}
          </h3>
          <p className="mt-1 max-w-prose text-[11px] text-surface-muted">
            {t("admin:benchConfigPreflightHint")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void reload()}
            disabled={loading}
            className="rounded border border-white/10 px-2 py-1 text-[11px] text-white hover:bg-white/5 disabled:opacity-50"
          >
            {loading ? t("admin:loading") : t("admin:benchConfigPreflightRefresh")}
          </button>
          {needsDbInit ? (
            <button
              type="button"
              onClick={() => void onInitialize()}
              disabled={initBusy || loading}
              className="rounded border border-amber-500/40 bg-amber-950/40 px-2 py-1 text-[11px] text-amber-100 hover:bg-amber-950/60 disabled:opacity-50"
            >
              {initBusy ? t("admin:loading") : t("admin:benchConfigPreflightInitDb")}
            </button>
          ) : null}
        </div>
      </div>

      {error ? <p className="mt-2 text-xs text-red-300">{error}</p> : null}

      {loading && !fingerprint ? (
        <p className="mt-3 text-xs text-surface-muted">{t("admin:loading")}</p>
      ) : (
        <>
          {fingerprint ? (
            <p className="mt-2 break-all font-mono text-[10px] text-surface-muted">
              {gitSha && gitSha !== "unknown" ? `${gitSha.slice(0, 12)} · ` : ""}
              {fingerprint.slice(0, 48)}…
            </p>
          ) : null}
          <ul className="mt-3 grid gap-1.5 sm:grid-cols-2">
            {summaryKnobs.map((k) => (
              <li
                key={k.id}
                className="rounded border border-white/5 bg-black/25 px-2 py-1.5 text-[11px]"
              >
                <span className="font-mono text-white/80">{k.id}</span>
                <span className="ml-2 text-surface-muted">{formatEffective(k.effective)}</span>
                <span
                  className={`ml-1 text-[10px] ${
                    k.source === "db_override" ? "text-emerald-400/90" : "text-amber-300/80"
                  }`}
                >
                  ({sourceLabel(k.source, t)})
                </span>
              </li>
            ))}
          </ul>

          <div className="mt-4 rounded-lg border border-white/10 bg-black/30 p-3">
            <h4 className="text-[11px] font-medium uppercase text-surface-muted">
              {t("admin:benchConfigQuickEdit")}
            </h4>
            <p className="mt-1 text-[10px] text-surface-muted">{t("admin:benchConfigQuickEditHint")}</p>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <select
                value={editKnobId}
                onChange={(e) => setEditKnobId(e.target.value)}
                className="rounded border border-white/10 bg-black/40 px-2 py-1.5 text-xs text-white"
              >
                <option value="">{t("admin:agentConfigSelectKnob")}</option>
                {writableKnobs.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.id}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={!editKnobId || applyBusy}
                onClick={() => void onApplyKnob()}
                className="rounded bg-emerald-700/90 px-2 py-1.5 text-xs text-white hover:bg-emerald-600 disabled:opacity-50"
              >
                {applyBusy ? t("admin:agentConfigApplying") : t("admin:agentConfigApplyBtn")}
              </button>
            </div>
            {selectedKnob ? (
              <textarea
                className="mt-2 min-h-[72px] w-full rounded border border-white/10 bg-black/40 p-2 font-mono text-[11px] text-white"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
              />
            ) : null}
          </div>

          {moreKnobs.length > 0 ? (
            <div className="mt-2">
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="text-[11px] text-sky-400 hover:underline"
              >
                {expanded
                  ? t("admin:benchConfigPreflightLess")
                  : t("admin:benchConfigPreflightMore", { count: moreKnobs.length })}
              </button>
              {expanded ? (
                <ul className="mt-2 grid gap-1 sm:grid-cols-2">
                  {moreKnobs.map((k) => (
                    <li
                      key={k.id}
                      className="rounded border border-white/5 bg-black/20 px-2 py-1 text-[10px] font-mono text-surface-muted"
                    >
                      {k.id}: {formatEffective(k.effective)}{" "}
                      <span className="text-[9px]">({sourceLabel(k.source, t)})</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
