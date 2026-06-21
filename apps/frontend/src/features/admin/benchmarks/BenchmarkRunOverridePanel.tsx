/**
 * Run-level harness overrides — same knob-picker UX as Harness page, but applies only to this benchmark run.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { AuthContextValue } from "../../../auth/AuthContext";
import {
  fetchAgentConfigKnobs,
  isHarnessKnob,
  type AgentConfigKnob,
} from "../agentConfig/agentConfigApi";

export type RunOverridePatch = { knob_id: string; value: unknown };

function knobHelpKey(id: string) {
  return `harnessKnobHelp_${id.replace(/\./g, "_")}`;
}

function formatKnobValue(knob: AgentConfigKnob, override: unknown | undefined): string {
  const v = override !== undefined ? override : knob.effective;
  if (v === null || v === undefined) {
    if (knob.effective_label) return knob.effective_label;
    if (knob.id === "tool_routing.domain_order") return "(scan order)";
    return "—";
  }
  if (typeof v === "boolean") return v ? "true" : "false";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "[]";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function valueForEdit(knob: AgentConfigKnob, override: unknown | undefined): string {
  const v = override !== undefined ? override : knob.effective ?? knob.default ?? "";
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

function parseKnobValue(knob: AgentConfigKnob, raw: string): unknown {
  if (knob.type === "integer") {
    const n = parseInt(raw, 10);
    if (!Number.isFinite(n)) throw new Error("expected integer");
    return n;
  }
  if (knob.type === "number") {
    const n = Number(raw);
    if (!Number.isFinite(n)) throw new Error("expected number");
    return n;
  }
  if (knob.type === "boolean") {
    if (raw === "true") return true;
    if (raw === "false") return false;
    throw new Error("expected true or false");
  }
  if (knob.type === "string_list") {
    if (raw.trim().startsWith("[")) return JSON.parse(raw);
    return JSON.parse(raw || "[]");
  }
  if (knob.type === "json") return JSON.parse(raw || "{}");
  return raw;
}

function formatKnobSource(
  source: string | undefined,
  t: (key: string, opts?: { defaultValue?: string }) => string,
): string {
  if (!source) return "—";
  const key = `agentConfigSource_${source}`;
  return t(`admin:${key}`, { defaultValue: source });
}

type Props = {
  auth: AuthContextValue;
  overrides: RunOverridePatch[];
  onChange: (overrides: RunOverridePatch[]) => void;
};

export function BenchmarkRunOverridePanel({ auth, overrides, onChange }: Props) {
  const { t } = useTranslation(["admin"]);
  const [knobs, setKnobs] = useState<AgentConfigKnob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [editValue, setEditValue] = useState("");

  const overrideMap = useMemo(
    () => new Map(overrides.map((p) => [p.knob_id, p.value])),
    [overrides],
  );

  const reload = useCallback(async () => {
    if (!auth.accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAgentConfigKnobs(auth, { harness_only: true });
      const list = (res.knobs || []).filter((k) => isHarnessKnob(k) && k.writable !== false);
      setKnobs(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!selectedId && knobs[0]?.id) setSelectedId(knobs[0].id);
  }, [knobs, selectedId]);

  const selected = knobs.find((k) => k.id === selectedId);
  const selectedOverride = selected ? overrideMap.get(selected.id) : undefined;
  const hasOverride = selected ? overrideMap.has(selected.id) : false;

  useEffect(() => {
    if (!selected) {
      setEditValue("");
      return;
    }
    setEditValue(valueForEdit(selected, selectedOverride));
  }, [selected, selectedOverride]);

  function setOverrideForKnob(knob: AgentConfigKnob) {
    try {
      const value = parseKnobValue(knob, editValue);
      const next = overrides.filter((p) => p.knob_id !== knob.id);
      next.push({ knob_id: knob.id, value });
      onChange(next);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function clearOverride(knobId: string) {
    onChange(overrides.filter((p) => p.knob_id !== knobId));
    setError(null);
  }

  return (
    <section className="rounded-xl border border-amber-500/20 bg-amber-950/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-xs font-medium uppercase text-amber-200/90">
            {t("admin:benchRunOverridesTitle")}
            {overrides.length > 0 ? (
              <span className="ml-2 rounded bg-amber-600/40 px-1.5 py-0.5 text-[10px] text-amber-100">
                {overrides.length}
              </span>
            ) : null}
          </h3>
          <p className="mt-1 max-w-prose text-[11px] text-surface-muted">
            {t("admin:benchRunOverridesHint")}
          </p>
        </div>
        <Link
          to="/admin/agent-config"
          className="shrink-0 text-[11px] text-sky-400 hover:underline"
        >
          {t("admin:benchHarnessContextEdit")} →
        </Link>
      </div>

      {error ? (
        <p className="mt-2 rounded border border-red-500/40 bg-red-500/10 px-2 py-1 text-xs text-red-200">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="mt-4 text-sm text-surface-muted">{t("admin:loading")}</p>
      ) : (
        <div className="mt-4 grid min-h-[280px] gap-4 md:grid-cols-2">
          <section className="min-h-0 overflow-auto rounded-lg border border-surface-border bg-[#111] p-3">
            <h4 className="mb-2 text-sm font-medium text-white">{t("admin:agentConfigKnobs")}</h4>
            <ul className="space-y-1">
              {knobs.map((k) => {
                const ov = overrideMap.get(k.id);
                const active = selectedId === k.id;
                const overridden = overrideMap.has(k.id);
                return (
                  <li key={k.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(k.id)}
                      className={`w-full rounded px-2 py-1.5 text-left text-sm ${
                        active ? "bg-white/10 text-white" : "text-surface-muted hover:bg-white/5"
                      }`}
                    >
                      <span className="font-mono text-xs">{k.id}</span>
                      {overridden ? (
                        <span className="ml-2 text-[10px] uppercase text-amber-400/90">
                          {t("admin:benchRunOverrideActive")}
                        </span>
                      ) : null}
                      <span
                        className={`ml-2 text-xs ${overridden ? "text-amber-200/90" : "opacity-70"}`}
                      >
                        {formatKnobValue(k, ov)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>

          <section className="flex min-h-0 flex-col gap-3 overflow-auto rounded-lg border border-surface-border bg-[#111] p-3">
            <h4 className="text-sm font-medium text-white">{t("admin:benchRunOverrideEditTitle")}</h4>
            {selected ? (
              <>
                <p className="text-xs text-surface-muted">
                  {selected.layer ? `[${selected.layer}] ` : ""}
                  {selected.doc}
                </p>

                <div className="rounded border border-surface-border/60 bg-black/20 p-2 text-xs text-surface-muted">
                  <p className="font-medium text-white/90">{t("admin:benchRunOverrideHarnessBaseline")}</p>
                  <p className="mt-1 font-mono">{formatKnobValue(selected, undefined)}</p>
                  <p className="mt-2">
                    {t("admin:agentConfigEffectiveSource")}: {formatKnobSource(selected.source, t as any)}
                  </p>
                </div>

                {hasOverride ? (
                  <div className="rounded border border-amber-500/30 bg-amber-950/30 p-2 text-xs">
                    <p className="font-medium text-amber-100/90">{t("admin:benchRunOverrideForRun")}</p>
                    <p className="mt-1 font-mono text-amber-200">{formatKnobValue(selected, selectedOverride)}</p>
                  </div>
                ) : null}

                <div className="rounded border border-blue-500/30 bg-blue-500/5 p-2 text-xs text-blue-100/90">
                  {t(`admin:${knobHelpKey(selected.id)}`, {
                    defaultValue: selected.doc || selected.id,
                  })}
                </div>

                <label className="text-xs text-surface-muted">{t("admin:benchRunOverrideValueLabel")}</label>
                <textarea
                  className="min-h-[80px] w-full rounded border border-surface-border bg-black/30 p-2 font-mono text-sm text-white"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                />

                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setOverrideForKnob(selected)}
                    className="rounded bg-amber-700 px-3 py-2 text-sm text-white hover:bg-amber-600"
                  >
                    {t("admin:benchRunOverrideSetBtn")}
                  </button>
                  {hasOverride ? (
                    <button
                      type="button"
                      onClick={() => clearOverride(selected.id)}
                      className="rounded border border-white/15 px-3 py-2 text-sm text-surface-muted hover:bg-white/5"
                    >
                      {t("admin:benchRunOverrideUseHarness")}
                    </button>
                  ) : null}
                </div>
              </>
            ) : (
              <p className="text-sm text-surface-muted">{t("admin:agentConfigSelectKnob")}</p>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
