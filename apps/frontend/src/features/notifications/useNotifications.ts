import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import type { DashboardUnreadSummary, NotificationItem, NotificationSummary } from "./types";

const POLL_MS = 45_000;

export function useNotifications(enabled = true) {
  const auth = useAuth();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [summary, setSummary] = useState<NotificationSummary>({
    unread_count: 0,
    dashboard_unread: { dashboards: {}, blocks: {} },
  });
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const refreshSummary = useCallback(async () => {
    if (!enabled || !auth.accessToken) return;
    try {
      const res = await apiFetch("/v1/user/notifications/summary", auth);
      if (!res.ok || !mountedRef.current) return;
      const j = (await res.json()) as {
        unread_count?: number;
        dashboard_unread?: DashboardUnreadSummary;
      };
      setSummary({
        unread_count: typeof j.unread_count === "number" ? j.unread_count : 0,
        dashboard_unread: j.dashboard_unread ?? { dashboards: {}, blocks: {} },
      });
    } catch {
      /* ignore */
    }
  }, [auth, enabled]);

  const refreshList = useCallback(async () => {
    if (!enabled || !auth.accessToken) return;
    setLoading(true);
    try {
      const res = await apiFetch("/v1/user/notifications?limit=40", auth);
      if (!res.ok || !mountedRef.current) return;
      const j = (await res.json()) as { notifications?: NotificationItem[] };
      setItems(j.notifications ?? []);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [auth, enabled]);

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshSummary(), refreshList()]);
  }, [refreshSummary, refreshList]);

  useEffect(() => {
    if (!enabled || !auth.accessToken) {
      setItems([]);
      setSummary({ unread_count: 0, dashboard_unread: { dashboards: {}, blocks: {} } });
      return;
    }
    void refreshSummary();
    const id = window.setInterval(() => void refreshSummary(), POLL_MS);
    const onFocus = () => void refreshSummary();
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("focus", onFocus);
    };
  }, [auth.accessToken, enabled, refreshSummary]);

  useEffect(() => {
    if (open && auth.accessToken) void refreshList();
  }, [open, auth.accessToken, refreshList]);

  const markRead = useCallback(
    async (id: string) => {
      await apiFetch(`/v1/user/notifications/${id}/read`, auth, { method: "PATCH" });
      setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
      await refreshSummary();
    },
    [auth, refreshSummary]
  );

  const markAllRead = useCallback(async () => {
    await apiFetch("/v1/user/notifications/read-all", auth, { method: "POST" });
    setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    await refreshSummary();
  }, [auth, refreshSummary]);

  const markDashboardSeen = useCallback(
    async (dashboardId: string, blockIds?: string[]) => {
      await apiFetch("/v1/user/notifications/mark-dashboard-seen", auth, {
        method: "POST",
        body: JSON.stringify({ dashboard_id: dashboardId, block_ids: blockIds }),
      });
      await refreshSummary();
    },
    [auth, refreshSummary]
  );

  const dashboardUnreadCount = useCallback(
    (dashboardId: string) => summary.dashboard_unread.dashboards[dashboardId] ?? 0,
    [summary.dashboard_unread.dashboards]
  );

  const blockUnreadIds = useCallback(
    (dashboardId: string): Set<string> => {
      const m = summary.dashboard_unread.blocks[dashboardId];
      if (!m) return new Set();
      return new Set(Object.keys(m).filter((k) => (m[k] ?? 0) > 0));
    },
    [summary.dashboard_unread.blocks]
  );

  return {
    items,
    summary,
    open,
    setOpen,
    loading,
    refreshAll,
    refreshSummary,
    markRead,
    markAllRead,
    markDashboardSeen,
    dashboardUnreadCount,
    blockUnreadIds,
  };
}
