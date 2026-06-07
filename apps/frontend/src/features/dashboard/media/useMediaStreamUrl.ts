import { useAuth } from "../../../auth/AuthContext";
import { mediaItemStreamSrc } from "../../media/mediaStreamSrc";

const MEDIA_REF_PREFIX = "media:";

export function mediaIdFromRef(ref: string | undefined): string | null {
  const s = (ref || "").trim();
  if (!s.startsWith(MEDIA_REF_PREFIX)) return null;
  const id = s.slice(MEDIA_REF_PREFIX.length).trim();
  return id || null;
}

/** Authenticated same-origin URL for uploaded media only. */
export function useMediaStreamUrl(mediaId: string | null): string | null {
  const auth = useAuth();
  return mediaItemStreamSrc(mediaId, auth.accessToken);
}
