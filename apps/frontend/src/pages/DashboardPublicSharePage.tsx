import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { DashboardGridCanvas } from "../features/dashboard/DashboardGridCanvas";
import { PublicGalleryShareView } from "../features/dashboard/PublicGalleryShareView";
import {
  DashboardPublicShareProvider,
  fetchPublicShareDashboard,
  publicSharePasswordStorageKey,
} from "../features/dashboard/DashboardPublicShareContext";
import { publicShareUsesGalleryPresentation } from "../features/dashboard/publicSharePresentation";
import { parseUiLayout } from "../features/dashboard/layoutMode";
import type { DashboardDetail, UiLayout } from "../features/dashboard/types";

function asUiLayout(raw: unknown): UiLayout | null {
  return parseUiLayout(raw);
}

export function DashboardPublicSharePage() {
  const { t } = useTranslation(["dashboard"]);
  const [params] = useSearchParams();
  const token = (params.get("t") || "").trim();
  const [detail, setDetail] = useState<DashboardDetail | null>(null);
  const [data, setData] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [passwordRequired, setPasswordRequired] = useState(false);
  const [shareLabel, setShareLabel] = useState("");
  const [password, setPassword] = useState("");
  const [passwordInput, setPasswordInput] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);

  const loadShare = useCallback(
    async (pw: string | null) => {
      if (!token) return;
      setLoading(true);
      setError(null);
      setPasswordError(null);
      try {
        const result = await fetchPublicShareDashboard(token, pw);
        if (result.error === "invalid_password") {
          setPasswordRequired(true);
          setPasswordError(t("dashboard:publicShareWrongPassword"));
          setDetail(null);
          setData({});
          return;
        }
        if (result.error === "not_found" || !result.ok) {
          setError(t("dashboard:publicShareNotFound"));
          setDetail(null);
          setData({});
          setPasswordRequired(false);
          return;
        }
        if (result.passwordRequired) {
          setPasswordRequired(true);
          setShareLabel(result.shareLabel || "");
          setDetail(null);
          setData({});
          return;
        }
        const d = result.dashboard as DashboardDetail | undefined;
        if (!d) {
          setError(t("dashboard:publicShareNotFound"));
          return;
        }
        setPasswordRequired(false);
        setDetail(d);
        setData((d.data && typeof d.data === "object" ? d.data : {}) as Record<string, unknown>);
        if (pw?.trim()) {
          setPassword(pw.trim());
          try {
            sessionStorage.setItem(publicSharePasswordStorageKey(token), pw.trim());
          } catch {
            /* ignore */
          }
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setDetail(null);
        setData({});
      } finally {
        setLoading(false);
      }
    },
    [token, t]
  );

  useEffect(() => {
    if (!token) {
      setLoading(false);
      setError(t("dashboard:publicShareMissingToken"));
      setDetail(null);
      setData({});
      return;
    }
    let stored: string | null = null;
    try {
      stored = sessionStorage.getItem(publicSharePasswordStorageKey(token));
    } catch {
      stored = null;
    }
    void loadShare(stored);
  }, [token, t, loadShare]);

  const uiLayout = useMemo(() => asUiLayout(detail?.ui_layout), [detail]);
  const galleryPresentation = useMemo(
    () => publicShareUsesGalleryPresentation(uiLayout),
    [uiLayout]
  );

  const onSubmitPassword = (e: FormEvent) => {
    e.preventDefault();
    void loadShare(passwordInput);
  };

  const pageTitle =
    (detail?.share_label || "").trim() ||
    (detail?.title || "").trim() ||
    t("dashboard:kindDashboardDefault");

  if (!token) {
    return (
      <div className="mx-auto flex max-w-lg flex-1 flex-col justify-center bg-neutral-950 p-deep text-center">
        <h1 className="text-lg font-medium text-ink-primary">{t("dashboard:publicShareTitle")}</h1>
        <p className="mt-soft text-sm text-red-300">{t("dashboard:publicShareMissingToken")}</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center bg-neutral-950 p-deep text-sm text-ink-muted">
        {t("dashboard:loading")}
      </div>
    );
  }

  if (passwordRequired && !detail) {
    return (
      <div className="mx-auto flex min-h-dvh max-w-md flex-1 flex-col justify-center bg-neutral-950 p-deep">
        <h1 className="text-lg font-medium text-ink-primary">
          {shareLabel || t("dashboard:publicShareTitle")}
        </h1>
        <p className="mt-soft text-sm text-ink-muted">{t("dashboard:publicSharePasswordPrompt")}</p>
        <form className="mt-wide space-y-soft" onSubmit={onSubmitPassword}>
          <input
            type="password"
            value={passwordInput}
            onChange={(e) => setPasswordInput(e.target.value)}
            placeholder={t("dashboard:publicSharePasswordPlaceholder")}
            className="w-full rounded-card border border-line-strong bg-field px-soft py-base text-sm text-ink-primary outline-none focus:border-violet-500/50"
            autoComplete="current-password"
          />
          {passwordError ? <p className="text-xs text-red-300">{passwordError}</p> : null}
          <button
            type="submit"
            className="w-full rounded-card bg-violet-600 px-wide py-base text-sm font-medium text-ink-on-fill hover:bg-violet-500"
          >
            {t("dashboard:publicShareUnlock")}
          </button>
        </form>
      </div>
    );
  }

  if (error || !detail || !uiLayout) {
    return (
      <div className="mx-auto flex max-w-lg flex-1 flex-col justify-center bg-neutral-950 p-deep text-center">
        <h1 className="text-lg font-medium text-ink-primary">{t("dashboard:publicShareTitle")}</h1>
        <p className="mt-soft text-sm text-red-300">{error || t("dashboard:publicShareNotFound")}</p>
      </div>
    );
  }

  return (
    <DashboardPublicShareProvider token={token} password={password || null}>
      {galleryPresentation ? (
        <PublicGalleryShareView
          title={pageTitle}
          subtitle={
            detail.share_label && detail.title && detail.share_label !== detail.title
              ? detail.title
              : undefined
          }
          layout={uiLayout}
          data={data}
        />
      ) : (
        <div className="flex min-h-dvh flex-1 flex-col overflow-hidden bg-neutral-950">
          <header className="shrink-0 border-b border-line bg-panel px-wide py-wide sm:px-broad">
            <p className="text-meta font-semibold uppercase tracking-wide text-sky-300/90">
              {t("dashboard:publicShareBadge")}
            </p>
            <h1 className="mt-tight text-xl font-semibold text-ink-primary">{pageTitle}</h1>
            <p className="mt-tight text-xs text-ink-muted">
              {detail.allowed_block_ids && detail.allowed_block_ids.length > 0
                ? t("dashboard:publicShareScopeBlocks", {
                    count: detail.allowed_block_ids.length,
                  })
                : t("dashboard:publicShareScopeFull")}
            </p>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto p-wide sm:p-broad">
            <DashboardGridCanvas
              layout={uiLayout}
              setLayout={() => {}}
              data={data}
              setData={() => {}}
              editMode={false}
              contentReadOnly
              dashboardId={detail.id}
            />
          </div>
        </div>
      )}
    </DashboardPublicShareProvider>
  );
}
