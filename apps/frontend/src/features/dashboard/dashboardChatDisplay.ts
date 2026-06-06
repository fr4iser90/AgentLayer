/** Trim reasoning leaks and pasted tool JSON from dashboard embedded chat bubbles. */

const SIMULATION_MARKERS = [
  "**warte auf benutzereingabe",
  "**benutzer:**",
  "**meine reaktion:**",
  "**user input:**",
  "**user:**",
  "(self-correction",
  "<think>",
  "wait, i am the ai",
];

const TOOL_JSON_NAMES = new Set([
  "dashboard.read",
  "propose_layouts",
  "patch_layout",
  "patch_data",
  "list",
]);

function truncateAtMarkers(text: string): string {
  const lower = text.toLowerCase();
  let cut = text.length;
  for (const m of SIMULATION_MARKERS) {
    const idx = lower.indexOf(m);
    if (idx >= 0) cut = Math.min(cut, idx);
  }
  return cut < text.length ? text.slice(0, cut).trimEnd() : text;
}

function stripThoughtBlocks(text: string): string {
  return text
    .replace(/\[Thought\][\s\S]*?(?=\n{2,}|$)/gi, "")
    .replace(/<think>[\s\S]*?(?:<\/redacted_thinking>|$)/gi, "");
}

function stripEmbeddedToolJson(text: string): string {
  if (!text.includes("{")) return text;
  const parts: string[] = [];
  let i = 0;
  while (i < text.length) {
    const start = text.indexOf("{", i);
    if (start < 0) {
      parts.push(text.slice(i));
      break;
    }
    parts.push(text.slice(i, start));
    let end = start + 1;
    let depth = 1;
    let inStr = false;
    let esc = false;
    while (end < text.length && depth > 0) {
      const ch = text[end];
      if (inStr) {
        if (esc) esc = false;
        else if (ch === "\\") esc = true;
        else if (ch === '"') inStr = false;
      } else if (ch === '"') inStr = true;
      else if (ch === "{") depth += 1;
      else if (ch === "}") depth -= 1;
      end += 1;
    }
    const chunk = text.slice(start, end);
    let drop = false;
    try {
      const obj = JSON.parse(chunk) as { name?: string; proposals?: unknown };
      const name = typeof obj.name === "string" ? obj.name.trim() : "";
      if (TOOL_JSON_NAMES.has(name) || name.endsWith(".propose_layouts")) drop = true;
      else if (Array.isArray(obj.proposals)) drop = true;
    } catch {
      /* keep */
    }
    if (drop) {
      i = end;
      continue;
    }
    parts.push(chunk);
    i = end;
  }
  return parts.join("");
}

export function sanitizeDashboardAssistantText(text: string, maxChars = 14_000): string {
  if (!text.trim()) return text;
  let t = stripThoughtBlocks(text.trim());
  t = truncateAtMarkers(t);
  t = stripEmbeddedToolJson(t);
  t = t.replace(/\n{3,}/g, "\n\n").trim();
  if (t.length > maxChars) {
    t = `${t.slice(0, maxChars - 40).trimEnd()}\n\n…`;
  }
  return t;
}
