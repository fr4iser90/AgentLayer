import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";

import { getPath, setPath } from "./dashboardDataPaths";

/**
 * HTTPS hostnames allowed for iframe `src`. Only these may load — no arbitrary URLs.
 * Add hosts here deliberately (e.g. Google Calendar embed, YouTube, Vimeo).
 */
export const EMBED_ALLOWED_HOSTNAMES = [
  "calendar.google.com",
  "docs.google.com",
  "drive.google.com",
  "www.youtube.com",
  "youtube.com",
  "www.youtube-nocookie.com",
  "player.vimeo.com",
  "www.openstreetmap.org",
] as const;

function hostnameAllowed(hostname: string): boolean {
  const h = hostname.toLowerCase();
  return EMBED_ALLOWED_HOSTNAMES.some((allowed) => {
    const a = allowed.toLowerCase();
    return h === a || h.endsWith(`.${a}`);
  });
}

/** Returns true if `raw` is a valid https URL whose host is allowlisted. */
export function embedUrlAllowed(raw: string): boolean {
  const s = raw.trim();
  if (!s) return false;
  let u: URL;
  try {
    u = new URL(s);
  } catch {
    return false;
  }
  if (u.protocol !== "https:") return false;
  return hostnameAllowed(u.hostname);
}

type EmbedState = { url: string; title: string; height: number };

function readEmbed(raw: unknown): EmbedState {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const o = raw as Record<string, unknown>;
    const h = Number(o.height);
    return {
      url: String(o.url ?? "").trim(),
      title: String(o.title ?? ""),
      height: Number.isFinite(h) && h >= 120 && h <= 2000 ? Math.round(h) : 480,
    };
  }
  return { url: "", title: "", height: 480 };
}

export function EmbedBlockBody(props: {
  dp: string;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  sectionTitle: string;
  readOnly: boolean;
}) {
  const { t } = useTranslation(["dashboard"]);
  const { dp, data, setData, sectionTitle, readOnly } = props;
  const st = readEmbed(dp ? getPath(data, dp) : undefined);

  const patch = (partial: Partial<EmbedState>) => {
    setData((d) => {
      const cur = readEmbed(dp ? getPath(d, dp) : undefined);
      return setPath(d, dp, { ...cur, ...partial } as unknown);
    });
  };

  const allowed = embedUrlAllowed(st.url);
  const title = st.title.trim() || sectionTitle;

  return (
    <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-3 md:p-4">
      <h3 className="mb-2 text-sm font-medium text-white">{title}</h3>
      {!readOnly ? (
        <div className="dashboard-grid-no-drag mb-3 space-y-2">
          <div>
            <label className="mb-1 block text-[10px] uppercase text-surface-muted">
              {t("dashboard:embedTitleOptionalLabel")}
            </label>
            <input
              type="text"
              className="w-full rounded-lg border border-surface-border bg-black/40 px-3 py-2 text-sm text-white"
              placeholder={sectionTitle}
              value={st.title}
              onChange={(e) => patch({ title: e.target.value })}
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] uppercase text-surface-muted">
              {t("dashboard:embedUrlLabel")}
            </label>
            <input
              type="url"
              className="w-full rounded-lg border border-surface-border bg-black/40 px-3 py-2 font-mono text-xs text-neutral-100"
              placeholder={t("dashboard:embedUrlPlaceholder")}
              value={st.url}
              onChange={(e) => patch({ url: e.target.value })}
            />
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label className="mb-1 block text-[10px] uppercase text-surface-muted">
                {t("dashboard:embedHeightLabel")}
              </label>
              <input
                type="number"
                min={120}
                max={2000}
                step={20}
                className="w-28 rounded-lg border border-surface-border bg-black/40 px-2 py-1.5 text-sm text-white"
                value={st.height}
                onChange={(e) => patch({ height: Number(e.target.value) || 480 })}
              />
            </div>
          </div>
          {st.url && !allowed ? (
            <p className="rounded-lg border border-amber-500/40 bg-amber-950/30 px-2 py-1.5 text-xs text-amber-200">
              {t("dashboard:embedUrlNotAllowed")}{" "}
              {EMBED_ALLOWED_HOSTNAMES.slice(0, 4).join(", ")} …
            </p>
          ) : null}
          <p className="text-[10px] leading-snug text-surface-muted">
            {t("dashboard:embedGoogleCalendarHint")}
          </p>
        </div>
      ) : null}
      {allowed ? (
        <div
          className="overflow-hidden rounded-lg border border-white/10 bg-black/40"
          style={{ height: st.height }}
        >
          <iframe
            title={title}
            src={st.url}
            className="h-full w-full border-0"
            loading="lazy"
            referrerPolicy="no-referrer-when-downgrade"
            allow="clipboard-read; clipboard-write; fullscreen"
          />
        </div>
      ) : st.url && readOnly ? (
        <p className="rounded-lg border border-red-500/30 bg-red-950/20 px-3 py-4 text-sm text-red-200">
          {t("dashboard:embedUnavailableReadOnly")}
        </p>
      ) : !st.url ? (
        <p className="rounded-lg border border-dashed border-white/15 py-10 text-center text-sm text-surface-muted">
          {readOnly
            ? t("dashboard:embedEmptyReadOnly")
            : t("dashboard:embedEmptyEditable")}
        </p>
      ) : null}
    </section>
  );
}
