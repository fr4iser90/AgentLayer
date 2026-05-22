import { Link } from "react-router-dom";
import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";

function StatusCard({
  title,
  status,
  detail,
  to,
}: {
  title: string;
  status: string;
  detail?: string;
  to: string;
}) {
  return (
    <Link
      to={to}
      className="block rounded-xl border border-surface-border bg-surface-raised/80 p-4 transition-colors hover:border-white/20 hover:bg-white/5"
    >
      <p className="text-[10px] font-medium uppercase tracking-wide text-surface-muted">{title}</p>
      <p className="mt-2 text-sm font-medium text-white">{status}</p>
      {detail ? <p className="mt-1 text-xs text-surface-muted">{detail}</p> : null}
      <p className="mt-3 text-xs text-sky-400/90">Configure →</p>
    </Link>
  );
}

export function AdminInterfacesOverviewPage() {
  const s = useOperatorSettings();

  if (s.loading) {
    return (
      <AdminInterfacesPageShell title="Interfaces" description="Loading operator settings…">
        <p className="text-sm text-surface-muted">Loading…</p>
      </AdminInterfacesPageShell>
    );
  }

  return (
    <AdminInterfacesPageShell
      title="Interfaces"
      description={
        <>
          Operator platform settings. API base:{" "}
          <span className="font-mono text-neutral-300">{s.baseUrl}</span> — Bearer JWT or user API key.{" "}
          <a href="/auth/policy" className="text-sky-400 hover:underline">
            GET /auth/policy
          </a>
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <StatusCard
          title="Discord"
          status={s.bridgeEnabled ? "Bridge on" : "Bridge off"}
          detail={s.tokenConfigured ? "Token stored" : "No token"}
          to="/admin/interfaces/bridges"
        />
        <StatusCard
          title="Telegram"
          status={s.tgBridgeEnabled ? "Bridge on" : "Bridge off"}
          detail={s.tgTokenConfigured ? "Token stored" : "No token"}
          to="/admin/interfaces/bridges"
        />
        <StatusCard
          title="LLM"
          status={s.llmPrimaryBackend === "external" ? "External API" : "Ollama"}
          detail={s.llmSmartRouting ? "Smart routing on" : "Smart routing off"}
          to="/admin/interfaces/llm"
        />
        <StatusCard
          title="Memory & RAG"
          status={[s.memoryEnabled && "Memory", s.ragEnabled && "RAG"].filter(Boolean).join(" · ") || "Off"}
          detail={s.ragEnabled ? `Embed: ${s.ragEmbeddingModel}` : undefined}
          to="/admin/interfaces/memory"
        />
        <StatusCard
          title="Automation"
          status={s.schedulerEnabled ? "Operator tick on" : "Operator tick off"}
          detail={
            s.schedulerJobsWorkerEnabled
              ? "scheduler_jobs worker on"
              : "scheduler_jobs worker off"
          }
          to="/admin/interfaces/automation"
        />
        <StatusCard
          title="Platform"
          status={`Agent mode: ${s.agentModeEffective}`}
          detail={
            s.workspaceAllowSelfEditing ? "Self-edit workspace allowed" : "Self-edit workspace off"
          }
          to="/admin/interfaces/platform"
        />
      </div>
      <p className="mt-6 text-xs text-surface-muted">
        Persisted user schedules: <Link to="/admin/schedules" className="text-sky-400 hover:underline">Admin → Schedules</Link>.
        Plugin cron registry:{" "}
        <Link to="/admin/scheduled-jobs" className="text-sky-400 hover:underline">Admin → Plugin cron</Link>.
      </p>
    </AdminInterfacesPageShell>
  );
}
