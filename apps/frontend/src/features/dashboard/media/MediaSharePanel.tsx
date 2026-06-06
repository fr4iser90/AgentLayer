import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../auth/AuthContext";
import { apiFetch } from "../../../lib/api";

type UploadItem = {
  id: string;
  title: string;
  artist?: string;
  original_name?: string;
  license?: string | null;
  shareable?: boolean;
  access?: string;
};

type ShareGrant = {
  id: string;
  viewer_email?: string;
  permission: string;
};

const LICENSES = ["owned", "cc-by", "cc-by-sa", "cc0", "other"] as const;

export function MediaSharePanel() {
  const { t } = useTranslation(["dashboard"]);
  const auth = useAuth();
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [grants, setGrants] = useState<ShareGrant[]>([]);
  const [license, setLicense] = useState<string>("owned");
  const [licenseNote, setLicenseNote] = useState("");
  const [shareEmail, setShareEmail] = useState("");
  const [sharePerm, setSharePerm] = useState<"play" | "play_and_download">("play");
  const [busy, setBusy] = useState(false);

  const loadUploads = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await apiFetch("/v1/media/items?source_kind=upload", auth);
      const j = (await res.json()) as { items?: UploadItem[]; detail?: unknown };
      if (!res.ok) {
        setErr(typeof j.detail === "string" ? j.detail : t("dashboard:mediaShareLoadFailed"));
        setUploads([]);
        return;
      }
      setUploads((j.items ?? []).filter((x) => x.access === "owner" || !x.access));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [auth, t]);

  useEffect(() => {
    void loadUploads();
  }, [loadUploads]);

  const loadGrants = async (itemId: string) => {
    const res = await apiFetch(`/v1/media/items/${encodeURIComponent(itemId)}/shares`, auth);
    const j = (await res.json()) as { grants?: ShareGrant[] };
    if (res.ok) setGrants(j.grants ?? []);
    else setGrants([]);
  };

  const openItem = (id: string, currentLicense: string | null | undefined) => {
    setExpandedId(id);
    setLicense(currentLicense && LICENSES.includes(currentLicense as (typeof LICENSES)[number]) ? currentLicense : "owned");
    setLicenseNote("");
    setShareEmail("");
    void loadGrants(id);
  };

  const saveLicense = async (itemId: string) => {
    setBusy(true);
    setErr(null);
    try {
      const res = await apiFetch(`/v1/media/items/${encodeURIComponent(itemId)}`, auth, {
        method: "PATCH",
        body: JSON.stringify({ license, license_note: licenseNote }),
      });
      const j = (await res.json()) as { detail?: unknown };
      if (!res.ok) {
        setErr(typeof j.detail === "string" ? j.detail : t("dashboard:mediaLicenseSaveFailed"));
        return;
      }
      await loadUploads();
    } finally {
      setBusy(false);
    }
  };

  const shareItem = async (itemId: string) => {
    const email = shareEmail.trim();
    if (!email) return;
    setBusy(true);
    setErr(null);
    try {
      const item = uploads.find((u) => u.id === itemId);
      if (!item?.shareable) {
        const licRes = await apiFetch(`/v1/media/items/${encodeURIComponent(itemId)}`, auth, {
          method: "PATCH",
          body: JSON.stringify({ license, license_note: licenseNote }),
        });
        if (!licRes.ok) {
          const lj = (await licRes.json()) as { detail?: unknown };
          setErr(typeof lj.detail === "string" ? lj.detail : t("dashboard:mediaLicenseSaveFailed"));
          return;
        }
      }
      const res = await apiFetch(`/v1/media/items/${encodeURIComponent(itemId)}/share`, auth, {
        method: "POST",
        body: JSON.stringify({ email, permission: sharePerm }),
      });
      const j = (await res.json()) as { detail?: unknown };
      if (!res.ok) {
        setErr(typeof j.detail === "string" ? j.detail : t("dashboard:mediaShareFailed"));
        return;
      }
      setShareEmail("");
      await loadGrants(itemId);
      await loadUploads();
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (grantId: string, itemId: string) => {
    setBusy(true);
    try {
      await apiFetch(`/v1/media/share-grants/${encodeURIComponent(grantId)}`, auth, {
        method: "DELETE",
      });
      await loadGrants(itemId);
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <p className="text-xs text-surface-muted">{t("dashboard:loading")}</p>;
  }

  const ownedUploads = uploads.filter((u) => u.access !== "shared");

  return (
    <div className="dashboard-grid-no-drag mt-4 rounded-lg border border-white/10 bg-black/30 p-3">
      <h4 className="text-xs font-medium uppercase tracking-wide text-surface-muted">
        {t("dashboard:mediaSharePanelTitle")}
      </h4>
      <p className="mt-1 text-[10px] leading-snug text-surface-muted">{t("dashboard:mediaSharePanelHint")}</p>
      {err ? <p className="mt-2 text-xs text-red-400">{err}</p> : null}
      {ownedUploads.length === 0 ? (
        <p className="mt-2 text-xs text-surface-muted">{t("dashboard:mediaShareNoUploads")}</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {ownedUploads.map((u) => {
            const label = u.title?.trim() || u.original_name?.trim() || u.id.slice(0, 8);
            const open = expandedId === u.id;
            return (
              <li key={u.id} className="rounded-md border border-white/10 p-2">
                <button
                  type="button"
                  className="flex w-full items-center justify-between text-left text-sm text-white"
                  onClick={() => (open ? setExpandedId(null) : openItem(u.id, u.license))}
                >
                  <span className="truncate">{label}</span>
                  <span className="ml-2 shrink-0 text-[10px] text-surface-muted">
                    {u.shareable ? t("dashboard:mediaShareable") : t("dashboard:mediaNeedsLicense")}
                  </span>
                </button>
                {open ? (
                  <div className="mt-3 space-y-2 border-t border-white/10 pt-3">
                    <label className="block text-[10px] uppercase text-surface-muted">
                      {t("dashboard:mediaLicenseLabel")}
                      <select
                        className="mt-1 block w-full rounded border border-surface-border bg-black/40 px-2 py-1 text-xs text-white"
                        value={license}
                        onChange={(e) => setLicense(e.target.value)}
                      >
                        {LICENSES.map((l) => (
                          <option key={l} value={l}>
                            {l}
                          </option>
                        ))}
                      </select>
                    </label>
                    <input
                      type="text"
                      className="w-full rounded border border-surface-border bg-black/40 px-2 py-1 text-xs text-white"
                      placeholder={t("dashboard:mediaLicenseNotePlaceholder")}
                      value={licenseNote}
                      onChange={(e) => setLicenseNote(e.target.value)}
                    />
                    <button
                      type="button"
                      disabled={busy}
                      className="rounded border border-surface-border px-2 py-1 text-[10px] text-white hover:bg-white/5"
                      onClick={() => void saveLicense(u.id)}
                    >
                      {t("dashboard:mediaSaveLicense")}
                    </button>
                    {u.shareable || license ? (
                      <>
                        <div className="flex flex-wrap gap-2 pt-2">
                          <input
                            type="email"
                            className="min-w-[10rem] flex-1 rounded border border-surface-border bg-black/40 px-2 py-1 text-xs text-white"
                            placeholder={t("dashboard:mediaShareEmailPlaceholder")}
                            value={shareEmail}
                            onChange={(e) => setShareEmail(e.target.value)}
                          />
                          <select
                            className="rounded border border-surface-border bg-black/40 px-2 py-1 text-xs text-white"
                            value={sharePerm}
                            onChange={(e) =>
                              setSharePerm(e.target.value as "play" | "play_and_download")
                            }
                          >
                            <option value="play">{t("dashboard:mediaPermPlay")}</option>
                            <option value="play_and_download">{t("dashboard:mediaPermDownload")}</option>
                          </select>
                          <button
                            type="button"
                            disabled={busy || !shareEmail.trim()}
                            className="rounded border border-sky-500/40 bg-sky-950/40 px-2 py-1 text-[10px] text-sky-100"
                            onClick={() => void shareItem(u.id)}
                          >
                            {t("dashboard:mediaShareAction")}
                          </button>
                        </div>
                        {grants.length > 0 ? (
                          <ul className="mt-2 space-y-1 text-[10px] text-surface-muted">
                            {grants.map((g) => (
                              <li key={g.id} className="flex items-center justify-between gap-2">
                                <span>
                                  {g.viewer_email || g.id.slice(0, 8)} · {g.permission}
                                </span>
                                <button
                                  type="button"
                                  className="text-red-300 hover:text-red-200"
                                  disabled={busy}
                                  onClick={() => void revoke(g.id, u.id)}
                                >
                                  {t("dashboard:delete")}
                                </button>
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </>
                    ) : null}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
