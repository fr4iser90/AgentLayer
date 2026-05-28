import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export function HomePage() {
  const { t } = useTranslation(["common"]);
  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-6 py-12">
        <h1 className="text-2xl font-semibold text-white">{t("common:app.title")}</h1>
        <p className="mt-2 text-sm text-surface-muted">
          {t("common:home.intro")}{" "}
          <Link to="/admin" className="text-sky-400 hover:underline">
            {t("common:userMenu.admin")}
          </Link>
          .
        </p>
        <ul className="mt-8 flex flex-col gap-3">
          <li>
            <Link
              to="/chat"
              className="block rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-white hover:bg-white/5"
            >
              <span className="font-medium">{t("common:nav.chat")}</span>
              <span className="mt-1 block text-sm text-surface-muted">{t("common:home.chatDesc")}</span>
            </Link>
          </li>
          <li>
            <Link
              to="/studio"
              className="block rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-white hover:bg-white/5"
            >
              <span className="font-medium">{t("common:nav.studio")}</span>
              <span className="mt-1 block text-sm text-surface-muted">{t("common:home.studioDesc")}</span>
            </Link>
          </li>
          <li>
            <Link
              to="/tasks"
              className="block rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-white hover:bg-white/5"
            >
              <span className="font-medium">{t("common:nav.tasks")}</span>
              <span className="mt-1 block text-sm text-surface-muted">{t("common:home.tasksDesc")}</span>
            </Link>
          </li>
          <li>
            <Link
              to="/dashboard"
              className="block rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-white hover:bg-white/5"
            >
              <span className="font-medium">{t("common:nav.dashboard")}</span>
              <span className="mt-1 block text-sm text-surface-muted">{t("common:home.dashboardDesc")}</span>
            </Link>
          </li>
        </ul>
      </div>
    </div>
  );
}
