import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { SETUP_WIZARD_ACTIVE_KEY, useAuth } from "../auth/AuthContext";
import { defaultLandingPath } from "../auth/tenantSurface";
import { TextInput } from "../ui/Field";
import { Button } from "../ui/Button";

export function LoginPage() {
  const { t } = useTranslation(["auth"]);
  const { accessToken, user, loading, setupStatus, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!loading && setupStatus?.needs_setup) {
      navigate("/setup", { replace: true });
      return;
    }
    if (!loading && accessToken) {
      if (sessionStorage.getItem(SETUP_WIZARD_ACTIVE_KEY) === "1") {
        navigate("/setup", { replace: true });
        return;
      }
      if (setupStatus?.needs_provider_wizard) {
        navigate("/setup", { replace: true });
        return;
      }
      navigate(defaultLandingPath(user), { replace: true });
    }
  }, [loading, accessToken, user, setupStatus, navigate]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    const result = await login(email.trim(), password);
    setPending(false);
    if (!result.ok) {
      // Four different failures, four different next actions. Sending someone
      // back to the password field when the backend is down is the one this
      // used to produce for all of them.
      setError(
        result.reason === "credentials"
          ? t("auth:invalidCredentials")
          : result.reason === "rateLimited"
            ? t("auth:loginRateLimited")
            : result.reason === "unreachable"
              ? t("auth:loginUnreachable")
              : t("auth:loginServerError")
      );
      return;
    }
    // Landing path runs in useEffect once ``user`` (incl. allowed_nav) is set.
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <div className="mx-auto max-w-dialog px-broad py-grand">
        <h1 className="text-2xl font-semibold text-ink-primary">{t("auth:loginTitle")}</h1>
        <p className="mt-base text-sm text-ink-muted">
          {t("auth:loginSubtitle")}
        </p>
        {setupStatus?.needs_setup ? (
          <p className="mt-wide text-sm text-ink-muted">
            {t("auth:instanceNotSetup")}{" "}
            <Link to="/setup" className="text-accent hover:underline">
              {t("auth:startSetup")}
            </Link>
          </p>
        ) : null}
        <form onSubmit={onSubmit} className="mt-deep flex flex-col gap-wide">
          <label className="flex flex-col gap-snug text-sm">
            <span className="text-ink-muted">{t("auth:emailLabel")}</span>
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
            <span className="text-ink-muted">{t("auth:passwordLabel")}</span>
            <TextInput
              type="password"
              name="password"
              autoComplete="current-password"
              value={password}
              onChange={(ev) => setPassword(ev.target.value)}
              required
            />
          </label>
          {error ? (
            <p className="text-sm text-danger" role="alert">
              {error}
            </p>
          ) : null}
          <Button
            variant="primary"
            size="lg"
            type="submit"
            disabled={pending || loading}
            className="px-wide py-firm text-sm"
          >
            {pending ? t("auth:signingIn") : t("auth:signIn")}
          </Button>
        </form>
      </div>
    </div>
  );
}
