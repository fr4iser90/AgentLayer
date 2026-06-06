import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { DashboardSummary } from "./types";
import { DEFAULT_HUBS, groupDashboardsByHub, type DashboardHubId } from "./dashboardHubNav";

function relativeActivity(iso: string, t: (key: string, opts?: any) => string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return t("dashboard:updated");
  const s = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (s < 60) return t("dashboard:justNow");
  const m = Math.floor(s / 60);
  if (m < 60) return t("dashboard:minutesAgo", { count: m });
  const h = Math.floor(m / 60);
  if (h < 48) return t("dashboard:hoursAgo", { count: h });
  const d = Math.floor(h / 24);
  return t("dashboard:daysAgo", { count: d });
}

function accessHint(role: string | undefined, t: (key: string) => string): string {
  if (role === "viewer") return t("dashboard:accessReadOnly");
  if (role === "editor") return t("dashboard:accessShared");
  if (role === "co_owner") return t("dashboard:accessCoOwner");
  return t("dashboard:accessOwner");
}

function StatCard(props: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-raised px-4 py-3">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-surface-muted">{props.label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-white">{props.value}</p>
      {props.sub ? <p className="mt-0.5 text-xs text-surface-muted">{props.sub}</p> : null}
    </div>
  );
}

export function DashboardOverviewPanel(props: {
  list: DashboardSummary[];
  kindLabelFor: (kind: string, templateId?: string | null) => string;
  onOpenDashboard: (id: string) => void;
  dashboardUnreadCount?: (id: string) => number;
}) {
  const { t } = useTranslation(["dashboard"]);
  const { list, kindLabelFor, onOpenDashboard, dashboardUnreadCount } = props;

  const grouped = useMemo(() => groupDashboardsByHub(list), [list]);

  const kindCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const w of list) {
      const k = (w.kind || "").trim().toLowerCase() || "—";
      m.set(k, (m.get(k) ?? 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [list]);

  const sharedWithYou = useMemo(
    () => list.filter((w) => w.access_role && w.access_role !== "owner").length,
    [list]
  );

  const hubsWithItems = useMemo(() => {
    const order = DEFAULT_HUBS.map((h) => h.id);
    return order.filter((id) => (grouped[id as DashboardHubId]?.items.length ?? 0) > 0);
  }, [grouped]);

  if (list.length === 0) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 py-6">
        <div>
          <h1 className="text-xl font-semibold text-white">{t("dashboard:overviewTitle")}</h1>
          <p className="mt-1 text-sm text-surface-muted">{t("dashboard:overviewEmpty")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8 py-6">
      <div>
        <h1 className="text-xl font-semibold text-white">{t("dashboard:overviewTitle")}</h1>
        <p className="mt-1 text-sm text-surface-muted">
          {t("dashboard:overviewSubtitle")}
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label={t("dashboard:statTotalDashboards")} value={String(list.length)} />
        <StatCard
          label={t("dashboard:statSharedWithYou")}
          value={String(sharedWithYou)}
          sub={sharedWithYou === 0 ? t("dashboard:statOnlyOwnedDashboards") : undefined}
        />
        <StatCard label={t("dashboard:statTemplateKindsInUse")} value={String(kindCounts.length)} />
        <StatCard
          label={t("dashboard:statHubsWithItems")}
          value={String(hubsWithItems.length)}
          sub={t("dashboard:statHubsWithItemsSub", { total: 6 })}
        />
      </div>

      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-surface-muted">{t("dashboard:byTemplateKind")}</h2>
        <ul className="mt-2 flex flex-wrap gap-2">
          {kindCounts.map(([kind, n]) => (
            <li
              key={kind}
              className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm text-neutral-200"
            >
              <span className="text-white">{kindLabelFor(kind, undefined)}</span>
              <span className="text-surface-muted"> · {n}</span>
            </li>
          ))}
        </ul>
      </div>

      {DEFAULT_HUBS.map((hub) => {
        const items = grouped[hub.id]?.items ?? [];
        if (items.length === 0) return null;
        return (
          <section key={hub.id} className="space-y-3">
            <h2 className="text-sm font-medium text-white">{hub.label}</h2>
            <ul className="grid gap-3 sm:grid-cols-2">
              {items.map((w) => (
                <li key={w.id}>
                  <button
                    type="button"
                    onClick={() => onOpenDashboard(w.id)}
                    className="flex w-full flex-col rounded-xl border border-surface-border bg-surface-raised p-4 text-left transition hover:border-sky-500/35 hover:bg-white/[0.03]"
                  >
                    <span className="font-medium text-white">
                      {w.title || w.kind}
                      {(dashboardUnreadCount?.(w.id) ?? 0) > 0 ? (
                        <span className="ml-1.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-orange-500 px-1 text-[9px] font-bold text-black align-middle">
                          !
                        </span>
                      ) : null}
                    </span>
                    <span className="mt-1 text-xs text-surface-muted">
                      {kindLabelFor(w.kind, w.template_id)}
                    </span>
                    <span className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-white/45">
                      <span className="rounded border border-white/10 px-1.5 py-0.5">{accessHint(w.access_role, t)}</span>
                      <span>{t("dashboard:updatedPrefix")} {relativeActivity(w.updated_at, t)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
