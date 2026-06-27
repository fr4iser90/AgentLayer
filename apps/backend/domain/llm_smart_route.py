"""Heuristic + small router model: local catalog provider vs external API per chat request.

Enable ``llm_smart_routing_enabled`` in operator settings (Web UI / DB). External
credentials still come from operator_settings; this module only picks which backend
to use for the main completion.

**How many LLM HTTP calls per user chat turn (this module + main completion)?**

- Heuristics alone decide (``smart_route:heuristic_*``): **one** call — only the main
  ``/v1/chat/completions``.
- Heuristics are inconclusive: **two** calls — first a configured router model/provider,
  then the main completion.
- Fail-safe: if the local router call fails, fall back to the local provider for the main completion.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal, Protocol

from apps.backend.core.config import config
from apps.backend.domain.model_routing import messages_contain_image_parts
from apps.backend.domain.plugin_system.tool_routing import last_user_text

logger = logging.getLogger(__name__)

_EXTERNAL_HINTS = (
    "komplex",
    "complex analysis",
    "analysiere",
    "analyze in depth",
    "refactor",
    "architektur",
    "architecture",
    "debugging session",
    "großes projekt",
    "large codebase",
    "production system",
    "security audit",
    "multi-step",
    "mehrstufig",
    "ocr",
    "transkrib",
)


class SmartRouteDependencies(Protocol):
    def smart_routing_params(self) -> dict[str, Any]: ...

    def catalog_provider_exists(self, provider_id: str) -> bool: ...

    def post_catalog_chat_completions(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str,
        provider_id: str,
        timeout: float,
        temperature: int,
        max_tokens: int,
        stream: bool,
    ) -> tuple[dict[str, Any], bool]: ...


_deps: SmartRouteDependencies | None = None


def register_smart_route_dependencies(deps: SmartRouteDependencies) -> None:
    global _deps
    _deps = deps


def _require_deps() -> SmartRouteDependencies:
    if _deps is None:
        raise RuntimeError("smart route dependencies not registered")
    return _deps


def smart_routing_params() -> dict[str, Any]:
    return _require_deps().smart_routing_params()


def catalog_provider_exists(provider_id: str) -> bool:
    return _require_deps().catalog_provider_exists(provider_id)


def post_catalog_chat_completions(
    *,
    messages: list[dict[str, Any]],
    model: str,
    provider_id: str,
    timeout: float,
    temperature: int,
    max_tokens: int,
    stream: bool,
) -> tuple[dict[str, Any], bool]:
    return _require_deps().post_catalog_chat_completions(
        messages=messages,
        model=model,
        provider_id=provider_id,
        timeout=timeout,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=stream,
    )


def _count_code_fences(text: str) -> int:
    if not text:
        return 0
    return text.count("```") // 2


def _heuristic_snapshot(messages: list[dict[str, Any]], p: dict[str, Any]) -> dict[str, Any]:
    last = (last_user_text(messages) or "").strip()
    n_msgs = len(messages)
    n_fence = _count_code_fences(last)
    long_prompt = len(last) >= int(p["long_prompt_chars"])
    short = len(last) <= int(p["short_local_max_chars"])
    has_image = messages_contain_image_parts(messages)
    low = last.lower()
    keyword_hit = any(h in low for h in _EXTERNAL_HINTS)
    many_msgs = n_msgs > int(p["many_messages"])
    many_fences = n_fence >= int(p["many_code_fences"])

    return {
        "last_user_chars": len(last),
        "message_count": n_msgs,
        "code_fence_pairs_approx": n_fence,
        "has_image_or_multimodal": has_image,
        "keyword_complex_hint": keyword_hit,
        "long_prompt": long_prompt,
        "short_prompt": short,
        "many_messages": many_msgs,
        "many_code_fences": many_fences,
    }


def _force_external(s: dict[str, Any]) -> bool:
    if s["has_image_or_multimodal"]:
        return True
    if s["long_prompt"]:
        return True
    if s["many_code_fences"]:
        return True
    if s["keyword_complex_hint"]:
        return True
    if s["many_messages"]:
        return True
    return False


def _force_local(s: dict[str, Any]) -> bool:
    if s["has_image_or_multimodal"]:
        return False
    if s["long_prompt"] or s["many_code_fences"] or s["keyword_complex_hint"]:
        return False
    if s["short_prompt"] and s["message_count"] <= 6:
        return True
    return False


def _parse_router_json(content: str) -> dict[str, Any] | None:
    t = (content or "").strip()
    if not t:
        return None
    if "```" in t:
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", t)
        if m:
            t = m.group(1).strip()
    try:
        out = json.loads(t)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        m2 = re.search(r"\{[\s\S]*\}", t)
        if m2:
            try:
                out = json.loads(m2.group(0))
                return out if isinstance(out, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _router_provider_id(p: dict[str, Any]) -> str | None:
    raw = str(p.get("router_model_catalog_owned_by") or "").strip()
    if not raw:
        raw = (getattr(config, "LLM_ROUTER_PROVIDER_ID", None) or "").strip()
    if raw:
        if catalog_provider_exists(raw):
            return raw
    return None


def _call_local_router_model(
    messages: list[dict[str, Any]], snap: dict[str, Any], p: dict[str, Any]
) -> dict[str, Any] | None:
    model = str(p.get("router_model") or "").strip()
    if not model:
        logger.warning("smart route: router model not configured in Admin → Interfaces")
        return None
    provider_id = _router_provider_id(p)
    if not provider_id:
        logger.warning("smart route: router provider not configured or unavailable")
        return None
    last = (last_user_text(messages) or "")[:2000]
    user_payload = (
        "Classify whether the MAIN chat completion should run on-device (local) or on external cloud API.\n"
        f"Signals (JSON): {json.dumps(snap, ensure_ascii=False)}\n"
        f"Last user message (truncated):\n{last}"
    )
    sys_prompt = (
        "You are a routing classifier. Reply with ONE JSON object only, no markdown fences:\n"
        '{"route":"provider"|"provider_db","confidence":0.0,"reason":"..."}\n'
        "- route=local if a small on-device model is enough (short chat, simple Q&A).\n"
        "- route=external if the task needs stronger cloud models (deep reasoning, long code, architecture, risk).\n"
        "- confidence: how sure (0..1) that LOCAL is sufficient; if unsure, prefer low confidence.\n"
    )
    timeout = float(p.get("router_timeout_sec") or 12.0)
    try:
        data, _omitted = post_catalog_chat_completions(
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_payload},
            ],
            model=model,
            provider_id=provider_id,
            timeout=timeout,
            temperature=0,
            max_tokens=200,
            stream=False,
        )
    except Exception as e:
        logger.warning("smart route: router model call failed: %s", e)
        return None
    try:
        choice0 = (data.get("choices") or [{}])[0]
        msg = (choice0.get("message") or {}) if isinstance(choice0, dict) else {}
        content = msg.get("content")
        text = content if isinstance(content, str) else ""
        return _parse_router_json(text)
    except Exception as e:
        logger.warning("smart route: bad router response: %s", e)
        return None


def decide_smart_backend(
    messages: list[dict[str, Any]],
) -> tuple[Literal["provider", "provider_db"], str]:
    """
    Return (backend, reason_tag) for the main LLM request.

    - ``provider`` = first env catalog provider (``provider_1`` by default).
    - ``provider_db`` = first saved DB endpoint (``provider_db_1``, …).

    Call budget: 0 or 1 extra **local** router request (see module docstring), then
    exactly one main completion — never two admin calls caused by routing alone.
    """
    p = smart_routing_params()
    snap = _heuristic_snapshot(messages, p)

    if _force_external(snap):
        return "provider_db", "smart_route:heuristic_external"

    if _force_local(snap):
        return "provider", "smart_route:heuristic_local"

    parsed = _call_local_router_model(messages, snap, p)
    if not parsed:
        return "provider", "smart_route:router_fail_fallback_local"

    route = str(parsed.get("route") or "").strip().lower()
    try:
        conf = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    reason = str(parsed.get("reason") or "")[:200]

    min_conf = float(p.get("local_confidence_min") or 0.7)

    if route in ("provider_db", "cloud", "api"):
        return "provider_db", f"smart_route:router:{reason or 'provider_db'}"

    if route in ("provider", "ondevice", "device"):
        if conf < min_conf:
            return "provider_db", f"smart_route:low_confidence_local({conf:.2f}<{min_conf})"
        return "provider", f"smart_route:router_local({conf:.2f}):{reason or 'ok'}"

    return "provider", "smart_route:router_ambiguous_fallback_local"
