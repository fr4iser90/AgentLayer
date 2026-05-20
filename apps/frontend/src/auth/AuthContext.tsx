import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type AuthUser = {
  id: string;
  email: string;
  role: string;
};

export type SetupStatus = {
  needs_setup: boolean;
  needs_admin: boolean;
  needs_llm: boolean;
  needs_provider_wizard?: boolean;
  llm_reachable: boolean;
  setup_token_required?: boolean;
  setup_token_source?: "env" | "auto" | null;
};

/** Set while setup steps 2–3 are in progress (survives brief redirects). */
export const SETUP_WIZARD_ACTIVE_KEY = "agentlayer.setup.wizardActive";

type AuthPayload = {
  access_token: string;
  user: AuthUser;
};

export type AuthContextValue = {
  accessToken: string | null;
  user: AuthUser | null;
  loading: boolean;
  setupStatus: SetupStatus | null;
  refreshSetupStatus: () => Promise<SetupStatus | null>;
  refresh: () => Promise<string | null>;
  login: (email: string, password: string) => Promise<boolean>;
  completeSetup: (
    email: string,
    password: string,
    passwordConfirm: string,
    setupToken: string
  ) => Promise<{ ok: true } | { ok: false; error: string }>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function applyAuthPayload(
  data: AuthPayload,
  setAccessToken: (t: string | null) => void,
  setUser: (u: AuthUser | null) => void
) {
  setAccessToken(data.access_token);
  setUser(data.user ?? null);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [setupStatus, setSetupStatus] = useState<SetupStatus | null>(null);

  const refreshSetupStatus = useCallback(async (): Promise<SetupStatus | null> => {
    try {
      const r = await fetch("/auth/setup-status");
      if (!r.ok) return null;
      const d = (await r.json()) as SetupStatus;
      setSetupStatus(d);
      return d;
    } catch {
      return null;
    }
  }, []);

  const refresh = useCallback(async (): Promise<string | null> => {
    const r = await fetch("/auth/refresh", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (r.ok) {
      const d = (await r.json()) as AuthPayload;
      applyAuthPayload(d, setAccessToken, setUser);
      return d.access_token;
    }
    setAccessToken(null);
    setUser(null);
    return null;
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<boolean> => {
    const r = await fetch("/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim(), password }),
    });
    if (!r.ok) {
      setAccessToken(null);
      setUser(null);
      return false;
    }
    const d = (await r.json()) as AuthPayload;
    applyAuthPayload(d, setAccessToken, setUser);
    return true;
  }, []);

  const completeSetup = useCallback(
    async (
      email: string,
      password: string,
      passwordConfirm: string,
      setupToken: string
    ): Promise<{ ok: true } | { ok: false; error: string }> => {
      const r = await fetch("/auth/setup", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          password,
          password_confirm: passwordConfirm,
          setup_token: setupToken.trim(),
        }),
      });
      if (!r.ok) {
        let msg = "Einrichtung fehlgeschlagen.";
        try {
          const d = (await r.json()) as { detail?: string };
          if (typeof d.detail === "string") msg = d.detail;
        } catch {
          /* ignore */
        }
        return { ok: false, error: msg };
      }
      const d = (await r.json()) as AuthPayload;
      applyAuthPayload(d, setAccessToken, setUser);
      await refreshSetupStatus();
      return { ok: true };
    },
    [refreshSetupStatus]
  );

  useEffect(() => {
    void (async () => {
      await refreshSetupStatus();
      await refresh();
      setLoading(false);
    })();
  }, [refresh, refreshSetupStatus]);

  const logout = useCallback(async () => {
    await fetch("/auth/logout", { method: "POST", credentials: "include" });
    setAccessToken(null);
    setUser(null);
    window.location.href = "/app/login";
  }, []);

  const value = useMemo(
    () => ({
      accessToken,
      user,
      loading,
      setupStatus,
      refreshSetupStatus,
      refresh,
      login,
      completeSetup,
      logout,
    }),
    [
      accessToken,
      user,
      loading,
      setupStatus,
      refreshSetupStatus,
      refresh,
      login,
      completeSetup,
      logout,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const c = useContext(AuthContext);
  if (!c) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return c;
}
