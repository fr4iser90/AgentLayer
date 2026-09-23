import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import type { UiBlock } from "./types";
import { useDashboardPublicShare } from "./DashboardPublicShareContext";

type PreviewEvent = {
  summary?: string;
  start?: string;
  end?: string;
  busy?: boolean;
};

type Preview = {
  events?: PreviewEvent[];
  count?: number;
  days_effective?: number;
  projection_kind?: string;
  projection_stale?: boolean;
  error?: string;
};

// The owner-side reason for an empty preview, mapped rather than shown
// raw. "This friend has no calendar configured" and "not shared with you"
// are different facts and send the reader to different people; the status
// code alone cannot carry that, and an internal error string is not
// something to put in front of a user.
const OWNER_EMPTY_ERRORS = new Set(["owner_has_no_calendar_configured"]);

export function ShareWidgetBlockBody(props: { block: UiBlock }) {
  const { t } = useTranslation(["dashboard"]);
  const auth = useAuth();
  const { token: publicShareToken } = useDashboardPublicShare();
  const p = props.block.props;
  const friendUserId = String(p.friendUserId || "").trim();
  const resourceType = String(p.resourceType || "google_calendar").trim();
  const daysAhead = Number(p.daysAhead) || 7;
  const label = String(p.friendDisplayName || p.title || "").trim();
  const [summary, setSummary] = useState<string>("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    // The preview endpoint is auth-only: it reads the *viewer's* share of the
    // friend's calendar. An anonymous reader has no such share, so the call
    // can only 401. Skip it instead of firing it and rendering the answer.
    if (publicShareToken) {
      setErr(t("dashboard:publicShareAuthOnlyBlock"));
      return;
    }
    if (!friendUserId) {
      setErr(t("dashboard:shareWidgetNoFriend"));
      return;
    }
    setErr(null);
    try {
      const res = await apiFetch(
        `/v1/shares/preview/${encodeURIComponent(resourceType)}?owner_user_id=${encodeURIComponent(
          friendUserId,
        )}&days=${daysAhead}`,
        auth,
      );
      const raw = await res.text();
      if (res.status === 403) {
        setErr(t("dashboard:shareWidgetNotShared"));
        return;
      }
      if (res.status === 404) {
        setErr(t("dashboard:shareWidgetNotPreviewable", { type: resourceType }));
        return;
      }
      if (res.status === 401) {
        setErr(t("dashboard:publicShareAuthOnlyBlock"));
        return;
      }
      if (!res.ok) {
        console.warn("share preview load failed", res.status, raw);
        setErr(t("dashboard:shareWidgetLoadFailed"));
        return;
      }
      const j = JSON.parse(raw) as { preview?: Preview };
      const next = j.preview ?? {};
      if (next.error) {
        setPreview(null);
        setSummary(
          OWNER_EMPTY_ERRORS.has(next.error)
            ? t("dashboard:shareWidgetOwnerEmpty")
            : t("dashboard:shareWidgetLoadFailed"),
        );
        return;
      }
      const events = Array.isArray(next.events) ? next.events : [];
      if (!events.length) {
        setPreview(next);
        setSummary(t("dashboard:shareWidgetNothing"));
        return;
      }
      const lines = events.slice(0, 8).map((ev) => {
        const what = ev?.summary || t("dashboard:shareWidgetBusy");
        return `• ${what}${ev?.start ? ` — ${ev.start}` : ""}`;
      });
      setPreview(next);
      setSummary(lines.join("\n"));
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("dashboard:shareWidgetLoadFailed"));
    }
  }, [auth, daysAhead, friendUserId, publicShareToken, resourceType, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const effectiveDays = preview?.days_effective ?? daysAhead;
  const kind = preview?.projection_kind;

  return (
    <section className="rounded-sheet border border-line bg-card p-4">
      <h3 className="text-sm font-medium text-ink-primary">
        {label || t("dashboard:shareWidgetTitle")}
      </h3>
      <p className="mt-1 text-meta uppercase tracking-wide text-ink-muted">
        {resourceType}
        {kind ? ` · ${kind}` : ""} · {t("dashboard:shareWidgetDays", { count: effectiveDays })}
        {preview?.projection_stale ? ` · ${t("dashboard:shareWidgetStale")}` : ""}
      </p>
      {err ? (
        <p className="mt-3 text-sm text-amber-300">{err}</p>
      ) : (
        <pre className="mt-3 whitespace-pre-wrap text-sm text-ink-primary font-sans">{summary}</pre>
      )}
      {publicShareToken ? null : (
        <button type="button" className="mt-2 text-xs text-sky-400 hover:underline" onClick={() => void load()}>
          {t("dashboard:shareWidgetRefresh")}
        </button>
      )}
    </section>
  );
}
