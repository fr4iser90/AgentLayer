"""System prompt snippet so agents know how to use the media library from chat."""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class MediaChatPromptDependencies(Protocol):
    def media_tables_exist(self) -> bool: ...

    def effective_media_library_enabled(self, *, user_id: uuid.UUID) -> bool: ...

    def media_quota_snapshot(self, *, user_id: uuid.UUID, tenant_id: int) -> dict[str, Any]: ...

    def dashboard_list(self, user_id: uuid.UUID, tenant_id: int, *, limit: int = 40) -> list[dict[str, Any]]: ...


_deps: MediaChatPromptDependencies | None = None


def register_media_chat_prompt_dependencies(deps: MediaChatPromptDependencies) -> None:
    global _deps
    _deps = deps


class _MediaDbPort:
    def media_tables_exist(self) -> bool:
        return bool(_deps and _deps.media_tables_exist())


class _MediaPolicyPort:
    def effective_media_library_enabled(self, *, user_id: uuid.UUID) -> bool:
        return bool(_deps and _deps.effective_media_library_enabled(user_id=user_id))

    def media_quota_snapshot(self, *, user_id: uuid.UUID, tenant_id: int) -> dict[str, Any]:
        if _deps is None:
            return {}
        return _deps.media_quota_snapshot(user_id=user_id, tenant_id=tenant_id)


class _DashboardDbPort:
    def dashboard_list(
        self,
        user_id: uuid.UUID,
        tenant_id: int,
        *,
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        return _deps.dashboard_list(user_id, tenant_id, limit=limit) if _deps is not None else []


media_db = _MediaDbPort()
media_policy = _MediaPolicyPort()
dashboard_db = _DashboardDbPort()


def build_media_library_context_snippet(
    *,
    user_id: uuid.UUID | None,
    tenant_id: int | None,
    ingested_audio: list[dict[str, Any]] | None = None,
    caller_is_admin: bool = False,
) -> str:
    if user_id is None or tenant_id is None:
        return ""
    if not media_db.media_tables_exist():
        return ""
    if not media_policy.effective_media_library_enabled(user_id=user_id):
        if caller_is_admin:
            return (
                "## Media library disabled (operator settings)\n"
                "Do not delegate to coding for streams, web search, or media setup.\n"
                "Call **media_quota** to confirm `library_enabled: false`, then **web_search** is still available here for stream URLs.\n"
                "As admin: `delegate` to `operator` with the user's playback goal only; operator uses "
                "`settings_get` → `settings_patch` (delta from live settings).\n"
                "After operator succeeds, retry media_add_stream / media_enqueue.\n"
                "Alternative: Admin → Interfaces → Platform in the Web UI."
            )
        return (
            "Media library is disabled by the operator. Tell the user to ask their admin to enable it under "
            "Admin → Interfaces → Platform (media library + uploads)."
        )

    snap = media_policy.media_quota_snapshot(user_id=user_id, tenant_id=tenant_id)
    boards = dashboard_db.dashboard_list(user_id, tenant_id, limit=40)
    media_boards = [b for b in boards if (b.get("kind") or "").strip() == "media_station"]
    has_player = False
    for b in boards:
        ul = b.get("ui_layout") if isinstance(b.get("ui_layout"), dict) else {}
        blocks = ul.get("blocks") if isinstance(ul.get("blocks"), list) else []
        for bl in blocks:
            if isinstance(bl, dict) and str(bl.get("type") or "").strip() == "media_player":
                has_player = True
                break
        if has_player:
            break

    lines = [
        "## Media library (music / radio / queue)",
        "You have media_* tools when this agent includes the media domain.",
        "Do not delegate to coding for music/radio — use media_* tools (or operator delegate only when library is off).",
        "Workflow:",
        "1. media_quota — check library_enabled, upload_enabled, remaining_bytes.",
        "2. media_list — list uploads, embeds, and external_link streams in the user's library "
        "(reuse saved streams; do not web_search again if already in the library).",
        "3. User MP3/audio in chat: attachments are auto-ingested to the library; use media_enqueue with media_item_id.",
        "4. YouTube/Vimeo: media_add_embed or media_enqueue with external_url (embed allowlist).",
        "5. Internet radio / HTTPS stream (MDR Jump, icecast): use web_search to find the official "
        "HTTPS stream URL, then media_add_stream and media_enqueue with play_now=true "
        "(stream host must be allowlisted).",
        "6. media_enqueue updates a dashboard media_player queue; playback continues in the app footer mini-player for uploads and streams.",
        "7. dashboard_id: omit when the user has exactly one board; prefer a media_station board when several exist.",
        "No YouTube downloading. Do not claim you lack audio tools when media_* are available.",
    ]
    lines.append(
        f"Quota: used {snap.get('used_bytes', 0)} / {snap.get('quota_bytes', 0)} bytes; "
        f"upload_enabled={snap.get('upload_enabled')}."
    )
    if media_boards:
        titles = ", ".join(
            f"{b.get('title') or 'Media station'} ({b.get('id')})" for b in media_boards[:5]
        )
        lines.append(f"Media-station dashboards: {titles}.")
    elif not has_player:
        lines.append(
            "User may need a dashboard with a media_player block (template media_station-v1) before enqueue works."
        )
    if ingested_audio:
        lines.append("Just ingested from this message:")
        for it in ingested_audio:
            lines.append(
                f"- {it.get('title')}: media_item_id={it.get('media_item_id')} — enqueue with play_now=true."
            )
    return "\n".join(lines)
