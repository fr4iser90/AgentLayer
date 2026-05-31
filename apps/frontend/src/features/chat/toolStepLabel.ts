/** Human-readable one-line label for a tool invocation (cards + activity). */

const VERB_BY_TOOL: Record<string, string> = {
  coding_read_file: "Reading",
  coding_edit: "Editing",
  coding_apply_patch: "Patching",
  coding_search: "Searching",
  coding_glob: "Finding files",
  coding_list_dir: "Listing",
  coding_bash: "Shell",
  coding_git_read: "Git",
  coding_git_sync: "Git sync",
  coding_git_push: "Git push",
  coding_todo: "Planning",
  coding_graph: "Analyzing",
  coding_semantic_search: "Semantic search",
  coding_symbols: "Symbols",
  coding_lsp: "LSP",
  retrieve_context: "Retrieving context",
  rag_search: "RAG search",
  security_scan_start: "Starting scan",
  security_scan_status: "Scan status",
  security_scan_findings: "Loading findings",
  security_scan_resolve: "Resolving scan",
  security_scan_list: "Listing scans",
  security_scan_get: "Loading scan",
  security_scan_targets_list: "Listing targets",
};

function basename(path: string): string {
  const norm = path.replace(/\\/g, "/");
  const parts = norm.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

function pickSummaryField(summary: string, keys: string[]): string {
  for (const key of keys) {
    const re = new RegExp(`${key}=([^\\s]+)`);
    const m = summary.match(re);
    if (m?.[1]) {
      const raw = m[1].replace(/\\n/g, " ").trim();
      if (raw && raw !== "(empty)" && raw !== "<missing>") {
        return key === "path" ? basename(raw) : raw.length > 80 ? `${raw.slice(0, 77)}…` : raw;
      }
    }
  }
  return "";
}

export function formatToolStepLabel(toolName: string | undefined, summary: string | undefined): string {
  const tool = (toolName ?? "").trim();
  const sum = (summary ?? "").trim();
  const verb =
    VERB_BY_TOOL[tool] ??
    (tool.startsWith("security_scan_")
      ? "Scanning"
      : tool.startsWith("coding_")
        ? tool.replace(/^coding_/, "").replace(/_/g, " ")
        : tool.replace(/_/g, " ") || "Working");

  if (!sum) return verb;

  const detail =
    pickSummaryField(sum, ["path", "query", "command", "operation", "pattern", "glob"]) ||
    (sum.length <= 80 ? sum : `${sum.slice(0, 77)}…`);

  return detail ? `${verb} ${detail}` : verb;
}
