"""Dashboard onboarding manifests (``*.setup.json`` in bundle folders)."""

from __future__ import annotations

import json
import logging
from typing import Any

from apps.backend.infrastructure.dashboards.dashboard_bundle import bundles_by_kind

logger = logging.getLogger(__name__)

_SETUP_CACHE: dict[str, dict[str, Any] | None] = {}


def _pick_lang(obj: Any, lang: str) -> str:
    if isinstance(obj, str):
        return obj.strip()
    if not isinstance(obj, dict):
        return ""
    key = (lang or "en").strip().lower()[:2]
    for k in (key, "en", "de"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for v in obj.values():
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _pick_lang_list(obj: Any, lang: str) -> list[str]:
    if isinstance(obj, list):
        return [str(x).strip() for x in obj if str(x).strip()]
    if not isinstance(obj, dict):
        return []
    key = (lang or "en").strip().lower()[:2]
    for k in (key, "en", "de"):
        raw = obj.get(k)
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
    return []


def load_setup_raw(kind: str) -> dict[str, Any] | None:
    k = (kind or "").strip().lower()
    if not k or k == "custom":
        return None
    if k in _SETUP_CACHE:
        return _SETUP_CACHE[k]

    bundle = bundles_by_kind().get(k)
    if bundle is None or bundle.setup is None or not bundle.setup.is_file():
        _SETUP_CACHE[k] = None
        return None
    try:
        raw = json.loads(bundle.setup.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("invalid setup json for kind %s: %s", k, e)
        _SETUP_CACHE[k] = None
        return None
    if not isinstance(raw, dict):
        _SETUP_CACHE[k] = None
        return None
    _SETUP_CACHE[k] = raw
    return raw


def localize_setup(raw: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    steps_out: list[dict[str, str]] = []
    for step in raw.get("steps") or []:
        if not isinstance(step, dict):
            continue
        sid = str(step.get("id") or "").strip()
        if not sid:
            continue
        steps_out.append(
            {
                "id": sid,
                "label": _pick_lang(step.get("label"), lang),
                "tool_hint": str(step.get("tool_hint") or "").strip(),
            }
        )

    return {
        "version": int(raw.get("version") or 1),
        "kind": str(raw.get("kind") or "").strip(),
        "greeting": _pick_lang(raw.get("greeting"), lang),
        "agent_prompt": _pick_lang(raw.get("agent_prompt"), lang),
        "steps": steps_out,
        "suggested_tools": [
            str(x).strip()
            for x in (raw.get("suggested_tools") or [])
            if isinstance(x, str) and str(x).strip()
        ],
        "chat_starters": _pick_lang_list(raw.get("chat_starters"), lang),
    }


def onboarding_for_kind(kind: str, lang: str = "en") -> dict[str, Any] | None:
    raw = load_setup_raw(kind)
    if not raw:
        return None
    out = localize_setup(raw, lang)
    if not out.get("greeting") and not out.get("agent_prompt"):
        return None
    return out


def onboarding_for_dashboard(row: dict[str, Any], lang: str = "en") -> dict[str, Any] | None:
    kind = str(row.get("kind") or "").strip().lower()
    return onboarding_for_kind(kind, lang)


def attach_onboarding(row: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    ob = onboarding_for_dashboard(row, lang)
    if not ob:
        return row
    return {**row, "onboarding": ob}


def setup_tool_payload(kind: str, lang: str = "en") -> dict[str, Any] | None:
    """Extra fields for agent ``create_dashboard`` tool responses."""
    raw = load_setup_raw(kind)
    if not raw:
        return None
    return {
        "onboarding": {
            "de": localize_setup(raw, "de"),
            "en": localize_setup(raw, "en"),
            "preferred": localize_setup(raw, lang),
        },
        "setup_hint": (
            "Run the onboarding conversation: greet the user using onboarding.preferred (or de/en), "
            "offer the listed steps, and use the suggested dashboard tools (list_append, patch_data, …). "
            "Do not install schema — only fill this board."
        ),
    }
