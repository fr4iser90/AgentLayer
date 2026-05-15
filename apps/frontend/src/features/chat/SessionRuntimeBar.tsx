import type { SessionRuntimePayload, TokenUsageTotals } from "../../lib/api";

type Props = {
  runtime: SessionRuntimePayload | null;
  usage: TokenUsageTotals;
  className?: string;
};

export function SessionRuntimeBar({ runtime, usage, className = "" }: Props) {
  const mcp = runtime?.mcp;
  const hasUsage = usage.total > 0 || usage.rounds > 0;
  if (!mcp && !hasUsage) return null;

  const servers = mcp?.servers ?? [];
  const connected = servers.filter((s) => s.connected).length;

  return (
    <div
      className={`rounded-lg border border-white/10 bg-black/30 px-2.5 py-1.5 text-[10px] leading-snug text-neutral-300 ${className}`}
    >
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <span className="font-semibold uppercase tracking-wide text-surface-muted">MCP</span>
        {!mcp ? (
          <span className="text-neutral-500">—</span>
        ) : !mcp.enabled ? (
          <span className="text-neutral-500">disabled</span>
        ) : !mcp.import_ok ? (
          <span className="text-amber-300/90" title="Install the `mcp` Python package on the server">
            package missing
          </span>
        ) : mcp.config_error ? (
          <span className="text-red-400/90" title={mcp.config_error}>
            config error
          </span>
        ) : servers.length === 0 ? (
          <span className="text-neutral-500">no servers</span>
        ) : (
          <span
            className="tabular-nums"
            title={servers.map((s) => `${s.id}: ${s.connected ? `${s.tool_count} tools` : s.error || "down"}`).join("\n")}
          >
            <span className={connected > 0 ? "text-emerald-400/95" : "text-amber-300/90"}>{connected}</span>
            <span className="text-neutral-500">/{servers.length}</span>
            <span className="ml-1 text-neutral-500">servers</span>
          </span>
        )}
        {hasUsage ? (
          <>
            <span className="text-neutral-600">·</span>
            <span className="font-semibold uppercase tracking-wide text-surface-muted">Tokens</span>
            <span className="tabular-nums text-neutral-200">
              in {usage.prompt.toLocaleString()} · out {usage.completion.toLocaleString()} · Σ{" "}
              {usage.total.toLocaleString()}
              {usage.rounds > 0 ? <span className="text-neutral-500"> ({usage.rounds} LLM rounds)</span> : null}
            </span>
          </>
        ) : null}
      </div>
    </div>
  );
}
