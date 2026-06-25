import { useEffect, useMemo, useRef, useState } from "react";
import {
  catalogModelOptionUnreachableTitle,
  catalogRowForSelection,
  compactModelDisplayName,
  isCatalogModelOptionDisabled,
  modelCapabilityBadges,
  modelCatalogSelectValue,
  parseModelCatalogSelection,
  providerDisplayLabel,
  type ModelCatalogAgentlayer,
  type ModelCapabilityBadge,
  type ModelRow,
} from "../../lib/modelCatalog";

type ModelCatalogSelectProps = {
  rows: ModelRow[];
  agentlayer: ModelCatalogAgentlayer | null;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  loading?: boolean;
  loadingLabel: string;
  emptyLabel: string;
  ariaLabel: string;
  size?: "sm" | "md";
};

const CHIP_TONES: Record<ModelCapabilityBadge["tone"], string> = {
  text: "border-sky-400/30 bg-sky-500/10 text-sky-100",
  vision: "border-violet-400/35 bg-violet-500/15 text-violet-100",
  audio: "border-amber-400/35 bg-amber-500/15 text-amber-100",
  context: "border-emerald-400/35 bg-emerald-500/15 text-emerald-100",
};

function ModelBadge({ badge, compact = false }: { badge: ModelCapabilityBadge; compact?: boolean }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border px-1.5 py-0.5 font-medium ${compact ? "text-[9px]" : "text-[10px]"} ${CHIP_TONES[badge.tone]}`}
    >
      {badge.label}
    </span>
  );
}

function selectedLabel(row: ModelRow | undefined, value: string): string {
  if (row) return compactModelDisplayName(row.id, 38);
  const parsed = parseModelCatalogSelection(value);
  return compactModelDisplayName(parsed.modelId || value, 38);
}

export function ModelCatalogSelect({
  rows,
  agentlayer,
  value,
  onChange,
  disabled = false,
  loading = false,
  loadingLabel,
  emptyLabel,
  ariaLabel,
  size = "md",
}: ModelCatalogSelectProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const selected = useMemo(() => catalogRowForSelection(rows, value), [rows, value]);
  const selectedProvider = selected?.owned_by
    ? providerDisplayLabel(selected.owned_by, agentlayer)
    : undefined;
  const selectedBadges = selected ? modelCapabilityBadges(selected) : [];
  const isDisabled = disabled || loading || rows.length === 0;
  const buttonTextSize = size === "sm" ? "text-xs" : "text-sm";
  const buttonPadding = size === "sm" ? "px-2 py-1.5" : "px-2.5 py-1.5";

  useEffect(() => {
    if (!open) return;
    function onPointerDown(ev: PointerEvent) {
      if (!rootRef.current?.contains(ev.target as Node)) setOpen(false);
    }
    function onKeyDown(ev: KeyboardEvent) {
      if (ev.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        className={`mt-0.5 flex w-full items-center justify-between gap-2 rounded-lg border border-surface-border bg-[#1a1a1a] ${buttonPadding} text-left text-neutral-100 shadow-sm outline-none transition hover:border-sky-500/45 hover:bg-[#202020] focus:border-sky-400/70 focus:ring-2 focus:ring-sky-500/20 disabled:cursor-not-allowed disabled:opacity-60 ${buttonTextSize}`}
        disabled={isDisabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium">
            {loading ? loadingLabel : rows.length === 0 ? emptyLabel : selectedLabel(selected, value)}
          </span>
          {selectedProvider ? (
            <span className="block truncate text-[10px] text-surface-muted">{selectedProvider}</span>
          ) : null}
        </span>
        {selectedBadges.length > 0 ? (
          <span className="hidden max-w-[45%] shrink-0 flex-wrap justify-end gap-1 sm:flex">
            {selectedBadges.map((badge) => (
              <ModelBadge key={badge.key} badge={badge} compact={size === "sm"} />
            ))}
          </span>
        ) : null}
        <span className="shrink-0 text-surface-muted">v</span>
      </button>
      {open && !isDisabled ? (
        <div className="absolute z-50 mt-1 max-h-72 w-full overflow-auto rounded-xl border border-surface-border bg-[#111] p-1 shadow-2xl shadow-black/50">
          <div role="listbox" aria-label={ariaLabel} className="space-y-1">
            {rows.map((row) => {
              const rowValue = modelCatalogSelectValue(row);
              const rowDisabled = isCatalogModelOptionDisabled(row, agentlayer);
              const active = rowValue === value;
              const provider = providerDisplayLabel(row.owned_by, agentlayer);
              const title = rowDisabled
                ? catalogModelOptionUnreachableTitle(row, agentlayer)
                : `${row.id} (${provider})`;
              return (
                <button
                  key={rowValue}
                  type="button"
                  role="option"
                  aria-selected={active}
                  disabled={rowDisabled}
                  title={title}
                  className={`flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left transition ${
                    active ? "bg-sky-500/15 ring-1 ring-sky-400/30" : "hover:bg-white/5"
                  } ${rowDisabled ? "cursor-not-allowed opacity-45" : ""}`}
                  onClick={() => {
                    if (rowDisabled) return;
                    onChange(rowValue);
                    setOpen(false);
                  }}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-neutral-100">{row.id}</span>
                    <span className="block truncate text-[10px] text-surface-muted">{provider}</span>
                  </span>
                  <span className="flex max-w-[48%] shrink-0 flex-wrap justify-end gap-1 pt-0.5">
                    {modelCapabilityBadges(row).map((badge) => (
                      <ModelBadge key={badge.key} badge={badge} compact />
                    ))}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}
