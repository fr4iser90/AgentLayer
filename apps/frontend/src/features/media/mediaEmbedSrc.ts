import { embedUrlAllowed } from "../dashboard/EmbedBlock";

/** Convert watch/share URLs to iframe ``src`` (YouTube, Vimeo). */
export function embedIframeSrc(externalUrl: string, opts?: { autoplay?: boolean }): string | null {
  const raw = externalUrl.trim();
  if (!raw) return null;
  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    return null;
  }
  const host = u.hostname.toLowerCase();
  const autoplay = opts?.autoplay ?? false;
  const ap = autoplay ? "?autoplay=1" : "";

  if (host.includes("youtube.com") || host === "youtu.be" || host.endsWith(".youtu.be")) {
    let id = u.searchParams.get("v");
    if (!id && (host === "youtu.be" || host.endsWith(".youtu.be"))) {
      id = u.pathname.replace(/^\//, "").split("/")[0] || null;
    }
    if (host.includes("youtube.com") && u.pathname.startsWith("/embed/")) {
      return autoplay ? `${raw}${raw.includes("?") ? "&" : "?"}autoplay=1` : raw;
    }
    if (!id) return null;
    return `https://www.youtube-nocookie.com/embed/${encodeURIComponent(id)}${ap}`;
  }

  if (host.includes("vimeo.com")) {
    if (host === "player.vimeo.com") {
      return autoplay ? `${raw}${raw.includes("?") ? "&" : "?"}autoplay=1` : raw;
    }
    const m = u.pathname.match(/\/(\d+)/);
    if (m?.[1]) return `https://player.vimeo.com/video/${m[1]}${ap}`;
  }

  return embedUrlAllowed(raw) ? raw : null;
}
