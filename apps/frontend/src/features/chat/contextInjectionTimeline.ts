import type { LiveLogAppend } from "./useAgentLiveTurn";

export type ContextInjectionPayload = {
  kind?: string;
  label?: string;
  body?: string;
  chars?: number;
  truncated?: boolean;
  unchanged?: boolean;
  digest?: string;
};

/** Append expandable context-injection timeline rows from ``agent.session``. */
export function appendContextInjectionsFromSession(
  appendLine: (kind: string, text: string, extras?: LiveLogAppend) => void,
  raw: unknown
): void {
  if (!Array.isArray(raw) || raw.length === 0) return;
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const row = item as ContextInjectionPayload;
    // Backend only lists blocks actually sent to the LLM; skip legacy "unchanged" rows.
    if (row.unchanged === true) continue;
    const label =
      (typeof row.label === "string" && row.label.trim()) ||
      (typeof row.kind === "string" && row.kind.trim()) ||
      "Context";
    const body = typeof row.body === "string" ? row.body : "";
    if (!body.trim() && !(typeof row.chars === "number" && row.chars > 0)) {
      // Empty placeholder — nothing was injected.
      continue;
    }
    const chars =
      typeof row.chars === "number" && Number.isFinite(row.chars)
        ? Math.max(0, Math.floor(row.chars))
        : body.length;
    appendLine("context_inject", label, {
      streamOffset: 0,
      injectKind: typeof row.kind === "string" ? row.kind : undefined,
      injectLabel: label,
      injectBody: body || undefined,
      injectChars: chars,
    });
  }
}
