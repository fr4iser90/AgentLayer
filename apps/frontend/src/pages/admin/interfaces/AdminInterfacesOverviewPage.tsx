import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation(["admin"]);
  return (
    <Link
      to={to}
      className="block rounded-xl border border-surface-border bg-surface-raised/80 p-4 transition-colors hover:border-white/20 hover:bg-white/5"
    >
      <p className="text-[10px] font-medium uppercase tracking-wide text-surface-muted">{title}</p>
      <p className="mt-2 text-sm font-medium text-white">{status}</p>
      {detail ? <p className="mt-1 text-xs text-surface-muted">{detail}</p> : null}
      <p className="mt-3 text-xs text-sky-400/90">{t("admin:configureCta")}</p>
    </Link>
  );
}

export function AdminInterfacesOverviewPage() {
  const { t } = useTranslation(["admin"]);
  const s = useOperatorSettings();

  if (s.loading) {
    return (
      <AdminInterfacesPageShell
        title={t("admin:interfacesTitle")}
        description={t("admin:interfacesLoadingOperatorSettings")}
      >
        <p className="text-sm text-surface-muted">{t("admin:loading")}</p>
      </AdminInterfacesPageShell>
    );
  }

  return (
    <AdminInterfacesPageShell
      title={t("admin:interfacesTitle")}
      description={
        <>
          {t("admin:interfacesOverviewDescriptionPrefix")}{" "}
          <span className="font-mono text-neutral-300">{s.baseUrl}</span> — Bearer JWT or user API key.{" "}
          <a href="/auth/policy" className="text-sky-400 hover:underline">
            {t("admin:authPolicyEndpoint")}
          </a>
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <StatusCard
          title={t("admin:discord")}
          status={s.bridgeEnabled ? t("admin:bridgeOn") : t("admin:bridgeOff")}
          detail={s.tokenConfigured ? t("admin:tokenStored") : t("admin:noToken")}
          to="/admin/interfaces/bridges"
        />
        <StatusCard
          title={t("admin:telegram")}
          status={s.tgBridgeEnabled ? t("admin:bridgeOn") : t("admin:bridgeOff")}
          detail={s.tgTokenConfigured ? t("admin:tokenStored") : t("admin:noToken")}
          to="/admin/interfaces/bridges"
        />
        <StatusCard
          title={t("admin:interfacesProvidersTitle")}
          status={t("admin:endpointsCount", { count: s.extLlmEndpoints.filter((e) => e.baseUrl.trim()).length })}
          detail={t("admin:interfacesProvidersDescription")}
          to="/admin/interfaces/providers"
        />
        <StatusCard
          title={t("admin:interfacesModelPoliciesTitle")}
          status={t("admin:interfacesModelPoliciesStatus")}
          detail={t("admin:interfacesModelPoliciesDescription")}
          to="/admin/interfaces/model-policies"
        />
        <StatusCard
          title={t("admin:interfacesRoutingTitle")}
          status={s.llmSmartRouting ? t("admin:smartRoutingOn") : t("admin:providerModelInChat")}
          detail={t("admin:interfacesRoutingDescription")}
          to="/admin/interfaces/routing"
        />
        <StatusCard
          title={t("admin:memoryRagTitle")}
          status={
            [s.memoryEnabled && t("admin:memory"), s.ragEnabled && t("admin:rag")].filter(Boolean).join(" · ") ||
            t("admin:statusOff")
          }
          detail={
            s.embeddingApiBaseEffective
              ? `${s.ragEmbeddingModel} @ ${s.embeddingApiBaseEffective}`
              : s.ragEnabled
                ? `${t("admin:embed")}: ${s.ragEmbeddingModel}`
                : undefined
          }
          to="/admin/interfaces/memory"
        />
        <StatusCard
          title={t("admin:navAutomation")}
          status={s.schedulerEnabled ? t("admin:operatorTickOn") : t("admin:operatorTickOff")}
          detail={
            s.schedulerJobsWorkerEnabled
              ? t("admin:schedulerWorkerOn")
              : t("admin:schedulerWorkerOff")
          }
          to="/admin/interfaces/automation"
        />
        <StatusCard
          title={t("admin:navPlatform")}
          status={t("admin:agentModeEffective", { mode: s.agentModeEffective })}
          detail={
            s.workspaceAllowSelfEditing ? t("admin:selfEditWorkspaceAllowed") : t("admin:selfEditWorkspaceOff")
          }
          to="/admin/interfaces/platform"
        />
      </div>
      <p className="mt-6 text-xs text-surface-muted">
        {t("admin:persistedUserSchedules")}{" "}
        <Link to="/admin/schedules" className="text-sky-400 hover:underline">
          {t("admin:adminToSchedules")}
        </Link>
        . {t("admin:pluginCronRegistry")}{" "}
        <Link to="/admin/scheduled-jobs" className="text-sky-400 hover:underline">
          {t("admin:adminToPluginCron")}
        </Link>
        .
      </p>
    </AdminInterfacesPageShell>
  );
}
