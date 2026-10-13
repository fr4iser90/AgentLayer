"""LLM provider, model-routing profile, and tool-round/timeout settings."""

from __future__ import annotations

import logging
import os

from apps.backend.infrastructure.platform.config_env import env_bool as _env_bool
from apps.backend.infrastructure.platform.config_env import env_int as _env_int

logger = logging.getLogger(__name__)

# --- Unified LLM providers (OpenAI-compatible) ---
# Numbered env rows: LLM_PROVIDER_1_BASE_URL, LLM_PROVIDER_1_LABEL, LLM_PROVIDER_1_API_KEY,
# LLM_PROVIDER_1_API_HEADER_NAME (default Authorization), optional _MODEL_DEFAULT/_VLM/_AGENT/_CODING,
# optional LLM_PROVIDER_N_MAX_PARALLEL (1–64, default 1).
# Parsed by :mod:`llm_env_providers`; registered as provider_1, provider_2, … in the catalog.
LLM_HTTP_MAX_PARALLEL_DEFAULT = max(1, min(64, _env_int("LLM_HTTP_MAX_PARALLEL_DEFAULT", 4)))
LLM_AUX_PROVIDER_ID = (os.environ.get("LLM_AUX_PROVIDER_ID") or "").strip() or None
LLM_ROUTER_PROVIDER_ID = (os.environ.get("LLM_ROUTER_PROVIDER_ID") or "").strip() or None
LLM_AUX_MODEL = (os.environ.get("LLM_AUX_MODEL") or "").strip() or None

# Hybrid model routing: per-profile defaults (empty = endpoint catalog model_default / UI picker).
AGENT_MODEL_PROFILE_DEFAULT = (os.environ.get("AGENT_MODEL_PROFILE_DEFAULT") or "").strip() or None
AGENT_MODEL_PROFILE_VLM = (os.environ.get("AGENT_MODEL_PROFILE_VLM") or "").strip() or None
AGENT_MODEL_PROFILE_AGENT = (os.environ.get("AGENT_MODEL_PROFILE_AGENT") or "").strip() or None
AGENT_MODEL_PROFILE_CODING = (os.environ.get("AGENT_MODEL_PROFILE_CODING") or "").strip() or None
# If false, client ``model`` and X-Agent-Model-Override are ignored (profiles / auto-VLM only).
AGENT_ALLOW_MODEL_OVERRIDE = _env_bool("AGENT_ALLOW_MODEL_OVERRIDE", True)
# Comma-separated roles (e.g. admin) allowed to override; empty = any authenticated user (Bearer → DB user).
AGENT_MODEL_OVERRIDE_ROLES = frozenset(
    x.strip().lower()
    for x in (os.environ.get("AGENT_MODEL_OVERRIDE_ROLES") or "").split(",")
    if x.strip()
)
# If true, unauthenticated optional-route callers may still set model / override header.
AGENT_MODEL_OVERRIDE_ANONYMOUS = _env_bool("AGENT_MODEL_OVERRIDE_ANONYMOUS", False)

MAX_TOOL_ROUNDS_CAP = max(256, _env_int("AGENT_MAX_TOOL_ROUNDS_CAP", 16384))


def _parse_tool_rounds_env(raw: str, *, env_name: str) -> int | None:
    """Parse ``AGENT_MAX_TOOL_ROUNDS`` / ``SUBAGENT_MAX_TOOL_ROUNDS``: empty → None; <=0 → cap; else clamped."""
    if not raw.strip():
        return None
    try:
        v = int(raw.strip())
    except ValueError:
        logger.warning("invalid %s %r — ignored", env_name, raw)
        return None
    if v <= 0:
        logger.info(
            "%s=%s → using high cap %s tool rounds (override with AGENT_MAX_TOOL_ROUNDS_CAP)",
            env_name,
            raw.strip(),
            MAX_TOOL_ROUNDS_CAP,
        )
        return MAX_TOOL_ROUNDS_CAP
    return max(1, min(v, MAX_TOOL_ROUNDS_CAP))


def _resolve_max_tool_rounds() -> int:
    """``AGENT_MAX_TOOL_ROUNDS``: positive = limit (capped); 0 or negative = cap; unset = 8."""
    raw = (os.environ.get("AGENT_MAX_TOOL_ROUNDS") or "").strip()
    if not raw:
        return 8
    parsed = _parse_tool_rounds_env(raw, env_name="AGENT_MAX_TOOL_ROUNDS")
    return parsed if parsed is not None else 8


MAX_TOOL_ROUNDS = _resolve_max_tool_rounds()


def _resolve_subagent_max_tool_rounds() -> int:
    """``SUBAGENT_MAX_TOOL_ROUNDS`` overrides ``AGENT_MAX_TOOL_ROUNDS`` for ``delegate`` sub-agents only."""
    raw = (os.environ.get("SUBAGENT_MAX_TOOL_ROUNDS") or "").strip()
    if raw:
        parsed = _parse_tool_rounds_env(raw, env_name="SUBAGENT_MAX_TOOL_ROUNDS")
        if parsed is not None:
            return parsed
    return MAX_TOOL_ROUNDS


SUBAGENT_MAX_TOOL_ROUNDS = _resolve_subagent_max_tool_rounds()


def _resolve_subagent_timeout_sec() -> float | None:
    """``SUBAGENT_TIMEOUT_SEC``: positive = wall-clock cap for ``delegate`` runs; unset or <=0 = no limit."""
    raw = (os.environ.get("SUBAGENT_TIMEOUT_SEC") or "").strip()
    if not raw:
        return None
    try:
        v = float(raw)
    except ValueError:
        logger.warning(
            "invalid SUBAGENT_TIMEOUT_SEC %r — no sub-agent wall-clock timeout",
            raw,
        )
        return None
    if v <= 0:
        return None
    return v


SUBAGENT_TIMEOUT_SEC = _resolve_subagent_timeout_sec()


def _resolve_llm_chat_timeout_sec() -> float | None:
    """``AGENT_LLM_CHAT_TIMEOUT_SEC``: unset or <=0 = no HTTP read timeout; positive = seconds."""
    raw = (os.environ.get("AGENT_LLM_CHAT_TIMEOUT_SEC") or "").strip()
    if not raw:
        return None
    try:
        v = float(raw)
    except ValueError:
        logger.warning("invalid AGENT_LLM_CHAT_TIMEOUT_SEC %r — no LLM HTTP timeout", raw)
        return None
    if v <= 0:
        return None
    return v


LLM_CHAT_TIMEOUT_SEC: float | None = _resolve_llm_chat_timeout_sec()
