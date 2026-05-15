"""Chat tool: run iterative HTML build/sanitize loop (implementation in ``workflows/creative/``)."""

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
from typing import Any, Callable

from apps.backend.domain.chat_image_attachments import merge_chat_images_into_html_build_assets
from apps.backend.domain.plugin_system.tool_routing import last_user_text
from apps.backend.domain.tool_invocation_context import get_tool_invocation_messages

logger = logging.getLogger(__name__)

__version__ = "1.0.1"
TOOL_ID = "run_iterative_html_build"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "meta"
TOOL_LABEL = "Iterative HTML build"
TOOL_DESCRIPTION = (
    "Runs a multi-round local-LLM loop: generate one self-contained HTML5 page from your goal, "
    "validate, then revise until pass or max rounds (same limit as AGENT_MAX_TOOL_ROUNDS). "
    "Output is written under workflows/creative/output/iterative-html/<timestamp>/. "
    "If the user attached PNG/JPEG/WebP/GIF images in the same chat turn, they are saved under "
    "uploads/ with their original filenames (e.g. hero.png) automatically — do not base64 them "
    "into the tool arguments unless you need extra assets beyond the chat uploads. "
    "Optional ``assets`` in parameters: small images as base64 when not from chat."
)
TOOL_CAPABILITIES = ("creative.web.build",)

_wf_mod: Any | None = None


def _workflow_module() -> Any:
    global _wf_mod
    if _wf_mod is not None:
        return _wf_mod
    repo = Path(__file__).resolve().parents[3]
    path = repo / "workflows" / "creative" / "iterative_html_build.py"
    if not path.is_file():
        raise RuntimeError(f"workflow implementation missing: {path}")
    spec = importlib.util.spec_from_file_location("iterative_html_build_workflow", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load workflow spec")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _wf_mod = mod
    return mod


_GOAL_ALIASES = ("goal", "description", "brief", "prompt", "product_goal", "product_brief")


def _coalesce_goal(arguments: dict[str, Any]) -> dict[str, Any]:
    """Many models send ``description`` instead of ``goal``; normalize to ``goal``."""
    out = dict(arguments)
    if isinstance(out.get("goal"), str) and out["goal"].strip():
        return out
    for key in _GOAL_ALIASES[1:]:
        v = out.get(key)
        if isinstance(v, str) and v.strip():
            out["goal"] = v.strip()
            logger.info("run_iterative_html_build: using %r as goal (mapped to goal)", key)
            return out
    return out


def _goal_from_chat_if_empty(arguments: dict[str, Any]) -> dict[str, Any]:
    """If the model emitted ``{}``, use the last user message text as the product brief."""
    out = dict(arguments)
    if isinstance(out.get("goal"), str) and out["goal"].strip():
        return out
    msgs = get_tool_invocation_messages()
    if not msgs:
        return out
    hint = last_user_text(msgs).strip()
    if hint:
        out["goal"] = hint
        logger.info(
            "run_iterative_html_build: filled goal from last user message (%d chars)", len(hint)
        )
    return out


def run_iterative_html_build(arguments: dict[str, Any]) -> str:
    arguments = merge_chat_images_into_html_build_assets(
        dict(arguments or {}),
        get_tool_invocation_messages(),
    )
    arguments = _coalesce_goal(arguments)
    arguments = _goal_from_chat_if_empty(arguments)
    goal = arguments.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "goal (string) is required — describe the single page to build. "
                    "Use parameter name ``goal`` (or ``description``). If arguments were empty, "
                    "your last chat message is used when present."
                ),
            },
            ensure_ascii=False,
        )
    try:
        mod = _workflow_module()
        fn = getattr(mod, "iterative_html_build", None)
        if not callable(fn):
            return json.dumps({"ok": False, "error": "iterative_html_build not found in workflow module"})
        return str(fn(arguments))
    except Exception as e:
        logger.exception("run_iterative_html_build failed")
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "run_iterative_html_build": run_iterative_html_build,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_iterative_html_build",
            "TOOL_DESCRIPTION": "Runs a multi-round local-LLM loop: generate one self-contained HTML5 page from your goal, "
            "validate, then revise until pass or max rounds (same limit as AGENT_MAX_TOOL_ROUNDS). "
            "Output is written under workflows/creative/output/iterative-html/<timestamp>/. "
            "If the user attached PNG/JPEG/WebP/GIF images in the same chat turn, they are saved under "
            "uploads/ with their original filenames (e.g. hero.png) automatically — do not base64 them "
            "into the tool arguments unless you need extra assets beyond the chat uploads. "
            "Optional ``assets`` in parameters: small images as base64 when not from chat.",
            "parameters": {
                "type": "object",
                "required": ["goal"],
                "properties": {
                    "goal": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Full product brief in natural language (German or English). "
                            "One static index.html: layout, copy, optional CSS animation, inline assets. "
                            "If you use ``description`` instead, the server maps it to goal."
                        ),
                    },
                    "description": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Same meaning as ``goal`` — some models use this key; prefer ``goal`` when possible."
                        ),
                    },
                    "assets": {
                        "type": "array",
                        "TOOL_DESCRIPTION": (
                            "Optional extra images (not already attached in chat). Each element: object with "
                            "`name` (filename), `media_type` (e.g. image/png), `data_base64` (standard base64, "
                            "no data: prefix). Max 5 files total including chat uploads; max ~400KB decoded each."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "media_type": {"type": "string"},
                                "data_base64": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
]
