import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

type Prefs = {
  telegram_enabled: boolean;
  discord_enabled: boolean;
  telegram_schedules: boolean;
  telegram_dashboard: boolean;
  discord_schedules: boolean;
  discord_dashboard: boolean;
  external_failures_only: boolean;
};

const DEFAULT_PREFS: Prefs = {
  telegram_enabled: false,
  discord_enabled: false,
  telegram_schedules: true,
  telegram_dashboard: false,
  discord_schedules: true,
  discord_dashboard: false,
  external_failures_only: true,
};

function Toggle(props: {
  label: string;
  hint?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label
      className={[
        "flex cursor-pointer items-start gap-soft rounded-card border border-line px-soft py-firm",
        props.disabled ? "cursor-not-allowed opacity-50" : "hover:bg-white/[0.03]",
      ].join(" ")}
    >
      <input
        type="checkbox"
        className="mt-tight"
        checked={props.checked}
        disabled={props.disabled}
        onChange={(e) => props.onChange(e.target.checked)}
      />
      <span className="min-w-0 flex-1">
        <span className="block text-sm text-ink-primary">{props.label}</span>
        {props.hint ? <span className="mt-hair block text-xs text-ink-muted">{props.hint}</span> : null}
      </span>
    </label>
  );
}

export function NotificationsSettings() {
  const { t } = useTranslation(["settings", "notifications"]);
  const auth = useAuth();
  const [prefs, setPrefs] = useState<Prefs>(DEFAULT_PREFS);
  const [telegramLinked, setTelegramLinked] = useState(false);
  const [discordLinked, setDiscordLinked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await apiFetch("/v1/user/notifications/prefs", auth);
      if (!res.ok) {
        setError(await res.text());
        return;
      }
      const j = (await res.json()) as {
        prefs?: Partial<Prefs>;
        telegram_linked?: boolean;
        discord_linked?: boolean;
      };
      setPrefs({ ...DEFAULT_PREFS, ...(j.prefs ?? {}) });
      setTelegramLinked(Boolean(j.telegram_linked));
      setDiscordLinked(Boolean(j.discord_linked));
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const res = await apiFetch("/v1/user/notifications/prefs", auth, {
        method: "PUT",
        body: JSON.stringify(prefs),
      });
      if (!res.ok) {
        const txt = await res.text();
        setError(txt);
        return;
      }
      const j = (await res.json()) as {
        prefs?: Partial<Prefs>;
        telegram_linked?: boolean;
        discord_linked?: boolean;
      };
      setPrefs({ ...DEFAULT_PREFS, ...(j.prefs ?? {}) });
      setTelegramLinked(Boolean(j.telegram_linked));
      setDiscordLinked(Boolean(j.discord_linked));
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-ink-muted">{t("settings:notificationsLoading")}</p>;
  }

  return (
    <div className="mx-auto max-w-xl space-y-broad">
      <div>
        <h1 className="text-xl font-semibold text-ink-primary">{t("settings:notificationsTitle")}</h1>
        <p className="mt-tight text-sm text-ink-muted">{t("settings:notificationsIntro")}</p>
      </div>

      {error ? (
        <div className="rounded-card border border-red-500/40 bg-red-950/30 px-soft py-base text-sm text-red-200">
          {error}
        </div>
      ) : null}
      {saved ? (
        <div className="rounded-card border border-emerald-500/30 bg-emerald-950/20 px-soft py-base text-sm text-emerald-200">
          {t("settings:notificationsSaved")}
        </div>
      ) : null}

      <section className="space-y-base">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          {t("settings:notificationsWebTitle")}
        </h2>
        <p className="text-sm text-ink-muted">{t("settings:notificationsWebHint")}</p>
      </section>

      <section className="space-y-base">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Telegram</h2>
        {!telegramLinked ? (
          <p className="text-sm text-ink-muted">
            {t("settings:notificationsLinkTelegram")}{" "}
            <Link to="/settings/connections" className="text-sky-400 hover:text-sky-300">
              {t("settings:connectionsTitle")}
            </Link>
          </p>
        ) : null}
        <Toggle
          label={t("settings:notificationsTelegramEnable")}
          hint={t("settings:notificationsTelegramEnableHint")}
          checked={prefs.telegram_enabled}
          disabled={!telegramLinked}
          onChange={(v) => setPrefs((p) => ({ ...p, telegram_enabled: v }))}
        />
        {prefs.telegram_enabled ? (
          <div className="ml-base space-y-base border-l border-line pl-soft">
            <Toggle
              label={t("settings:notificationsSchedules")}
              checked={prefs.telegram_schedules}
              onChange={(v) => setPrefs((p) => ({ ...p, telegram_schedules: v }))}
            />
            <Toggle
              label={t("settings:notificationsDashboard")}
              checked={prefs.telegram_dashboard}
              onChange={(v) => setPrefs((p) => ({ ...p, telegram_dashboard: v }))}
            />
          </div>
        ) : null}
      </section>

      <section className="space-y-base">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Discord</h2>
        {!discordLinked ? (
          <p className="text-sm text-ink-muted">
            {t("settings:notificationsLinkDiscord")}{" "}
            <Link to="/settings/connections" className="text-sky-400 hover:text-sky-300">
              {t("settings:connectionsTitle")}
            </Link>
          </p>
        ) : null}
        <Toggle
          label={t("settings:notificationsDiscordEnable")}
          hint={t("settings:notificationsDiscordEnableHint")}
          checked={prefs.discord_enabled}
          disabled={!discordLinked}
          onChange={(v) => setPrefs((p) => ({ ...p, discord_enabled: v }))}
        />
        {prefs.discord_enabled ? (
          <div className="ml-base space-y-base border-l border-line pl-soft">
            <Toggle
              label={t("settings:notificationsSchedules")}
              checked={prefs.discord_schedules}
              onChange={(v) => setPrefs((p) => ({ ...p, discord_schedules: v }))}
            />
            <Toggle
              label={t("settings:notificationsDashboard")}
              checked={prefs.discord_dashboard}
              onChange={(v) => setPrefs((p) => ({ ...p, discord_dashboard: v }))}
            />
          </div>
        ) : null}
      </section>

      <section className="space-y-base">
        <Toggle
          label={t("settings:notificationsFailuresOnly")}
          hint={t("settings:notificationsFailuresOnlyHint")}
          checked={prefs.external_failures_only}
          onChange={(v) => setPrefs((p) => ({ ...p, external_failures_only: v }))}
        />
      </section>

      <div className="flex gap-base">
        <button
          type="button"
          disabled={saving}
          className="rounded-card bg-sky-600 px-wide py-base text-sm font-medium text-ink-on-fill hover:bg-sky-500 disabled:opacity-50"
          onClick={() => void save()}
        >
          {saving ? t("settings:notificationsSaving") : t("settings:notificationsSave")}
        </button>
        <button
          type="button"
          className="rounded-card border border-line px-wide py-base text-sm text-ink-primary hover:bg-white/5"
          onClick={() => void load()}
        >
          {t("settings:reloadFromServer")}
        </button>
      </div>
    </div>
  );
}
