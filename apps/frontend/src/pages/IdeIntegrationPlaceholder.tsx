/**
 * Placeholder for a future external IDE / editor connector (replaces the old in-process PIDEA path).
 * Routes stay stable (`/ide-agent`, `/admin/ide-integration`) for a later HTTP/MCP bridge.
 */
export function IdeIntegrationPlaceholder(props: { variant: "app" | "admin" }) {
  const isAdmin = props.variant === "admin";
  return (
    <div className="mx-auto max-w-xl px-6 py-12 text-neutral-200">
      <h1 className="text-xl font-semibold text-white">
        {isAdmin ? "IDE integration (admin)" : "IDE integration"}
      </h1>
      <p className="mt-3 text-sm leading-relaxed text-surface-muted">
        Server-side PIDEA / Playwright control has been removed from this codebase. A future version may expose a
        small HTTP or MCP surface here so an external tool can drive an IDE on the user&apos;s machine — without
        bundling PIDEA inside AgentLayer.
      </p>
      <p className="mt-4 text-sm text-surface-muted">
        Persisted <span className="font-mono text-neutral-400">scheduler_jobs</span> with{" "}
        <span className="font-mono text-neutral-400">execution_target=ide_agent</span> and the{" "}
        <span className="font-mono text-neutral-400">project_runs</span> queue are not executed on the server; use{" "}
        <span className="font-mono text-neutral-400">server_periodic</span> for background LLM work, or run IDE flows
        outside AgentLayer until a connector exists.
      </p>
    </div>
  );
}
