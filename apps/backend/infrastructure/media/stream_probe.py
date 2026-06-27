"""HTTP probe for live stream URLs before persisting to the media library."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from apps.backend.infrastructure.media import media_policy

_PROBE_BYTES = 16_384
_USER_AGENT = "AgentLayer-StreamProbe/1.0"
_DEFAULT_TIMEOUT = 12.0


@dataclass(frozen=True)
class StreamProbeResult:
    ok: bool
    error: str = ""
    kind: str = ""
    http_status: int = 0


def is_hls_stream_url(url: str) -> bool:
    lower = (url or "").lower()
    return ".m3u8" in lower or "/hls/" in lower


def _cors_allows_browser_fetch(headers: httpx.Headers) -> bool:
    acao = (headers.get("access-control-allow-origin") or "").strip()
    return acao == "*" or bool(acao)


def _looks_like_html(chunk: bytes) -> bool:
    head = chunk.lstrip()[:512].lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html") or b"<html" in head


def _looks_like_hls_manifest(chunk: bytes) -> bool:
    text = chunk.decode("utf-8", errors="ignore")
    return "#EXTM3U" in text or "#EXT-X-" in text


def _looks_like_audio(chunk: bytes, content_type: str) -> bool:
    ct = (content_type or "").lower()
    if ct.startswith("audio/") or "mpeg" in ct or "mp4" in ct:
        return True
    if not chunk:
        return False
    if chunk.startswith(b"ID3"):
        return True
    if len(chunk) >= 2 and chunk[0] == 0xFF and (chunk[1] & 0xE0) == 0xE0:
        return True
    if chunk.startswith(b"OggS") or chunk.startswith(b"fLaC"):
        return True
    return False


def probe_stream_url(url: str, *, timeout: float = _DEFAULT_TIMEOUT) -> StreamProbeResult:
    """Fetch stream head; verify format and (for HLS) browser CORS."""
    raw = (url or "").strip()
    if not raw:
        return StreamProbeResult(False, "empty stream URL")
    if not media_policy.stream_url_allowed(raw):
        return StreamProbeResult(False, "stream URL not allowed (HTTPS + allowlisted host)")

    hls = is_hls_stream_url(raw)
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout, connect=min(8.0, timeout)),
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            with client.stream("GET", raw) as resp:
                status = resp.status_code
                if status >= 400:
                    return StreamProbeResult(
                        False,
                        f"stream unreachable: HTTP {status}",
                        "hls" if hls else "audio",
                        status,
                    )
                chunk = b""
                for block in resp.iter_bytes(4096):
                    chunk += block
                    if len(chunk) >= _PROBE_BYTES:
                        break
                content_type = (resp.headers.get("content-type") or "").split(";")[0].strip()

                if _looks_like_html(chunk):
                    return StreamProbeResult(
                        False,
                        "stream URL returned HTML (not audio)",
                        "hls" if hls else "audio",
                        status,
                    )

                if hls:
                    if not _looks_like_hls_manifest(chunk):
                        return StreamProbeResult(
                            False,
                            "URL is not a valid HLS manifest (#EXTM3U missing)",
                            "hls",
                            status,
                        )
                    if not _cors_allows_browser_fetch(resp.headers):
                        return StreamProbeResult(
                            False,
                            "HLS stream not playable in browser (no Access-Control-Allow-Origin); "
                            "find another official stream URL",
                            "hls",
                            status,
                        )
                    return StreamProbeResult(True, kind="hls", http_status=status)

                if not _looks_like_audio(chunk, content_type):
                    return StreamProbeResult(
                        False,
                        "stream URL did not return recognizable audio data",
                        "audio",
                        status,
                    )
                return StreamProbeResult(True, kind="audio", http_status=status)
    except httpx.TimeoutException:
        return StreamProbeResult(False, "stream probe timed out")
    except httpx.RequestError as exc:
        return StreamProbeResult(False, f"stream probe failed: {exc}")


def validate_stream_for_library(url: str) -> str | None:
    """Return error message when URL must not be stored; ``None`` when ok."""
    result = probe_stream_url(url)
    return None if result.ok else (result.error or "stream validation failed")
