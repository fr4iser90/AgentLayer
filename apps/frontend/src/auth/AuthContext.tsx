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

export type AuthContextValue = {
  accessToken: string | null;
  user: AuthUser | null;
  loading: boolean;
  /** Returns new access token on success, or null if refresh failed. */
  refresh: () => Promise<string | null>;
  /** Email/password; sets access token + user on success. */
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (): Promise<string | null> => {
    const r = await fetch("/auth/refresh", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (r.ok) {
      const d = (await r.json()) as { access_token: string; user: AuthUser };
      setAccessToken(d.access_token);
      setUser(d.user ?? null);
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
    const d = (await r.json()) as { access_token: string; user: AuthUser };
    setAccessToken(d.access_token);
    setUser(d.user ?? null);
    return true;
  }, []);

  useEffect(() => {
    void (async () => {
      await refresh();
      setLoading(false);
    })();
  }, [refresh]);

  const logout = useCallback(async () => {
    await fetch("/auth/logout", { method: "POST", credentials: "include" });
    setAccessToken(null);
    setUser(null);
    window.location.href = "/app/login";
  }, []);

  const value = useMemo(
    () => ({ accessToken, user, loading, refresh, login, logout }),
    [accessToken, user, loading, refresh, login, logout]
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
