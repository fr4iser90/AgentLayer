import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation(["admin"]);
  return (
    <Link
      to={to}
      className="block rounded-xl border border-surface-border bg-surface-raised/80 p-4 transition-colors hover:border-white/20 hover:bg-white/5"
    >
      <p className="text-[10px] font-medium uppercase tracking-wide text-surface-muted">{title}</p>
      <p className="mt-2 text-sm font-medium text-white">{status}</p>
      {detail ? <p className="mt-1 text-xs text-surface-muted">{detail}</p> : null}
      <p className="mt-3 text-xs text-sky-400/90">{t("admin:openCard")}</p>
    </Link>
  );
}

export function AdminDashboard() {
  const auth = useAuth();
  const { t } = useTranslation(["admin"]);
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
      <h1 className="text-xl font-semibold text-white">{t("admin:overview")}</h1>
      <p className="mt-2 text-sm text-surface-muted">
        {t("admin:adminDashboardIntro")}
      </p>

      {loading ? (
        <p className="mt-8 text-sm text-surface-muted">{t("admin:loadingStatus")}</p>
      ) : (
        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          <StatusCard
            title={t("admin:discord")}
            status={op?.discord_bot_enabled ? t("admin:on") : t("admin:off")}
            detail={op?.discord_bot_token_configured ? t("admin:tokenConfigured") : t("admin:noToken")}
            to="/admin/interfaces/bridges"
          />
          <StatusCard
            title={t("admin:telegram")}
            status={op?.telegram_bot_enabled ? t("admin:on") : t("admin:off")}
            detail={op?.telegram_bot_token_configured ? t("admin:tokenConfigured") : t("admin:noToken")}
            to="/admin/interfaces/bridges"
          />
          <StatusCard
            title={t("admin:llm")}
            status={op?.llm_smart_routing_enabled ? t("admin:smartRouting") : t("admin:catalogProviders")}
            detail={t("admin:endpointsModelInComposer")}
            to="/admin/interfaces/llm"
          />
          <StatusCard
            title={t("admin:jobsWorker")}
            status={op?.scheduler_jobs_worker_enabled !== false ? t("admin:running") : t("admin:stopped")}
            detail={op?.scheduler_enabled ? t("admin:operatorTickOn") : t("admin:operatorTickOff")}
            to="/admin/interfaces/automation"
          />
          <StatusCard
            title={t("admin:schedulesTitle")}
            status={t("admin:userJobs")}
            detail={t("admin:crudSchedulerJobs")}
            to="/admin/schedules"
          />
          <StatusCard
            title={t("admin:runTraces")}
            status={t("admin:debug")}
            detail={t("admin:agentRunHistory")}
            to="/admin/run-traces"
          />
        </div>
      )}
    </div>
  );
}
