import { FormEvent, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { evaluateFormula } from "./formulaEval";

export type FormulaInputOption = {
  label: string;
  value: number;
};

export type FormulaInputDef = {
  key: string;
  label: string;
  optional?: boolean;
  /** number (default) | select | percent (UI shows %, formula uses fraction 0–1) */
  control?: "number" | "select" | "percent";
  options?: FormulaInputOption[];
  defaultValue?: number;
  step?: number;
  placeholder?: string;
};

export type FormulaOutputDef = {
  key: string;
  label: string;
  expr: string;
};

type Props = {
  title?: string;
  disclaimer?: string;
  formulaNote?: string;
  inputs: FormulaInputDef[];
  outputs: FormulaOutputDef[];
  readOnly?: boolean;
};

function initialValues(inputs: FormulaInputDef[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const inp of inputs) {
    if (inp.defaultValue === undefined || !Number.isFinite(inp.defaultValue)) continue;
    if (inp.control === "percent") {
      out[inp.key] = String(inp.defaultValue * 100);
    } else {
      out[inp.key] = String(inp.defaultValue);
    }
  }
  return out;
}

export function FormulaCalcBlockBody({
  title,
  disclaimer,
  formulaNote,
  inputs,
  outputs,
  readOnly,
}: Props) {
  const { t } = useTranslation(["dashboard"]);
  const inputDefs = useMemo(() => (Array.isArray(inputs) ? inputs : []), [inputs]);
  const outputDefs = useMemo(() => (Array.isArray(outputs) ? outputs : []), [outputs]);
  const [values, setValues] = useState<Record<string, string>>(() => initialValues(inputDefs));
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, number> | null>(null);

  useEffect(() => {
    setValues(initialValues(inputDefs));
    setResults(null);
    setError(null);
  }, [inputDefs]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (readOnly) return;
    setError(null);
    const nums: Record<string, number> = {};
    try {
      for (const inp of inputDefs) {
        const raw = (values[inp.key] ?? "").trim();
        if (!raw) {
          if (inp.defaultValue !== undefined && Number.isFinite(inp.defaultValue)) {
            nums[inp.key] = inp.defaultValue;
            continue;
          }
          if (inp.optional) continue;
          throw new Error(t("dashboard:formulaMissingInput", { key: inp.label || inp.key }));
        }
        const n = Number(raw);
        if (!Number.isFinite(n)) {
          throw new Error(t("dashboard:formulaBadNumber", { key: inp.label || inp.key }));
        }
        if (inp.control === "percent") {
          if (n < 0 || n > 100) {
            throw new Error(t("dashboard:formulaBadPercent", { key: inp.label || inp.key }));
          }
          nums[inp.key] = n / 100;
        } else {
          nums[inp.key] = n;
        }
      }
      const out: Record<string, number> = {};
      for (const o of outputDefs) {
        out[o.key] = evaluateFormula(o.expr, nums);
      }
      setResults(out);
    } catch (err) {
      setResults(null);
      setError(err instanceof Error ? err.message : t("dashboard:formulaFailed"));
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-soft overflow-auto p-tight text-sm">
      {title ? <h3 className="font-medium text-ink-primary">{title}</h3> : null}
      {(disclaimer || t("dashboard:formulaDisclaimer")) && (
        <p className="rounded-tile border border-warning/30 bg-warning-subtle px-base py-tight text-xs text-badge-warning">
          {disclaimer || t("dashboard:formulaDisclaimer")}
        </p>
      )}
      <form onSubmit={onSubmit} className="space-y-base">
        {inputDefs.map((inp) => {
          const control = inp.control || "number";
          if (control === "select" && Array.isArray(inp.options) && inp.options.length > 0) {
            return (
              <label key={inp.key} className="block text-xs text-ink-muted">
                {inp.label}
                <select
                  className="mt-tight w-full rounded-tile border border-line bg-field px-base py-snug text-sm text-ink-primary"
                  disabled={readOnly}
                  value={values[inp.key] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [inp.key]: e.target.value }))}
                  required={!inp.optional}
                >
                  <option value="">{t("dashboard:formulaSelectPlaceholder")}</option>
                  {inp.options.map((opt) => (
                    <option key={`${inp.key}-${opt.value}`} value={String(opt.value)}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
            );
          }
          return (
            <label key={inp.key} className="block text-xs text-ink-muted">
              {inp.label}
              {control === "percent" ? (
                <span className="ml-tight text-meta opacity-70">{t("dashboard:formulaPercentHint")}</span>
              ) : null}
              <div className="relative mt-tight">
                <input
                  className="w-full rounded-tile border border-line bg-field px-base py-snug text-sm text-ink-primary"
                  type="number"
                  step={inp.step ?? (control === "percent" ? 1 : "any")}
                  disabled={readOnly}
                  placeholder={inp.placeholder}
                  value={values[inp.key] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [inp.key]: e.target.value }))}
                  required={!inp.optional}
                />
                {control === "percent" ? (
                  <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-xs text-ink-muted">
                    %
                  </span>
                ) : null}
              </div>
            </label>
          );
        })}
        {!readOnly ? (
          <button
            type="submit"
            className="rounded-tile bg-accent px-soft py-snug text-xs font-medium text-ink-on-fill hover:bg-accent-hover"
          >
            {t("dashboard:formulaCalculate")}
          </button>
        ) : null}
      </form>
      {formulaNote ? <p className="font-mono text-meta text-ink-muted">{formulaNote}</p> : null}
      {error ? <p className="text-xs text-badge-danger">{error}</p> : null}
      {results ? (
        <ul className="space-y-tight text-ink-primary">
          {outputDefs.map((o) => (
            <li key={o.key}>
              <span className="text-ink-muted">{o.label}: </span>
              {Number.isFinite(results[o.key]) ? results[o.key].toFixed(4).replace(/\.?0+$/, "") : "—"}
              <span className="ml-base font-mono text-meta text-ink-muted">{o.expr}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
