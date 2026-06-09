"""Tool ranking, guards, arguments, registry helpers."""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from json import JSONDecoder
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

import httpx

from apps.backend.core.config import config
from apps.backend.domain.identity import get_identity
from apps.backend.api import memory as memory_api
from apps.backend.domain.agent_registry import get_agent_registry
from apps.backend.infrastructure.openai_compat_http import http_post_chat_completions
from apps.backend.infrastructure.openai_stream_aggregate import stream_chat_completions_aggregate
from apps.backend.infrastructure.stream_repetition_guard import apply_repetition_guard_to_completion
from apps.backend.domain.plugin_system.registry import get_registry
from apps.backend.dashboard import db as dashboard_db
from apps.backend.domain.plugin_system.capability_governance import parse_user_capability_confirm
from apps.backend.domain.plugin_system.capability_index import filter_merged_tools_by_capabilities
from apps.backend.domain.plugin_system.tool_routing import (
    TOOL_INTROSPECTION,
    classify_user_tool_categories,
    filter_merged_tools_by_categories,
    filter_merged_tools_by_domain,
    last_user_text,
)
from apps.backend.domain.schedule_run_context import record_schedule_abort, record_schedule_tool_event
from apps.backend.domain.tool_executor import execute_tool
from apps.backend.domain.tool_invocation_context import (
    bind_capability_confirmed,
    reset_capability_confirmed,
    reset_tool_invocation_messages,
    set_tool_invocation_messages,
)
from apps.backend.domain.llm_smart_route import decide_smart_backend
from apps.backend.domain.model_routing import profile_default_model_id, resolve_effective_model
from apps.backend.domain.user_persona import _append_system_block, apply_user_persona_system
from apps.backend.infrastructure.operator_settings import (
    external_llm_should_failover,
    llm_chat_transport,
    normalize_model_catalog_owned_by,
    smart_llm_routing_enabled,
)

logger = logging.getLogger(__name__)

from apps.backend.domain.agent_io import (  # noqa: E402
    _format_normalized_tool_args_for_recap,
    _parse_tool_arguments,
    _text_blobs_from_message,
)
from apps.backend.domain.agent_prompts import (  # noqa: E402
    AgentChatCancelled,
    WorkspaceAccessDenied,
    _tool_spec_name,
)

# =============================================================================
# Tool Ranking System (Phase 1: Semantic Search based)
# =============================================================================

# Tool Embedding Cache (computed once, cached in memory)
_tool_embedding_cache: dict[str, list[float]] = {}
_tool_embedding_loaded = False


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _get_tool_description(tool_spec: dict[str, Any]) -> str:
    """Extract description from tool spec."""
    func = tool_spec.get("function", {})
    return func.get("description", "") or ""


# Survive category router + semantic top-N when an agent allowlists them (e.g. coding + SSC).
_AGENT_CREDENTIAL_TOOL_NAMES = frozenset(
    {
        "save_user_secret",
        "register_secrets",
        "request_user_secret",
        "secrets_help",
        "user_secrets_status",
    }
)
# Always forwarded to the LLM when the agent allowlists them (ranking would drop them otherwise).
_AGENT_GIT_NETWORK_TOOL_NAMES = frozenset(
    {
        "git_push",
        "git_sync",
    }
)
_CODING_READ_TOOL_PINS = frozenset(
    {
        "read_file",
        "search",
        "glob",
        "list_dir",
        "retrieve_context",
    }
)
_SECURITY_AUDITOR_READ_PINS = frozenset(
    {
        "read_file",
        "search",
        "glob",
        "list_dir",
        "retrieve_context",
        "git_read",
        "findings",
        "resolve",
        "start",
        "status",
    }
)


def _partition_tool_specs_by_name(
    tools: list[Any], pin_names: frozenset[str]
) -> tuple[list[Any], list[Any]]:
    pinned: list[Any] = []
    rest: list[Any] = []
    for spec in tools:
        n = _tool_spec_name(spec)
        if n is not None and n in pin_names:
            pinned.append(spec)
        else:
            rest.append(spec)
    return pinned, rest


def _credential_tools_for_agent(agent_id: str | None) -> frozenset[str]:
    if not agent_id or not str(agent_id).strip():
        return frozenset()
    ag = get_agent_registry().get_agent(str(agent_id).strip())
    if not ag:
        return frozenset()
    allowed = frozenset(ag.get("tool_names") or [])
    return _AGENT_CREDENTIAL_TOOL_NAMES & allowed


def _git_network_tools_for_agent(agent_id: str | None) -> frozenset[str]:
    if not agent_id or not str(agent_id).strip():
        return frozenset()
    ag = get_agent_registry().get_agent(str(agent_id).strip())
    if not ag:
        return frozenset()
    allowed = frozenset(ag.get("tool_names") or [])
    return _AGENT_GIT_NETWORK_TOOL_NAMES & allowed


def _pinned_tools_for_agent(agent_id: str | None) -> frozenset[str]:
    """Deprecated — tool forward uses ranking only (no pins)."""
    _ = agent_id
    return frozenset()


def _rank_tools_by_user_input(
    tools: list[dict[str, Any]], 
    user_input: str,
    tool_triggers: dict[str, tuple[str, ...]],
) -> list[dict[str, Any]]:
    """
    Rank tools by semantic similarity to user input + trigger boost + context boost.
    Returns sorted tools (highest score first).
    """
    from apps.backend.api.rag import embed_one
    
    if not config.AGENT_TOOLS_RANKING_ENABLED:
        return tools
    
    if not user_input or not tools:
        return tools
    
    min_threshold = config.AGENT_TOOLS_MIN_SCORE_THRESHOLD
    fallback_all = config.AGENT_TOOLS_RANKING_FALLBACK_ALL
    
    try:
        # 1. Get user input embedding
        user_emb = embed_one(user_input)
    except Exception as e:
        logger.warning(f"Tool ranking: failed to get user embedding: {e}")
        return tools
    
    # 2. Ensure tool embeddings are cached (lazy load)
    global _tool_embedding_loaded
    tools_to_embed = []
    
    for tool in tools:
        tool_id = tool.get("function", {}).get("name", "")
        if tool_id and tool_id not in _tool_embedding_cache:
            desc = _get_tool_description(tool)
            if desc:
                tools_to_embed.append((tool_id, desc))
    
    # Lazy load missing embeddings
    user_emb_dim = len(user_emb) if user_emb else 768
    if tools_to_embed:
        for tool_id, desc in tools_to_embed:
            try:
                emb = embed_one(desc[:2000])  # Truncate long descriptions
                _tool_embedding_cache[tool_id] = emb
            except Exception as e:
                logger.debug(f"Tool ranking: failed to embed tool {tool_id}: {e}")
                _tool_embedding_cache[tool_id] = [0.0] * user_emb_dim  # Fallback
    
    _tool_embedding_loaded = True
    
    # 3. Calculate scores for ALL tools
    all_scores: list[tuple[int, float]] = []
    
    for idx, tool in enumerate(tools):
        tool_id = tool.get("function", {}).get("name", "")
        
        # Semantic similarity score
        tool_emb = _tool_embedding_cache.get(tool_id)
        semantic_score = 0.0
        if tool_emb is not None:
            semantic_score = _cosine_similarity(user_emb, tool_emb)
        
        # Normalize by semantic weight
        semantic_score = semantic_score * config.AGENT_TOOLS_SEMANTIC_WEIGHT
        
        # Trigger boost
        trigger_score = 0.0
        triggers = tool_triggers.get(tool_id, ())
        if triggers:
            user_input_lower = user_input.lower()
            for trigger in triggers:
                if trigger.lower() in user_input_lower:
                    trigger_score = config.AGENT_TOOLS_TRIGGER_BOOST
                    break
        
        # Context boost (workspace check - optional, vorerst deaktiviert)
        context_score = 0.0
        
        # Final score
        final_score = semantic_score + trigger_score + context_score
        all_scores.append((idx, final_score))
        
        # Debug logging (top 5)
        if idx < 5:
            logger.debug(
                f"Tool ranking: {tool_id}: semantic={semantic_score:.3f}, "
                f"trigger={trigger_score:.3f}, context={context_score:.3f}, final={final_score:.3f}"
            )
    
    # 4. Sort by score (highest first)
    all_scores.sort(key=lambda x: x[1], reverse=True)
    
    # 5. Check if scores are too low (fallback to unsorted pool)
    if all_scores:
        max_score = all_scores[0][1]
        if max_score < min_threshold and fallback_all:
            logfn = logger.debug if config.AGENT_LOG_TOOL_PIPELINE else logger.info
            logfn(
                "Tool ranking: max score %.3f below threshold %s, falling back to all tools",
                max_score,
                min_threshold,
            )
            return tools

    # 6. Return full allowlist sorted by relevance (forward count = context token budget)
    ranked_tools = [tools[i] for i, _ in all_scores]
    
    logfn = logger.debug if config.AGENT_LOG_TOOL_PIPELINE else logger.info
    logfn(
        "Tool ranking: sorted %d tools by relevance (max_score=%.3f)",
        len(ranked_tools),
        all_scores[0][1] if all_scores else 0.0,
    )
    
    return ranked_tools


# =============================================================================
# Extra system text from ``dashboard.data._agentlayer`` (see dashboard settings UI).
_MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS = 8000


def _dashboard_data_agent_instructions(data: Any) -> str:
    """Return trimmed instructions from ``data._agentlayer`` (optional)."""
    if not isinstance(data, dict):
        return ""
    meta = data.get("_agentlayer")
    if not isinstance(meta, dict):
        return ""
    raw = meta.get("system_prompt_extra")
    if raw is None:
        raw = meta.get("instructions")
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if not s:
        return ""
    if len(s) > _MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS:
        logger.warning(
            "dashboard agent instructions truncated from %d to %d chars",
            len(s),
            _MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS,
        )
        return s[:_MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS]
    return s


# Non-empty allowlist: only these tool function names (after policy / disabled filters).
_MAX_DASHBOARD_TOOL_ALLOWLIST_LEN = 200


def _dashboard_data_tool_allowlist(data: Any) -> frozenset[str] | None:
    """Return allowed tool names from ``data._agentlayer.tool_allowlist`` or None if unset/empty."""
    if not isinstance(data, dict):
        return None
    meta = data.get("_agentlayer")
    if not isinstance(meta, dict):
        return None
    raw = meta.get("tool_allowlist")
    if raw is None:
        raw = meta.get("allowed_tools")
    if raw is None:
        return None
    if isinstance(raw, str):
        parts = [x.strip() for x in raw.replace(",", " ").split() if x.strip()]
        if not parts:
            return None
        names = parts
    elif isinstance(raw, list):
        names = [str(x).strip() for x in raw if isinstance(x, str) and str(x).strip()]
        if not names:
            return None
    else:
        return None
    if len(names) > _MAX_DASHBOARD_TOOL_ALLOWLIST_LEN:
        logger.warning(
            "dashboard tool_allowlist truncated from %d to %d entries",
            len(names),
            _MAX_DASHBOARD_TOOL_ALLOWLIST_LEN,
        )
        names = names[:_MAX_DASHBOARD_TOOL_ALLOWLIST_LEN]
    return frozenset(names)


def _dashboard_tool_allowlist_from_request_context(dashboard_ctx: Any) -> frozenset[str] | None:
    if not isinstance(dashboard_ctx, dict):
        return None
    wid_s = dashboard_ctx.get("dashboard_id")
    if not isinstance(wid_s, str) or not wid_s.strip():
        return None
    try:
        wid = uuid.UUID(wid_s.strip())
    except ValueError:
        return None
    ident = get_identity()
    if ident[1] is None:
        return None
    tid, uid = ident
    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return None
    return _dashboard_data_tool_allowlist(ws.get("data"))


async def _thread_with_cancel(
    cancel_event: asyncio.Event | None,
    func: Callable[..., Any],
    /,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run blocking work in a thread; abort promptly when ``cancel_event`` is set.

    Still waits for the worker to finish when cancelled so per-provider LLM slots
    is released before returning.
    """
    if cancel_event is None:
        return await asyncio.to_thread(func, *args, **kwargs)
    worker = asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))
    watcher = asyncio.create_task(cancel_event.wait())
    try:
        done, _pending = await asyncio.wait(
            {worker, watcher}, return_when=asyncio.FIRST_COMPLETED
        )
        if watcher in done and cancel_event.is_set():
            try:
                await worker
            except Exception:
                pass
            raise AgentChatCancelled()
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass
        return await worker
    finally:
        if not worker.done():
            pass


def _registry_tool_spec_by_registered_name(name: str) -> dict[str, Any] | None:
    n = (name or "").strip()
    if not n:
        return None
    for spec in get_registry().chat_tool_specs:
        if not isinstance(spec, dict):
            continue
        fn = spec.get("function")
        if isinstance(fn, dict) and fn.get("name") == n:
            return copy.deepcopy(spec)
    return None


def _http_error_recovery_hint(tool_name: str, result: str) -> str | None:
    if not config.AGENT_TOOL_HTTP_ERROR_RECOVERY_HINTS:
        return None
    if len(result) > 8000:
        return None
    rl = result.lower()
    markers = (
        "http error",
        "bad request",
        "401 unauthorized",
        "403 forbidden",
        "404 not found",
        " 400 ",
        "'400'",
        '"400"',
        "status 400",
        "status 401",
        "status 403",
        "status 404",
        "httpx",
        "for url 'http",
        'for url "http',
    )
    if not any(m in rl for m in markers):
        return None
    fix_strategy = (
        "For a **one-line API fix** (wrong query param, URL), **`update`** is usually enough; "
        "use **`replace`** if you need a larger rewrite. "
    )
    return (
        "The previous tool output suggests an HTTP/API failure. "
        "Do not blame the API key first: **400 Bad Request** often means **wrong query parameters** "
        "(e.g. OpenWeather `/data/2.5/weather` expects **`q`** for the place name, not `city`). "
        "**401** more often means an invalid or missing key. "
        + fix_strategy
        + "Next steps: (1) **`read`** the `.py` for this tool (use `registered_tool_name` "
        f"{tool_name!r} or `filename`). (2) Optionally **`search`** for the vendor's current API docs. "
        "(3) Apply the fix with **`replace`** and/or **`update`**; use **`https://`**. "
        "(4) Or delegate to built-ins: **`invoke_registered_tool`**(`\"openweather_current\"`, "
        "`{\"location\": \"…\"}`) / `forecast` from Python in an extra tool."
    )


def _tool_parameter_recovery_hint(tool_name: str, result: str) -> str | None:
    """Short system nudge when models emit tool_calls without required JSON fields (common on some GGUF builds)."""
    if not result or len(result) > 800:
        return None
    rl = result.lower()
    if tool_name == "bash" and "command" in rl:
        return (
            "The last `bash` call was missing or empty **command**. "
            "You must pass a JSON object with a non-empty string **command** (one shell line). "
            'Example: {"command": "git status"} or {"command": "ls -la", "workdir": ""}.'
        )
    if tool_name in (
        "read_file",
        "write_file",
        "replace",
        "edit",
        "apply_patch",
    ) and "path" in rl:
        return (
            f"The last `{tool_name}` call was missing or empty **path**. "
            'Pass {"path": "relative/path/from/workspace/root"} plus other required fields per the schema.'
        )
    if tool_name == "task" and "description" in rl and "required" in rl:
        return (
            "The last `task` call was missing **description** and/or **prompt**. "
            r'Example: {"description": "Review README", "prompt": "Summarize README.md and propose edits."}'
        )
    return None


def _infer_read_file_path_from_context(
    assistant_msg: dict[str, Any],
    messages: list[dict[str, Any]],
    workspace_root: Path | None,
) -> str | None:
    """When models call coding_read_file with {{}}, map README / backtick paths to a real relative path."""
    combined = last_user_text(messages) + "\n" + "\n".join(_text_blobs_from_message(assistant_msg))
    cl = combined.lower()
    if workspace_root and workspace_root.is_dir():
        for m in re.finditer(r"`([^`\n]{1,240}?\.(?:md|rst|txt|yaml|yml|toml|json))`", combined, re.I):
            cand = m.group(1).strip().lstrip("./")
            if not cand or ".." in cand or cand.startswith("/"):
                continue
            try:
                if (workspace_root / cand).is_file():
                    return cand
            except OSError:
                continue
        if "readme" in cl or "read me" in cl:
            for candidate in (
                "README.md",
                "readme.md",
                "Readme.md",
                "README.rst",
                "README.txt",
                "readme.txt",
                "docs/README.md",
                "doc/README.md",
            ):
                try:
                    if (workspace_root / candidate).is_file():
                        return candidate
                except OSError:
                    continue
            return "README.md"
    return None


def _infer_shell_command_from_assistant_message(assistant_msg: dict[str, Any]) -> str | None:
    """When wire-format tool_calls have `{}` arguments, some GGUF models still describe the shell line in prose."""
    blobs = _text_blobs_from_message(assistant_msg)
    text = "\n".join(blobs)
    if not text.strip():
        return None
    fence = re.search(r"```(?:bash|sh|shell|zsh)?\s*\n([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        for line in fence.group(1).splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                return s
    shell_prefixes = (
        "git ",
        "gh ",
        "npm ",
        "pnpm ",
        "yarn ",
        "bun ",
        "npx ",
        "cd ",
        "ls ",
        "pwd",
        "cat ",
        "head ",
        "tail ",
        "python ",
        "python3 ",
        "uv ",
        "ruff ",
        "pytest",
        "mypy ",
        "echo ",
        "mkdir ",
        "touch ",
        "cp ",
        "mv ",
        "rm ",
        "find ",
        "grep ",
        "sed ",
        "awk ",
        "curl ",
        "wget ",
        "docker ",
        "kubectl ",
        "make ",
        "cargo ",
        "go ",
    )
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("```"):
            continue
        if s.startswith(("- ", "* ", "• ")):
            s = s[2:].strip()
        sl = s.lower()
        if sl in ("ls", "pwd"):
            return s
        if any(sl.startswith(p) for p in shell_prefixes):
            return s
    for m in re.finditer(r"`([^`]{3,500})`", text):
        inner = m.group(1).strip()
        sl = inner.lower()
        if sl.startswith("git ") or sl.startswith(("npm ", "pnpm ", "yarn ", "python ", "docker ")):
            return inner
    m = re.search(r"\b(git\s+clone\b[^\n`'\"]{0,500})", text, re.IGNORECASE)
    if m:
        s = m.group(1).strip().rstrip(",.;:\"'")
        if len(s) > 8:
            return s
    return None


def _infer_shell_command_from_user_text(user_text: str) -> str | None:
    """Infer a shell one-liner from the latest user message when models emit empty ``bash`` JSON (GGUF)."""
    if not (user_text or "").strip():
        return None
    ut = user_text.strip()
    ul = ut.lower()
    fence = re.search(r"```(?:bash|sh|shell|zsh)?\s*\n([\s\S]*?)```", ut, re.IGNORECASE)
    if fence:
        for line in fence.group(1).splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            sl = s.lower()
            if sl.startswith(("git ", "gh ", "npm ", "pnpm ", "yarn ", "docker ", "curl ", "wget ")):
                return s
    if re.search(r"\bgit\s+pull\b", ul):
        if "ff-only" in ul or "ff only" in ul:
            return "git pull --ff-only"
        m2 = re.search(r"(git\s+pull[^\n`,;]{0,80})", ut, re.IGNORECASE)
        return (m2.group(1).strip().rstrip(",.;") if m2 else "git pull")
    if re.search(r"\bgit\s+fetch\b", ul):
        m2 = re.search(r"(git\s+fetch[^\n`]{0,200})", ut, re.IGNORECASE)
        return (m2.group(1).strip().rstrip(",.;") if m2 else "git fetch")
    if re.search(r"\bgit\s+status\b", ul):
        return "git status"
    if re.search(r"\bgit\s+log\b", ul):
        m2 = re.search(r"(git\s+log[^\n`]{0,160})", ut, re.IGNORECASE)
        return m2.group(1).strip() if m2 else "git log -n 10 --oneline"
    update_cues = (
        "git pull",
        "up to date",
        "up-to-date",
        "nicht up to date",
        "geupdatet",
        "updaten",
        " aktualisi",
        "pullen",
        "pull machen",
        "remote holen",
        "neueste version",
        "auf den stand",
        "ein pull",
        "was pull",
    )
    ctx_cues = (
        "git",
        "repo",
        "repository",
        "workspace",
        "projekt",
        "project",
        "branch",
        "remote",
        "klonen",
        "clone",
    )
    if any(c in ul for c in update_cues) and any(c in ul for c in ctx_cues):
        return "git pull"
    if re.search(r"\bpull\b", ul) and "git" in ul:
        if "ff-only" in ul or "ff only" in ul:
            return "git pull --ff-only"
        m2 = re.search(r"(git\s+pull[^\n`,;]{0,80})", ut, re.IGNORECASE)
        return (m2.group(1).strip().rstrip(",.;") if m2 else "git pull")
    return None


def _normalize_tool_call_arguments(
    name: str,
    args: dict[str, Any],
    assistant_msg: dict[str, Any],
    messages: list[dict[str, Any]],
    tool_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Repair empty / aliased tool JSON from sloppy OpenAI-compatible tool_calls (common with Qwen GGUF)."""
    out = dict(args)
    n = (name or "").strip()
    ws = (tool_context or {}).get("workspace") if tool_context else None
    root_p: Path | None = None
    if isinstance(ws, dict):
        rp = ws.get("path")
        if isinstance(rp, str) and rp.strip():
            root_p = Path(rp)
    if n == "bash":
        if not str(out.get("command") or "").strip():
            for alt in ("shell", "cmd", "bash", "bash_command", "script", "line", "input"):
                v = out.get(alt)
                if isinstance(v, str) and v.strip():
                    out["command"] = v.strip()
                    break
        unattended = bool(tool_context and tool_context.get("agent_unattended"))
        if not unattended:
            if not str(out.get("command") or "").strip():
                inferred = _infer_shell_command_from_assistant_message(assistant_msg)
                if inferred:
                    out["command"] = inferred
            if not str(out.get("command") or "").strip():
                inferred_u = _infer_shell_command_from_user_text(last_user_text(messages))
                if inferred_u:
                    out["command"] = inferred_u
    elif n == "task":
        if not str(out.get("description") or "").strip():
            for alt in ("title", "name", "task", "summary", "label"):
                v = out.get(alt)
                if isinstance(v, str) and v.strip():
                    out["description"] = v.strip()[:200]
                    break
        if not str(out.get("prompt") or "").strip():
            for alt in ("instructions", "instruction", "body", "content", "task_prompt", "query"):
                v = out.get(alt)
                if isinstance(v, str) and v.strip():
                    out["prompt"] = v.strip()
                    break
        if not str(out.get("description") or "").strip() or not str(out.get("prompt") or "").strip():
            ut = last_user_text(messages)
            if ut.strip():
                if not str(out.get("description") or "").strip():
                    u = ut.strip()
                    out["description"] = u if len(u) <= 120 else u[:117] + "..."
                if not str(out.get("prompt") or "").strip():
                    out["prompt"] = ut.strip()
    elif n in ("retrieve_context", "search", "semantic_search"):
        if not str(out.get("query") or "").strip():
            for alt in ("q", "search", "text", "prompt", "question", "keywords"):
                v = out.get(alt)
                if isinstance(v, str) and v.strip():
                    out["query"] = v.strip()
                    break
        if not str(out.get("query") or "").strip():
            ut = (last_user_text(messages) or "").strip()
            if ut:
                out["query"] = ut[:4000]
    elif n == "glob":
        if not str(out.get("pattern") or "").strip():
            for alt in ("glob", "file_pattern", "glob_pattern", "match"):
                v = out.get(alt)
                if isinstance(v, str) and v.strip():
                    out["pattern"] = v.strip()
                    break
        if not str(out.get("pattern") or "").strip():
            path_given = out.get("path")
            if isinstance(path_given, str) and path_given.strip() and "*" in path_given:
                out["pattern"] = path_given.strip()
        if not str(out.get("pattern") or "").strip():
            ut = (last_user_text(messages) or "").lower()
            if ".py" in ut or "python" in ut:
                out["pattern"] = "**/*.py"
            elif ".ts" in ut or "typescript" in ut:
                out["pattern"] = "**/*.{ts,tsx}"
            elif ".md" in ut or "markdown" in ut:
                out["pattern"] = "**/*.md"
            else:
                out["pattern"] = "**/*"
        if not str(out.get("path") or "").strip():
            out["path"] = "."
    elif n == "list_dir":
        if not str(out.get("path") or "").strip():
            out["path"] = "."
    elif n == "read_file":
        if not str(out.get("path") or "").strip():
            for alt in ("file", "filepath", "filename", "target", "rel_path", "relative_path"):
                v = out.get(alt)
                if isinstance(v, str) and v.strip():
                    out["path"] = v.strip()
                    break
        if not str(out.get("path") or "").strip():
            inferred = _infer_read_file_path_from_context(assistant_msg, messages, root_p)
            if inferred:
                out["path"] = inferred
    elif n in ("write_file", "replace", "edit"):
        if not str(out.get("path") or "").strip():
            for alt in ("file", "filepath", "filename", "target", "rel_path", "relative_path"):
                v = out.get(alt)
                if isinstance(v, str) and v.strip():
                    out["path"] = v.strip()
                    break
    elif n == "settings_patch":
        # Alias unwrap only (malformed nesting) — no semantic inference; see settings_patch error payload.
        if not out:
            for alt in ("settings", "patch", "body", "changes", "values"):
                nested = args.get(alt)
                if isinstance(nested, dict) and nested:
                    out = dict(nested)
                    break
    return out


def _agent_tool_budget_system_message(max_rounds: int) -> str:
    """Injected once per agent tool-loop request so models know the exact server cap."""
    n = max(1, int(max_rounds))
    if n <= 1:
        return (
            "## Tool-loop budget (server)\n\n"
            "This reply allows **only one** tool-loop LLM round (one completion; optional tool_calls). "
            "Use tools only if needed, then answer — the user can continue in a **new message** if more rounds are required."
        )
    return (
        "## Tool-loop budget (server)\n\n"
        f"- The server allows **at most {n}** tool-loop LLM rounds for this assistant reply (counting this completion).\n"
        f"- **Round {n}** is **text-only**: the API omits `tools[]` — respond with **natural language only** "
        "(no `tool_calls`). Either **summarize** prior tool outputs from the transcript **or** say clearly that "
        "more exploration is needed and ask the user to send a **follow-up message** (new tool budget).\n"
        f"- **Round {n - 1}** is the last round that receives tool definitions; plan tool use before then.\n"
        "- Avoid empty `{}` tool JSON (often normalizes to identical calls and can trigger loop guards).\n\n"
        "If work is unfinished, say so explicitly — the user may send a follow-up message."
    )


def _agent_near_max_tool_rounds_reminder(current_round: int, max_rounds: int) -> str:
    """Shown the round before the final text-only round (requires max_rounds >= 3)."""
    return (
        f"You are in **LLM tool-loop round {current_round} of {max_rounds}**. "
        f"The **next** round ({current_round + 1}) is the **last**; it will be **text-only** (no tools in the API). "
        "Finish critical tool calls **this** round if you still need them, or prepare a complete plain-text "
        "wrap-up on the next turn."
    )


def _agent_final_round_text_only_hint(current_round: int, max_rounds: int) -> str:
    """Shown immediately before the final LLM call (no tools[])."""
    return (
        f"**Round {current_round} of {max_rounds}** — final tool-loop round: **no** `tools[]` will be sent. "
        "Reply with **plain Markdown only** — the API **never** runs tools from prose. "
        "**Never** write `<tool_call>`, `</tool_call>`, `<function=…>`, or similar XML.\n\n"
        "**You must do exactly one of:**\n"
        "(A) **Synthesize** everything useful from **existing** `tool` messages above (findings, errors, paths, "
        "open questions, next steps for the user); **or**\n"
        "(B) If the transcript is **not** enough to answer, say that plainly and tell the user to send **one new "
        "message** to continue (a new request gets a fresh tool budget — you cannot call more tools in this reply).\n\n"
        "Do not stall with vague intent to explore — either recap what you already have, or ask for a follow-up."
    )


def _assistant_plain_text_from_message(msg: dict[str, Any]) -> str:
    return "\n".join(_text_blobs_from_message(msg)).strip()


_TOOL_RECAP_HEADER = "## Tool transcript (server-extracted)"
_ROUNDS_DIGEST_HEADER = "## LLM tool rounds (server-extracted)"


def _tool_call_id_to_name_map(messages: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in messages:
        if m.get("role") != "assistant":
            continue
        tcs = m.get("tool_calls")
        if not isinstance(tcs, list):
            continue
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            tid = str(tc.get("id") or "").strip()
            fn = tc.get("function") or {}
            nm = str(fn.get("name") or "").strip() if isinstance(fn, dict) else ""
            if tid and nm:
                out[tid] = nm
    return out


def _tool_call_id_to_args_recap_line(messages: list[dict[str, Any]], *, max_len: int = 400) -> dict[str, str]:
    """Short, human-readable args from prior assistant ``tool_calls`` (by ``tool_call_id``).

    Uses the same :func:`_normalize_tool_call_arguments` as execution so defaults (e.g.
    ``list_dir`` → ``path=.``) show up, and empty ``glob`` shows
    ``pattern=<missing>``.
    """
    out: dict[str, str] = {}
    for m in messages:
        if m.get("role") != "assistant":
            continue
        tcs = m.get("tool_calls")
        if not isinstance(tcs, list):
            continue
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            tid = str(tc.get("id") or "").strip()
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            if not isinstance(fn, dict) or not tid:
                continue
            name = str(fn.get("name") or "").strip()
            raw = fn.get("arguments")
            if raw in (None, "", "{}") or (isinstance(raw, dict) and not raw):
                if isinstance(tc.get("arguments"), (str, dict)) and tc.get("arguments") not in (None, ""):
                    raw = tc.get("arguments")
            args0 = _parse_tool_arguments(raw)
            norm = _normalize_tool_call_arguments(name, dict(args0), m, messages, None)
            out[tid] = _format_normalized_tool_args_for_recap(name, norm, max_len=max_len)
    return out


def _summarize_tool_json_body(raw: str, *, max_body: int) -> str:
    s = (raw or "").strip()
    if not s:
        return "(empty)"
    if not s.startswith("{"):
        return s[:max_body] + ("…" if len(s) > max_body else "")

    try:
        o = json.loads(s)
    except json.JSONDecodeError:
        return s[:max_body] + ("…" if len(s) > max_body else "")
    if not isinstance(o, dict):
        return s[:max_body] + ("…" if len(s) > max_body else "")

    meta: list[str] = []
    if "ok" in o:
        meta.append(f"ok={bool(o.get('ok'))}")
    for key in ("path", "pattern", "query", "path_prefix", "operation", "search_engine"):
        val = o.get(key)
        if isinstance(val, str) and val.strip():
            u = val.strip().replace("\n", " ")
            if len(u) > 220:
                u = u[:220] + "…"
            meta.append(f"{key}={u}")
    if "regex" in o and isinstance(o.get("regex"), bool):
        meta.append(f"regex={bool(o.get('regex'))}")
    ec = o.get("exit_code")
    if isinstance(ec, int) or (isinstance(ec, str) and str(ec).strip().isdigit()):
        meta.append(f"exit_code={ec}")
    if isinstance(o.get("count"), int):
        meta.append(f"count={o['count']}")
    if isinstance(o.get("files_scanned"), int):
        meta.append(f"files_scanned={o['files_scanned']}")
    if isinstance(o.get("line_count_total"), int):
        meta.append(f"line_count_total={o['line_count_total']}")
    if o.get("truncated") is True or o.get("truncated_lines") is True:
        meta.append("truncated=true")
    if o.get("truncated_matches") is True:
        meta.append("truncated_matches=true")
    if o.get("truncated_scan") is True:
        meta.append("truncated_scan=true")
    err = o.get("error")
    if isinstance(err, str) and err.strip():
        meta.append("error=" + err.strip()[:480])
    th = o.get("truncation_hint")
    if isinstance(th, str) and th.strip():
        u = th.strip().replace("\n", " ")
        meta.append("hint=" + (u[:300] + "…" if len(u) > 300 else u))
    if o.get("deduplicated") is True:
        meta.append("deduplicated=true")
    srv_note = o.get("message")
    u = (srv_note if isinstance(srv_note, str) else "").strip()
    dedup = o.get("deduplicated") is True
    if dedup:
        # Avoid repeating the same long boilerplate for every skipped parallel/loop call.
        if u.startswith("Identical tool+arguments"):
            previews_note = (
                "server_note: _(skipped — identical tool+args; use the earlier matching result "
                "in this transcript)_"
            )
        elif u:
            previews_note = "server_note:\n" + (u if len(u) <= 400 else u[:400] + "…")
        else:
            previews_note = "server_note: _(skipped — identical tool+args)_"
    elif u:
        previews_note = "server_note:\n" + (u if len(u) <= 900 else u[:900] + "…")
    else:
        previews_note = ""

    previews: list[str] = []
    if previews_note:
        previews.append(previews_note)

    files = o.get("files")
    if isinstance(files, list) and files:
        names = [str(x).replace("\n", " ") for x in files[:45] if x is not None]
        if names:
            tail = len(files) - len(names)
            head = ", ".join(names)
            if tail > 0:
                head += f" …(+{tail} more in payload)"
            previews.append(f"files ({len(files)}): {head}")

    entries = o.get("entries")
    if isinstance(entries, list) and entries:
        bits: list[str] = []
        for ent in entries[:35]:
            if not isinstance(ent, dict):
                continue
            p = str(ent.get("path") or ent.get("name") or "").strip()
            if not p:
                continue
            suf = "/" if ent.get("is_dir") else ""
            bits.append(p + suf)
        if bits:
            tail = len(entries) - len(bits)
            line = ", ".join(bits)
            if tail > 0:
                line += f" …(+{tail} more entries)"
            previews.append(f"listing: {line}")

    matches = o.get("matches")
    if isinstance(matches, list) and matches:
        mlines: list[str] = []
        for m in matches[:14]:
            if not isinstance(m, dict):
                continue
            pth = str(m.get("path") or "").strip()
            ln = m.get("line")
            tx = m.get("text")
            ts = tx.strip()[:180] + ("…" if isinstance(tx, str) and len(tx.strip()) > 180 else "") if isinstance(tx, str) else ""
            if pth and isinstance(ln, int):
                mlines.append(f"  {pth}:{ln}: {ts}".rstrip())
            elif pth:
                mlines.append(f"  {pth}: {ts}".rstrip())
        if mlines:
            tail = len(matches) - len(mlines)
            block = "matches:\n" + "\n".join(mlines)
            if tail > 0:
                block += f"\n  …(+{tail} more matches)"
            previews.append(block)

    out_text = o.get("output")
    if isinstance(out_text, str) and out_text.strip():
        u = out_text.strip()
        previews.append("output:\n" + (u if len(u) <= max_body - 80 else u[: max_body - 80] + "…"))

    content = o.get("content")
    if isinstance(content, str) and content.strip() and "path" in o:
        u = content.strip()
        cap = min(1600, max(200, max_body - 120))
        previews.append(
            "file_content:\n"
            + (u if len(u) <= cap else u[:cap] + "…")
        )

    body = " | ".join(meta) if meta else ""
    for p in previews:
        if not p.strip():
            continue
        sep = "\n" if body else ""
        if len(body) + len(sep) + len(p) > max_body:
            room = max_body - len(body) - len(sep) - 1
            if room > 40:
                body += sep + p[:room] + "…"
            else:
                body += "\n…[preview truncated]"
            break
        body += sep + p

    if not body.strip():
        return s[:max_body] + ("…" if len(s) > max_body else "")
    if len(body) > max_body:
        return body[:max_body] + "…"
    return body


def _build_tool_transcript_recap(
    messages: list[dict[str, Any]],
    *,
    max_entries: int = 32,
    max_body_chars: int = 2200,
) -> str:
    """Deterministic markdown from ``role: tool`` payloads (JSON-aware)."""
    id_to_name = _tool_call_id_to_name_map(messages)
    id_to_args = _tool_call_id_to_args_recap_line(messages, max_len=400)
    lines: list[str] = []
    n = 0
    for m in messages:
        if m.get("role") != "tool":
            continue
        n += 1
        if n > max_entries:
            lines.append(f"\n_…{n - max_entries} more tool message(s) omitted._\n")
            break
        tid = str(m.get("tool_call_id") or "").strip()
        name = id_to_name.get(tid, "tool")
        body = m.get("content")
        text = body if isinstance(body, str) else str(body)
        summ = _summarize_tool_json_body(text, max_body=max_body_chars)
        req = (id_to_args.get(tid) or "").strip()
        if req:
            req_safe = req.replace("`", "'")
            lines.append(f"### {n}. `{name}`\n**Tool args:** `{req_safe}`\n{summ}\n")
        else:
            lines.append(f"### {n}. `{name}`\n{summ}\n")
    if not lines:
        return f"{_TOOL_RECAP_HEADER}\n\n_No tool messages in this reply._\n"
    return f"{_TOOL_RECAP_HEADER}\n\n" + "\n".join(lines)


def _build_llm_tool_rounds_digest(
    messages: list[dict[str, Any]],
    *,
    max_rounds_shown: int = 32,
    max_calls_per_round: int = 24,
    max_args_len: int = 320,
) -> str:
    """Per-assistant-turn list of tool names + normalized args (what the model *requested*)."""
    blocks: list[str] = []
    r = 0
    for m in messages:
        if m.get("role") != "assistant":
            continue
        tcs = m.get("tool_calls")
        if not isinstance(tcs, list) or not tcs:
            continue
        r += 1
        if r > max_rounds_shown:
            blocks.append(f"_…{r - max_rounds_shown} more LLM tool round(s) omitted._")
            break
        lines: list[str] = [f"### Round {r}"]
        n_call = 0
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            n_call += 1
            if n_call > max_calls_per_round:
                rest = len(tcs) - max_calls_per_round
                lines.append(f"- _…{rest} more tool_call(s) in this round._")
                break
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            if not isinstance(fn, dict):
                continue
            name = str(fn.get("name") or "").strip() or "tool"
            raw = fn.get("arguments")
            if raw in (None, "", "{}") or (isinstance(raw, dict) and not raw):
                if isinstance(tc.get("arguments"), (str, dict)) and tc.get("arguments") not in (None, ""):
                    raw = tc.get("arguments")
            args0 = _parse_tool_arguments(raw)
            norm = _normalize_tool_call_arguments(name, dict(args0), m, messages, None)
            arg_line = _format_normalized_tool_args_for_recap(name, norm, max_len=max_args_len)
            lines.append(f"- `{name}`: {arg_line}")
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    return f"{_ROUNDS_DIGEST_HEADER}\n\n" + "\n\n".join(blocks)


def _build_client_tool_context_markdown(messages: list[dict[str, Any]]) -> str:
    """LLM tool rounds (requests) plus tool transcript (results) for the client-facing reply."""
    digest = _build_llm_tool_rounds_digest(messages).strip()
    recap = _build_tool_transcript_recap(messages).strip()
    if digest and recap:
        return digest + "\n\n" + recap
    return digest or recap


def _client_reply_is_only_server_tool_context_prefix(tail: str) -> bool:
    t = (tail or "").strip()
    if not t:
        return True
    return t.startswith(_TOOL_RECAP_HEADER) or t.startswith(_ROUNDS_DIGEST_HEADER)


def _merge_deterministic_tool_recap_into_final_completion(
    data: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    plain_completion: bool,
) -> bool:
    """Prefix assistant content with server recap when the tool loop ends (mutates ``data``)."""
    if plain_completion:
        return False
    try:
        recap = _build_client_tool_context_markdown(messages)
        if not recap.strip():
            return False
        cap = 18_000
        recap_use = recap if len(recap) <= cap else recap[:cap] + "\n\n…[truncated]"
        ch_list = data.get("choices")
        if not isinstance(ch_list, list) or not ch_list:
            return False
        ch0 = ch_list[0]
        if not isinstance(ch0, dict):
            return False
        msg0 = ch0.get("message")
        if not isinstance(msg0, dict):
            return False
        ex = msg0.get("content")
        if ex is None:
            msg0["content"] = ""
            ex = ""
        elif not isinstance(ex, str):
            return False
        tail = ex.strip()
        sep = "\n\n---\n\n### Model reply\n\n"
        if not tail or _client_reply_is_only_server_tool_context_prefix(tail):
            msg0["content"] = recap_use.strip()[:80_000]
        else:
            merged = (recap_use.rstrip() + sep + tail).strip()
            if len(merged) > 80_000:
                merged = merged[:80_000] + "…"
            msg0["content"] = merged
        msg0.pop("tool_calls", None)
        ch0["message"] = msg0
        ch_list[0] = ch0
        return True
    except (TypeError, KeyError, IndexError):
        return False


def _agent_final_text_looks_like_placeholder_tool_markup(text: str) -> bool:
    """GGUF models often emit fake XML tool blocks when tools[] is omitted."""
    if not (text or "").strip():
        return True
    tl = text.lower()
    if "<tool_call" in tl or "</tool_call>" in tl:
        return True
    if "<function=" in tl or "</function>" in tl:
        return True
    return False


def _strip_prose_fake_tool_markup(text: str) -> str:
    """Remove non-executable tool-like XML some models print when no tools[] are sent."""
    if not text:
        return text
    out = text
    out = re.sub(r"<tool_call\b[^>]*>[\s\S]*?</tool_call>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"</?tool_call\b[^>]*>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"<function\s*=[^>]*>\s*</function>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"<function[^>]*>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"</function>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def _sanitize_final_completion_assistant_content(data: dict[str, Any]) -> bool:
    """Strip fake tool XML from ``choices[0].message.content`` when present (mutates ``data``)."""
    try:
        ch_list = data.get("choices")
        if not isinstance(ch_list, list) or not ch_list:
            return False
        ch0 = ch_list[0]
        if not isinstance(ch0, dict):
            return False
        msg = ch0.get("message")
        if not isinstance(msg, dict):
            return False
        raw = msg.get("content")
        if not isinstance(raw, str) or not raw.strip():
            return False
        if not _agent_final_text_looks_like_placeholder_tool_markup(raw):
            return False
        stripped = _strip_prose_fake_tool_markup(raw)
        if stripped.strip():
            msg["content"] = stripped
        else:
            msg["content"] = (
                "_(The model returned tool-call markup instead of plain text — no readable answer was produced. "
                "Send a follow-up message to continue; tool results from earlier rounds are still in the transcript.)_"
            )
        msg.pop("tool_calls", None)
        ch0["message"] = msg
        ch_list[0] = ch0
        return True
    except (TypeError, KeyError, IndexError):
        return False


def _synthetic_final_llm_http_error_completion(*, status: int, model_id: str) -> dict[str, Any]:
    """Minimal OpenAI-shaped completion when the last LLM call fails (proxy 502, etc.)."""
    mid = model_id if isinstance(model_id, str) and model_id.strip() else "unknown"
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        f"_(The language model server returned **HTTP {status}** on the **final summary** round "
                        f"(model `{mid}`) — no generated answer was returned.)_\n\n"
                        "**What you can do:** wait a moment and **retry**; check **Agent activity** for outputs from "
                        "earlier tool rounds in this reply; send a **new message** asking to summarize those results "
                        "or to keep exploring (that starts a fresh tool budget)._"
                    ),
                },
                "finish_reason": "stop",
            }
        ],
        "model": mid,
    }


_AGENT_TOOL_THRASH_HINT = (
    "Tool loop guard: the same tool has failed **repeatedly** with the **same error message**. "
    "On the next assistant message you must either fix the JSON arguments (non-empty fields per schema) "
    "or answer the user in **plain text** explaining what is wrong — do not repeat identical failing tool calls."
)


_AGENT_TOOL_THRASH_FORCE_TEXT = (
    "Repeated identical tool failures were detected. **Tools are disabled for this round** — respond with a "
    "normal assistant message only: summarize the error, quote it briefly, and state the exact JSON fields "
    "required for the next successful call (e.g. coding_bash → `{\"command\": \"…\"}`)."
)

_AGENT_TOOL_DOOM_LOOP_HINT = (
    "Loop guard: the **same tool** was called with the **same arguments** repeatedly. "
    "Stop repeating that call: change parameters, try a different approach, or answer the user in **plain text** "
    "with what you learned and what to do next. "
    "If this is **read-only Plan** mode, synthesize your **handoff plan** now (markdown): proposed edits, files for Build, "
    "checklist — do not call that tool again with the same args."
)

_AGENT_TOOL_DOOM_FORCE_TEXT = (
    "Repeated identical tool calls were detected. **Tools are disabled for this assistant turn** — reply with a "
    "normal message only: summarize what tool output you already have, then deliver a **complete plan** "
    "(markdown): proposed changes, files/paths for the Build agent, ordered steps. "
    "Ask at most one clarifying question if something essential is still unknown. "
    "Do **not** emit fake `<tool_call>` / `</tool_call>` or XML tool markup — the chat API does not parse that from text."
)


def _agent_tool_doom_loop_tick(
    doom_key: str | None,
    doom_count: int,
    *,
    tool_name: str,
    args: dict[str, Any],
    max_streak: int,
    exclude_names: frozenset[str],
) -> tuple[str | None, int, str | None]:
    """Detect repeated identical tool invocations (stuck doom-loop guard)."""
    if max_streak < 2:
        return doom_key, doom_count, None
    if tool_name in exclude_names:
        return doom_key, doom_count, None
    try:
        args_canon = json.dumps(dict(args), sort_keys=True, separators=(",", ":"), default=str)
    except TypeError:
        args_canon = str(args)
    if len(args_canon) > 1200:
        args_canon = args_canon[:1200] + "…"
    dk = f"{tool_name}|{args_canon}"
    if dk == doom_key:
        n = doom_count + 1
    else:
        dk, n = dk, 1
    if n >= max_streak:
        return None, 0, _AGENT_TOOL_DOOM_LOOP_HINT
    return dk, n, None


def _tool_result_summary(result: str | None) -> tuple[bool | None, str | None]:
    """Parse leading JSON object from a tool result string: (ok, error text) or (None, None) if unknown."""
    if not result or not str(result).strip():
        return None, None
    s = result.strip()
    if not s.startswith("{"):
        return None, None
    try:
        o = json.loads(s)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(o, dict):
        return None, None
    if "ok" not in o:
        return None, None
    if o.get("ok") is True:
        return True, None
    err = o.get("error")
    if isinstance(err, str) and err.strip():
        return False, err.strip()
    return False, None


def _tool_result_followup_hint(tool_name: str, result: str | None) -> str | None:
    """System hint when a tool result needs explicit operator follow-up (sub-agent issues, register-only tasks)."""
    if not result or not str(result).strip().startswith("{"):
        return None
    try:
        o = json.loads(result)
    except json.JSONDecodeError:
        return None
    if not isinstance(o, dict):
        return None
    if tool_name == "task" and o.get("mode") == "register_only":
        warn = o.get("warning") or o.get("detail")
        if isinstance(warn, str) and warn.strip():
            return (
                "coding_task did **not** run a sub-agent — it only registered a task id. "
                f"{warn.strip()} Use **agent_delegate** with run_subagent=true for real execution."
            )
    problems = o.get("problems")
    prob_lines: list[str] = []
    if isinstance(problems, list):
        prob_lines = [str(p).strip() for p in problems if isinstance(p, str) and str(p).strip()]
    if o.get("ok") is False:
        err = o.get("error")
        if isinstance(err, str) and err.strip():
            prob_lines.insert(0, err.strip())
        hint = o.get("hint")
        if isinstance(hint, str) and hint.strip():
            prob_lines.append(hint.strip())
        if prob_lines:
            who = tool_name or "tool"
            return f"{who} failed: " + " | ".join(prob_lines[:5])
    if prob_lines and tool_name in ("delegate", "task"):
        return f"{tool_name} completed with warnings: " + " | ".join(prob_lines[:5])
    return None


async def _emit_secret_prompt_from_tool_result(
    tool_name: str,
    result: str | None,
    *,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    agent_run_id: str,
) -> None:
    """After ``request_user_secret``, push ``agent.secret_prompt`` to the WebSocket client."""
    if tool_name != "request_user_secret" or event_emit is None:
        return
    if not result or not str(result).strip().startswith("{"):
        return
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict) or data.get("ok") is not True:
        return
    sp = data.get("secret_prompt")
    if not isinstance(sp, dict) or not sp.get("prompt_id"):
        return
    ev: dict[str, Any] = {
        "type": "agent.secret_prompt",
        "agent_run_id": agent_run_id,
        "prompt_id": str(sp["prompt_id"]),
        "service_key": str(sp.get("service_key") or ""),
        "mode": str(sp.get("mode") or "authenticated"),
        "title": sp.get("title"),
        "help": sp.get("help"),
        "fields": sp.get("fields") if isinstance(sp.get("fields"), list) else [],
        "reason": sp.get("reason"),
    }
    await event_emit(ev)


def _agent_tool_thrash_tick(
    thrash_key: str | None,
    thrash_count: int,
    *,
    tool_name: str,
    ok_r: bool | None,
    err_r: str | None,
    max_streak: int,
) -> tuple[str | None, int, str | None, bool]:
    """
    Advance thrash detector after one tool result.

    Returns ``(new_key, new_count, optional_system_hint, force_text_only_next_round)``.
    """
    if max_streak < 2:
        return thrash_key, thrash_count, None, False
    if ok_r is True:
        return None, 0, None, False
    if ok_r is None:
        return thrash_key, thrash_count, None, False
    err_norm = (err_r or "(no error text)")[:200]
    key = f"{tool_name}|{err_norm}"
    if key == thrash_key:
        n = thrash_count + 1
    else:
        n = 1
    if n >= max_streak:
        logger.warning(
            "agent tool thrash: streak=%d tool=%s — forcing text-only next round",
            n,
            tool_name,
        )
        return None, 0, None, True
    if n == max_streak - 1:
        return key, n, _AGENT_TOOL_THRASH_HINT, False
    return key, n, None, False


# Client-only keys: never forward to the upstream chat API.
_BODY_KEYS_STRIP_FROM_LLM = frozenset(
    {
        "tool_prefetch",
        "agent_router_categories",
        "TOOL_DOMAIN",
        "agent_pause_between_rounds",
        "agent_disabled_tools",
        "agent_plain_completion",
        "agent_capability_hints",
        "agent_capability_confirm",
        "agent_max_tool_rounds",
        "agent_llm_backend",
        "agent_tool_name_allowlist",
        "agent_id",
        "agent_parent_run_id",
        "agent_permission_ask",
        "agent_unattended",
        "agent_stream_llm",
    }
)


# **Ask** before destructive workspace tools (Plan + Build on WebSocket when ``agent_permission_ask``).
_CODING_TOOLS_PERMISSION_ASK = frozenset(
    {
        "bash",
        "git_sync",
        "write_file",
        "edit",
        "apply_patch",
        "replace",
    }
)

# Tool results passed to the LLM as-is — no extra system hints appended after these calls.
PLANNER_NO_EXTRA_HINTS_AFTER_TOOL = frozenset(
    {
        "settings_patch",
        "settings_get",
        "get_tool_help",
    }
)
__all__ = [
    '_AGENT_CREDENTIAL_TOOL_NAMES',
    '_AGENT_GIT_NETWORK_TOOL_NAMES',
    '_AGENT_TOOL_DOOM_FORCE_TEXT',
    '_AGENT_TOOL_DOOM_LOOP_HINT',
    '_AGENT_TOOL_THRASH_FORCE_TEXT',
    '_AGENT_TOOL_THRASH_HINT',
    '_BODY_KEYS_STRIP_FROM_LLM',
    '_CODING_READ_TOOL_PINS',
    '_CODING_TOOLS_PERMISSION_ASK',
    'PLANNER_NO_EXTRA_HINTS_AFTER_TOOL',
    '_MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS',
    '_MAX_DASHBOARD_TOOL_ALLOWLIST_LEN',
    '_ROUNDS_DIGEST_HEADER',
    '_SECURITY_AUDITOR_READ_PINS',
    '_TOOL_RECAP_HEADER',
    '_agent_final_round_text_only_hint',
    '_agent_final_text_looks_like_placeholder_tool_markup',
    '_agent_near_max_tool_rounds_reminder',
    '_agent_tool_budget_system_message',
    '_agent_tool_doom_loop_tick',
    '_agent_tool_thrash_tick',
    '_assistant_plain_text_from_message',
    '_build_client_tool_context_markdown',
    '_build_llm_tool_rounds_digest',
    '_build_tool_transcript_recap',
    '_client_reply_is_only_server_tool_context_prefix',
    '_cosine_similarity',
    '_credential_tools_for_agent',
    '_dashboard_data_agent_instructions',
    '_dashboard_data_tool_allowlist',
    '_dashboard_tool_allowlist_from_request_context',
    '_emit_secret_prompt_from_tool_result',
    '_get_tool_description',
    '_git_network_tools_for_agent',
    '_http_error_recovery_hint',
    '_infer_read_file_path_from_context',
    '_infer_shell_command_from_assistant_message',
    '_infer_shell_command_from_user_text',
    '_merge_deterministic_tool_recap_into_final_completion',
    '_normalize_tool_call_arguments',
    '_partition_tool_specs_by_name',
    '_pinned_tools_for_agent',
    '_rank_tools_by_user_input',
    '_registry_tool_spec_by_registered_name',
    '_sanitize_final_completion_assistant_content',
    '_strip_prose_fake_tool_markup',
    '_summarize_tool_json_body',
    '_synthetic_final_llm_http_error_completion',
    '_thread_with_cancel',
    '_tool_call_id_to_args_recap_line',
    '_tool_call_id_to_name_map',
    '_tool_embedding_loaded',
    '_tool_parameter_recovery_hint',
    '_tool_result_followup_hint',
    '_tool_result_summary',
]
