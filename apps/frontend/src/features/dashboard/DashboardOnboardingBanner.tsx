import { useTranslation } from "react-i18next";
import { Badge } from "../../ui/Badge";
import type { DashboardOnboarding } from "./types";

const DISMISS_PREFIX = "dashboard-onboarding-dismiss:";

export function isOnboardingDismissed(dashboardId: string): boolean {
  try {
    return localStorage.getItem(`${DISMISS_PREFIX}${dashboardId}`) === "1";
  } catch {
    return false;
  }
}

export function dismissOnboarding(dashboardId: string): void {
  try {
    localStorage.setItem(`${DISMISS_PREFIX}${dashboardId}`, "1");
  } catch {
    /* ignore */
  }
}

type Props = {
  dashboardId: string;
  onboarding: DashboardOnboarding;
  readOnly?: boolean;
  onStartChat: (message: string) => void;
  onDismiss: () => void;
};

export function DashboardOnboardingBanner({
  dashboardId,
  onboarding,
  readOnly = false,
  onStartChat,
  onDismiss,
}: Props) {
  const { t } = useTranslation(["dashboard"]);

  const steps = onboarding.steps ?? [];
  const starters = onboarding.chat_starters ?? [];

  return (
    <div className="mb-wide rounded-sheet border border-emerald-500/30 bg-emerald-950/20 p-wide">
      <div className="flex items-start justify-between gap-soft">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-200/90">
            {t("dashboard:onboardingTitle")}
          </p>
          <p className="mt-base text-sm text-emerald-50/95">{onboarding.greeting}</p>
        </div>
        <button
          type="button"
          className="shrink-0 rounded-tile border border-line px-base py-tight text-meta text-ink-muted hover:bg-white/5"
          onClick={() => {
            dismissOnboarding(dashboardId);
            onDismiss();
          }}
        >
          {t("dashboard:onboardingDismiss")}
        </button>
      </div>

      {steps.length > 0 ? (
        <ul className="mt-soft flex flex-wrap gap-base">
          {steps.map((step) => (
            <li key={step.id} className="flex items-center">
              <Badge tone="success">{step.label}</Badge>
            </li>
          ))}
        </ul>
      ) : null}

      {!readOnly && starters.length > 0 ? (
        <div className="mt-soft flex flex-wrap gap-base">
          {starters.map((starter) => (
            <button
              key={starter}
              type="button"
              className="rounded-card border border-emerald-500/35 bg-emerald-900/30 px-soft py-snug text-left text-xs text-emerald-50 hover:bg-emerald-800/40"
              onClick={() => onStartChat(starter)}
            >
              {starter}
            </button>
          ))}
          <button
            type="button"
            className="rounded-card bg-emerald-600/80 px-soft py-snug text-xs font-medium text-ink-primary hover:bg-emerald-500"
            onClick={() =>
              onStartChat(
                t("dashboard:onboardingGenericStarter", {
                  greeting: onboarding.greeting.slice(0, 120),
                })
              )
            }
          >
            {t("dashboard:onboardingStartChat")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
