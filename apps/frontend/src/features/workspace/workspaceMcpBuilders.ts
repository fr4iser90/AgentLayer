/** MCP stdio server row (matches backend ``_parse_servers_payload``). */
export type McpStdioServerRow = {
  id: string;
  command: string;
  args: string[];
  env?: Record<string, string>;
  cwd?: string | null;
};

export type UvMcpLaunchMode = "uvx" | "tool";

export type UvMcpPreset = {
  id: string;
  label: string;
  packageSpec: string;
  launchMode: UvMcpLaunchMode;
  /** Console script when using ``tool`` mode, or ``uvx --from`` entry (defaults to package base name). */
  binary: string;
  mcpArgs: string[];
  toolInstallHint?: string;
  useWorkspaceCwd?: boolean;
};

export const UV_MCP_PRESETS: UvMcpPreset[] = [
  {
    id: "cocoindex-full",
    label: "cocoindex-code [full] — semantic code search",
    packageSpec: "cocoindex-code[full]",
    launchMode: "uvx",
    binary: "ccc",
    mcpArgs: ["mcp"],
    toolInstallHint: "uv tool install --upgrade 'cocoindex-code[full]'",
    useWorkspaceCwd: true,
  },
  {
    id: "mcp-fetch",
    label: "mcp-server-fetch (uvx)",
    packageSpec: "mcp-server-fetch",
    launchMode: "uvx",
    binary: "mcp-server-fetch",
    mcpArgs: [],
    useWorkspaceCwd: false,
  },
  {
    id: "custom",
    label: "Custom package…",
    packageSpec: "",
    launchMode: "uvx",
    binary: "",
    mcpArgs: ["mcp"],
    useWorkspaceCwd: true,
  },
];

const SERVER_ID_RE = /^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$/;

export function packageBaseName(packageSpec: string): string {
  const s = packageSpec.trim();
  const noExtras = s.split("[")[0]?.trim() ?? "";
  return noExtras || "mcp-server";
}

export function defaultServerIdFromPackage(packageSpec: string): string {
  const base = packageBaseName(packageSpec);
  return base.replace(/_/g, "-").slice(0, 64);
}

export function validateMcpServerId(id: string): string | null {
  const t = id.trim();
  if (!t) return "Server id is required.";
  if (!SERVER_ID_RE.test(t)) {
    return "Id must be alphanumeric/hyphens only (no underscores), max 64 chars.";
  }
  return null;
}

export function uvToolInstallCommand(packageSpec: string): string {
  const p = packageSpec.trim();
  if (!p) return "uv tool install --upgrade '<package>'";
  if (/[\s'"\\]/.test(p)) return `uv tool install --upgrade ${JSON.stringify(p)}`;
  return `uv tool install --upgrade '${p}'`;
}

/** Build stdio MCP JSON row for ``uvx`` or an installed ``uv tool`` binary. */
export function buildUvMcpServerRow(input: {
  serverId: string;
  packageSpec: string;
  launchMode: UvMcpLaunchMode;
  binary: string;
  mcpArgs: string[];
  workspacePath?: string | null;
  useWorkspaceCwd?: boolean;
}): { row: McpStdioServerRow } | { error: string } {
  const idErr = validateMcpServerId(input.serverId);
  if (idErr) return { error: idErr };

  const pkg = input.packageSpec.trim();
  if (!pkg) return { error: "Package spec is required (e.g. cocoindex-code[full])." };

  const binary = input.binary.trim() || packageBaseName(pkg);
  const extraArgs = input.mcpArgs.map((a) => a.trim()).filter(Boolean);

  let command: string;
  let args: string[];

  if (input.launchMode === "uvx") {
    command = "uvx";
    if (binary && extraArgs.length > 0) {
      args = ["--from", pkg, binary, ...extraArgs];
    } else if (binary && binary !== packageBaseName(pkg)) {
      args = ["--from", pkg, binary, ...extraArgs];
    } else {
      args = [pkg, ...extraArgs];
    }
  } else {
    command = binary;
    args = [...extraArgs];
    if (!command) return { error: "Binary name is required for installed-tool mode (e.g. ccc)." };
  }

  const row: McpStdioServerRow = { id: input.serverId.trim(), command, args };
  if (input.useWorkspaceCwd && input.workspacePath?.trim()) {
    row.cwd = input.workspacePath.trim();
  }
  return { row };
}

export function parseMcpServersJson(text: string): { servers: McpStdioServerRow[] } | { error: string } {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text) as unknown;
  } catch {
    return { error: "Invalid JSON." };
  }
  if (!Array.isArray(parsed)) {
    return { error: "Root value must be a JSON array." };
  }
  const servers: McpStdioServerRow[] = [];
  for (const item of parsed) {
    if (!item || typeof item !== "object") continue;
    const o = item as Record<string, unknown>;
    const id = typeof o.id === "string" ? o.id : "";
    const command = typeof o.command === "string" ? o.command : "";
    const args = Array.isArray(o.args) ? o.args.map(String) : [];
    if (!id || !command) continue;
    const row: McpStdioServerRow = { id, command, args };
    if (o.env && typeof o.env === "object" && !Array.isArray(o.env)) {
      row.env = Object.fromEntries(
        Object.entries(o.env as Record<string, unknown>).map(([k, v]) => [k, String(v)])
      );
    }
    if (typeof o.cwd === "string" && o.cwd.trim()) row.cwd = o.cwd.trim();
    else if (o.cwd === null) row.cwd = null;
    servers.push(row);
  }
  return { servers };
}

export function mergeMcpServer(
  servers: McpStdioServerRow[],
  row: McpStdioServerRow,
  replace: boolean
): McpStdioServerRow[] {
  const idx = servers.findIndex((s) => s.id === row.id);
  if (idx >= 0) {
    if (!replace) return servers;
    const next = [...servers];
    next[idx] = row;
    return next;
  }
  return [...servers, row];
}
