import { createContext, useContext, type ReactNode } from "react";

export const SHARE_PASSWORD_HEADER = "X-Dashboard-Share-Password";

export type DashboardPublicShareContextValue = {
  token: string | null;
  password: string | null;
};

const DashboardPublicShareContext = createContext<DashboardPublicShareContextValue>({
  token: null,
  password: null,
});

export function DashboardPublicShareProvider(props: {
  token: string | null;
  password: string | null;
  children: ReactNode;
}) {
  return (
    <DashboardPublicShareContext.Provider
      value={{ token: props.token, password: props.password }}
    >
      {props.children}
    </DashboardPublicShareContext.Provider>
  );
}

export function useDashboardPublicShare(): DashboardPublicShareContextValue {
  return useContext(DashboardPublicShareContext);
}

/** @deprecated use useDashboardPublicShare */
export function useDashboardPublicShareToken(): string | null {
  return useContext(DashboardPublicShareContext).token;
}

export function publicSharePasswordStorageKey(token: string): string {
  return `dashboard-share-pw:${token.slice(0, 16)}`;
}

export async function fetchPublicShareDashboard(
  token: string,
  password?: string | null
): Promise<{
  ok: boolean;
  status: number;
  passwordRequired?: boolean;
  shareLabel?: string;
  dashboard?: unknown;
  error?: string;
}> {
  const headers: Record<string, string> = {};
  if (password?.trim()) {
    headers[SHARE_PASSWORD_HEADER] = password.trim();
  }
  const res = await fetch(`/v1/dashboards/shared/${encodeURIComponent(token)}`, {
    credentials: "include",
    headers,
  });
  const raw = await res.text();
  let j: {
    password_required?: boolean;
    share_label?: string;
    dashboard?: unknown;
    detail?: unknown;
  } = {};
  try {
    j = JSON.parse(raw) as typeof j;
  } catch {
    j = {};
  }
  if (res.status === 401) {
    const detail = typeof j.detail === "string" ? j.detail : "";
    return {
      ok: false,
      status: 401,
      error: detail === "invalid_password" ? "invalid_password" : detail || "unauthorized",
    };
  }
  if (!res.ok) {
    return { ok: false, status: res.status, error: "not_found" };
  }
  if (j.password_required) {
    return {
      ok: true,
      status: 200,
      passwordRequired: true,
      shareLabel: j.share_label || "",
    };
  }
  return { ok: true, status: 200, dashboard: j.dashboard };
}

export async function fetchPublicShareFile(
  token: string,
  fileId: string,
  password?: string | null
): Promise<Response> {
  const headers: Record<string, string> = {};
  if (password?.trim()) {
    headers[SHARE_PASSWORD_HEADER] = password.trim();
  }
  return fetch(
    `/v1/dashboards/shared/${encodeURIComponent(token)}/files/${encodeURIComponent(fileId)}/content`,
    { credentials: "include", headers }
  );
}
