export type NotificationItem = {
  id: string;
  kind: string;
  severity: string;
  title: string;
  body: string;
  link_path: string | null;
  source_ref: Record<string, unknown>;
  read: boolean;
  created_at: string | null;
  read_at: string | null;
};

export type DashboardUnreadSummary = {
  dashboards: Record<string, number>;
  blocks: Record<string, Record<string, number>>;
};

export type NotificationSummary = {
  unread_count: number;
  dashboard_unread: DashboardUnreadSummary;
};
