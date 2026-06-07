import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import {
  fetchPublicShareFile,
  useDashboardPublicShare,
} from "./DashboardPublicShareContext";

const FILE_REF_PREFIX = "file:";

export function GalleryImage(props: { url: string; alt: string; className?: string }) {
  const { t } = useTranslation(["dashboard"]);
  const auth = useAuth();
  const { token: publicShareToken, password: publicSharePassword } = useDashboardPublicShare();
  const { url, alt, className = "h-full w-full object-cover" } = props;
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const blobRef = useRef<string | null>(null);

  useEffect(() => {
    if (!url.startsWith(FILE_REF_PREFIX)) {
      if (blobRef.current) {
        URL.revokeObjectURL(blobRef.current);
        blobRef.current = null;
      }
      setBlobUrl(null);
      return;
    }
    const id = url.slice(FILE_REF_PREFIX.length).trim();
    if (!id) {
      if (blobRef.current) {
        URL.revokeObjectURL(blobRef.current);
        blobRef.current = null;
      }
      setBlobUrl(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      const contentPath = `/v1/dashboards/files/${id}/content`;
      const res = publicShareToken
        ? await fetchPublicShareFile(publicShareToken, id, publicSharePassword)
        : await apiFetch(contentPath, auth);
      if (!res.ok || cancelled) return;
      const b = await res.blob();
      if (cancelled) return;
      if (blobRef.current) URL.revokeObjectURL(blobRef.current);
      const created = URL.createObjectURL(b);
      blobRef.current = created;
      setBlobUrl(created);
    })();
    return () => {
      cancelled = true;
      if (blobRef.current) {
        URL.revokeObjectURL(blobRef.current);
        blobRef.current = null;
      }
    };
  }, [url, auth, auth.accessToken, publicShareToken, publicSharePassword]);

  if (url.startsWith(FILE_REF_PREFIX)) {
    if (!blobUrl) {
      return (
        <div className="flex h-full min-h-[120px] items-center justify-center text-xs text-surface-muted">
          {t("dashboard:imageLoading")}
        </div>
      );
    }
    return <img src={blobUrl} alt={alt} className={className} />;
  }
  return (
    <img
      src={url}
      alt={alt}
      className={className}
      onError={(e) => {
        (e.target as HTMLImageElement).style.display = "none";
      }}
    />
  );
}
