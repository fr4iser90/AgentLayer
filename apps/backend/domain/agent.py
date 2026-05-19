"""
Chat completion with tool-call loop (**Planner**): builds messages and asks the model which tools to call.

Deterministic tool execution goes through :func:`apps.domain.tool_executor.execute_tool` (**Executor**).
See ``docs/adr/0001-tool-and-agent-architecture.md``.
"""

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
from typing import Any, Literal

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
from apps.backend.domain.model_routing import ollama_model_for_profile, resolve_effective_model
from apps.backend.domain.user_persona import _append_system_block, apply_user_persona_system
from apps.backend.infrastructure.operator_settings import (
    external_llm_should_failover,
    llm_chat_transport,
    normalize_model_catalog_owned_by,
    smart_llm_routing_enabled,
)

logger = logging.getLogger(__name__)

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
    {"save_user_secret", "register_secrets", "secrets_help"}
)
# Always forwarded to the LLM when the agent allowlists them (ranking would drop them otherwise).
_AGENT_GIT_NETWORK_TOOL_NAMES = frozenset(
    {
        "coding_git_push",
        "coding_git_sync",
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
    """Tools always prepended to ranked tools[] (credentials + git push/sync)."""
    return _credential_tools_for_agent(agent_id) | _git_network_tools_for_agent(agent_id)


def _rank_tools_by_user_input(
    tools: list[dict[str, Any]], 
    user_input: str,
    tool_triggers: dict[str, tuple[str, ...]],
) -> list[dict[str, Any]]:
    """
    Rank tools by semantic similarity to user input + trigger boost + context boost.
    Returns sorted tools (highest score first).
    """
    from apps.backend.api.rag import ollama_embed_one
    
    if not config.AGENT_TOOLS_RANKING_ENABLED:
        return tools
    
    if not user_input or not tools:
        return tools
    
    max_tools = config.AGENT_TOOLS_MAX_RANKING
    min_threshold = config.AGENT_TOOLS_MIN_SCORE_THRESHOLD
    fallback_all = config.AGENT_TOOLS_RANKING_FALLBACK_ALL
    
    try:
        # 1. Get user input embedding
        user_emb = ollama_embed_one(user_input)
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
                emb = ollama_embed_one(desc[:2000])  # Truncate long descriptions
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
    
    # 5. Check if scores are too low (fallback)
    if all_scores:
        max_score = all_scores[0][1]
        if max_score < min_threshold:
            if fallback_all:
                logger.info(
                    f"Tool ranking: max score {max_score:.3f} below threshold {min_threshold}, "
                    f"falling back to all tools"
                )
                return tools
            else:
                # Still limit to max_tools even with low scores
                top_indices = [s[0] for s in all_scores[:max_tools]]
                return [tools[i] for i in top_indices]
    
    # 6. Return top N tools
    top_indices = [s[0] for s in all_scores[:max_tools]]
    ranked_tools = [tools[i] for i in top_indices]
    
    logger.info(
        f"Tool ranking: ranked {len(tools)} tools to top {len(ranked_tools)} "
        f"(max_score={all_scores[0][1]:.3f})"
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


class AgentChatCancelled(Exception):
    """Client aborted in-flight chat (e.g. WebSocket ``{"type":"cancel"}``)."""


async def _thread_with_cancel(
    cancel_event: asyncio.Event | None,
    func: Callable[..., Any],
    /,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run blocking work in a thread; abort promptly when ``cancel_event`` is set.

    Still waits for the worker to finish when cancelled so ``LLM_HTTP_SERIALIZE_LOCK``
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


class WorkspaceAccessDenied(Exception):
    """Raised when a named workspace cannot be bound for the current user (fail closed)."""


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
        "For a **one-line API fix** (wrong query param, URL), **`update_tool`** is usually enough; "
        "use **`replace_tool`** if you need a larger rewrite. "
    )
    return (
        "The previous tool output suggests an HTTP/API failure. "
        "Do not blame the API key first: **400 Bad Request** often means **wrong query parameters** "
        "(e.g. OpenWeather `/data/2.5/weather` expects **`q`** for the place name, not `city`). "
        "**401** more often means an invalid or missing key. "
        + fix_strategy
        + "Next steps: (1) **`read_tool`** the `.py` for this tool (use `registered_tool_name` "
        f"{tool_name!r} or `filename`). (2) Optionally **`search_web`** for the vendor's current API docs. "
        "(3) Apply the fix with **`replace_tool`** and/or **`update_tool`**; use **`https://`**. "
        "(4) Or delegate to built-ins: **`invoke_registered_tool`**(`\"openweather_current\"`, "
        "`{\"location\": \"…\"}`) / `openweather_forecast` from Python in an extra tool."
    )


def _tool_parameter_recovery_hint(tool_name: str, result: str) -> str | None:
    """Short system nudge when models emit tool_calls without required JSON fields (common on some GGUF builds)."""
    if not result or len(result) > 800:
        return None
    rl = result.lower()
    if tool_name == "coding_bash" and "command" in rl:
        return (
            "The last `coding_bash` call was missing or empty **command**. "
            "You must pass a JSON object with a non-empty string **command** (one shell line). "
            'Example: {"command": "git status"} or {"command": "ls -la", "workdir": ""}.'
        )
    if tool_name in (
        "coding_read_file",
        "coding_write_file",
        "coding_replace",
        "coding_edit",
        "coding_apply_patch",
    ) and "path" in rl:
        return (
            f"The last `{tool_name}` call was missing or empty **path**. "
            'Pass {"path": "relative/path/from/workspace/root"} plus other required fields per the schema.'
        )
    if tool_name == "coding_task" and "description" in rl and "required" in rl:
        return (
            "The last `coding_task` call was missing **description** and/or **prompt**. "
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
    """Infer a shell one-liner from the latest user message when models emit empty ``coding_bash`` JSON (GGUF)."""
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


def _is_git_pull_command(command: str) -> bool:
    c = (command or "").strip().lower()
    if not c:
        return False
    return c == "git pull" or c.startswith("git pull ")


def _looks_like_shell_command(command: str) -> bool:
    s = (command or "").strip()
    if not s or len(s) > 400:
        return False
    sl = s.lower()
    if " now i need" in sl or s.endswith(":"):
        return False
    if sl in ("ls", "pwd"):
        return True
    return any(
        sl.startswith(p)
        for p in (
            "git ",
            "gh ",
            "npm ",
            "pnpm ",
            "yarn ",
            "npx ",
            "cd ",
            "cat ",
            "mkdir ",
            "touch ",
            "cp ",
            "mv ",
            "find ",
            "grep ",
            "python",
            "ruff ",
            "pytest",
            "docker ",
            "make ",
        )
    )


def _unattended_blocked_tool_json(
    name: str,
    args: dict[str, Any],
    tool_context: dict[str, Any],
) -> str | None:
    if not tool_context.get("agent_unattended"):
        return None
    if tool_context.get("schedule_git_pull_done"):
        if name == "coding_git_sync" and str(args.get("operation") or "pull").strip().lower() == "pull":
            pr = tool_context.get("schedule_git_pull_result") or "completed"
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        f"Git pull already completed this run ({pr}). "
                        "Do NOT run pull again. Next: agent/doc-* branch, then "
                        "coding_write_file docs/MAINTENANCE_REPORT.md."
                    ),
                    "pull_result": pr,
                },
                ensure_ascii=False,
            )
        if name == "coding_bash":
            cmd = str(args.get("command") or "").strip()
            if _is_git_pull_command(cmd):
                pr = tool_context.get("schedule_git_pull_result") or "completed"
                return json.dumps(
                    {
                        "ok": False,
                        "error": (
                            f"Git pull already completed this run ({pr}). "
                            "Use coding_write_file for docs/MAINTENANCE_REPORT.md."
                        ),
                        "pull_result": pr,
                    },
                    ensure_ascii=False,
                )
    if name == "coding_bash":
        cmd = str(args.get("command") or "").strip()
        if not cmd:
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        'coding_bash requires {"command": "…"} — empty {} is not allowed '
                        "for scheduled runs. Example: {\"command\": \"git checkout -b agent/doc-20260517\"}."
                    ),
                },
                ensure_ascii=False,
            )
        if not _looks_like_shell_command(cmd):
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        f"Invalid shell command (not a one-liner): {cmd[:120]!r}. "
                        "Send a real command or use coding_git_sync for pull."
                    ),
                },
                ensure_ascii=False,
            )
    return None


def _unattended_mark_git_pull_done(
    name: str,
    result: str,
    tool_context: dict[str, Any],
) -> str | None:
    """If a pull succeeded, set context flags and return a system hint for the model."""
    if not tool_context.get("agent_unattended"):
        return None
    try:
        o = json.loads(result)
    except json.JSONDecodeError:
        return None
    if not isinstance(o, dict) or o.get("ok") is not True:
        return None
    pull_result: str | None = None
    if name == "coding_git_sync" and str(o.get("operation") or "").strip().lower() == "pull":
        pull_result = str(o.get("pull_result") or "completed")
    elif name == "coding_bash":
        cmd = str(o.get("command") or "")
        if _is_git_pull_command(cmd) and int(o.get("exit_code") or 0) == 0:
            pull_result = str(o.get("pull_result") or "completed")
    if not pull_result:
        return None
    tool_context["schedule_git_pull_done"] = True
    tool_context["schedule_git_pull_result"] = pull_result
    msg = str(o.get("message") or "").strip()
    steps = o.get("next_steps")
    step_txt = ""
    if isinstance(steps, list) and steps:
        step_txt = " Next: " + "; ".join(str(x) for x in steps[:3])
    return (
        f"[Schedule git] Pull complete (pull_result={pull_result}). "
        f"{msg} Do NOT call coding_git_sync pull or coding_bash git pull again.{step_txt}"
    )


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
    if n == "coding_bash":
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
    elif n == "coding_task":
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
    elif n in ("retrieve_context", "coding_search", "coding_semantic_search"):
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
    elif n == "coding_glob":
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
    elif n == "coding_list_dir":
        if not str(out.get("path") or "").strip():
            out["path"] = "."
    elif n == "coding_read_file":
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
    elif n in ("coding_write_file", "coding_replace", "coding_edit"):
        if not str(out.get("path") or "").strip():
            for alt in ("file", "filepath", "filename", "target", "rel_path", "relative_path"):
                v = out.get(alt)
                if isinstance(v, str) and v.strip():
                    out["path"] = v.strip()
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
    ``coding_list_dir`` → ``path=.``) show up, and empty ``coding_glob`` shows
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
        msg["content"] = stripped if stripped.strip() else ""
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


# Client-only keys: never forward to Ollama (not in upstream Chat Completions request schema).
_BODY_KEYS_STRIP_FROM_OLLAMA = frozenset(
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
        "coding_bash",
        "coding_git_sync",
        "coding_write_file",
        "coding_edit",
        "coding_apply_patch",
        "coding_replace",
    }
)


def _parse_disabled_tool_names(raw: Any) -> set[str]:
    """Client hint: tool function names to omit from this request (after policy filter)."""
    if not isinstance(raw, list):
        return set()
    return {str(x).strip() for x in raw if str(x).strip()}


def _coerce_body_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    s = str(value).strip().lower()
    if not s:
        return default
    return s in ("1", "true", "yes", "on")


def _permission_reply_user_message(m: dict[str, Any]) -> str | None:
    raw = m.get("message")
    if isinstance(raw, str):
        t = raw.strip()
        return t[:800] if t else None
    return None


async def _wait_for_tool_permission_reply(
    *,
    control_queue: asyncio.Queue,
    cancel_event: asyncio.Event | None,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    agent_run_id: str,
    request_id: str,
    tool_name: str,
    args_preview: str,
    round_i: int,
    handle_control: Callable[[dict[str, Any]], bool],
) -> tuple[str, str | None]:
    """Block until client sends ``permission_reply`` for ``request_id``.

    Returns ``(reply, optional_message)`` where ``reply`` is ``once``, ``always``, or ``reject``.
    """
    if event_emit:
        await event_emit(
            {
                "type": "agent.permission_ask",
                "agent_run_id": agent_run_id,
                "request_id": request_id,
                "tool_name": tool_name,
                "args_preview": args_preview,
                "round": round_i + 1,
            }
        )
    while True:
        m = await control_queue.get()
        if not isinstance(m, dict):
            continue
        if m.get("type") == "permission_reply":
            if str(m.get("request_id") or "") != request_id:
                logger.debug("discarding permission_reply (stale request_id)")
                continue
            raw = str(m.get("reply") or "").strip().lower()
            fb = _permission_reply_user_message(m)
            if raw in ("once", "allow", "1", "yes", "ok"):
                return "once", fb
            if raw in ("always", "all"):
                return "always", fb
            if raw in ("reject", "deny", "no", "0"):
                return "reject", fb
            logger.debug("invalid permission_reply reply=%r; still waiting", raw)
            continue
        if handle_control(m):
            raise AgentChatCancelled()
        if cancel_event is not None and cancel_event.is_set():
            raise AgentChatCancelled()


def _parse_router_category_tokens(raw: str | None) -> frozenset[str]:
    if not raw or not str(raw).strip():
        return frozenset()
    return frozenset(x.strip().lower() for x in str(raw).split(",") if x.strip())


def _parse_router_categories_value(raw: Any) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        return _parse_router_category_tokens(raw)
    if isinstance(raw, list):
        return frozenset(str(x).strip().lower() for x in raw if str(x).strip())
    return frozenset()


def _parse_capability_hints(raw: Any) -> frozenset[str]:
    """Client hint: filter tools to those declaring any of these capability strings (ADR 0001)."""
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        return frozenset(x.strip() for x in raw.replace(",", " ").split() if x.strip())
    if isinstance(raw, list):
        return frozenset(str(x).strip() for x in raw if str(x).strip())
    return frozenset()


def _inject_agent_system_prompt(messages: list[dict[str, Any]], agent_id: str | None) -> list[dict[str, Any]]:
    """Inject agent-specific system prompt from registry."""
    if not agent_id:
        return messages
    agent = get_agent_registry().get_agent(agent_id)
    if not agent:
        logger.debug("agent %r not found, skipping system prompt injection", agent_id)
        return messages
    system_prompt = agent.get("system_prompt", "")
    if not system_prompt:
        return messages
    if not messages:
        return [{"role": "system", "content": system_prompt}]
    out = list(messages)
    if out[0].get("role") == "system":
        existing = out[0].get("content") or ""
        out[0] = {
            **out[0],
            "content": (existing + "\n\n" + system_prompt).strip() if existing else system_prompt,
        }
    else:
        out.insert(0, {"role": "system", "content": system_prompt})
    return out


def _inject_system_prompt(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not config.SYSTEM_PROMPT_EXTRA:
        return messages
    extra = config.SYSTEM_PROMPT_EXTRA
    if not messages:
        return [{"role": "system", "content": extra}]
    out = list(messages)
    if out[0].get("role") == "system":
        existing = out[0].get("content") or ""
        out[0] = {
            **out[0],
            "content": (existing + "\n\n" + extra).strip() if existing else extra,
        }
    else:
        out.insert(0, {"role": "system", "content": extra})
    return out


_SECRETS_CREDENTIAL_DISCIPLINE = """## Credentials and API keys (mandatory)

- **Never** edit ``docker/.env``, ``.env``, or similar env files to store user API keys, tokens, or passwords — those writes are **blocked**.
- When the user pastes a credential in chat and asks to save it, call **`save_user_secret`** with the integration's ``service_key`` (e.g. ``ssc_api_key`` for SimpleSecCheck, ``github_pat`` for GitHub) and the secret value.
- Use **`register_secrets`** / Settings → Connections only when the user must run OTP curl themselves; prefer **`save_user_secret`** when they pasted the key in chat.
- Operator env vars (``SSC_API_KEY`` in docker) are for humans/ops — not for you to write from a chat turn.
"""

_TOOL_USAGE_DISCIPLINE = """## Tool usage (discipline)

- The API **tools[]** list is a compact catalog; full JSON Schema for a tool is returned from **get_tool_help** when needed.
- **Do not** loop on `list_tool_categories`, `list_tools_in_category`, `list_available_tools`, or `get_tool_help`. At most one short discovery pass if you truly do not know a tool name.
- When intent is clear, **call the action tool first** (e.g. **git pull / sync repo** → `coding_git_sync` or `coding_bash` with `{"command":"git pull"}`; `git clone` / repo URL → `coding_bash`; read a file → `coding_read_file` or `fs_read_file`).
- Use **get_tool_help at most once** per tool you are about to call with non-obvious arguments; do not repeat it every round for the same tool.
- Prefer concrete workspace tools (`coding_git_sync`, `coding_bash`, `coding_read_file`, `fs_read_file`, GitHub-related tools) over plugin meta tools (`create_tool`, …) unless the user explicitly asks to build or install a plugin.
"""

_CODING_PLAN_TOOL_DISCIPLINE = """## **Plan** discipline (this stack)

- Tool names follow the **permission groups** mapped in your system prompt: read/list/glob/grep → exploration; **edit** + **bash** + **task** + **lsp** → same ``coding_*`` names as Build; destructive steps may require UI approval (**ask**) when the client enables it.
- Default stance: **analyze first**, then a markdown handoff; apply edits or shell only after approval or when the user clearly wants execution here.
- Reuse existing tool results in the transcript — no identical tool+arguments spam.
"""

_SECURITY_AUDITOR_TOOL_DISCIPLINE = """## **Security auditor** discipline (this stack)

- Same ``coding_*`` / ``project_*`` (and optional RAG) surface as in your system prompt; **edit** and **bash** may require UI approval (**ask**) when the client enables it — prefer read-only passes first.
- Stay within **authorized scope** (workspace + user-named targets). No open-ended internet-wide scanning or replication-style objectives.
- Reuse existing tool results in the transcript — no identical tool+arguments spam.
"""

_CODING_BUILD_TOOL_DISCIPLINE = """## **Build** discipline (this stack)

- Use only ``coding_*`` / ``project_explain`` from **tools[]** — no registry meta tools.
- Map work to permission groups (read, list, glob, grep, edit, bash, task, lsp) as in your system prompt; call with complete JSON.
- Destructive tools may require UI approval when enabled — **ask** semantics for **edit** / **bash** when the client enables them.
- Do not re-list or re-read the same path when that output is already in the transcript; proceed to edit, bash, or a new path.
"""

_TOOL_DISCIPLINE_BY_PRESET: dict[str, str] = {
    "coding_plan": _CODING_PLAN_TOOL_DISCIPLINE,
    "coding_build": _CODING_BUILD_TOOL_DISCIPLINE,
    "security_auditor": _SECURITY_AUDITOR_TOOL_DISCIPLINE,
}


def _agent_behavior_flags(agent_id: str | None) -> dict[str, Any]:
    """Resolved from the agent plugin registry — no hard-coded agent id lists for these flags."""
    base: dict[str, Any] = {
        "strict_workspace": False,
        "coding_tools_permission_ask": False,
        "tool_discipline_preset": None,
    }
    if not agent_id or not str(agent_id).strip():
        return base
    ag = get_agent_registry().get_agent(str(agent_id).strip())
    if not ag:
        return base
    preset = ag.get("tool_discipline_preset")
    preset_norm: str | None = None
    if isinstance(preset, str) and preset.strip():
        preset_norm = preset.strip().lower()
    return {
        "strict_workspace": bool(ag.get("strict_workspace")),
        "coding_tools_permission_ask": bool(ag.get("coding_tools_permission_ask")),
        "tool_discipline_preset": preset_norm,
    }


def _append_tool_usage_discipline(
    messages: list[dict[str, Any]], *, agent_id: str | None = None
) -> list[dict[str, Any]]:
    flags = _agent_behavior_flags(agent_id)
    preset = flags.get("tool_discipline_preset")
    if isinstance(preset, str) and preset in _TOOL_DISCIPLINE_BY_PRESET:
        snippet = _TOOL_DISCIPLINE_BY_PRESET[preset].strip()
    else:
        snippet = _TOOL_USAGE_DISCIPLINE.strip()
    secrets_snippet = _SECRETS_CREDENTIAL_DISCIPLINE.strip()
    combined = "\n\n".join(s for s in (secrets_snippet, snippet) if s)
    if not combined:
        return messages
    out = list(messages)
    if out and out[0].get("role") == "system":
        prev = str(out[0].get("content") or "")
        out[0] = {**out[0], "content": (prev + "\n\n" + combined).strip()}
    else:
        out.insert(0, {"role": "system", "content": combined})
    return out


def _inject_dashboard_context(
    messages: list[dict[str, Any]], raw: Any
) -> list[dict[str, Any]]:
    """
    Optional client hint: ``agent_dashboard_context: { "dashboard_id": "<uuid>" }``.
    Resolved server-side so the model only sees dashboards the user may access.
    """
    if not isinstance(raw, dict):
        return messages
    wid_s = raw.get("dashboard_id")
    if not isinstance(wid_s, str) or not wid_s.strip():
        return messages
    try:
        wid = uuid.UUID(wid_s.strip())
    except ValueError:
        return messages
    ident = get_identity()
    if ident[1] is None:
        return messages
    tid, uid = ident
    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        note = (
            "[Dashboard context] The client requested a default dashboard id but it is not "
            "accessible to this user; do not assume a dashboard id until tools return one."
        )
    else:
        k = (ws.get("kind") or "").strip()
        title = (ws.get("title") or "").strip()
        role = (ws.get("access_role") or "").strip()
        note = (
            f"[Dashboard context] The user opened this dashboard in the app. "
            f"dashboard_id={wid!s}, kind={k!r}, title={title!r}, access_role={role!r}. "
            f"For shopping_list_* tools, use this dashboard_id when the user means 'this list' "
            f"and does not clearly mean a different list; for pets_* when kind is pets, or ideas_* "
            f"when kind is ideas, use the same id. If unsure which list, call shopping_list_dashboards; "
            f"for pets boards pets_dashboards; for ideas boards ideas_dashboards."
        )
        extra = _dashboard_data_agent_instructions(ws.get("data"))
        if extra:
            note = note + "\n\n[Dashboard-specific agent instructions]\n" + extra
    out = list(messages)
    if not out:
        return [{"role": "system", "content": note}]
    if out[0].get("role") == "system":
        existing = out[0].get("content") or ""
        out[0] = {
            **out[0],
            "content": (existing + "\n\n" + note).strip() if existing else note,
        }
    else:
        out.insert(0, {"role": "system", "content": note})
    return out


def _inject_user_memory_context(messages: list[dict[str, Any]], raw_dashboard_ctx: Any) -> list[dict[str, Any]]:
    """
    Inject persisted user memory (facts + semantic notes) as a system snippet.
    Writes are opt-in via tools; this is read-only retrieval.
    """
    q = (last_user_text(messages) or "").strip()
    if not q:
        return messages

    wid: uuid.UUID | None = None
    if isinstance(raw_dashboard_ctx, dict):
        wsid = raw_dashboard_ctx.get("dashboard_id")
        if isinstance(wsid, str) and wsid.strip():
            try:
                wid = uuid.UUID(wsid.strip())
            except ValueError:
                wid = None

    try:
        snippet = memory_api.render_memory_context(dashboard_id=wid, user_query=q)
    except Exception:
        snippet = ""
    if not snippet:
        return messages

    out = list(messages)
    if not out:
        return [{"role": "system", "content": snippet}]
    if out[0].get("role") == "system":
        existing = out[0].get("content") or ""
        out[0] = {
            **out[0],
            "content": (existing + "\n\n" + snippet).strip() if existing else snippet,
        }
    else:
        out.insert(0, {"role": "system", "content": snippet})
    return out


def _inject_workspace_retrieval_bootstrap(
    messages: list[dict[str, Any]],
    workspace: dict[str, Any] | None,
    agent_id: str | None,
) -> list[dict[str, Any]]:
    """First user turn only: index stats, repo tree, retrieve_context hint."""
    if agent_id not in ("coding", "coding_plan"):
        return messages
    if not workspace or not isinstance(workspace, dict):
        return messages
    user_turns = sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "user")
    if user_turns > 1:
        return messages
    try:
        from apps.backend.infrastructure.workspace_retrieval_bootstrap import (
            build_retrieval_bootstrap_snippet,
        )

        snippet = build_retrieval_bootstrap_snippet(workspace)
    except Exception:
        return messages
    if not snippet:
        return messages
    out = list(messages)
    if not out:
        return [{"role": "system", "content": snippet}]
    if out[0].get("role") == "system":
        existing = out[0].get("content") or ""
        out[0] = {
            **out[0],
            "content": (existing + "\n\n" + snippet).strip() if existing else snippet,
        }
    else:
        out.insert(0, {"role": "system", "content": snippet})
    return out


def _inject_workspace_verify_hints(
    messages: list[dict[str, Any]],
    workspace: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Inject verify policy hints from workspace fields (DB-backed ``verify_command`` / ``verify_required``)."""
    if not workspace or not isinstance(workspace, dict):
        return messages
    lines: list[str] = []
    vc = workspace.get("verify_command")
    if isinstance(vc, str) and vc.strip():
        lines.append(
            "This workspace has a **verify** command (stored server-side) — run it with the "
            "`coding_workspace_verify` tool (same allowlisting as `coding_bash`) or manually: "
            f"`{vc.strip()}`"
        )
    if workspace.get("verify_required"):
        lines.append(
            "Policy: **verify_required** is enabled — run `coding_workspace_verify` until it succeeds "
            "(exit code 0) before you finish with a final user-facing answer."
        )
    if not lines:
        return messages
    snippet = "\n".join(lines)
    out = list(messages)
    if not out:
        return [{"role": "system", "content": snippet}]
    if out[0].get("role") == "system":
        existing = out[0].get("content") or ""
        out[0] = {
            **out[0],
            "content": (existing + "\n\n" + snippet).strip() if existing else snippet,
        }
    else:
        out.insert(0, {"role": "system", "content": snippet})
    return out


def _tool_spec_name(entry: Any) -> str | None:
    if not isinstance(entry, dict):
        return None
    fn = entry.get("function")
    if isinstance(fn, dict):
        n = fn.get("name")
        return str(n) if n else None
    return None


def _merge_tools(body_tools: list[Any] | None) -> list[Any]:
    """
    Always merge the live registry tool list into the request for Ollama.

    Open WebUI often sends its own non-empty ``tools`` list; previously that
    replaced our list entirely so the model never saw agent-layer tools.
    """
    ours = get_registry().chat_tool_specs
    if not body_tools:
        return ours
    seen = {n for t in ours if (n := _tool_spec_name(t))}
    merged: list[Any] = list(ours)
    for t in body_tools:
        if not isinstance(t, dict):
            continue
        n = _tool_spec_name(t)
        if n is None:
            merged.append(t)
            continue
        if n not in seen:
            merged.append(t)
            seen.add(n)
    logger.debug(
        "tools merge: registry=%d client=%d merged=%d",
        len(ours),
        len(body_tools),
        len(merged),
    )
    return merged


_CATALOG_PARAM_HINT = (
    "Parameters may be abbreviated in this catalog. If you already know the arguments, call the tool "
    "directly. Only use get_tool_help(tool_name) once when you need the full JSON Schema for that tool."
)


def _full_schema_tool_function(name: str, fn: dict[str, Any]) -> dict[str, Any]:
    """OpenAI tools[] entry with registry ``parameters`` (required for unattended / schedule runs)."""
    desc = (fn.get("TOOL_DESCRIPTION") or fn.get("description") or "").strip()
    cand = fn.get("parameters")
    if isinstance(cand, dict) and cand.get("properties"):
        params: dict[str, Any] = copy.deepcopy(cand)
        if "type" not in params:
            params["type"] = "object"
    else:
        params = {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": params,
        },
    }


def _catalog_tool_function(name: str, fn: dict[str, Any]) -> dict[str, Any]:
    """Small tools[] entry: TOOL_LABEL + TOOL_DESCRIPTION hint; minimal parameters (never full domain schemas)."""
    desc = (fn.get("TOOL_DESCRIPTION") or "").strip()
    if _CATALOG_PARAM_HINT not in desc:
        desc = f"{desc}\n\n{_CATALOG_PARAM_HINT}".strip() if desc else _CATALOG_PARAM_HINT
    if name == "get_tool_help":
        params: dict[str, Any] = {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "Exact tool name from list_tools_in_category or list_available_tools",
                },
            },
            "required": ["tool_name"],
        }
    elif name == "list_tools_in_category":
        params = {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category id from list_tool_categories",
                },
            },
            "required": ["category"],
        }
    elif name.startswith("mcp__"):
        cand = fn.get("parameters")
        if isinstance(cand, dict) and cand:
            params = cand
        else:
            params = {
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            }
    elif fn.get("chat_full_parameters"):
        desc = (fn.get("TOOL_DESCRIPTION") or fn.get("description") or "").strip()
        cand = fn.get("parameters")
        if isinstance(cand, dict) and cand.get("properties"):
            params = copy.deepcopy(cand)
            if "type" not in params:
                params["type"] = "object"
        else:
            params = {
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            }
    else:
        params = {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": params,
        },
    }


def _tools_for_chat_request(
    merged_tools: list[Any],
    *,
    full_schema: bool = False,
) -> list[Any]:
    """
    Build tools[] for the LLM request.

    Default (**full_schema** from ``AGENT_TOOLS_FULL_SCHEMA``, usually **true**): registry JSON Schema per tool.
    **full_schema=False**: compact catalog (name + hint; empty ``parameters``) — legacy/token-saving mode.
    """
    builder = _full_schema_tool_function if full_schema else _catalog_tool_function
    out: list[Any] = []
    for spec in merged_tools:
        if not isinstance(spec, dict):
            out.append(spec)
            continue
        name = _tool_spec_name(spec)
        fn = spec.get("function")
        if not name or not isinstance(fn, dict):
            out.append(spec)
            continue
        out.append(builder(name, fn))
    return out


def _tools_payload_size_estimate(tools: list[Any]) -> tuple[int, int, int]:
    """
    (json_char_count, est_tokens_low, est_tokens_high) for the tools[] array as sent in the request.

    Heuristic only: chars/4 .. chars/3 — not the model tokenizer; real usage depends on the backend.
    """
    if not tools:
        return 0, 0, 0
    raw = json.dumps(tools, ensure_ascii=False, separators=(",", ":"))
    c = len(raw)
    lo = (c + 3) // 4
    hi = (c + 2) // 3
    return c, lo, hi


def _log_tools_request_estimate(TOOL_LABEL: str, tools: list[Any]) -> None:
    if not config.AGENT_LOG_TOOLS_REQUEST_ESTIMATE:
        return
    n = len(tools)
    jc, lo, hi = _tools_payload_size_estimate(tools)
    logger.info(
        "tools request %s: tool_defs=%d json_chars=%d est_tokens~%d-%d (heuristic, not tokenizer)",
        TOOL_LABEL,
        n,
        jc,
        lo,
        hi,
    )


def _parse_tool_arguments(raw: str | dict | None) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("invalid tool arguments JSON: %s", raw[:200])
        return {}


def _format_normalized_tool_args_for_recap(
    name: str, norm: dict[str, Any], *, max_len: int = 400
) -> str:
    """Single-line summary of normalized tool arguments (shared by round digest + tool recap)."""
    bits: list[str] = []
    for key in (
        "command",
        "pattern",
        "path",
        "path_prefix",
        "query",
        "prompt",
        "operation",
        "rel",
        "glob",
        "patch_text",
        "old_string",
        "new_string",
        "include_files",
        "include_directories",
    ):
        if key not in norm:
            continue
        val = norm.get(key)
        if isinstance(val, str):
            u = val.strip().replace("\n", "\\n")
            if not u:
                continue
            if len(u) > 140:
                u = u[:140] + "…"
            bits.append(f"{key}={u}")
        elif isinstance(val, (bool, int, float)):
            bits.append(f"{key}={val}")
    nl = (name or "").lower()
    if nl == "coding_glob" and not str(norm.get("pattern") or "").strip():
        bits.insert(0, "pattern=<missing>")
    if nl == "coding_search" and not str(norm.get("query") or "").strip():
        bits.insert(0, "query=<missing>")
    if bits:
        line = " ".join(bits)
    else:
        try:
            compact = json.dumps(norm, ensure_ascii=False, sort_keys=True, default=str)
        except TypeError:
            compact = repr(norm)
        line = compact if compact.strip() not in ("{}", "") else "(empty)"
    line = line.replace("\n", " ")
    if len(line) > max_len:
        line = line[:max_len] + "…"
    return line


def _unwrap_fenced_json(text: str) -> str:
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if not lines:
        return t
    lines = lines[1:]
    while lines and lines[-1].strip() in ("```", ""):
        lines.pop()
    return "\n".join(lines).strip()


def _extract_first_json_object(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    if start < 0:
        return None
    try:
        obj, _end = JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _strip_model_output_markers(text: str) -> str:
    """
    Remove whole-line angle-bracket sentinels some models emit (e.g. Nemotron
    ``<｜begin▁of▁string>`` / ``<｜end▁of▁string>``) so ``replace_tool({...})`` prose can be parsed.
    """
    lines_out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if len(s) >= 3 and s[0] == "<" and s[-1] == ">" and "\n" not in s:
            inner = s[1:-1].lower()
            if any(
                needle in inner
                for needle in (
                    "begin",
                    "end",
                    "start",
                    "eof",
                    "eot",
                    "string",
                    "think",
                    "reasoning",
                )
            ):
                continue
        lines_out.append(line)
    return "\n".join(lines_out).strip()


def _parse_parenthesized_tool_call(text: str) -> tuple[str, dict[str, Any]] | None:
    """
    Parse ``read_tool({...})`` / ``replace_tool({...})`` style text when the model
    does not emit native ``tool_calls`` (common with small Nemotron builds).
    """
    names = sorted(_CONTENT_META_TOOL_NAMES, key=len, reverse=True)
    for name in names:
        key = name + "("
        pos = 0
        while True:
            idx = text.find(key, pos)
            if idx < 0:
                break
            j = idx + len(key)
            while j < len(text) and text[j] in " \t\r\n":
                j += 1
            if j >= len(text) or text[j] != "{":
                pos = idx + 1
                continue
            try:
                obj, _end = JSONDecoder().raw_decode(text[j:])
            except json.JSONDecodeError:
                pos = idx + 1
                continue
            if isinstance(obj, dict):
                return name, obj
            pos = idx + 1
    return None


def _known_tool_names() -> set[str]:
    return {n for t in get_registry().chat_tool_specs if (n := _tool_spec_name(t))}


def _coerce_params_dict(p: Any) -> dict[str, Any] | None:
    if p is None:
        return {}
    if isinstance(p, dict):
        return p
    if isinstance(p, str):
        s = p.strip()
        if not s:
            return {}
        try:
            o = json.loads(s)
        except json.JSONDecodeError:
            return None
        return dict(o) if isinstance(o, dict) else None
    return None


# JSON where the function name is under ``tool_name`` (Nemotron) instead of ``name`` / ``tool``.
_CONTENT_META_TOOL_NAMES = frozenset(
    {
        "read_tool",
        "replace_tool",
        "create_tool",
        "update_tool",
        "rename_tool",
        "list_tools",
        "list_available_tools",
        "get_tool_help",
    }
)

# Models often put filename/source at the JSON root while using "tool"/"name" instead of nested parameters.
_CONTENT_META_TOP_LEVEL_ARG_KEYS = (
    "filename",
    "registered_tool_name",
    "tool_name",
    "name",
    "source",
    "old_string",
    "new_string",
    "replace_all",
    "old_filename",
    "new_filename",
    "overwrite",
    "TOOL_DESCRIPTION",
)


def _merge_meta_tool_obj_args(name: str, obj: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    if name not in _CONTENT_META_TOOL_NAMES:
        return base
    out = dict(base)
    if isinstance(obj.get("parameters"), dict):
        out.update(obj["parameters"])
    if isinstance(obj.get("arguments"), dict):
        out.update(obj["arguments"])
    for k in _CONTENT_META_TOP_LEVEL_ARG_KEYS:
        if k in obj:
            out[k] = obj[k]
    return out


def _parse_tool_intent_from_content(content: str) -> tuple[str, dict[str, Any]] | None:
    """
    Some models emit JSON like {\"tool\": \"<name>\", \"parameters\": {...}} in message content
    instead of wire-format ``tool_calls``.
    """
    t = _strip_model_output_markers(_unwrap_fenced_json(content))
    pc = _parse_parenthesized_tool_call(t)
    if pc:
        return pc
    obj = _extract_first_json_object(t)
    if not obj:
        return None
    name: str | None = None
    params: dict[str, Any] | None = None
    tnk = obj.get("tool_name")
    if isinstance(tnk, str) and tnk.strip() in _CONTENT_META_TOOL_NAMES:
        name = tnk.strip()
        params = {k: v for k, v in obj.items() if k != "tool_name"}
        params = _merge_meta_tool_obj_args(name, obj, params)
        return name, params
    if isinstance(obj.get("tool"), str):
        name = str(obj["tool"]).strip()
        p = obj.get("parameters")
        if not isinstance(p, dict):
            p = obj.get("arguments")
        if not isinstance(p, dict):
            p = obj.get("params")
        params = _coerce_params_dict(p)
    elif isinstance(obj.get("name"), str):
        name = str(obj["name"]).strip()
        p = obj.get("parameters")
        if not isinstance(p, dict):
            p = obj.get("arguments")
        if not isinstance(p, dict):
            p = obj.get("params")
        params = _coerce_params_dict(p)
    elif isinstance(obj.get("function"), str):
        name = str(obj["function"]).strip()
        p = obj.get("parameters")
        if not isinstance(p, dict):
            p = obj.get("arguments")
        if not isinstance(p, dict):
            p = obj.get("params")
        params = _coerce_params_dict(p)
    if not name or params is None:
        return None
    if isinstance(params, dict):
        params = _merge_meta_tool_obj_args(name, obj, params)
    return name, params


def _content_fallback_args_acceptable(name: str, params: dict[str, Any]) -> bool:
    """Reject synthetic tool_calls that would no-op or loop (e.g. read_tool({}))."""
    if name == "read_tool":
        return any(
            str(params.get(k) or "").strip()
            for k in ("filename", "registered_tool_name", "tool_name", "name")
        )
    if name == "replace_tool":
        if not str(params.get("source") or "").strip():
            return False
        return any(
            str(params.get(k) or "").strip()
            for k in ("filename", "registered_tool_name", "tool_name", "name")
        )
    if name == "update_tool":
        if not str(params.get("old_string") or "").strip():
            return False
        return any(
            str(params.get(k) or "").strip()
            for k in ("filename", "registered_tool_name", "tool_name", "name")
        )
    if name == "create_tool":
        if str(params.get("source") or "").strip():
            return True
        return bool(str(params.get("tool_name") or "").strip() or str(params.get("name") or "").strip())
    if name == "rename_tool":
        return bool(str(params.get("old_filename") or "").strip()) and bool(
            str(params.get("new_filename") or "").strip()
        )
    if name == "get_tool_help":
        return bool(str(params.get("tool_name") or "").strip())
    if name == "coding_bash":
        return bool(str(params.get("command") or "").strip())
    if name == "coding_task":
        rps = params.get("run_plan_subagent")
        if (isinstance(rps, bool) and rps) or (
            isinstance(rps, str) and rps.strip().lower() in ("1", "true", "yes", "on")
        ):
            return bool(str(params.get("prompt") or "").strip())
        return bool(str(params.get("description") or "").strip()) and bool(
            str(params.get("prompt") or "").strip()
        )
    if name == "coding_read_file":
        return bool(str(params.get("path") or "").strip())
    if name == "coding_git_sync":
        op = str(params.get("operation") or "pull").strip().lower()
        return op in ("pull", "fetch")
    return True


def _text_blobs_from_message(msg: dict[str, Any]) -> list[str]:
    """Collect strings where models may hide JSON tool intent (reasoning models, multimodal content)."""
    blobs: list[str] = []
    t = msg.get("text")
    if isinstance(t, str) and t.strip():
        blobs.append(t)
    c = msg.get("content")
    if isinstance(c, str) and c.strip():
        blobs.append(c)
    elif isinstance(c, list):
        for part in c:
            if isinstance(part, dict):
                if part.get("type") == "text" and isinstance(part.get("text"), str):
                    blobs.append(part["text"])
                elif isinstance(part.get("content"), str):
                    blobs.append(part["content"])
            elif isinstance(part, str):
                blobs.append(part)
    for key in (
        "reasoning_content",
        "reasoning",
        "thinking",
        "thought",
        "reasoning_content_delta",  # some proxies
    ):
        v = msg.get(key)
        if isinstance(v, str) and v.strip():
            blobs.append(v)
    return blobs


def _synthetic_tool_calls_from_message(
    msg: dict[str, Any],
    choice: dict[str, Any] | None = None,
    *,
    allowed_tool_names: set[str] | None = None,
) -> list[dict[str, Any]] | None:
    """When ``AGENT_CONTENT_TOOL_FALLBACK`` is true: build wire-format ``tool_calls`` from message body (JSON / ``name({...})`` prose)."""
    if not config.CONTENT_TOOL_FALLBACK:
        return None
    if msg.get("tool_calls"):
        return None
    known = allowed_tool_names if allowed_tool_names is not None else _known_tool_names()
    blobs = _text_blobs_from_message(msg)
    if choice:
        for key in ("thought", "reasoning", "thinking"):
            v = choice.get(key)
            if isinstance(v, str) and v.strip():
                blobs.append(v)
    for blob in blobs:
        parsed = _parse_tool_intent_from_content(blob)
        if not parsed:
            continue
        name, params = parsed
        if name not in known:
            logger.debug("content tool JSON names unknown tool %r, ignoring", name)
            continue
        if not _content_fallback_args_acceptable(name, params):
            logger.info(
                "AGENT_CONTENT_TOOL_FALLBACK: reject %s with insufficient args %r",
                name,
                params,
            )
            continue
        tc = {
            "id": f"content-{uuid.uuid4().hex[:16]}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(params)},
        }
        logger.info(
            "AGENT_CONTENT_TOOL_FALLBACK: synthetic tool_calls for %s(%s) from message content",
            name,
            params,
        )
        return [tc]
    logger.debug(
        "AGENT_CONTENT_TOOL_FALLBACK: no tool intent in message content (keys=%s, blobs=%d)",
        list(msg.keys()),
        len(blobs),
    )
    return None


def _apply_tool_prefetch(messages: list[dict[str, Any]], prefetch: dict[str, Any]) -> None:
    args = {
        k: prefetch[k]
        for k in ("filename", "registered_tool_name", "tool_name", "name")
        if k in prefetch and prefetch[k] is not None and str(prefetch[k]).strip()
    }
    if not args:
        return
    snippet = execute_tool("read_tool", args)
    try:
        o = json.loads(snippet)
    except json.JSONDecodeError:
        o = {}
    if isinstance(o, dict) and o.get("ok") is True:
        src = str(o.get("source") or "")
        max_c = min(len(src), config.CREATE_TOOL_MAX_BYTES)
        block = (
            "Server prefetch via read_tool — edit this **extra-tool module** with read_tool/update_tool/replace_tool "
            "(not fs_* local disk tools — those edit paths on the agent host/container).\n\n"
            f"File: `{o.get('filename')}`\n\n```python\n{src[:max_c]}\n```"
        )
    else:
        err = o.get("error") if isinstance(o, dict) else snippet[:500]
        block = f"Server prefetch read_tool failed: {err}"
    if not messages:
        messages.append({"role": "system", "content": block})
        return
    if messages[0].get("role") == "system":
        prev = messages[0].get("content") or ""
        messages[0] = {
            **messages[0],
            "content": (block + "\n\n" + prev).strip() if prev else block,
        }
    else:
        messages.insert(0, {"role": "system", "content": block})


def _names_from_tool_list(tools: list[Any]) -> set[str]:
    return {n for t in tools if (n := _tool_spec_name(t))}


def _extract_tool_calls_from_completion_response(
    data: dict[str, Any],
    *,
    allowed_tool_names: set[str],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]] | None, bool]:
    """
    Parse choices[0].message and optional synthetic tool calls from content.
    Mutates ``data`` in place when synthetic tool_calls are applied (same as inline logic).
    """
    choice0 = (data.get("choices") or [{}])[0]
    if not isinstance(choice0, dict):
        choice0 = {}
    raw_msg = choice0.get("message")
    if not isinstance(raw_msg, dict):
        raw_msg = {}
    msg = dict(raw_msg)
    raw_tc = msg.get("tool_calls")
    had_native_tool_calls = isinstance(raw_tc, list) and len(raw_tc) > 0
    tool_calls = raw_tc if had_native_tool_calls else None
    if not tool_calls:
        tool_calls = _synthetic_tool_calls_from_message(
            msg, choice0, allowed_tool_names=allowed_tool_names
        )
        if tool_calls:
            msg["tool_calls"] = tool_calls
            choice0["message"] = msg
    return choice0, msg, tool_calls, had_native_tool_calls


def _approx_text_chars_in_messages(messages: list[dict[str, Any]]) -> int:
    return sum(sum(len(b) for b in _text_blobs_from_message(m)) for m in messages)


def _redact_secrets_for_log(s: str) -> str:
    """Best-effort masking for log previews (OpenWeather appid, Bearer tokens)."""
    s = re.sub(r"(?i)appid=[A-Za-z0-9._-]+", "appid=***", s)
    s = re.sub(r"(?i)bearer\s+[A-Za-z0-9._-]+", "Bearer ***", s)
    return s


def _redact_provider_error_text_for_log(raw: str | None, *, max_len: int = 500) -> str:
    """Truncate and redact LLM/HTTP provider error bodies before logging (not for clients)."""
    if not raw:
        return "(empty)"
    s = raw.strip().replace("\r\n", "\n")
    if len(s) > max_len:
        s = s[:max_len] + "…"
    s = _redact_secrets_for_log(s)
    s = re.sub(r"(?i)\bsk-[a-z0-9]{10,}\b", "sk-***", s)
    s = re.sub(r"(?i)\bxox[baprs]-[a-z0-9-]{8,}\b", "xox***", s)
    s = re.sub(r"(?i)(api[_-]?key|client_secret)\s*[:=]\s*[^\s&,\"']+", r"\1=<redacted>", s)
    return s


def _log_llm_completion_round(
    *,
    round_i: int,
    max_rounds_cap: int,
    model: Any,
    messages: list[dict[str, Any]],
    tools_for_round: list[Any],
    msg: dict[str, Any],
    choice0: dict[str, Any],
    tool_calls: list[Any] | None,
    had_native_tool_calls: bool,
) -> None:
    if not config.AGENT_LOG_LLM_ROUNDS:
        return
    ctx_msgs = len(messages)
    ctx_chars = _approx_text_chars_in_messages(messages)
    large = ""
    if ctx_chars >= config.AGENT_LOG_LARGE_CONTEXT_CHARS:
        large = f" LARGE_CTX(>={config.AGENT_LOG_LARGE_CONTEXT_CHARS} chars)"
    rt_names = [n for t in (tools_for_round or []) if (n := _tool_spec_name(t))]
    synthetic_tc_from_content = bool(tool_calls) and not had_native_tool_calls
    if tool_calls:
        call_names = [(tc.get("function") or {}).get("name") or "?" for tc in tool_calls]
        logger.info(
            "llm round %d/%d llm_model_id=%s reply=TOOLS calls=%s synthetic_tool_calls_from_content=%s "
            "ctx_msgs=%d ctx_text_chars~=%d tools_forwarded_count=%d tool_names=%s%s",
            round_i + 1,
            max_rounds_cap,
            model,
            call_names,
            synthetic_tc_from_content,
            ctx_msgs,
            ctx_chars,
            len(rt_names),
            rt_names,
            large,
        )
        return
    cap = config.AGENT_LOG_ASSISTANT_PREVIEW_CHARS
    blobs = list(_text_blobs_from_message(msg))
    for key in ("thought", "reasoning", "thinking"):
        v = choice0.get(key)
        if isinstance(v, str) and v.strip():
            blobs.append(v)
    joined = "\n".join(blobs)
    any_text = bool(joined.strip())
    if cap > 0:
        preview = _redact_secrets_for_log(joined[:cap])
    else:
        preview = "(set AGENT_LOG_ASSISTANT_PREVIEW_CHARS>0 for redacted snippet)"
    if not any_text:
        logfn = logger.warning if rt_names else logger.info
        logfn(
            "llm round %d/%d llm_model_id=%s reply=empty_text_no_tool_calls synthetic_tool_calls_from_content=%s "
            "ctx_msgs=%d ctx_text_chars~=%d tools_forwarded_count=%d%s",
            round_i + 1,
            max_rounds_cap,
            model,
            synthetic_tc_from_content,
            ctx_msgs,
            ctx_chars,
            len(rt_names),
            large,
        )
        return
    logger.info(
        "llm round %d/%d llm_model_id=%s reply=TEXT_NO_TOOLS synthetic_tool_calls_from_content=%s "
        "ctx_msgs=%d ctx_text_chars~=%d tools_forwarded_count=%d preview=%r%s",
        round_i + 1,
        max_rounds_cap,
        model,
        synthetic_tc_from_content,
        ctx_msgs,
        ctx_chars,
        len(rt_names),
        preview,
        large,
    )


_REPO_GIT_INTENT_RE = re.compile(
    r"\b(?:git\s+)?clone\b|\brep(?:ository|os?)\b|\bcodebase\b|\b(?:pull\s+request|pr)\b|"
    r"\bgit\s+init\b|\bgit\s+pull\b|\bgit\s+push\b|\bcommit(?:s)?\b|\bbranch\b|\bmerge\b|"
    r"\b(?:fork|star)\s+(?:this\s+)?(?:repo|repository)\b|\bgithub\.com/",
    re.IGNORECASE,
)


def _extract_https_git_url(text: str) -> str | None:
    if not (text or "").strip():
        return None
    for m in re.finditer(r"https://[^\s\)\]\"'<>]+", text):
        u = m.group(0).rstrip(").,;]")
        low = u.lower()
        if low.endswith(".git"):
            return u
        for marker in (
            "github.com/",
            "gitlab.com/",
            "bitbucket.org/",
            "codeberg.org/",
        ):
            if marker in low:
                return u
        if "/git/" in low or ".git" in low:
            return u
    return None


def _coding_repo_intent(text: str) -> bool:
    if _extract_https_git_url(text):
        return True
    return bool(text and _REPO_GIT_INTENT_RE.search(text))


def _is_elevated_admin(
    user_obj: Any,
    bearer_user_role: str | None,
    user_id: Any,
) -> bool:
    if (bearer_user_role or "").strip().lower() == "admin":
        return True
    if user_obj is not None and getattr(user_obj, "role", None) == "admin":
        return True
    if user_id:
        try:
            from apps.backend.infrastructure.db import db as _role_db

            if _role_db.user_role(user_id) == "admin":
                return True
        except Exception:
            pass
    return False


def _normalize_workspace_id_for_gate(workspace_id: Any) -> str | None:
    if workspace_id is None:
        return None
    if isinstance(workspace_id, str):
        s = workspace_id.strip()
        return s or None
    return str(workspace_id).strip() or None


def _raise_if_workspace_inaccessible(
    *,
    workspace_id: Any,
    user_id: Any,
    workspace: dict[str, Any] | None,
    agent_id: str | None,
) -> None:
    """Fail closed: never run coding tools with a client-supplied id we did not resolve."""
    wid = _normalize_workspace_id_for_gate(workspace_id)
    if wid and user_id and workspace is None:
        raise WorkspaceAccessDenied(
            "workspace_id is not available to this user (missing, not ready, or access denied)."
        )
    aid = (agent_id or "").strip() or None
    strict = False
    if aid:
        ag = get_agent_registry().get_agent(aid)
        if ag:
            strict = bool(ag.get("strict_workspace"))
    if strict and workspace is None:
        raise WorkspaceAccessDenied(
            f"{aid} requires a workspace_id that resolves to an accessible project workspace."
        )


def _completion_attach_agent_run_id(data: dict[str, Any], agent_run_id: str) -> dict[str, Any]:
    if isinstance(data, dict) and agent_run_id:
        data["agent_run_id"] = agent_run_id
    return data


def _workspace_tool_bound_workspace_id(tool_name: str, tool_result_json: str) -> str | None:
    """Return workspace id when ``workspace_bind`` / bound ``workspace_create`` succeeded."""
    if tool_name not in ("workspace_bind", "workspace_create"):
        return None
    try:
        data = json.loads(tool_result_json)
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("ok") is not True:
        return None
    if tool_name == "workspace_create" and not data.get("bound"):
        return None
    ws = data.get("workspace")
    if not isinstance(ws, dict):
        return None
    wid = ws.get("id")
    if wid is None:
        return None
    s = str(wid).strip()
    return s or None


async def _apply_workspace_tool_bind_side_effects(
    *,
    tool_name: str,
    result: str,
    tool_context: dict[str, Any],
    messages: list[dict[str, Any]],
    event_emit: Any,
    agent_run_id: str,
) -> None:
    """Refresh bootstrap snippet and notify UI after workspace_bind / workspace_create."""
    wid = _workspace_tool_bound_workspace_id(tool_name, result)
    if not wid:
        return
    ws = tool_context.get("workspace")
    if isinstance(ws, dict):
        try:
            from apps.backend.infrastructure.workspace_retrieval_bootstrap import (
                build_retrieval_bootstrap_snippet,
                maybe_schedule_index_on_attach,
            )

            snippet = build_retrieval_bootstrap_snippet(ws)
            if snippet:
                messages.append({"role": "system", "content": snippet})
            maybe_schedule_index_on_attach(ws)
        except Exception as e:
            logger.debug("workspace bind bootstrap skipped: %s", e)
    if event_emit:
        await event_emit(
            {
                "type": "agent.session",
                "agent_run_id": agent_run_id,
                "workspace_id": wid,
                "workspace_bound": True,
            }
        )


def _format_workspace_verify_recap(tool_result_json: str) -> str | None:
    """Build a short system snippet from ``coding_workspace_verify`` JSON output."""
    try:
        d = json.loads(tool_result_json)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    if "verify_command" not in d and "exit_code" not in d:
        return None
    parts: list[str] = ["[Workspace verify recap]"]
    cmd = d.get("verify_command")
    if isinstance(cmd, str) and cmd.strip():
        parts.append(f"command: {cmd.strip()[:400]}")
    if d.get("ok") is not None:
        parts.append(f"ok: {bool(d.get('ok'))}")
    if "exit_code" in d:
        parts.append(f"exit_code: {d.get('exit_code')}")
    out = d.get("output")
    if isinstance(out, str) and out.strip():
        sn = out.strip()
        if len(sn) > 1200:
            sn = sn[:1200] + "…"
        parts.append("output:\n" + sn)
    err = d.get("error")
    if isinstance(err, str) and err.strip() and (not isinstance(out, str) or not out.strip()):
        parts.append("error: " + err.strip()[:800])
    return "\n".join(parts)


async def _async_iter_chat_completion_sse(
    attempts_seq: list[tuple[str, dict[str, str], str]],
    payload_base: dict[str, Any],
    *,
    llm_backend: str,
    profile_key: str,
    timeout: float = 600.0,
) -> AsyncIterator[bytes]:
    """
    OpenAI-compatible POST with ``stream: true``; yield raw response bytes (typically SSE) from the first
    successful endpoint, with the same external failover / Ollama 429 fallback behaviour as blocking calls.
    """
    attempts_local = list(attempts_seq)
    lb = llm_backend
    outer_profile = profile_key
    timeout_cfg = httpx.Timeout(timeout, connect=120.0)
    while True:
        last_http: tuple[int, str, str] | None = None  # status, body, url
        last_trans: httpx.RequestError | None = None
        async with httpx.AsyncClient(timeout=timeout_cfg) as client:
            for b_url, b_headers, b_model in attempts_local:
                pl: dict[str, Any] = dict(payload_base)
                pl["stream"] = True
                pl["model"] = b_model
                h = dict(b_headers) if b_headers else {"Content-Type": "application/json"}
                try:
                    async with client.stream("POST", b_url, json=pl, headers=h) as resp:
                        if resp.status_code >= 400:
                            err_body = (await resp.aread()).decode("utf-8", errors="replace")
                            if lb == "external" and external_llm_should_failover(resp.status_code):
                                logger.warning(
                                    "LLM stream: external status=%s; trying next endpoint url=%s",
                                    resp.status_code,
                                    b_url,
                                )
                                last_http = (resp.status_code, err_body, b_url)
                                continue
                            err_red = _redact_provider_error_text_for_log(err_body, max_len=600)
                            logger.error(
                                "LLM stream failed (%s): status=%s url=%s body=%s",
                                lb,
                                resp.status_code,
                                b_url,
                                err_red,
                            )
                            resp.raise_for_status()
                        async for chunk in resp.aiter_raw():
                            if chunk:
                                yield chunk
                    return
                except httpx.HTTPStatusError:
                    raise
                except httpx.RequestError as e:
                    last_trans = e
                    logger.warning(
                        "LLM stream transport error (%s) url=%s model=%s: %s",
                        lb,
                        b_url,
                        b_model,
                        e,
                    )
                    continue
        if last_trans is not None and last_http is None:
            raise last_trans
        if last_http is not None:
            st, txt, url = last_http
            if st == 429 and lb == "external":
                local_model = ollama_model_for_profile(outer_profile)
                attempts_local, lb = llm_chat_transport(
                    local_model,
                    outer_profile,
                    False,
                    backend_override="ollama",
                    catalog_owned_by=None,
                )
                logger.warning(
                    "LLM stream: external 429; falling back to Ollama llm_model_id=%s",
                    local_model,
                )
                continue
            err_red = _redact_provider_error_text_for_log(txt, max_len=600)
            logger.error(
                "LLM stream failed (%s): status=%s url=%s body=%s",
                lb,
                st,
                url,
                err_red,
            )
            req = httpx.Request("POST", url)
            raise httpx.HTTPStatusError(
                f"HTTP {st}",
                request=req,
                response=httpx.Response(st, request=req, text=txt[:8000]),
            )
        raise RuntimeError("LLM stream: no chat/completions attempts")


async def chat_completion(
    body: dict[str, Any],
    *,
    router_categories_header: str | None = None,
    tool_domain_header: str | None = None,
    model_profile_header: str | None = None,
    model_override_header: str | None = None,
    bearer_user_role: str | None = None,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    control_queue: asyncio.Queue | None = None,
    cancel_event: asyncio.Event | None = None,
    stream_requested: bool = False,
) -> dict[str, Any] | AsyncIterator[bytes]:
    # Without ``stream_requested`` + plain completion, the tool loop uses blocking HTTP; HTTP callers may
    # wrap the final JSON as SSE. True streaming is returned as an async byte iterator (upstream SSE passthrough).
    body.pop("agent_tool_mode", None)
    body.pop("agent_mode", None)
    plain_completion = _coerce_body_bool(body.pop("agent_plain_completion", None), False)
    stream_llm_ws = _coerce_body_bool(body.pop("agent_stream_llm", None), False)
    extra_cats_body = _parse_router_categories_value(body.pop("agent_router_categories", None))
    extra_cats_hdr = _parse_router_category_tokens(router_categories_header)
    cap_hints = _parse_capability_hints(body.pop("agent_capability_hints", None))
    raw_tool_dom = body.pop("TOOL_DOMAIN", None)
    body_tool_dom = (
        str(raw_tool_dom).strip().lower()
        if isinstance(raw_tool_dom, str) and raw_tool_dom.strip()
        else ""
    )
    hdr_tool_dom = (tool_domain_header or "").strip().lower()
    tool_domain = hdr_tool_dom or body_tool_dom or None
    logger.debug("tool_domain_header=%r, body_tool_domain=%r, final tool_domain=%r", tool_domain_header, body_tool_dom, tool_domain)

    _cap_cf_tok = bind_capability_confirmed(
        parse_user_capability_confirm(body.pop("agent_capability_confirm", None))
    )
    dashboard_ctx = body.pop("agent_dashboard_context", None)
    _raw_max_rounds = body.pop("agent_max_tool_rounds", None)
    _raw_llm_be = body.pop("agent_llm_backend", None)
    _raw_catalog_owned = body.pop("agent_model_catalog_owned_by", None)
    catalog_owned_by = normalize_model_catalog_owned_by(_raw_catalog_owned)
    _raw_tool_allow = body.pop("agent_tool_name_allowlist", None)
    _raw_tools_ranking = body.pop("agent_tools_ranking_enabled", None)
    tools_ranking_enabled = bool(config.AGENT_TOOLS_RANKING_ENABLED)
    if _raw_tools_ranking is not None:
        tools_ranking_enabled = _coerce_body_bool(_raw_tools_ranking, tools_ranking_enabled)
    agent_id = body.pop("agent_id", None)
    if isinstance(agent_id, str):
        agent_id = agent_id.strip() or None
    parent_agent_run_id = body.pop("agent_parent_run_id", None)
    if isinstance(parent_agent_run_id, str):
        parent_agent_run_id = parent_agent_run_id.strip() or None
    else:
        parent_agent_run_id = None
    permission_ask = _coerce_body_bool(body.pop("agent_permission_ask", None), False)
    agent_unattended = _coerce_body_bool(body.pop("agent_unattended", None), False)
    tools_full_schema = _coerce_body_bool(
        body.pop("agent_tools_full_schema", None),
        config.AGENT_TOOLS_FULL_SCHEMA,
    )
    if agent_unattended:
        permission_ask = False
    agent_require_workspace_verify = _coerce_body_bool(
        body.pop("agent_require_workspace_verify", None), False
    )

    from apps.backend.domain.identity import set_workspace, get_identity
    workspace_id = body.pop("workspace_id", None)
    workspace = None
    workspace_token = None
    _bootstrap_messages = list(body.get("messages") or [])
    _bootstrap_last_user = last_user_text(_bootstrap_messages)
    agent_auto_routed = False
    workspace_auto_created = False

    # Get user from identity context (tenant_id, user_id)
    tenant_id, user_id = get_identity()

    # Load DB user first so workspace resolution (e.g. agentlayer-self gates) sees real role.
    user_obj = None
    if user_id:
        try:
            from apps.backend.infrastructure.db import db

            with db.pool().connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id, role FROM users WHERE id = %s", (user_id,))
                    row = cur.fetchone()
                    if row:

                        class UserObj:
                            def __init__(self, uid, role):
                                self.id = uid
                                self.role = role

                        user_obj = UserObj(user_id, row[1])
        except Exception:
            pass

    if agent_id:
        ag_def = get_agent_registry().get_agent(agent_id)
        if ag_def:
            min_r = str(ag_def.get("min_role") or "user").strip().lower()
            if min_r == "admin":
                from apps.backend.infrastructure.db import db as _role_db

                if _role_db.user_role(user_id) != "admin":
                    raise ValueError("This agent is only available to admin users.")

    _is_admin = _is_elevated_admin(user_obj, bearer_user_role, user_id)
    if (
        agent_id == "general"
        and _is_admin
        and not workspace_id
        and _coding_repo_intent(_bootstrap_last_user)
    ):
        logger.info(
            "chat_completion: auto-routing agent general -> coding (admin, repo/git intent)"
        )
        agent_id = "coding"
        agent_auto_routed = True

    if workspace_id and user_id:
        try:
            from apps.backend.infrastructure.workspace_service import ensure_workspace

            u = user_obj
            if u is None:

                class UserLike:
                    def __init__(self, uid):
                        self.id = uid
                        self.role = "user"

                u = UserLike(user_id)
            workspace = ensure_workspace(workspace_id, u)
            logger.debug("resolved workspace: %s", workspace.get("name") if workspace else None)
        except Exception as e:
            logger.warning("failed to resolve workspace: %s", e)
    elif (
        agent_id == "coding"
        and user_id
        and not workspace_id
        and _is_admin
        and _extract_https_git_url(_bootstrap_last_user)
    ):
        u = user_obj
        if u is None:

            class UserLike:
                def __init__(self, uid):
                    self.id = uid
                    self.role = "user"

            u = UserLike(user_id)
            try:
                from apps.backend.infrastructure.db import db as _role_db2

                u.role = _role_db2.user_role(user_id) or "user"
            except Exception:
                pass
        gu = _extract_https_git_url(_bootstrap_last_user)
        if gu and u is not None:
            try:
                from apps.backend.infrastructure.workspace_service import (
                    WorkspaceCreateError,
                    create_project_workspace_for_user,
                    ensure_workspace as _ensure_ws,
                    slug_from_git_url,
                )

                nm = f"{slug_from_git_url(gu)}-{uuid.uuid4().hex[:8]}"
                created = create_project_workspace_for_user(
                    u,
                    name=nm,
                    source="git",
                    git_url=gu,
                    git_branch="main",
                )
                wid = str(created["id"])
                workspace = _ensure_ws(wid, u)
                if workspace:
                    workspace_auto_created = True
                    logger.info(
                        "chat_completion: auto-created workspace %s from Git URL in message",
                        wid,
                    )
            except WorkspaceCreateError as e:
                logger.warning("auto-create workspace failed: %s", e.message)
            except Exception as e:
                logger.warning("auto-create workspace failed: %s", e)

    _raise_if_workspace_inaccessible(
        workspace_id=workspace_id,
        user_id=user_id,
        workspace=workspace if isinstance(workspace, dict) else None,
        agent_id=agent_id if isinstance(agent_id, str) else None,
    )

    workspace_token = set_workspace(workspace)

    # Prepare context dict for tools (DDD-style, with real objects)
    tool_context: dict[str, Any] = {"user": user_obj}
    if workspace and isinstance(workspace, dict):
        _p = workspace.get("path")
        if isinstance(_p, str) and _p.strip():
            tool_context["workspace"] = workspace
        if agent_id in ("coding", "coding_plan"):
            try:
                from apps.backend.infrastructure.workspace_retrieval_bootstrap import (
                    maybe_schedule_index_on_attach,
                )

                maybe_schedule_index_on_attach(workspace)
            except Exception as e:
                logger.debug("index-on-attach skipped: %s", e)
    if cancel_event is not None:
        tool_context["cancel_event"] = cancel_event

    agent_run_id = str(uuid.uuid4())
    tool_context["agent_run_id"] = agent_run_id
    tool_context["workspace_verify_succeeded"] = False
    tool_context["permission_always_allow_tools"] = set()
    _abf = _agent_behavior_flags(agent_id if isinstance(agent_id, str) else None)
    tool_context["agent_coding_tools_permission_ask"] = _abf["coding_tools_permission_ask"]
    tool_context["agent_unattended"] = agent_unattended
    _raw_conversation_id = body.pop("conversation_id", None)
    if _raw_conversation_id is not None:
        _cid_s = str(_raw_conversation_id).strip()
        if _cid_s:
            tool_context["conversation_id"] = _cid_s
    logger.info(
        "chat_completion start agent_run_id=%s parent_agent_run_id=%s agent_id=%r workspace_id=%s user_id=%s",
        agent_run_id,
        parent_agent_run_id,
        agent_id,
        _normalize_workspace_id_for_gate(workspace_id),
        str(user_id) if user_id else None,
    )

    if agent_require_workspace_verify:
        if not workspace or not isinstance(workspace, dict):
            raise ValueError(
                "agent_require_workspace_verify requires workspace_id to resolve to an accessible workspace."
            )

    try:

        max_tool_rounds_eff = config.MAX_TOOL_ROUNDS
        if _raw_max_rounds is not None:
            try:
                client_v = int(_raw_max_rounds)
                if client_v <= 0:
                    max_tool_rounds_eff = config.MAX_TOOL_ROUNDS
                else:
                    max_tool_rounds_eff = max(1, min(client_v, config.MAX_TOOL_ROUNDS))
            except (TypeError, ValueError):
                pass

        messages = _inject_system_prompt(list(body.get("messages") or []))
        from apps.backend.infrastructure.chat_secret_ingress import ingress_openai_messages_inplace

        ingress_openai_messages_inplace(messages, tenant_id=int(tenant_id), user_id=user_id)
        messages = _inject_dashboard_context(messages, dashboard_ctx)
        if agent_id:
            messages = _inject_agent_system_prompt(messages, agent_id)
        if agent_id and agent_id in config.AGENT_SKILLS_PROMPT_AGENT_IDS:
            from apps.backend.infrastructure.skills_prompt import load_combined_skills_prompt

            skills_snip = load_combined_skills_prompt(agent_id)
            if skills_snip:
                messages = _append_system_block(messages, skills_snip)
        pf = body.get("tool_prefetch")
        if isinstance(pf, dict):
            _apply_tool_prefetch(messages, pf)
        messages = apply_user_persona_system(messages)
        messages = _inject_user_memory_context(messages, dashboard_ctx)
        messages = _inject_workspace_retrieval_bootstrap(
            messages, workspace, agent_id if isinstance(agent_id, str) else None
        )
        messages = _inject_workspace_verify_hints(messages, workspace)

        model, model_reason, profile_key, model_is_override = resolve_effective_model(
            messages=messages,
            body_model=body.get("model"),
            profile_header=model_profile_header,
            override_header=model_override_header,
            bearer_user_role=bearer_user_role,
        )
        smart_route_reason = ""
        backend_override: Literal["ollama", "external"] | None = None
        if isinstance(_raw_llm_be, str):
            lo = _raw_llm_be.strip().lower()
            if lo == "ollama":
                backend_override = "ollama"
            elif lo == "external":
                backend_override = "external"
        if backend_override is None and not plain_completion and smart_llm_routing_enabled():
            # Smart routing: 0–1 extra local router call (Ollama), then one main completion — never two externals.
            bo, smart_route_reason = await asyncio.to_thread(decide_smart_backend, messages)
            backend_override = bo
            logger.info("smart LLM route: %s -> backend=%s", smart_route_reason, bo)
        elif backend_override is not None:
            logger.info("chat_completion: agent_llm_backend override -> %s", backend_override)
        attempts, llm_backend = llm_chat_transport(
            model,
            profile_key,
            model_is_override,
            backend_override=backend_override,
            catalog_owned_by=catalog_owned_by,
        )

        if plain_completion:
            merged_tools: list[Any] = []
            logger.debug("chat_completion: agent_plain_completion (no tools forwarded to Ollama)")
        else:
            merged_tools = _merge_tools(body.get("tools"))
        routed_category: str | None = None
        cats = classify_user_tool_categories(last_user_text(messages))
        cats = cats | extra_cats_body | extra_cats_hdr
        merged_tools = filter_merged_tools_by_categories(merged_tools, cats)
        logger.debug("tool_domain before check: %r, agent_id=%r", tool_domain, agent_id)
        if agent_id:
            agent = get_agent_registry().get_agent(agent_id)
            if agent:
                tool_domain_agent = agent.get("tool_domain")
                tool_names_agent = agent.get("tool_names", [])
                if tool_domain_agent:
                    merged_tools = filter_merged_tools_by_domain(merged_tools, tool_domain_agent)
                if tool_names_agent:
                    reg = get_registry()
                    allowed_tool_names = frozenset(tool_names_agent)
                    filtered = []
                    for spec in reg.chat_tool_specs:
                        n = spec.get("function", {}).get("name", "")
                        if n in allowed_tool_names:
                            filtered.append(spec)
                    merged_tools = filtered
                logger.info("agent %s: %d tools (domain=%s, explicit_names=%s)",
                           agent_id, len(merged_tools), tool_domain_agent, bool(tool_names_agent))
            else:
                logger.warning("agent_id %r not found in registry, falling back to tool_domain", agent_id)
        elif tool_domain:
            merged_tools = filter_merged_tools_by_domain(merged_tools, tool_domain)
        if cap_hints:
            merged_tools = filter_merged_tools_by_capabilities(
                merged_tools,
                cap_hints,
                tools_meta=get_registry().tools_meta,
            )
        if cats:
            routed_category = (
                next(iter(cats)) if len(cats) == 1 else "+".join(sorted(cats))
            )
        elif config.AGENT_ROUTER_STRICT_DEFAULT:
            routed_category = "minimal"
        else:
            routed_category = "full"

        try:
            from apps.backend.domain.identity import get_identity
            from apps.backend.domain.plugin_system.tool_policy import filter_chat_tool_specs
            from apps.backend.infrastructure.db import db as _identity_db
            from apps.backend.infrastructure.tool_operator_policy_db import policies_map

            _pmap = policies_map()
            _tenant_ctx, _user_ctx = get_identity()
            _role = _identity_db.user_role(_user_ctx)
            merged_tools = filter_chat_tool_specs(
                merged_tools,
                get_registry(),
                _pmap,
                _role,
                int(_tenant_ctx),
            )
        except Exception:
            logger.debug("operator/access tool filter skipped", exc_info=True)

        disabled_names = _parse_disabled_tool_names(body.get("agent_disabled_tools"))
        if disabled_names:
            merged_tools = [
                t
                for t in merged_tools
                if (n := _tool_spec_name(t)) is None or n not in disabled_names
            ]

        if isinstance(_raw_tool_allow, list) and _raw_tool_allow:
            allow_set = {str(x).strip() for x in _raw_tool_allow if str(x).strip()}
            if allow_set:
                merged_tools = [
                    t
                    for t in merged_tools
                    if (n := _tool_spec_name(t)) is None
                    or n in allow_set
                    or n in TOOL_INTROSPECTION
                ]

        wl = _dashboard_tool_allowlist_from_request_context(dashboard_ctx)
        if wl:
            before_ct = len(merged_tools)
            merged_tools = [
                t
                for t in merged_tools
                if (n := _tool_spec_name(t)) is None or n in wl
            ]
            if len(merged_tools) < before_ct:
                logger.info(
                    "dashboard tool allowlist: tools %d -> %d",
                    before_ct,
                    len(merged_tools),
                )
            if not merged_tools:
                logger.warning(
                    "dashboard tool allowlist left no tools after filters (allowed=%r…)",
                    sorted(wl)[:24],
                )

        if (
            not plain_completion
            and agent_id
            and agent_id in config.AGENT_MCP_AGENT_IDS
        ):
            try:
                from apps.backend.infrastructure.mcp_runtime import gather_mcp_chat_tool_specs_async

                mcp_extra = await gather_mcp_chat_tool_specs_async()
                if wl is not None and mcp_extra:
                    mcp_extra = [
                        t
                        for t in mcp_extra
                        if (nn := _tool_spec_name(t)) is None or nn in wl
                    ]
                if mcp_extra:
                    merged_tools = merged_tools + mcp_extra
                    logger.info(
                        "MCP: attached %d tool specs for agent_id=%s",
                        len(mcp_extra),
                        agent_id,
                    )
            except Exception:
                logger.warning("MCP tool discovery failed", exc_info=True)

        if not tools_full_schema and agent_unattended and _raw_tool_allow:
            tools_full_schema = True
        tools_for_request = _tools_for_chat_request(merged_tools, full_schema=tools_full_schema)
        if tools_full_schema and tools_for_request:
            logger.info(
                "tools request: full parameter schemas for %d tools (agent_unattended=%s)",
                len(tools_for_request),
                agent_unattended,
            )
        if config.AGENT_TOOLS_DENYLIST:
            deny = config.AGENT_TOOLS_DENYLIST
            tools_for_request = [
                t
                for t in tools_for_request
                if (n := _tool_spec_name(t)) is None or n not in deny
            ]

        # Tool Ranking: sort by semantic similarity to user input (Phase 1)
        pin_names = _pinned_tools_for_agent(agent_id)
        if pin_names:
            pinned_specs, tools_for_ranking = _partition_tool_specs_by_name(
                tools_for_request, pin_names
            )
        else:
            pinned_specs, tools_for_ranking = [], tools_for_request
        if tools_ranking_enabled and tools_for_ranking:
            try:
                # Get last user message for ranking (do not name this ``last_user_text`` — shadows imported helper).
                ranking_user_text: str | None = None
                for msg in reversed(body.get("messages", [])):
                    if msg.get("role") == "user":
                        c = msg.get("content")
                        ranking_user_text = c if isinstance(c, str) else None
                        break
                if ranking_user_text:
                    # Get tool triggers from registry
                    reg = get_registry()
                    tool_triggers: dict[str, tuple[str, ...]] = {}
                    # For now, use empty triggers - will be enhanced in Phase 2
                    tools_for_ranking = _rank_tools_by_user_input(
                        tools_for_ranking,
                        ranking_user_text,
                        tool_triggers,
                    )
            except Exception as e:
                logger.warning(f"Tool ranking failed, using unranked tools: {e}")
        if pinned_specs:
            tools_for_request = pinned_specs + tools_for_ranking
        elif tools_for_ranking is not tools_for_request:
            tools_for_request = tools_for_ranking

        if tools_for_request:
            names = [n for t in tools_for_request if (n := _tool_spec_name(t))]
            logger.info(
                "forwarding %d tools in chat request (llm_model_id=%s, category=%s): %s",
                len(names),
                model,
                routed_category or "full",
                names,
            )
        _log_tools_request_estimate("chat_completions", tools_for_request)
        if not plain_completion and tools_for_request:
            messages = _append_tool_usage_discipline(messages, agent_id=agent_id)
        pause_between_rounds = _coerce_body_bool(body.get("agent_pause_between_rounds"), False)
        if pause_between_rounds and control_queue is None:
            pause_between_rounds = False

        options = {
            k: v
            for k, v in body.items()
            if k not in ("messages", "model", "tools", "stream", *_BODY_KEYS_STRIP_FROM_OLLAMA)
        }

        if (
            stream_requested
            and plain_completion
            and not pause_between_rounds
            and control_queue is None
        ):
            payload_stream_base: dict[str, Any] = {"messages": messages, **options}

            async def _sse_stream() -> AsyncIterator[bytes]:
                async for chunk in _async_iter_chat_completion_sse(
                    attempts,
                    payload_stream_base,
                    llm_backend=llm_backend,
                    profile_key=profile_key,
                ):
                    yield chunk

            return _sse_stream()

        def merge_add_tools_from_message(names: list[Any]) -> None:
            existing = {
                x for x in (_tool_spec_name(s) for s in tools_for_request) if x
            }
            for raw in names:
                nn = str(raw).strip()
                if not nn or nn in existing:
                    continue
                if nn in config.AGENT_TOOLS_DENYLIST:
                    continue
                sp = _registry_tool_spec_by_registered_name(nn)
                if not sp:
                    continue
                slim = _tools_for_chat_request([sp], full_schema=tools_full_schema)
                if slim:
                    tools_for_request.append(slim[0])
                    existing.add(nn)

        def handle_control_dict(m: dict[str, Any]) -> bool:
            """Apply cancel/add_tools. Returns True if cancel was requested."""
            t = m.get("type")
            if t == "cancel" and cancel_event is not None:
                cancel_event.set()
                return True
            if t == "add_tools":
                raw_names = m.get("names")
                nlist = raw_names if isinstance(raw_names, list) else []
                merge_add_tools_from_message(nlist)
            return False

        async def drain_control_queue() -> None:
            if control_queue is None:
                return
            while True:
                try:
                    m = control_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if not isinstance(m, dict):
                    continue
                if m.get("type") == "continue_step":
                    logger.debug("discarding stray continue_step (not in agent.step_wait)")
                    continue
                if m.get("type") == "permission_reply":
                    logger.debug("discarding stray permission_reply (not waiting for permission)")
                    continue
                handle_control_dict(m)

        async def wait_for_continue_step_after_round(completed_round: int) -> None:
            if control_queue is None:
                return
            if event_emit:
                await event_emit(
                    {
                        "type": "agent.step_wait",
                        "agent_run_id": agent_run_id,
                        "after_round": completed_round,
                        "next_round": completed_round + 1,
                        "max_rounds": max_tool_rounds_eff,
                        "detail": (
                            "Send a frame {\"type\":\"continue_step\"} to start the next LLM round. "
                            "You may send {\"type\":\"add_tools\",\"names\":[\"...\"]} before that."
                        ),
                    }
                )
            while True:
                m = await control_queue.get()
                if not isinstance(m, dict):
                    continue
                if m.get("type") == "permission_reply":
                    logger.debug("discarding permission_reply during step_wait")
                    continue
                if m.get("type") == "continue_step":
                    await drain_control_queue()
                    if cancel_event is not None and cancel_event.is_set():
                        if event_emit:
                            await event_emit(
                                {
                                    "type": "agent.cancelled",
                                    "agent_run_id": agent_run_id,
                                    "phase": "step_wait",
                                    "round": completed_round + 1,
                                }
                            )
                        raise AgentChatCancelled()
                    return
                if handle_control_dict(m):
                    if event_emit:
                        await event_emit(
                            {
                                "type": "agent.cancelled",
                                "agent_run_id": agent_run_id,
                                "phase": "step_wait",
                                "round": completed_round + 1,
                            }
                        )
                    raise AgentChatCancelled()

        forwarded_preview = [n for t in tools_for_request if (n := _tool_spec_name(t)) is not None]
        if event_emit:
            await event_emit(
                {
                    "type": "agent.session",
                    "agent_run_id": agent_run_id,
                    "routed_category": routed_category,
                    "router_categories": sorted(cats),
                    "forwarded_tools": forwarded_preview,
                    "effective_model": model,
                    "model_resolution": model_reason,
                    "llm_backend": llm_backend,
                    "smart_route_reason": smart_route_reason or None,
                    "effective_agent_id": agent_id,
                    "workspace_id": str(workspace["id"])
                    if workspace and workspace.get("id")
                    else None,
                    "workspace_auto_created": workspace_auto_created,
                    "agent_auto_routed": agent_auto_routed,
                }
            )

        chosen: tuple[str, dict[str, str], str] | None = None
        thrash_key: str | None = None
        thrash_count = 0
        doom_key: str | None = None
        doom_count = 0
        force_no_tools_round = False
        force_no_tools_reason: str | None = None  # "thrash" | "doom"
        if not plain_completion and tools_for_request:
            messages.append(
                {
                    "role": "system",
                    "content": _agent_tool_budget_system_message(max_tool_rounds_eff),
                }
            )
        for round_i in range(max_tool_rounds_eff):
            await drain_control_queue()
            if cancel_event is not None and cancel_event.is_set():
                if event_emit:
                    await event_emit(
                        {
                            "type": "agent.cancelled",
                            "agent_run_id": agent_run_id,
                            "phase": "before_llm",
                            "round": round_i + 1,
                        }
                    )
                raise AgentChatCancelled()

            if force_no_tools_round:
                _guard_reason = force_no_tools_reason or "thrash"
                logger.info(
                    "chat tool loop round %d/%d: forwarding 0 tools (reason=loop_guard_%s)",
                    round_i + 1,
                    max_tool_rounds_eff,
                    _guard_reason,
                )
                tools_for_round = []
                if force_no_tools_reason == "doom":
                    messages.append({"role": "system", "content": _AGENT_TOOL_DOOM_FORCE_TEXT})
                else:
                    messages.append({"role": "system", "content": _AGENT_TOOL_THRASH_FORCE_TEXT})
                force_no_tools_round = False
                force_no_tools_reason = None
            else:
                tools_for_round = list(tools_for_request)
                if max_tool_rounds_eff >= 3 and round_i == max_tool_rounds_eff - 2:
                    messages.append(
                        {
                            "role": "system",
                            "content": _agent_near_max_tool_rounds_reminder(
                                round_i + 1, max_tool_rounds_eff
                            ),
                        }
                    )
                if max_tool_rounds_eff >= 2 and round_i == max_tool_rounds_eff - 1:
                    tools_for_round = []
                    recap_blob = _build_client_tool_context_markdown(messages)
                    cap = 10_000
                    if recap_blob.strip():
                        if len(recap_blob) > cap:
                            recap_blob = recap_blob[:cap] + "\n\n…[truncated]"
                        messages.append(
                            {
                                "role": "system",
                                "content": (
                                    "Below is **server-extracted** context for this reply: (1) each LLM tool "
                                    "round — which tools were **requested** and with which (normalized) arguments; "
                                    "(2) each tool **result** payload. Your final answer **must** be consistent "
                                    "with this material (do not invent file paths or outcomes not supported there).\n\n"
                                    + recap_blob
                                ),
                            }
                        )
                    messages.append(
                        {
                            "role": "system",
                            "content": _agent_final_round_text_only_hint(
                                round_i + 1, max_tool_rounds_eff
                            ),
                        }
                    )
                    logger.info(
                        "chat tool loop round %d/%d: forwarding 0 tools (reason=final_round_text_only_policy)",
                        round_i + 1,
                        max_tool_rounds_eff,
                    )
            allowed_names = _names_from_tool_list(tools_for_round)

            if event_emit:
                await event_emit(
                    {
                        "type": "agent.llm_round_start",
                        "agent_run_id": agent_run_id,
                        "round": round_i + 1,
                        "max_rounds": max_tool_rounds_eff,
                        "forwarded_tool_names": [
                            n for t in tools_for_round if (n := _tool_spec_name(t)) is not None
                        ],
                    }
                )

            use_llm_stream = bool(stream_llm_ws and event_emit is not None)
            round_no = round_i + 1

            async def _emit_llm_token_delta(s: str) -> None:
                if not s or event_emit is None:
                    return
                await event_emit(
                    {
                        "type": "agent.llm_delta",
                        "agent_run_id": agent_run_id,
                        "round": round_no,
                        "delta": s,
                    }
                )

            payload_base: dict[str, Any] = {
                "messages": messages,
                "stream": False,
                **options,
            }
            if use_llm_stream:
                so = payload_base.get("stream_options")
                if not isinstance(so, dict):
                    payload_base["stream_options"] = {"include_usage": True}
                elif so.get("include_usage") is not True:
                    payload_base["stream_options"] = {**so, "include_usage": True}
            if tools_for_round:
                payload_base["tools"] = tools_for_round

            last_failover: httpx.HTTPStatusError | None = None
            last_transport_error: httpx.RequestError | None = None
            chosen: tuple[str, dict[str, str], str] | None = None
            data: dict[str, Any] = {}
            tools_omitted = False
            while True:
                last_failover = None
                last_transport_error = None
                if use_llm_stream:
                    try:
                        data, tools_omitted, chosen_t = await stream_chat_completions_aggregate(
                            attempts,
                            dict(payload_base),
                            llm_backend=llm_backend,
                            profile_key=profile_key,
                            on_text_delta=_emit_llm_token_delta,
                            cancel_event=cancel_event,
                        )
                    except AgentChatCancelled:
                        raise
                    except httpx.HTTPStatusError:
                        raise
                    except httpx.RequestError:
                        raise
                    chosen = chosen_t
                    model = chosen[2]
                    break
                for b_url, b_headers, b_model in attempts:
                    pl = dict(payload_base)
                    pl["model"] = b_model
                    try:
                        data, tools_omitted = await _thread_with_cancel(
                            cancel_event,
                            http_post_chat_completions,
                            b_url,
                            pl,
                            headers=b_headers,
                            timeout=600.0,
                        )
                        chosen = (b_url, b_headers, b_model)
                        model = b_model
                        break
                    except httpx.RequestError as e:
                        last_transport_error = e
                        logger.warning(
                            "LLM chat/completions transport error (%s) url=%s model=%s: %s",
                            llm_backend,
                            b_url,
                            b_model,
                            e,
                        )
                        continue
                    except httpx.HTTPStatusError as e:
                        last_failover = e
                        sc = e.response.status_code
                        if llm_backend == "external" and external_llm_should_failover(sc):
                            logger.warning(
                                "LLM external attempt failed (status=%s); trying next endpoint",
                                sc,
                            )
                            continue
                        err_body = _redact_provider_error_text_for_log(
                            e.response.text, max_len=600
                        )
                        logger.error(
                            "LLM chat/completions failed (%s): status=%s llm_model_id=%s body=%s",
                            llm_backend,
                            sc,
                            b_model,
                            err_body,
                        )
                        raise
                else:
                    if last_failover is not None:
                        err_body = _redact_provider_error_text_for_log(
                            last_failover.response.text, max_len=600
                        )
                        if (
                            llm_backend == "external"
                            and last_failover.response.status_code == 429
                        ):
                            local_model = ollama_model_for_profile(profile_key)
                            attempts, llm_backend = llm_chat_transport(
                                local_model,
                                profile_key,
                                False,
                                backend_override="ollama",
                                catalog_owned_by=None,
                            )
                            model = local_model
                            logger.warning(
                                "LLM external: all endpoints returned 429 (quota/rate limit); "
                                "falling back to Ollama for this request (llm_model_id=%s). Next rounds use Ollama.",
                                local_model,
                            )
                            continue
                        logger.error(
                            "LLM external: all endpoints failed, last status=%s body=%s",
                            last_failover.response.status_code,
                            err_body,
                        )
                        raise last_failover
                    if last_transport_error is not None:
                        raise last_transport_error
                    raise RuntimeError("LLM: no chat/completions attempts")
                break

            if chosen is None:
                raise RuntimeError("LLM: internal error: no completion chosen after HTTP success")

            if tools_omitted:
                tools_for_round = []
                allowed_names = set()
                logger.warning(
                    "chat tool loop round %d/%d: provider returned tools_omitted=True — treating this completion "
                    "as text-only (no tools[] forwarded to model for this response)",
                    round_i + 1,
                    max_tool_rounds_eff,
                )

            apply_repetition_guard_to_completion(data)

            choice0, msg, tool_calls, had_native_tool_calls = (
                _extract_tool_calls_from_completion_response(
                    data,
                    allowed_tool_names=allowed_names,
                )
            )

            # Some models return only assistant text (TEXT_NO_TOOLS) even when tools[] is present.
            # OpenAI-compatible: retry once with tool_choice=required so the backend emits tool_calls.
            # Only on the first planner round: later rounds may legitimately return final text; forcing
            # tool_choice here would pick a random tool (e.g. register_secrets) and thrash the chat.
            if (
                round_i == 0
                and not tool_calls
                and tools_for_round
                and not plain_completion
                and not tools_omitted
                and config.AGENT_TOOL_CHOICE_REQUIRED_RETRY
            ):
                payload_retry = dict(payload_base)
                payload_retry["model"] = chosen[2]
                payload_retry["tool_choice"] = "required"
                try:
                    if use_llm_stream:
                        data_r, tools_omitted_r, chosen_r = await stream_chat_completions_aggregate(
                            attempts,
                            dict(payload_retry),
                            llm_backend=llm_backend,
                            profile_key=profile_key,
                            on_text_delta=_emit_llm_token_delta,
                            cancel_event=cancel_event,
                        )
                        chosen = chosen_r
                        model = chosen[2]
                    else:
                        data_r, tools_omitted_r = await _thread_with_cancel(
                            cancel_event,
                            http_post_chat_completions,
                            chosen[0],
                            payload_retry,
                            headers=chosen[1],
                            timeout=600.0,
                        )
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (400, 422):
                        logger.warning(
                            "Ollama rejected tool_choice=required (status=%s); keeping first completion. body~=%s",
                            e.response.status_code,
                            _redact_provider_error_text_for_log(e.response.text, max_len=320),
                        )
                    else:
                        err_body = _redact_provider_error_text_for_log(
                            e.response.text, max_len=600
                        )
                        logger.error(
                            "LLM chat/completions retry failed (%s): status=%s llm_model_id=%s body=%s",
                            llm_backend,
                            e.response.status_code,
                            model,
                            err_body,
                        )
                        raise
                else:
                    if not tools_omitted_r:
                        c0, m2, tc2, hn2 = _extract_tool_calls_from_completion_response(
                            data_r,
                            allowed_tool_names=allowed_names,
                        )
                        if tc2:
                            logger.info(
                                "agent: tool_choice=required retry produced tool_calls (llm_model_id=%s)",
                                model,
                            )
                            apply_repetition_guard_to_completion(data_r)
                            data, tools_omitted = data_r, tools_omitted_r
                            choice0, msg, tool_calls, had_native_tool_calls = (
                                c0,
                                m2,
                                tc2,
                                hn2,
                            )
                    else:
                        logger.warning(
                            "agent: tool_choice=required retry omitted tools (llm_model_id=%s); keeping first completion",
                            model,
                        )

            if not tools_for_round and tool_calls:
                n_disc = len(tool_calls) if isinstance(tool_calls, list) else 0
                logger.warning(
                    "chat tool loop round %d/%d: discarding %d tool_call(s) (no tools[] this round)",
                    round_i + 1,
                    max_tool_rounds_eff,
                    n_disc,
                )
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "This round did not include tool definitions in the API request. Any `tool_calls` "
                            "you produced are **discarded**. Reply with **plain text only**: merge findings from "
                            "earlier tool messages, note errors briefly, and state next steps."
                        ),
                    }
                )
                msg = dict(msg)
                msg.pop("tool_calls", None)
                choice0["message"] = msg
                ch_list = data.get("choices")
                if isinstance(ch_list, list) and ch_list and isinstance(ch_list[0], dict):
                    ch_list[0]["message"] = msg
                tool_calls = None
                had_native_tool_calls = False

            _log_llm_completion_round(
                round_i=round_i,
                max_rounds_cap=max_tool_rounds_eff,
                model=model,
                messages=messages,
                tools_for_round=tools_for_round,
                msg=msg,
                choice0=choice0 if isinstance(choice0, dict) else {},
                tool_calls=tool_calls if isinstance(tool_calls, list) else None,
                had_native_tool_calls=had_native_tool_calls,
            )

            if event_emit:
                tc_names = [
                    (tc.get("function") or {}).get("name")
                    for tc in (tool_calls or [])
                    if isinstance(tc, dict)
                ]
                usage_raw = data.get("usage") if isinstance(data, dict) else None
                usage_out = usage_raw if isinstance(usage_raw, dict) else None
                await event_emit(
                    {
                        "type": "agent.llm_round",
                        "agent_run_id": agent_run_id,
                        "round": round_i + 1,
                        "tool_calls": [str(x) for x in tc_names if x],
                        "had_native_tool_calls": had_native_tool_calls,
                        "content_excerpt": (
                            (msg.get("content") or "")[:400]
                            if isinstance(msg.get("content"), str)
                            else ""
                        ),
                        **({"usage": usage_out} if usage_out is not None else {}),
                    }
                )

            if not tool_calls:
                need_verify = bool(
                    workspace
                    and isinstance(workspace, dict)
                    and (
                        bool(workspace.get("verify_required")) or agent_require_workspace_verify
                    )
                )
                if need_verify:
                    vcmd = workspace.get("verify_command") if isinstance(workspace, dict) else None
                    has_cmd = isinstance(vcmd, str) and vcmd.strip()
                    if bool(workspace.get("verify_required")) and not has_cmd:
                        raise ValueError(
                            "Workspace has verify_required=true but no verify_command; "
                            "set verify_command via PATCH /v1/workspaces/{id}."
                        )
                    if agent_require_workspace_verify and not has_cmd:
                        raise ValueError(
                            "agent_require_workspace_verify was set but this workspace has no verify_command configured."
                        )
                    if not tool_context.get("workspace_verify_succeeded"):
                        raise ValueError(
                            "Workspace verify gate: run coding_workspace_verify successfully (exit 0) before "
                            "finishing, or disable verify_required / agent_require_workspace_verify."
                        )
                if _sanitize_final_completion_assistant_content(data):
                    logger.info(
                        "agent: stripped fake tool markup from final chat.completion (round %s/%s)",
                        round_i + 1,
                        max_tool_rounds_eff,
                    )
                if event_emit:
                    await event_emit(
                        {
                            "type": "agent.done",
                            "agent_run_id": agent_run_id,
                            "kind": "final_text",
                            "round": round_i + 1,
                        }
                    )
                return _completion_attach_agent_run_id(data, agent_run_id)

            # Append assistant message (includes tool_calls, and content if any)
            messages.append(msg)

            batch_recap: list[str] = []
            verify_recap_line: str | None = None
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                raw_args = fn.get("arguments")
                if (
                    raw_args in (None, "", "{}")
                    or (isinstance(raw_args, dict) and not raw_args)
                ) and tc.get("arguments") not in (None, ""):
                    raw_args = tc.get("arguments")
                args = _parse_tool_arguments(raw_args)
                _prev_args = dict(args)
                args = _normalize_tool_call_arguments(name, args, msg, messages, tool_context)
                if args != _prev_args:
                    logger.info(
                        "tool args normalized round=%s tool=%s %r -> %r",
                        round_i + 1,
                        name,
                        _prev_args,
                        args,
                    )
                tool_call_id = tc.get("id") or ""
                logger.info("tool round %s: %s(%s)", round_i + 1, name, args)
                if cancel_event is not None and cancel_event.is_set():
                    if event_emit:
                        await event_emit(
                            {
                                "type": "agent.cancelled",
                                "agent_run_id": agent_run_id,
                                "phase": "before_tool",
                                "round": round_i + 1,
                                "name": name,
                            }
                        )
                    raise AgentChatCancelled()
                if event_emit:
                    await event_emit(
                        {
                            "type": "agent.tool_start",
                            "agent_run_id": agent_run_id,
                            "round": round_i + 1,
                            "name": name,
                        }
                    )
                tctx = set_tool_invocation_messages(list(messages))
                try:
                    perm_always = tool_context.get("permission_always_allow_tools")
                    if not isinstance(perm_always, set):
                        perm_always = set()
                        tool_context["permission_always_allow_tools"] = perm_always
                    need_gate = (
                        permission_ask
                        and not bool(tool_context.get("agent_unattended"))
                        and bool(tool_context.get("agent_coding_tools_permission_ask"))
                        and name in _CODING_TOOLS_PERMISSION_ASK
                        and name not in perm_always
                    )
                    if need_gate and control_queue is None:
                        logger.warning(
                            "agent_permission_ask set but no control_queue; executing %s without approval",
                            name,
                        )
                    if need_gate and control_queue is not None:
                        preview = json.dumps(args, ensure_ascii=False, default=str)[:2000]
                        rid = str(uuid.uuid4())
                        rep, fb_msg = await _wait_for_tool_permission_reply(
                            control_queue=control_queue,
                            cancel_event=cancel_event,
                            event_emit=event_emit,
                            agent_run_id=agent_run_id,
                            request_id=rid,
                            tool_name=name,
                            args_preview=preview,
                            round_i=round_i,
                            handle_control=handle_control_dict,
                        )
                        if rep == "reject":
                            rej: dict[str, Any] = {
                                "ok": False,
                                "error": "User rejected permission for this tool call.",
                            }
                            if fb_msg:
                                rej["user_message"] = fb_msg
                            result = json.dumps(rej, ensure_ascii=False)
                        else:
                            if rep == "always":
                                perm_always.add(name)
                            blocked = _unattended_blocked_tool_json(name, args, tool_context)
                            result = (
                                blocked
                                if blocked is not None
                                else await _thread_with_cancel(
                                    cancel_event,
                                    execute_tool,
                                    name,
                                    args,
                                    context=tool_context,
                                )
                            )
                    else:
                        blocked = _unattended_blocked_tool_json(name, args, tool_context)
                        result = (
                            blocked
                            if blocked is not None
                            else await _thread_with_cancel(
                                cancel_event,
                                execute_tool,
                                name,
                                args,
                                context=tool_context,
                            )
                        )
                finally:
                    reset_tool_invocation_messages(tctx)
                ok_sum, err_sum = _tool_result_summary(result)
                git_hint = _unattended_mark_git_pull_done(name, result or "", tool_context)
                if git_hint:
                    messages.append({"role": "system", "content": git_hint[:2500]})
                record_schedule_tool_event(
                    round_num=round_i + 1,
                    tool_name=name,
                    args=args,
                    ok=ok_sum,
                    error=err_sum if not ok_sum else None,
                )
                if name == "coding_workspace_verify":
                    try:
                        _vd = json.loads(result)
                        if isinstance(_vd, dict) and _vd.get("ok") is True:
                            tool_context["workspace_verify_succeeded"] = True
                    except Exception:
                        pass
                    vr = _format_workspace_verify_recap(result)
                    if vr:
                        verify_recap_line = vr
                if event_emit:
                    await _apply_workspace_tool_bind_side_effects(
                        tool_name=name,
                        result=result or "",
                        tool_context=tool_context,
                        messages=messages,
                        event_emit=event_emit,
                        agent_run_id=agent_run_id,
                    )
                if config.AGENT_TOOL_THRASH_ENABLED:
                    nk, nc, thr_hint, force_next = _agent_tool_thrash_tick(
                        thrash_key,
                        thrash_count,
                        tool_name=name,
                        ok_r=ok_sum,
                        err_r=err_sum,
                        max_streak=config.AGENT_TOOL_THRASH_STREAK_MAX,
                    )
                    thrash_key, thrash_count = nk, nc
                    if thr_hint:
                        messages.append({"role": "system", "content": thr_hint})
                    if force_next:
                        force_no_tools_round = True
                        force_no_tools_reason = "thrash"
                        logger.info(
                            "tool loop guard: thrash streak reached for tool=%r — next LLM round will omit tools[]",
                            name,
                        )
                if config.AGENT_TOOL_DOOM_LOOP_ENABLED:
                    dk, dc, doom_hint = _agent_tool_doom_loop_tick(
                        doom_key,
                        doom_count,
                        tool_name=name,
                        args=args,
                        max_streak=config.AGENT_TOOL_DOOM_LOOP_STREAK_MAX,
                        exclude_names=config.AGENT_TOOL_DOOM_LOOP_EXCLUDE,
                    )
                    doom_key, doom_count = dk, dc
                    if doom_hint:
                        messages.append({"role": "system", "content": doom_hint})
                        force_no_tools_round = True
                        force_no_tools_reason = "doom"
                        try:
                            _args_preview = json.dumps(dict(args), sort_keys=True, separators=(",", ":"), default=str)
                        except TypeError:
                            _args_preview = str(args)
                        if len(_args_preview) > 400:
                            _args_preview = _args_preview[:400] + "…"
                        logger.info(
                            "tool loop guard: doom-loop streak reached (tool=%r args=%s max_streak=%d) — "
                            "next LLM round will omit tools[]",
                            name,
                            _args_preview,
                            config.AGENT_TOOL_DOOM_LOOP_STREAK_MAX,
                        )
                        if tool_context.get("agent_unattended"):
                            record_schedule_abort("repeated_tool_loop")
                if event_emit:
                    ev_done: dict[str, Any] = {
                        "type": "agent.tool_done",
                        "agent_run_id": agent_run_id,
                        "round": round_i + 1,
                        "name": name,
                        "result_chars": len(result or ""),
                    }
                    if ok_sum is not None:
                        ev_done["result_ok"] = ok_sum
                    if err_sum:
                        ev_done["result_error"] = err_sum[:500]
                    await event_emit(ev_done)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result,
                    }
                )
                recovery = _http_error_recovery_hint(name, result)
                if recovery:
                    messages.append({"role": "system", "content": recovery})
                param_recovery = _tool_parameter_recovery_hint(name, result or "")
                if param_recovery:
                    messages.append({"role": "system", "content": param_recovery})
                st = "ok" if ok_sum is True else ("err" if ok_sum is False else "?")
                batch_recap.append(f"{name}:{st}")

            if config.AGENT_SESSION_TOOL_RECAP_ENABLED and batch_recap:
                cap = config.AGENT_SESSION_TOOL_RECAP_MAX
                parts = batch_recap[:cap]
                tail = f" (+{len(batch_recap) - cap} more)" if len(batch_recap) > cap else ""
                recap_line = "[Session tool recap] " + ", ".join(parts) + tail
                messages.append({"role": "system", "content": recap_line[:900]})

            if verify_recap_line:
                messages.append({"role": "system", "content": verify_recap_line[:2500]})

            if (
                pause_between_rounds
                and control_queue is not None
                and round_i + 1 < max_tool_rounds_eff
            ):
                await wait_for_continue_step_after_round(round_i + 1)

        logger.warning(
            "max tool rounds (%s) exceeded ctx_msgs=%d ctx_text_chars~=%d",
            max_tool_rounds_eff,
            len(messages),
            _approx_text_chars_in_messages(messages),
        )
        if event_emit:
            await event_emit(
                {
                    "type": "agent.done",
                    "agent_run_id": agent_run_id,
                    "kind": "max_tool_rounds",
                    "round": max_tool_rounds_eff,
                }
            )
        return _completion_attach_agent_run_id(data, agent_run_id)
    finally:
        reset_capability_confirmed(_cap_cf_tok)
        from apps.backend.domain.identity import reset_workspace
        if workspace_token:
            reset_workspace(workspace_token)
