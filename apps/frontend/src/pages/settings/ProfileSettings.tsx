import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

type MeResponse = {
  id?: string;
  email?: string;
  role?: string;
  created_at?: string;
  discord_user_id?: string | null;
  telegram_user_id?: string | null;
  detail?: unknown;
};

export function ProfileSettings() {
  const { t } = useTranslation(["settings"]);
  const auth = useAuth();
  const { user, logout } = auth;
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await apiFetch("/auth/me", auth);
      const data = (await res.json()) as MeResponse;
      if (!res.ok) {
        setErr(typeof data.detail === "string" ? data.detail : t("settings:profileLoadFailed"));
        setMe(null);
        return;
      }
      setMe(data);
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("settings:profileLoadFailed"));
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, [auth, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const empty = t("settings:profileEmpty");
  const email = me?.email ?? user?.email ?? empty;
  const roleRaw = me?.role ?? user?.role ?? empty;
  const roleLabel =
    String(roleRaw).toLowerCase() === "admin"
      ? t("settings:profileRoleAdmin")
      : String(roleRaw).toLowerCase() === "user"
        ? t("settings:profileRoleUser")
        : roleRaw;
  const id = me?.id ?? user?.id ?? empty;
  const discordLinked = me?.discord_user_id?.trim() || null;
  const telegramLinked = me?.telegram_user_id?.trim() || null;
  const created = me?.created_at
    ? new Date(me.created_at).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : null;

  return (
    <div className="mx-auto max-w-xl space-y-8">
      <div>
        <h1 className="text-lg font-semibold text-white">{t("settings:profileTitle")}</h1>
        <p className="mt-2 text-sm text-surface-muted">
          {t("settings:profileIntroLead")}{" "}
          <code className="rounded bg-white/5 px-1 text-xs">GET /auth/me</code>.{" "}
          {t("settings:profileIntroConnectionsBefore")}{" "}
          <Link to="/settings/connections" className="text-sky-400 hover:underline">
            {t("settings:profileIntroConnectionsLink")}
          </Link>
          . {t("settings:profileIntroPasswordNote")}
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-surface-muted">{t("settings:profileLoading")}</p>
      ) : err ? (
        <p className="text-sm text-amber-400">{err}</p>
      ) : (
        <div className="rounded-xl border border-surface-border bg-surface-raised p-5">
          <dl className="space-y-4 text-sm">
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-surface-muted">{t("settings:profileEmail")}</dt>
              <dd className="mt-1 text-white">{email}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-surface-muted">{t("settings:profileUserId")}</dt>
              <dd className="mt-1 break-all font-mono text-xs text-neutral-300">{id}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-surface-muted">{t("settings:profileDiscordLinked")}</dt>
              <dd className="mt-1 font-mono text-xs text-neutral-300">{discordLinked ?? empty}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-surface-muted">{t("settings:profileTelegramLinked")}</dt>
              <dd className="mt-1 font-mono text-xs text-neutral-300">{telegramLinked ?? empty}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-surface-muted">{t("settings:profileRole")}</dt>
              <dd className="mt-1">
                <span
                  className={
                    String(roleRaw).toLowerCase() === "admin"
                      ? "rounded bg-emerald-500/20 px-2 py-0.5 text-xs text-emerald-300"
                      : "rounded bg-sky-500/20 px-2 py-0.5 text-xs text-sky-300"
                  }
                >
                  {roleLabel}
                </span>
              </dd>
            </div>
            {created ? (
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-surface-muted">{t("settings:profileMemberSince")}</dt>
                <dd className="mt-1 text-neutral-300">{created}</dd>
              </div>
            ) : null}
          </dl>
          <button
            type="button"
            className="mt-6 text-xs text-sky-400 hover:text-sky-300 hover:underline"
            onClick={() => void load()}
          >
            {t("settings:profileRefresh")}
          </button>
        </div>
      )}

      <div className="rounded-xl border border-surface-border bg-black/20 p-5">
        <h2 className="text-sm font-medium text-white">{t("settings:sessionTitle")}</h2>
        <p className="mt-1 text-xs text-surface-muted">{t("settings:profileSessionHint")}</p>
        <button
          type="button"
          className="mt-4 rounded-md border border-white/15 bg-white/5 px-4 py-2 text-sm text-neutral-200 hover:bg-white/10"
          onClick={() => void logout()}
        >
          {t("settings:signOut")}
        </button>
      </div>
    </div>
  );
}
