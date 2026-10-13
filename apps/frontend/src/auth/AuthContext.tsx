import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  accessTokenNeedsRefresh,
  msUntilProactiveRefresh,
} from "./tokenRefresh";
import { fetchWithTimeout } from "./fetchWithTimeout";

export type ProfessionPolicy = {
  profession_role_slug?: string | null;
  profession_role_name?: string | null;
  role_kind?: string;
  department_slug?: string | null;
  department_name?: string | null;
  capabilities?: string[];
  can_edit_content?: boolean;
  can_review_content?: boolean;
  can_publish_content?: boolean;
  can_manage_profession?: boolean;
};

export type AuthUser = {
  id: string;
  email: string;
  role: string;
  site_role?: string;
  /** P6 (Weg B): granted platform/admin capabilities (cumulative JSONB). Empty when unknown. */
  capabilities?: string[];
  tenant_id?: number;
  membership_role?: string | null;
  deployment_mode?: string;
  org_setup_required?: boolean;
  vertical_profile?: string | null;
  /** When set by tenant capability ``ui.allowed_nav``, first-party chrome is limited. */
  allowed_nav?: string[] | null;
  /** False when tenant policy limits structure edit to admin memberships. */
  dashboard_structure_edit?: boolean;
  /** Admin always; otherwise requires ``users.schedules_allowed``. */
  may_use_schedules?: boolean;
  /** Hosted server workspaces (ADR 0009). */
  may_use_server_workspaces?: boolean;
  /** Operator kill-switch for friendship + peer sharing (operator_settings). Absent = on. */
  friend_system_enabled?: boolean;
  profession_policy?: ProfessionPolicy;
};

export type SetupStatus = {
  needs_setup: boolean;
  needs_admin: boolean;
  needs_llm: boolean;
  needs_provider_wizard?: boolean;
  llm_reachable: boolean;
  setup_token_required?: boolean;
  setup_token_source?: "env" | "auto" | null;
  deployment_mode?: string;
  needs_deployment_mode?: boolean;
};

/** Set while setup steps 2–3 are in progress (survives brief redirects). */
export const SETUP_WIZARD_ACTIVE_KEY = "agentlayer.setup.wizardActive";

const SETUP_STATUS_CACHE_KEY = "agentlayer.setupStatus";

function readCachedSetupStatus(): SetupStatus | null {
  try {
    const raw = sessionStorage.getItem(SETUP_STATUS_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SetupStatus;
    if (parsed.needs_setup) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeCachedSetupStatus(status: SetupStatus): void {
  if (status.needs_setup) return;
  try {
    sessionStorage.setItem(SETUP_STATUS_CACHE_KEY, JSON.stringify(status));
  } catch {
    /* quota / private mode */
  }
}

/** Stable after first-start + provider wizard — safe to skip repeat fetches within the session. */
function isSetupStatusStable(status: SetupStatus): boolean {
  return !status.needs_setup && status.needs_provider_wizard !== true;
}

type AuthPayload = {
  access_token: string;
  user: AuthUser;
};

/**
 * Why a sign-in did not go through.
 *
 * `LoginPage` returned `auth:invalidCredentials` for every `!ok` — wrong
 * password, network down, a 500 from the backend, a rate limit. Telling someone
 * their password is wrong when the server is unreachable sends them back to the
 * password field, which is the one place the problem is not.
 */
export type LoginFailure = "credentials" | "rateLimited" | "unreachable" | "server";
export type LoginResult = { ok: true } | { ok: false; reason: LoginFailure };

export type AuthContextValue = {
  accessToken: string | null;
  user: AuthUser | null;
  loading: boolean;
  setupStatus: SetupStatus | null;
  refreshSetupStatus: () => Promise<SetupStatus | null>;
  refresh: () => Promise<string | null>;
  login: (email: string, password: string) => Promise<LoginResult>;
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

async function fetchUserProfile(accessToken: string): Promise<Partial<AuthUser> | null> {
  try {
    const r = await fetchWithTimeout("/auth/me", {
      credentials: "include",
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!r.ok) return null;
    return (await r.json()) as Partial<AuthUser>;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [setupStatus, setSetupStatus] = useState<SetupStatus | null>(() => readCachedSetupStatus());
  const accessTokenRef = useRef<string | null>(null);
  const proactiveRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refreshRef = useRef<() => Promise<string | null>>(async () => null);

  accessTokenRef.current = accessToken;

  const refreshSetupStatus = useCallback(async (): Promise<SetupStatus | null> => {
    try {
      const r = await fetchWithTimeout("/auth/setup-status");
      if (!r.ok) return null;
      const d = (await r.json()) as SetupStatus;
      setSetupStatus(d);
      writeCachedSetupStatus(d);
      return d;
    } catch {
      return null;
    }
  }, []);

  const clearProactiveRefreshTimer = useCallback(() => {
    if (proactiveRefreshTimerRef.current) {
      clearTimeout(proactiveRefreshTimerRef.current);
      proactiveRefreshTimerRef.current = null;
    }
  }, []);

  const scheduleProactiveRefresh = useCallback(
    (token: string | null) => {
      clearProactiveRefreshTimer();
      if (!token) return;
      const delay = msUntilProactiveRefresh(token);
      if (delay == null) return;
      proactiveRefreshTimerRef.current = setTimeout(() => {
        proactiveRefreshTimerRef.current = null;
        void refreshRef.current();
      }, delay);
    },
    [clearProactiveRefreshTimer]
  );

  const refresh = useCallback(async (): Promise<string | null> => {
    const r = await fetchWithTimeout("/auth/refresh", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (r.ok) {
      const d = (await r.json()) as AuthPayload;
      applyAuthPayload(d, setAccessToken, setUser);
      const profile = await fetchUserProfile(d.access_token);
      if (profile) {
        setUser((prev) => (prev ? { ...prev, ...profile } : prev));
      }
      scheduleProactiveRefresh(d.access_token);
      return d.access_token;
    }
    clearProactiveRefreshTimer();
    setAccessToken(null);
    setUser(null);
    return null;
  }, [clearProactiveRefreshTimer, scheduleProactiveRefresh]);

  refreshRef.current = refresh;

  const login = useCallback(
    async (email: string, password: string): Promise<LoginResult> => {
      let r: Response;
      try {
        r = await fetch("/auth/login", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: email.trim(), password }),
        });
      } catch {
        // No response at all: the backend is down or the request never left.
        return { ok: false, reason: "unreachable" };
      }
      if (!r.ok) {
        setAccessToken(null);
        setUser(null);
        if (r.status === 429) return { ok: false, reason: "rateLimited" };
        if (r.status === 401 || r.status === 400 || r.status === 422) {
          return { ok: false, reason: "credentials" };
        }
        return { ok: false, reason: "server" };
      }
      let d: AuthPayload;
      try {
        d = (await r.json()) as AuthPayload;
      } catch {
        return { ok: false, reason: "server" };
      }
      applyAuthPayload(d, setAccessToken, setUser);
      const profile = await fetchUserProfile(d.access_token);
      if (profile) {
        setUser((prev) => (prev ? { ...prev, ...profile } : prev));
      }
      scheduleProactiveRefresh(d.access_token);
      return { ok: true };
    },
    [scheduleProactiveRefresh]
  );

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
      const profile = await fetchUserProfile(d.access_token);
      if (profile) {
        setUser((prev) => (prev ? { ...prev, ...profile } : prev));
      }
      scheduleProactiveRefresh(d.access_token);
      await refreshSetupStatus();
      return { ok: true };
    },
    [refreshSetupStatus, scheduleProactiveRefresh]
  );

  const bootstrapSetupStatus = useCallback(async (): Promise<SetupStatus | null> => {
    const cached = readCachedSetupStatus();
    if (cached && isSetupStatusStable(cached)) {
      setSetupStatus(cached);
      return cached;
    }
    return refreshSetupStatus();
  }, [refreshSetupStatus]);

  useEffect(() => {
    void (async () => {
      try {
        await Promise.all([bootstrapSetupStatus(), refresh()]);
      } finally {
        setLoading(false);
      }
    })();
  }, [refresh, bootstrapSetupStatus]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      const tok = accessTokenRef.current;
      if (tok && accessTokenNeedsRefresh(tok)) {
        void refreshRef.current();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  useEffect(() => () => clearProactiveRefreshTimer(), [clearProactiveRefreshTimer]);

  const logout = useCallback(async () => {
    clearProactiveRefreshTimer();
    await fetch("/auth/logout", { method: "POST", credentials: "include" });
    setAccessToken(null);
    setUser(null);
    window.location.href = "/app/login";
  }, [clearProactiveRefreshTimer]);

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
