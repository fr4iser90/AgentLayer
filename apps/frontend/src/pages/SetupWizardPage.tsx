import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { SETUP_WIZARD_ACTIVE_KEY, useAuth } from "../auth/AuthContext";
import type { DeploymentMode } from "../auth/deploymentMode";
import {
  MIN_PASSWORD_LENGTH,
  passwordRejectionReason,
  passwordStrengthLevel,
} from "../auth/passwordStrength";
import { Radio } from "../ui/Radio";
import { TextInput } from "../ui/Field";
import { Button } from "../ui/Button";
import { SetupAiPhases } from "./setup/SetupAiPhases";
import { PageShell } from "../layout/PageShell";

const PASSWORD_RULE_KEYS = {
  atLeast: "setup:passwordRuleAtLeast",
  lower: "setup:passwordRuleLower",
  upper: "setup:passwordRuleUpper",
  digit: "setup:passwordRuleDigit",
  symbol: "setup:passwordRuleSymbol",
  sequence: "setup:passwordRuleSequence",
} as const;

export function SetupWizardPage() {
  const { t } = useTranslation(["setup"]);
  const navigate = useNavigate();
  const { accessToken, loading, setupStatus, refreshSetupStatus, completeSetup } = useAuth();

  const [step, setStep] = useState(0);
  const [deploymentMode, setDeploymentMode] = useState<DeploymentMode>("multi_tenant");
  const [deploymentPending, setDeploymentPending] = useState(false);
  const [deploymentError, setDeploymentError] = useState<string | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);

  const [setupToken, setSetupToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [adminError, setAdminError] = useState<string | null>(null);
  const [adminPending, setAdminPending] = useState(false);

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    const s = await refreshSetupStatus();
    setStatusLoading(false);
    return s;
  }, [refreshSetupStatus]);

  useEffect(() => {
    void (async () => {
      const s = await loadStatus();
      if (!s) return;
      if (s.needs_admin) return;
      const wizardActive =
        sessionStorage.getItem(SETUP_WIZARD_ACTIVE_KEY) === "1" ||
        s.needs_provider_wizard === true;
      if (wizardActive && accessToken) return;
      if (!accessToken) {
        navigate("/login", { replace: true });
      }
    })();
  }, [loadStatus, navigate, accessToken]);

  useEffect(() => {
    if (!loading && accessToken && setupStatus && !setupStatus.needs_admin) {
      const wizardActive =
        sessionStorage.getItem(SETUP_WIZARD_ACTIVE_KEY) === "1" ||
        setupStatus.needs_provider_wizard === true;
      if (wizardActive && step <= 1) {
        setStep(2);
      }
    }
  }, [loading, accessToken, setupStatus, step]);

  async function onDeploymentSubmit(e: FormEvent) {
    e.preventDefault();
    setDeploymentPending(true);
    setDeploymentError(null);
    try {
      const r = await fetch("/auth/setup/deployment-mode", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          deployment_mode: deploymentMode,
          setup_token: setupToken.trim(),
        }),
      });
      if (!r.ok) {
        let msg = t("setup:deploymentFailed");
        try {
          const d = (await r.json()) as { detail?: string };
          if (typeof d.detail === "string") msg = d.detail;
        } catch {
          /* ignore */
        }
        setDeploymentError(msg);
        return;
      }
      await refreshSetupStatus();
      setStep(1);
    } catch {
      setDeploymentError(t("setup:deploymentFailed"));
    } finally {
      setDeploymentPending(false);
    }
  }

  async function onAdminSubmit(e: FormEvent) {
    e.preventDefault();
    setAdminPending(true);
    setAdminError(null);
    const rejectKey = passwordRejectionReason(password);
    if (rejectKey) {
      setAdminPending(false);
      setAdminError(t(PASSWORD_RULE_KEYS[rejectKey]));
      return;
    }
    if (password !== passwordConfirm) {
      setAdminPending(false);
      setAdminError(t("setup:passwordMismatch"));
      return;
    }
    const result = await completeSetup(email.trim(), password, passwordConfirm, setupToken);
    setAdminPending(false);
    if (!result.ok) {
      setAdminError(result.error ?? t("setup:setupFailed"));
      return;
    }
    sessionStorage.setItem(SETUP_WIZARD_ACTIVE_KEY, "1");
    await refreshSetupStatus();
    setStep(2);
  }

  function finishWizard() {
    sessionStorage.removeItem(SETUP_WIZARD_ACTIVE_KEY);
  }

  if (statusLoading && !setupStatus) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-ink-muted">
        {t("setup:loading")}
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <PageShell density="dialog">
        {step < 2 ? (
          <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
            {t("setup:stepOf", { step: step + 1, total: 4 })}
          </p>
        ) : step === 2 ? (
          <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
            {t("setup:stepOf", { step: 3, total: 4 })}
          </p>
        ) : (
          <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
            {t("setup:stepOf", { step: 4, total: 4 })}
          </p>
        )}

        {step === 0 ? (
          <>
            <h1 className="mt-base text-2xl font-semibold text-ink-primary">{t("setup:step0Title")}</h1>
            <p className="mt-base text-sm text-ink-muted">{t("setup:step0Intro")}</p>
            <form onSubmit={onDeploymentSubmit} className="mt-deep flex flex-col gap-wide">
              {setupStatus?.setup_token_required ? (
                <label className="flex flex-col gap-snug text-sm">
                  <span className="text-ink-muted">{t("setup:setupToken")}</span>
                  <TextInput
                    type="password"
                    name="setup_token"
                    autoComplete="off"
                    value={setupToken}
                    onChange={(ev) => setSetupToken(ev.target.value)}
                    required
                  />
                  <p className="text-xs text-ink-muted">
                    {setupStatus.setup_token_source === "env"
                      ? t("setup:setupTokenEnv")
                      : t("setup:setupTokenLog")}
                  </p>
                </label>
              ) : null}
              <fieldset className="space-y-soft">
                <label className="flex cursor-pointer items-start gap-soft rounded-card border border-line p-wide">
                  <Radio
                    name="deployment_mode"
                    value="single_user"
                    checked={deploymentMode === "single_user"}
                    onChange={() => setDeploymentMode("single_user")}
                    className="mt-tight"
                  />
                  <span>
                    <span className="block text-sm font-medium text-ink-primary">
                      {t("setup:modeSingleTitle")}
                    </span>
                    <span className="mt-tight block text-xs text-ink-muted">
                      {t("setup:modeSingleDesc")}
                    </span>
                  </span>
                </label>
                <label className="flex cursor-pointer items-start gap-soft rounded-card border border-line p-wide">
                  <Radio
                    name="deployment_mode"
                    value="agent_system"
                    checked={deploymentMode === "agent_system"}
                    onChange={() => setDeploymentMode("agent_system")}
                    className="mt-tight"
                  />
                  <span>
                    <span className="block text-sm font-medium text-ink-primary">
                      {t("setup:modeAgentTitle")}
                    </span>
                    <span className="mt-tight block text-xs text-ink-muted">
                      {t("setup:modeAgentDesc")}
                    </span>
                  </span>
                </label>
                <label className="flex cursor-pointer items-start gap-soft rounded-card border border-line p-wide">
                  <Radio
                    name="deployment_mode"
                    value="multi_tenant"
                    checked={deploymentMode === "multi_tenant"}
                    onChange={() => setDeploymentMode("multi_tenant")}
                    className="mt-tight"
                  />
                  <span>
                    <span className="block text-sm font-medium text-ink-primary">
                      {t("setup:modeTenantTitle")}
                    </span>
                    <span className="mt-tight block text-xs text-ink-muted">
                      {t("setup:modeTenantDesc")}
                    </span>
                  </span>
                </label>
              </fieldset>
              {deploymentError ? (
                <p className="text-sm text-danger" role="alert">
                  {deploymentError}
                </p>
              ) : null}
              <Button
                variant="primary"
                size="lg"
                type="submit"
                disabled={deploymentPending}
                className="px-wide py-firm text-sm"
              >
                {deploymentPending ? t("setup:deploymentPending") : t("setup:continueBtn")}
              </Button>
            </form>
          </>
        ) : null}

        {step === 1 ? (
          <>
            <h1 className="mt-base text-2xl font-semibold text-ink-primary">{t("setup:step1Title")}</h1>
            <p className="mt-base text-sm text-ink-muted">{t("setup:step1Intro")}</p>
            <form onSubmit={onAdminSubmit} className="mt-deep flex flex-col gap-wide">
              <label className="flex flex-col gap-snug text-sm">
                <span className="text-ink-muted">{t("setup:email")}</span>
                <TextInput
                  type="email"
                  name="email"
                  autoComplete="username"
                  value={email}
                  onChange={(ev) => setEmail(ev.target.value)}
                  required
                />
              </label>
              <label className="flex flex-col gap-snug text-sm">
                <span className="text-ink-muted">{t("setup:password")}</span>
                <TextInput
                  type="password"
                  name="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(ev) => setPassword(ev.target.value)}
                  required
                  minLength={MIN_PASSWORD_LENGTH}
                />
                {(() => {
                  const level = passwordStrengthLevel(password);
                  const reject = passwordRejectionReason(password);
                  if (!password) return null;
                  const tone =
                    level <= 1 ? "bg-danger" : level === 2 ? "bg-warning" : "bg-success";
                  const label =
                    level <= 1
                      ? t("setup:passwordStrengthWeak")
                      : level === 2
                        ? t("setup:passwordStrengthOk")
                        : t("setup:passwordStrengthStrong");
                  return (
                    <div className="mt-snug space-y-tight" aria-live="polite">
                      <div
                        className="flex gap-tight"
                        role="meter"
                        aria-valuemin={0}
                        aria-valuemax={3}
                        aria-valuenow={level}
                        aria-label={label}
                      >
                        {[1, 2, 3].map((n) => (
                          <span
                            key={n}
                            className={`h-1.5 flex-1 rounded-pill ${level >= n ? tone : "bg-line"}`}
                          />
                        ))}
                      </div>
                      <p className="text-xs text-ink-muted">
                        {label}
                        {reject ? ` — ${t(PASSWORD_RULE_KEYS[reject])}` : null}
                      </p>
                    </div>
                  );
                })()}
              </label>
              <label className="flex flex-col gap-snug text-sm">
                <span className="text-ink-muted">{t("setup:passwordConfirm")}</span>
                <TextInput
                  type="password"
                  name="password_confirm"
                  autoComplete="new-password"
                  value={passwordConfirm}
                  onChange={(ev) => setPasswordConfirm(ev.target.value)}
                  required
                  minLength={MIN_PASSWORD_LENGTH}
                  aria-invalid={
                    passwordConfirm.length > 0 && passwordConfirm !== password ? true : undefined
                  }
                />
                {passwordConfirm ? (
                  <p
                    className={`text-xs ${
                      passwordConfirm === password ? "text-success" : "text-danger"
                    }`}
                    aria-live="polite"
                  >
                    {passwordConfirm === password
                      ? t("setup:passwordMatch")
                      : t("setup:passwordMismatch")}
                  </p>
                ) : null}
              </label>
              <p className="text-xs text-ink-muted">{t("setup:passwordHint")}</p>
              {adminError ? (
                <p className="text-sm text-danger" role="alert">
                  {adminError}
                </p>
              ) : null}
              <Button
                variant="primary"
                size="lg"
                type="submit"
                disabled={
                  adminPending ||
                  passwordStrengthLevel(password) < 2 ||
                  password !== passwordConfirm
                }
                className="px-wide py-firm text-sm"
              >
                {adminPending ? t("setup:adminPending") : t("setup:continueBtn")}
              </Button>
            </form>
          </>
        ) : null}

        {step === 2 && accessToken ? (
          <SetupAiPhases
            accessToken={accessToken}
            onComplete={() => {
              finishWizard();
              void refreshSetupStatus();
              setStep(3);
            }}
          />
        ) : null}

        {step === 3 ? (
          <>
            <h1 className="mt-base text-2xl font-semibold text-ink-primary">{t("setup:step3Title")}</h1>
            <p className="mt-base text-sm text-ink-muted">{t("setup:step3Intro")}</p>
            <div className="mt-deep flex flex-col gap-soft">
              <Link
                to="/chat"
                className="rounded-card bg-accent px-wide py-firm text-center text-sm font-medium text-ink-on-fill hover:bg-accent-hover"
              >
                {t("setup:goToChat")}
              </Link>
              <Link
                to="/admin"
                className="rounded-card border border-line px-wide py-firm text-center text-sm text-ink-primary hover:bg-white/5"
              >
                {t("setup:goToAdmin")}
              </Link>
            </div>
          </>
        ) : null}

        <p className="mt-pagePad text-center text-sm text-ink-muted">
          <Link to="/login" className="text-accent hover:underline">
            {t("setup:backToLogin")}
          </Link>
        </p>
      </PageShell>
    </div>
  );
}
