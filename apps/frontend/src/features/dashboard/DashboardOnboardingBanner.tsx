import { useTranslation } from "react-i18next";
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
    <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-200/90">
            {t("dashboard:onboardingTitle")}
          </p>
          <p className="mt-2 text-sm text-emerald-50/95">{onboarding.greeting}</p>
        </div>
        <button
          type="button"
          className="shrink-0 rounded-md border border-white/10 px-2 py-1 text-[10px] text-surface-muted hover:bg-white/5"
          onClick={() => {
            dismissOnboarding(dashboardId);
            onDismiss();
          }}
        >
          {t("dashboard:onboardingDismiss")}
        </button>
      </div>

      {steps.length > 0 ? (
        <ul className="mt-3 flex flex-wrap gap-2">
          {steps.map((step) => (
            <li
              key={step.id}
              className="rounded-full border border-emerald-500/25 bg-black/20 px-2.5 py-1 text-[11px] text-emerald-100/90"
            >
              {step.label}
            </li>
          ))}
        </ul>
      ) : null}

      {!readOnly && starters.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {starters.map((starter) => (
            <button
              key={starter}
              type="button"
              className="rounded-lg border border-emerald-500/35 bg-emerald-900/30 px-3 py-1.5 text-left text-xs text-emerald-50 hover:bg-emerald-800/40"
              onClick={() => onStartChat(starter)}
            >
              {starter}
            </button>
          ))}
          <button
            type="button"
            className="rounded-lg bg-emerald-600/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500"
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
