"""Validate uploaded dashboard file bytes (image magic + text/markdown family)."""

from __future__ import annotations

TEXT_MIME_BY_EXT: dict[str, str] = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".log": "text/plain",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
}

DEFAULT_BOARD_UPLOAD_MIME = (
    "image/jpeg,image/png,image/gif,image/webp,"
    "text/markdown,text/plain,text/csv,text/yaml,application/json"
)

_TEXT_LIKE_PREFIXES = ("text/",)
_TEXT_LIKE_EXACT = frozenset({"application/json", "application/yaml"})


def sniff_image_mime(head: bytes) -> str | None:
    if len(head) >= 3 and head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(head) >= 8 and head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(head) >= 6 and head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalized_content_type(raw: str | None) -> str:
    if not raw:
        return ""
    return raw.split(";")[0].strip().lower()


def is_image_mime(mime: str | None) -> bool:
    return bool(mime) and mime.startswith("image/")


def is_text_like_mime(mime: str | None) -> bool:
    if not mime:
        return False
    if mime.startswith(_TEXT_LIKE_PREFIXES):
        return True
    return mime in _TEXT_LIKE_EXACT


def _ext_mime(filename: str) -> str | None:
    name = (filename or "").strip().lower()
    if not name:
        return None
    for ext, mime in TEXT_MIME_BY_EXT.items():
        if name.endswith(ext):
            return mime
    return None


def _utf8_ok(data: bytes) -> bool:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def sniff_upload_mime(
    data: bytes,
    *,
    filename: str = "",
    declared: str | None = None,
) -> str | None:
    """Resolve MIME for board uploads: images by magic, text by extension/UTF-8."""
    if not data:
        return None
    img = sniff_image_mime(data[:64])
    if img:
        return img

    declared_n = normalized_content_type(declared)
    ext_mime = _ext_mime(filename)
    if ext_mime:
        if not _utf8_ok(data):
            return None
        return ext_mime

    if declared_n and is_text_like_mime(declared_n):
        if not _utf8_ok(data):
            return None
        # Prefer markdown when declared generically as text/plain but name suggests md
        return declared_n

    return None


def decode_text_payload(data: bytes) -> str | None:
    """Decode UTF-8 board text; returns None if invalid."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None
