import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import type { OperatorPublic } from "../../features/admin/operatorSettings/operatorSettingsTypes";

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
      <p className="mt-3 text-xs text-sky-400/90">Open →</p>
    </Link>
  );
}

export function AdminDashboard() {
  const auth = useAuth();
  const [op, setOp] = useState<OperatorPublic | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch("/v1/admin/operator-settings", auth);
        const j = (await res.json()) as OperatorPublic;
        if (!cancelled && res.ok) setOp(j);
      } catch {
        if (!cancelled) setOp(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [auth]);

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-xl font-semibold text-white">Overview</h1>
      <p className="mt-2 text-sm text-surface-muted">
        Operator console. Use the sidebar for platform settings, automation, users, and traces. Everything
        here requires an admin session.
      </p>

      {loading ? (
        <p className="mt-8 text-sm text-surface-muted">Loading status…</p>
      ) : (
        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          <StatusCard
            title="Discord"
            status={op?.discord_bot_enabled ? "On" : "Off"}
            detail={op?.discord_bot_token_configured ? "Token configured" : "No token"}
            to="/admin/interfaces/bridges"
          />
          <StatusCard
            title="Telegram"
            status={op?.telegram_bot_enabled ? "On" : "Off"}
            detail={op?.telegram_bot_token_configured ? "Token configured" : "No token"}
            to="/admin/interfaces/bridges"
          />
          <StatusCard
            title="LLM"
            status={op?.llm_smart_routing_enabled ? "Smart routing" : "Catalog providers"}
            detail="Endpoints + model in chat composer"
            to="/admin/interfaces/llm"
          />
          <StatusCard
            title="Jobs worker"
            status={op?.scheduler_jobs_worker_enabled !== false ? "Running" : "Stopped"}
            detail={op?.scheduler_enabled ? "Operator tick on" : "Operator tick off"}
            to="/admin/interfaces/automation"
          />
          <StatusCard
            title="Schedules"
            status="User jobs"
            detail="CRUD for scheduler_jobs"
            to="/admin/schedules"
          />
          <StatusCard
            title="Run traces"
            status="Debug"
            detail="Agent run history"
            to="/admin/run-traces"
          />
        </div>
      )}
    </div>
  );
}
