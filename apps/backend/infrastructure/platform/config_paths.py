"""On-disk roots (plugins, data dir) plus upload and media library storage settings."""

from __future__ import annotations

import os
from pathlib import Path

from apps.backend.infrastructure.platform.config_env import env_bool as _env_bool
from apps.backend.infrastructure.platform.config_env import env_int as _env_int

_PLUGINS_DIR_RAW = os.environ.get("AGENT_PLUGINS_DIR", "").strip()
if _PLUGINS_DIR_RAW:
    PLUGINS_DIR = Path(_PLUGINS_DIR_RAW)
else:
    PLUGINS_DIR = Path(__file__).resolve().parents[4] / "plugins"

DATA_DIR = os.environ.get("AGENT_DATA_DIR", "/data")

# Before replace_tool / update_tool / create_tool overwrite, copy prior .py here (UTC timestamp prefix).
TOOLS_BACKUP_ENABLED = _env_bool("AGENT_TOOLS_BACKUP_ENABLED", True)


def tools_backup_directory() -> Path:
    raw = (os.environ.get("AGENT_TOOLS_BACKUP_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(DATA_DIR) / "tool_backups"


# Dashboard UI: binary uploads (e.g. gallery). Operator may override max MB / MIME in DB.
WORKSPACE_UPLOAD_MAX_FILE_MB = max(1, min(_env_int("AGENT_WORKSPACE_UPLOAD_MAX_MB", 10), 512))


def WORKSPACE_upload_dir() -> Path:
    raw = (os.environ.get("AGENT_WORKSPACE_UPLOAD_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(DATA_DIR) / "WORKSPACE_uploads"


def WORKSPACE_upload_env_allowed_mime() -> frozenset[str]:
    from apps.backend.infrastructure.dashboards.dashboard_upload_bytes import DEFAULT_BOARD_UPLOAD_MIME

    raw = (
        os.environ.get("AGENT_WORKSPACE_UPLOAD_ALLOWED_MIME")
        or DEFAULT_BOARD_UPLOAD_MIME
    ).strip()
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


def dashboard_upload_dir() -> Path:
    """Gallery uploads (alias for ``WORKSPACE_upload_dir``)."""
    return WORKSPACE_upload_dir()


# --- Media library (user uploads + embed refs; bytes on disk under media_uploads/) ---
MEDIA_DEFAULT_USER_QUOTA_MB = max(1, min(_env_int("AGENT_MEDIA_DEFAULT_USER_QUOTA_MB", 500), 50_000))
MEDIA_UPLOAD_MAX_FILE_MB = max(1, min(_env_int("AGENT_MEDIA_UPLOAD_MAX_FILE_MB", 50), 512))


def media_upload_dir() -> Path:
    raw = (os.environ.get("AGENT_MEDIA_UPLOAD_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(DATA_DIR) / "media_uploads"


def media_upload_env_allowed_mime() -> frozenset[str]:
    raw = (
        os.environ.get("AGENT_MEDIA_UPLOAD_ALLOWED_MIME")
        or "audio/mpeg,audio/mp4,audio/flac,audio/ogg,audio/wav,video/mp4"
    ).strip()
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


def media_embed_env_allowed_hosts() -> frozenset[str]:
    raw = (
        os.environ.get("AGENT_MEDIA_EMBED_ALLOWED_HOSTS")
        or "www.youtube.com,youtube.com,www.youtube-nocookie.com,player.vimeo.com"
    ).strip()
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


def media_stream_env_allowed_hosts() -> frozenset[str]:
    raw = (
        os.environ.get("AGENT_MEDIA_STREAM_ALLOWED_HOSTS")
        or (
            "mdr.de,www.mdr.de,cast.addradio.de,listen.streamtheworld.com,"
            "playerservices.streamtheworld.com,icecast.mdradio.de,stream.radio.co,"
            "akamaized.net,mdr-radio-hls.akamaized.net"
        )
    ).strip()
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())
