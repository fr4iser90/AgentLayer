import { createContext, useContext, type ReactNode } from "react";
import { useNotifications } from "./useNotifications";
import type { NotificationItem, NotificationSummary } from "./types";

type NotificationContextValue = {
  items: NotificationItem[];
  summary: NotificationSummary;
  open: boolean;
  setOpen: (v: boolean | ((prev: boolean) => boolean)) => void;
  loading: boolean;
  refreshAll: () => Promise<void>;
  refreshSummary: () => Promise<void>;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
  markDashboardSeen: (dashboardId: string, blockIds?: string[]) => Promise<void>;
  dashboardUnreadCount: (dashboardId: string) => number;
  blockUnreadIds: (dashboardId: string) => Set<string>;
};

const NotificationContext = createContext<NotificationContextValue | null>(null);

export function NotificationProvider(props: { children: ReactNode; enabled?: boolean }) {
  const value = useNotifications(props.enabled ?? true);
  return <NotificationContext.Provider value={value}>{props.children}</NotificationContext.Provider>;
}

export function useNotificationContext(): NotificationContextValue {
  const ctx = useContext(NotificationContext);
  if (!ctx) {
    throw new Error("useNotificationContext requires NotificationProvider");
  }
  return ctx;
}

/** Safe when provider is absent (e.g. tests). */
export function useOptionalNotificationContext(): NotificationContextValue | null {
  return useContext(NotificationContext);
}
