import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import type { UiBlock } from "./types";

export function ShareWidgetBlockBody(props: { block: UiBlock }) {
  const { t } = useTranslation(["dashboard"]);
  const auth = useAuth();
  const p = props.block.props;
  const friendUserId = String(p.friendUserId || "").trim();
  const resourceType = String(p.resourceType || "google_calendar").trim();
  const daysAhead = Number(p.daysAhead) || 7;
  const label = String(p.friendDisplayName || p.title || "").trim();
  const [summary, setSummary] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!friendUserId) {
      setErr(t("dashboard:shareWidgetNoFriend"));
      return;
    }
    setErr(null);
    if (resourceType !== "google_calendar") {
      setSummary(t("dashboard:shareWidgetUnsupported", { type: resourceType }));
      return;
    }
    try {
      const res = await apiFetch(
        `/v1/shares/preview/calendar?owner_user_id=${encodeURIComponent(friendUserId)}&days=${daysAhead}`,
        auth,
      );
      const raw = await res.text();
      if (!res.ok) {
        setErr(raw || t("dashboard:shareWidgetLoadFailed"));
        return;
      }
      const j = JSON.parse(raw) as { calendar?: { events?: unknown[]; result?: string } };
      const cal = j.calendar;
      const events = cal?.events;
      if (Array.isArray(events)) {
        const lines = events.slice(0, 8).map((ev) => {
          if (ev && typeof ev === "object" && "summary" in ev) {
            const e = ev as { summary?: string; start?: string };
            return `• ${e.summary || "?"}${e.start ? ` — ${e.start}` : ""}`;
          }
          return `• ${String(ev)}`;
        });
        setSummary(lines.length ? lines.join("\n") : t("dashboard:shareWidgetNoEvents"));
      } else if (typeof cal?.result === "string") {
        setSummary(cal.result);
      } else {
        setSummary(t("dashboard:shareWidgetNoEvents"));
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("dashboard:shareWidgetLoadFailed"));
    }
  }, [auth, daysAhead, friendUserId, resourceType, t]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-4">
      <h3 className="text-sm font-medium text-white">
        {label || t("dashboard:shareWidgetTitle")}
      </h3>
      <p className="mt-1 text-[10px] uppercase tracking-wide text-surface-muted">
        {resourceType} · {t("dashboard:shareWidgetDays", { count: daysAhead })}
      </p>
      {err ? (
        <p className="mt-3 text-sm text-amber-300">{err}</p>
      ) : (
        <pre className="mt-3 whitespace-pre-wrap text-sm text-neutral-200 font-sans">{summary}</pre>
      )}
      <button type="button" className="mt-2 text-xs text-sky-400 hover:underline" onClick={() => void load()}>
        {t("dashboard:shareWidgetRefresh")}
      </button>
    </section>
  );
}
