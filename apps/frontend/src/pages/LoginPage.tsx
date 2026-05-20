import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { SETUP_WIZARD_ACTIVE_KEY, useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { accessToken, loading, setupStatus, refreshSetupStatus, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    void refreshSetupStatus();
  }, [refreshSetupStatus]);

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
      navigate("/", { replace: true });
    }
  }, [loading, accessToken, setupStatus, navigate]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    const ok = await login(email.trim(), password);
    setPending(false);
    if (!ok) {
      setError("Ungültige E-Mail oder Passwort.");
      return;
    }
    navigate("/", { replace: true });
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <div className="mx-auto max-w-sm px-6 py-12">
        <h1 className="text-2xl font-semibold text-white">Anmelden</h1>
        <p className="mt-2 text-sm text-surface-muted">
          Melden Sie sich mit Ihrem Agent-Layer-Konto an.
        </p>
        {setupStatus?.needs_setup ? (
          <p className="mt-4 text-sm text-surface-muted">
            Diese Instanz ist noch nicht eingerichtet.{" "}
            <Link to="/setup" className="text-sky-400 hover:underline">
              Ersteinrichtung starten
            </Link>
          </p>
        ) : null}
        <form onSubmit={onSubmit} className="mt-8 flex flex-col gap-4">
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="text-surface-muted">E-Mail</span>
            <input
              type="email"
              name="email"
              autoComplete="username"
              value={email}
              onChange={(ev) => setEmail(ev.target.value)}
              required
              className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white placeholder:text-white/30 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="text-surface-muted">Passwort</span>
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              value={password}
              onChange={(ev) => setPassword(ev.target.value)}
              required
              className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white placeholder:text-white/30 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
          </label>
          {error ? (
            <p className="text-sm text-red-400" role="alert">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={pending || loading}
            className="rounded-lg bg-sky-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {pending ? "Anmeldung…" : "Anmelden"}
          </button>
        </form>
      </div>
    </div>
  );
}
