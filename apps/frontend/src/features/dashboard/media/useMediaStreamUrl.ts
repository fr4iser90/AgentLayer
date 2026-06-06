import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../../auth/AuthContext";
import { apiFetch } from "../../../lib/api";

const MEDIA_REF_PREFIX = "media:";

export function mediaIdFromRef(ref: string | undefined): string | null {
  const s = (ref || "").trim();
  if (!s.startsWith(MEDIA_REF_PREFIX)) return null;
  const id = s.slice(MEDIA_REF_PREFIX.length).trim();
  return id || null;
}

/** Authenticated blob URL for uploaded media streams. */
export function useMediaStreamUrl(mediaId: string | null): string | null {
  const auth = useAuth();
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const blobRef = useRef<string | null>(null);

  useEffect(() => {
    if (!mediaId) {
      if (blobRef.current) {
        URL.revokeObjectURL(blobRef.current);
        blobRef.current = null;
      }
      setBlobUrl(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      const res = await apiFetch(`/v1/media/items/${encodeURIComponent(mediaId)}/stream`, auth);
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
  }, [mediaId, auth, auth.accessToken]);

  return blobUrl;
}
