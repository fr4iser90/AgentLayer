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
import { TextArea } from "../../../ui/Field";
import { Button } from "../../../ui/Button";

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
    <section className="rounded-sheet border border-warning/20 bg-warning-subtle p-wide">
      <div className="flex flex-wrap items-start justify-between gap-base">
        <div>
          <h3 className="text-xs font-medium uppercase text-badge-warning">
            {t("admin:benchRunOverridesTitle")}
            {overrides.length > 0 ? (
              <span className="ml-base rounded-tile bg-warning-subtle px-snug py-hair text-meta text-badge-warning">
                {overrides.length}
              </span>
            ) : null}
          </h3>
          <p className="mt-tight max-w-measure text-meta text-ink-muted">
            {t("admin:benchRunOverridesHint")}
          </p>
        </div>
        <Link
          to="/admin/agent-config"
          className="shrink-0 text-meta text-accent hover:underline"
        >
          {t("admin:benchHarnessContextEdit")} →
        </Link>
      </div>

      {error ? (
        <p className="mt-base rounded-tile border border-danger/40 bg-danger-subtle px-base py-tight text-xs text-badge-danger">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="mt-wide text-sm text-ink-muted">{t("admin:loading")}</p>
      ) : (
        <div className="mt-wide grid min-h-[280px] gap-wide md:grid-cols-2">
          <section className="min-h-0 overflow-auto rounded-card border border-line bg-[#111] p-soft">
            <h4 className="mb-base text-sm font-medium text-ink-primary">{t("admin:agentConfigKnobs")}</h4>
            <ul className="space-y-tight">
              {knobs.map((k) => {
                const ov = overrideMap.get(k.id);
                const active = selectedId === k.id;
                const overridden = overrideMap.has(k.id);
                return (
                  <li key={k.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(k.id)}
                      className={`w-full rounded-tile px-base py-snug text-left text-sm ${
                        active ? "bg-white/10 text-ink-primary" : "text-ink-muted hover:bg-white/5"
                      }`}
                    >
                      <span className="font-mono text-xs">{k.id}</span>
                      {overridden ? (
                        <span className="ml-base text-meta uppercase text-warning">
                          {t("admin:benchRunOverrideActive")}
                        </span>
                      ) : null}
                      <span
                        className={`ml-base text-xs ${overridden ? "text-badge-warning" : "opacity-70"}`}
                      >
                        {formatKnobValue(k, ov)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>

          <section className="flex min-h-0 flex-col gap-soft overflow-auto rounded-card border border-line bg-[#111] p-soft">
            <h4 className="text-sm font-medium text-ink-primary">{t("admin:benchRunOverrideEditTitle")}</h4>
            {selected ? (
              <>
                <p className="text-xs text-ink-muted">
                  {selected.layer ? `[${selected.layer}] ` : ""}
                  {selected.doc}
                </p>

                <div className="rounded-tile border border-line/60 bg-black/20 p-base text-xs text-ink-muted">
                  <p className="font-medium text-white/90">{t("admin:benchRunOverrideHarnessBaseline")}</p>
                  <p className="mt-tight font-mono">{formatKnobValue(selected, undefined)}</p>
                  <p className="mt-base">
                    {t("admin:agentConfigEffectiveSource")}: {formatKnobSource(selected.source, t as any)}
                  </p>
                </div>

                {hasOverride ? (
                  <div className="rounded-tile border border-warning/30 bg-warning-subtle p-base text-xs">
                    <p className="font-medium text-badge-warning">{t("admin:benchRunOverrideForRun")}</p>
                    <p className="mt-tight font-mono text-badge-warning">{formatKnobValue(selected, selectedOverride)}</p>
                  </div>
                ) : null}

                <div className="rounded-tile border border-blue-500/30 bg-blue-500/5 p-base text-xs text-blue-100/90">
                  {t(`admin:${knobHelpKey(selected.id)}`, {
                    defaultValue: selected.doc || selected.id,
                  })}
                </div>

                <label className="text-xs text-ink-muted">{t("admin:benchRunOverrideValueLabel")}</label>
                <TextArea
                  mono
                  className="min-h-[80px]"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                />

                <div className="flex flex-wrap gap-base">
                  <Button
                    variant="primary"
                    tone="warning"
                    type="button"
                    onClick={() => setOverrideForKnob(selected)}
                    className="px-soft py-base text-sm"
                  >
                    {t("admin:benchRunOverrideSetBtn")}
                  </Button>
                  {hasOverride ? (
                    <Button
                      type="button"
                      onClick={() => clearOverride(selected.id)}
                      className="px-soft py-base text-sm text-ink-muted hover:bg-white/5"
                    >
                      {t("admin:benchRunOverrideUseHarness")}
                    </Button>
                  ) : null}
                </div>
              </>
            ) : (
              <p className="text-sm text-ink-muted">{t("admin:agentConfigSelectKnob")}</p>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
