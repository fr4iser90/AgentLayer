import { Navigate, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AgentChatSessionProvider } from "../features/chat/AgentChatSessionProvider";
import { useAuth } from "./AuthContext";

/**
 * Access token only in React memory; refresh uses httpOnly cookie (see POST /auth/login).
 */
export function RequireSession() {
  const { t } = useTranslation(["auth"]);
  const { accessToken, loading, setupStatus } = useAuth();

  if (loading) {
    return (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center px-wide text-sm text-ink-muted">
        {t("auth:loading")}
      </div>
    );
  }

  if (!accessToken) {
    const target =
      setupStatus?.needs_setup || setupStatus?.needs_provider_wizard ? "/setup" : "/login";
    return <Navigate to={target} replace />;
  }

  return (
    <AgentChatSessionProvider>
      {/*
        Do not put overflow-hidden / h-full here. AppShell chooses scroll mode:
        - page (settings/admin/org): main is overflow-y-auto; this wrapper must
          grow with content so main can scroll.
        - fill (chat/app): AppShell applies [&>*]:h-full on main's child.
        A hard overflow-hidden here clipped every tall settings page.
      */}
      <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col">
        <Outlet />
      </div>
    </AgentChatSessionProvider>
  );
}
