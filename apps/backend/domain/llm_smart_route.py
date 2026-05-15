"""
Heuristic + small local model routing: Ollama vs external API per chat request.

Enable ``llm_smart_routing_enabled`` in operator settings (Web UI / DB). External
credentials still come from operator_settings; this module only picks which backend
to use for the main completion.

**How many LLM HTTP calls per user chat turn (this module + main completion)?**

- Heuristics alone decide (``smart_route:heuristic_*``): **one** call — only the main
  ``/v1/chat/completions`` (Ollama or external).
- Heuristics are inconclusive: **two** calls — first a **local** Ollama router
  (same ``OLLAMA_BASE_URL``), then the main completion. The router never hits the
  external API.
- Fail-safe: if the local router call fails or returns unusable JSON, we fall back
  to **Ollama** for the main completion so we do not burn external quota by mistake.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from apps.backend.core.config import config
from apps.backend.domain.model_routing import messages_contain_image_parts
from apps.backend.domain.plugin_system.tool_routing import last_user_text
from apps.backend.infrastructure.openai_compat_http import http_post_chat_completions
from apps.backend.infrastructure.operator_settings import smart_routing_params

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


def _call_local_router_model(
    messages: list[dict[str, Any]], snap: dict[str, Any], p: dict[str, Any]
) -> dict[str, Any] | None:
    model = str(p.get("router_model") or "nemotron-3-nano:4b").strip() or "nemotron-3-nano:4b"
    last = (last_user_text(messages) or "")[:2000]
    user_payload = (
        "Classify whether the MAIN chat completion should run on-device (local) or on external cloud API.\n"
        f"Signals (JSON): {json.dumps(snap, ensure_ascii=False)}\n"
        f"Last user message (truncated):\n{last}"
    )
    sys_prompt = (
        "You are a routing classifier. Reply with ONE JSON object only, no markdown fences:\n"
        '{"route":"local"|"external","confidence":0.0,"reason":"..."}\n'
        "- route=local if a small on-device model is enough (short chat, simple Q&A).\n"
        "- route=external if the task needs stronger cloud models (deep reasoning, long code, architecture, risk).\n"
        "- confidence: how sure (0..1) that LOCAL is sufficient; if unsure, prefer low confidence.\n"
    )
    url = f"{config.OLLAMA_BASE_URL.rstrip('/')}/v1/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_payload},
        ],
        "stream": False,
        "temperature": 0,
        "max_tokens": 200,
    }
    timeout = float(p.get("router_timeout_sec") or 12.0)
    try:
        data, _omitted = http_post_chat_completions(url, payload, timeout=timeout)
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
) -> tuple[Literal["ollama", "external"], str]:
    """
    Return (backend, reason_tag) for the main LLM request.

    - ``ollama`` = use local OpenAI-compatible Ollama endpoint.
    - ``external`` = use operator-configured external API.

    Call budget: 0 or 1 extra **local** router request (see module docstring), then
    exactly one main completion — never two external calls caused by routing alone.
    """
    p = smart_routing_params()
    snap = _heuristic_snapshot(messages, p)

    if _force_external(snap):
        return "external", "smart_route:heuristic_external"

    if _force_local(snap):
        return "ollama", "smart_route:heuristic_local"

    parsed = _call_local_router_model(messages, snap, p)
    if not parsed:
        # Router is local-only; do not send the main request to external on parse/HTTP failure.
        return "ollama", "smart_route:router_fail_fallback_ollama"

    route = str(parsed.get("route") or "").strip().lower()
    try:
        conf = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    reason = str(parsed.get("reason") or "")[:200]

    min_conf = float(p.get("local_confidence_min") or 0.7)

    if route in ("external", "cloud", "api"):
        return "external", f"smart_route:router:{reason or 'external'}"

    if route in ("local", "ollama", "ondevice", "device"):
        if conf < min_conf:
            return "external", f"smart_route:low_confidence_local({conf:.2f}<{min_conf})"
        return "ollama", f"smart_route:router_local({conf:.2f}):{reason or 'ok'}"

    # Unclear route token — prefer local main completion to avoid surprise external quota use.
    return "ollama", "smart_route:router_ambiguous_fallback_ollama"
