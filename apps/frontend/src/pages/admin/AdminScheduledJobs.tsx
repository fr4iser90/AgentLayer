import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export function AdminScheduledJobs() {
  const { t } = useTranslation(["admin"]);
  return (
    <div className="mx-auto max-w-page px-broad py-page">
      <h1 className="text-2xl font-semibold text-ink-primary">{t("admin:pluginCronTitle")}</h1>
      <p className="mt-wide text-sm text-ink-muted">{t("admin:pluginCronIntro")}</p>
      <p className="mt-wide text-sm text-ink-muted">
        <Link to="/admin/schedules" className="text-accent hover:underline">
          {t("admin:schedulesTitle")}
        </Link>
      </p>
      <p className="mt-wide text-sm text-ink-muted">{t("admin:pluginCronLlmNote")}</p>
      <p className="mt-wide text-sm text-badge-warning">{t("admin:pluginCronNoApi")}</p>
    </div>
  );
}
