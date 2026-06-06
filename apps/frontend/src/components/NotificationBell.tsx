import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useNotificationContext } from "../features/notifications/NotificationProvider";

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

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open, setOpen]);

  const unread = summary.unread_count;

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        className="relative flex h-9 w-9 items-center justify-center rounded-full text-neutral-200 outline-none ring-sky-500/40 hover:bg-white/10 focus-visible:ring-2"
        aria-expanded={open}
        aria-haspopup="menu"
        title={t("notifications:bellTitle")}
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden className="text-base leading-none">
          🔔
        </span>
        {unread > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-orange-500 px-1 text-[10px] font-semibold text-black">
            {unread > 99 ? "99+" : unread}
          </span>
        ) : null}
      </button>
      {open ? (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1 flex w-[min(22rem,calc(100vw-2rem))] flex-col rounded-lg border border-surface-border bg-[#1a1a1a] shadow-xl"
        >
          <div className="flex items-center justify-between gap-2 border-b border-white/10 px-3 py-2">
            <p className="text-sm font-medium text-white">{t("notifications:inboxTitle")}</p>
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
          <div className="max-h-[min(60vh,420px)] overflow-y-auto py-1">
            {loading && items.length === 0 ? (
              <p className="px-3 py-6 text-center text-sm text-surface-muted">{t("common:nav.loading")}</p>
            ) : items.length === 0 ? (
              <p className="px-3 py-6 text-center text-sm text-surface-muted">{t("notifications:empty")}</p>
            ) : (
              items.map((n) => (
                <div
                  key={n.id}
                  role="menuitem"
                  className={[
                    "border-b border-white/5 px-3 py-2.5 last:border-b-0",
                    n.read ? "opacity-70" : "bg-white/[0.02]",
                  ].join(" ")}
                >
                  <div className="flex items-start gap-2">
                    <span
                      className={["mt-1.5 h-2 w-2 shrink-0 rounded-full", severityDot(n.severity)].join(" ")}
                      aria-hidden
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-white">{n.title}</p>
                      {n.body ? (
                        <p className="mt-0.5 line-clamp-2 text-xs text-surface-muted">{n.body}</p>
                      ) : null}
                      <p className="mt-1 text-[10px] text-white/30">{relativeTime(n.created_at, t)}</p>
                      <div className="mt-2 flex flex-wrap gap-2">
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
                            className="text-xs text-surface-muted hover:text-neutral-300"
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
          <div className="border-t border-white/10 px-3 py-2">
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
