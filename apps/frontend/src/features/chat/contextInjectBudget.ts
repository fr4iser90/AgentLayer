/** Rough token estimate for UI budgeting (same heuristic as AdminAgents prompt length). */
export function approxTokensFromChars(chars: number): number {
  if (!Number.isFinite(chars) || chars <= 0) return 0;
  return Math.max(1, Math.floor(chars / 4));
}

export function injectItemCharCount(item: {
  chars?: number;
  body?: string;
}): number {
  if (typeof item.chars === "number" && item.chars > 0) return item.chars;
  return item.body?.trim().length ?? 0;
}
