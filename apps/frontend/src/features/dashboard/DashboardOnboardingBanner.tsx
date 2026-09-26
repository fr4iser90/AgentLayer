import { useTranslation } from "react-i18next";
import { Badge } from "../../ui/Badge";
import type { DashboardOnboarding } from "./types";
import { Button } from "../../ui/Button";

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
    <div className="mb-wide rounded-sheet border border-success/30 bg-success-subtle p-wide">
      <div className="flex items-start justify-between gap-soft">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-badge-success">
            {t("dashboard:onboardingTitle")}
          </p>
          <p className="mt-base text-sm text-badge-success">{onboarding.greeting}</p>
        </div>
        <Button
          type="button"
          className="shrink-0 px-base py-tight text-meta text-ink-muted hover:bg-white/5"
          onClick={() => {
            dismissOnboarding(dashboardId);
            onDismiss();
          }}
        >
          {t("dashboard:onboardingDismiss")}
        </Button>
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
            <Button
              variant="plain"
              block
              key={starter}
              type="button"
              className="rounded-card border border-success/35 bg-success-subtle px-soft py-snug text-xs text-badge-success hover:bg-success-subtle"
              onClick={() => onStartChat(starter)}
            >
              {starter}
            </Button>
          ))}
          <Button
            variant="primary"
            tone="success"
            size="sm"
            type="button"
            className="px-soft py-snug text-xs"
            onClick={() =>
              onStartChat(
                t("dashboard:onboardingGenericStarter", {
                  greeting: onboarding.greeting.slice(0, 120),
                })
              )
            }
          >
            {t("dashboard:onboardingStartChat")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
