import { useRef } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bell } from "lucide-react";
import { useNotificationContext } from "../features/notifications/NotificationProvider";
import { Tooltip } from "../ui/Tooltip";
import { useClickOutside } from "../ui/useClickOutside";

function severityDot(severity: string): string {
  if (severity === "error" || severity === "action_required") return "bg-red-400";
  if (severity === "warning") return "bg-amber-400";
  return "bg-sky-400";
}

function toAppPath(linkPath: string | null): string {
  const p = (linkPath || "").trim();
  if (!p) return "/";
  if (p.startsWith("/app")) return p.slice(4) || "/";
  if (p.startsWith("/")) return p;
  return `/${p}`;
}

function relativeTime(iso: string | null, t: (key: string, opts?: object) => string): string {
  if (!iso) return "";
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return "";
  const s = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (s < 60) return t("notifications:justNow");
  const m = Math.floor(s / 60);
  if (m < 60) return t("notifications:minutesAgo", { count: m });
  const h = Math.floor(m / 60);
  if (h < 48) return t("notifications:hoursAgo", { count: h });
  return t("notifications:daysAgo", { count: Math.floor(h / 24) });
}

export function NotificationBell() {
  const { t } = useTranslation(["notifications", "common"]);
  const {
    items,
    summary,
    open,
    setOpen,
    loading,
    markRead,
    markAllRead,
  } = useNotificationContext();
  const rootRef = useRef<HTMLDivElement | null>(null);

  useClickOutside(rootRef, () => setOpen(false), open);

  const unread = summary.unread_count;

  return (
    <div className="relative" ref={rootRef}>
      <Tooltip label={t("notifications:bellTitle")}>
      <button
          type="button"
          className="relative flex h-9 w-9 items-center justify-center rounded-pill text-ink-primary outline-none ring-sky-500/40 hover:bg-white/10 focus-visible:ring-2"
          aria-expanded={open}
          aria-haspopup="menu"
          onClick={() => setOpen((v) => !v)}
        >
          <Bell aria-hidden className="h-[18px] w-[18px]" />
          {unread > 0 ? (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-pill bg-orange-500 px-tight text-meta font-semibold text-black">
              {unread > 99 ? "99+" : unread}
            </span>
          ) : null}
        </button>
      </Tooltip>
      {open ? (
        <div
          role="menu"
          className="absolute right-0 z-menu mt-tight flex w-[min(22rem,calc(100vw-2rem))] flex-col rounded-card border border-line bg-raised shadow-xl"
        >
          <div className="flex items-center justify-between gap-base border-b border-line px-soft py-base">
            <p className="text-sm font-medium text-ink-primary">{t("notifications:inboxTitle")}</p>
            {unread > 0 ? (
              <button
                type="button"
                className="text-xs text-sky-400 hover:text-sky-300"
                onClick={() => void markAllRead()}
              >
                {t("notifications:markAllRead")}
              </button>
            ) : null}
          </div>
          <div className="max-h-[min(60vh,420px)] overflow-y-auto py-tight">
            {loading && items.length === 0 ? (
              <p className="px-soft py-broad text-center text-sm text-ink-muted">{t("common:nav.loading")}</p>
            ) : items.length === 0 ? (
              <p className="px-soft py-broad text-center text-sm text-ink-muted">{t("notifications:empty")}</p>
            ) : (
              items.map((n) => (
                <div
                  key={n.id}
                  role="menuitem"
                  className={[
                    "border-b border-line-subtle px-soft py-firm last:border-b-0",
                    n.read ? "opacity-70" : "bg-white/[0.02]",
                  ].join(" ")}
                >
                  <div className="flex items-start gap-base">
                    <span
                      className={["mt-snug h-2 w-2 shrink-0 rounded-pill", severityDot(n.severity)].join(" ")}
                      aria-hidden
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-ink-primary">{n.title}</p>
                      {n.body ? (
                        <p className="mt-hair line-clamp-2 text-xs text-ink-muted">{n.body}</p>
                      ) : null}
                      <p className="mt-tight text-meta text-white/30">{relativeTime(n.created_at, t)}</p>
                      <div className="mt-base flex flex-wrap gap-base">
                        {n.link_path ? (
                          <Link
                            to={toAppPath(n.link_path)}
                            className="text-xs text-sky-400 hover:text-sky-300"
                            onClick={() => {
                              if (!n.read) void markRead(n.id);
                              setOpen(false);
                            }}
                          >
                            {t("notifications:open")}
                          </Link>
                        ) : null}
                        {!n.read ? (
                          <button
                            type="button"
                            className="text-xs text-ink-muted hover:text-neutral-300"
                            onClick={() => void markRead(n.id)}
                          >
                            {t("notifications:dismiss")}
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
          <div className="border-t border-line px-soft py-base">
            <Link
              to="/settings/notifications"
              className="text-xs text-sky-400 hover:text-sky-300"
              onClick={() => setOpen(false)}
            >
              {t("notifications:settingsLink")}
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
