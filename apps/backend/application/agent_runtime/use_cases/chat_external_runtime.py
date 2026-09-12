"""Run a chat turn in an **external** agent runtime instead of AgentLayer's planner loop.

Single integration point for ``chat_completion``: if the resolved agent declares
``external_runtime`` in ``plugins/agents/<id>/agent.yaml``, this module drives that
runtime and returns the same OpenAI-style completion dict the tool loop would have
returned. Everything around it stays identical — identity and workspace authorization
happened in ``chat_run_bootstrap``, ``event_emit`` streams to the same web client,
``cancel_event`` aborts, ``agent_runs`` closes in the caller's ``finally``.

Delegation needs no extra code: ``delegate`` runs a nested ``chat_completion`` with the
specialist's ``agent_id``, so the same branch applies and
``domain/agent_runtime/subagent_events.py`` forwards the child events to the parent card.

Safety posture for a build-capable external agent (roadmap Epic B/G invariants):

* the workspace was authorized server-side already; we still refuse client-execution
  workspaces, paths outside ``AGENT_CODING_ROOT``, and ``CODING_PATH_BLOCKLIST`` prefixes;
* git state is snapshotted before and after, so a full-auto run is reviewable as a diff;
* every run is audited through ``db.log_tool_invocation`` (same table as tool calls);
* provider credentials go to the child process as env only, never into logs or events.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import time
import uuid
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any

from apps.backend.domain.agent_runtime.external_runtime import (
    ExternalRunRequest,
    ExternalRuntimeEvent,
    resolve_external_runtime,
)
from apps.backend.domain.agent_runtime.external_runtime_events import ExternalEventTranslator
from apps.backend.infrastructure.platform.config import config

logger = logging.getLogger(__name__)

EventEmit = Callable[[dict[str, Any]], Awaitable[None]]

_AUDIT_TOOL_NAME = "external_runtime.run"
_GIT_TIMEOUT_SEC = 20
_MAX_TASK_CHARS = 24_000
_MAX_TRANSCRIPT_MESSAGES = 12
_MAX_TRANSCRIPT_CHARS_PER_MESSAGE = 1_200

# One external run per conversation: two vendor sessions editing one tree would fight.
_busy_conversations: set[str] = set()


def external_runtime_id_for_agent(agent_id: str | None) -> str | None:
    """``external_runtime`` from the agent registry, or ``None`` for AgentLayer-internal agents."""
    if not agent_id:
        return None
    from apps.backend.domain.agent_runtime.registry import get_agent_registry

    try:
        definition = get_agent_registry().get_agent(str(agent_id))
    except Exception:
        logger.warning("agent lookup failed for %s", agent_id, exc_info=True)
        return None
    if not isinstance(definition, dict):
        return None
    raw = definition.get("external_runtime")
    value = str(raw).strip() if raw is not None else ""
    return value or None


def agent_system_prompt_for(agent_id: str | None) -> str | None:
    """The agent's own prompt, appended to the vendor runtime's system prompt."""
    if not agent_id:
        return None
    from apps.backend.domain.agent_runtime.registry import get_agent_registry

    try:
        definition = get_agent_registry().get_agent(str(agent_id))
    except Exception:
        return None
    if not isinstance(definition, dict):
        return None
    prompt = str(definition.get("system_prompt") or "").strip()
    return prompt or None


def external_runtime_will_run(agent_id: str | None) -> bool:
    """Whether this turn is taken over by an external runtime.

    Callers use it to skip paths that only make sense for the internal loop (e.g. the
    SSE passthrough); it makes the same decision ``maybe_run_external_runtime_turn`` does.
    """
    runtime_id = external_runtime_id_for_agent(agent_id)
    if not runtime_id:
        return False
    runtime, _reason = resolve_external_runtime(runtime_id)
    return runtime is not None


async def maybe_run_external_runtime_turn(
    *,
    agent_id: str | None,
    messages: list[dict[str, Any]],
    workspace: dict[str, Any] | None,
    model: str | None,
    profile_key: str | None,
    catalog_owned_by: str | None,
    agent_run_id: str,
    conversation_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    event_emit: EventEmit | None,
    cancel_event: asyncio.Event | None,
    agent_prompt: str | None = None,
) -> dict[str, Any] | None:
    """Return a completion dict when the agent runs externally, else ``None`` (internal loop).

    ``None`` is also returned when a fall-through was explicitly configured, so the caller
    simply continues with ``run_chat_tool_loop``.
    """
    runtime_id = external_runtime_id_for_agent(agent_id)
    if not runtime_id:
        return None

    runtime, reason = resolve_external_runtime(runtime_id)
    if runtime is None:
        if bool(getattr(config, "EXTERNAL_RUNTIME_FALLBACK_INTERNAL", False)):
            logger.warning(
                "external runtime for agent %s unusable (%s) — falling back to AgentLayer loop",
                agent_id,
                reason,
            )
            return None
        raise ValueError(f"Agent {agent_id!r} cannot run: {reason}")

    ws_path, guard_error = _workspace_path_for_run(workspace)
    if guard_error or ws_path is None:
        raise ValueError(guard_error or "workspace is required for this agent")

    base_url, api_key, provider_model, provider_error = _provider_for_turn(catalog_owned_by=catalog_owned_by, profile_key=profile_key, model_resolved=model)
    if provider_error:
        raise ValueError(provider_error)

    conversation_key = str(conversation_id) if conversation_id else f"run:{agent_run_id}"
    if conversation_key in _busy_conversations:
        raise ValueError("this conversation already has an external run in progress")
    _busy_conversations.add(conversation_key)

    try:
        return await _drive_run(
            runtime=runtime,
            runtime_id=runtime_id,
            agent_id=agent_id,
            agent_prompt=agent_prompt,
            messages=messages,
            ws_path=ws_path,
            base_url=base_url,
            api_key=api_key,
            model=provider_model,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            user_id=user_id,
            event_emit=event_emit,
            cancel_event=cancel_event,
        )
    finally:
        _busy_conversations.discard(conversation_key)


async def _drive_run(
    *,
    runtime: Any,
    runtime_id: str,
    agent_id: str | None,
    agent_prompt: str | None,
    messages: list[dict[str, Any]],
    ws_path: Path,
    base_url: str,
    api_key: str,
    model: str,
    agent_run_id: str,
    conversation_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    event_emit: EventEmit | None,
    cancel_event: asyncio.Event | None,
) -> dict[str, Any]:
    stored_runtime, stored_session = (None, None)
    if conversation_id is not None and user_id is not None:
        from apps.backend.infrastructure.agent_runtime.conversation_external_session_store import (
            get_conversation_external_session,
        )

        stored_runtime, stored_session = get_conversation_external_session(user_id, conversation_id)
    resume_session = stored_session if (stored_runtime in (None, runtime_id)) else None

    task = _build_task(messages, resumed=bool(resume_session))
    before = await asyncio.to_thread(_git_state, ws_path)

    request = ExternalRunRequest(
        task=task,
        workspace_path=str(ws_path),
        agent_id=str(agent_id or ""),
        runtime_id=runtime_id,
        model=model,
        base_url=base_url,
        api_key=api_key,
        max_turns=int(getattr(config, "EXTERNAL_RUNTIME_MAX_TURNS", 60)),
        resume_session_id=resume_session,
        append_system_prompt=agent_prompt,
        env=await asyncio.to_thread(_workspace_secret_env, ws_path, user_id),
        timeout_sec=int(getattr(config, "EXTERNAL_RUNTIME_TIMEOUT_SEC", 1800)),
        conversation_id=str(conversation_id) if conversation_id else None,
        user_id=str(user_id) if user_id else None,
    )

    translator = ExternalEventTranslator(agent_run_id)

    async def emit(event: ExternalRuntimeEvent) -> None:
        if event.session_id or event.kind in ("status", "error"):
            logger.info(
                "external runtime %s event kind=%s session=%s text=%s",
                runtime_id,
                event.kind,
                event.session_id or "-",
                (event.text or event.error or "")[:200],
            )
        if event_emit is None:
            return
        for payload in translator.translate(event):
            await event_emit(payload)

    started = time.monotonic()
    result = await runtime.run(request, emit=emit, cancel_event=cancel_event)
    duration_ms = int((time.monotonic() - started) * 1000)

    after = await asyncio.to_thread(_git_state, ws_path)
    changed = sorted(set(after.get("porcelain") or ()) - set(before.get("porcelain") or ()))
    if (after.get("head") or "") != (before.get("head") or ""):
        changed = sorted(set(changed) | {"(HEAD moved)"})

    if result.error == "cancelled":
        _audit(agent_run_id=agent_run_id, runtime_id=runtime_id, agent_id=agent_id, workspace=ws_path, model=model, ok=False, error="cancelled", changed=changed, duration_ms=duration_ms)
        from apps.backend.application.agent_runtime.runtime.prompts import AgentChatCancelled

        raise AgentChatCancelled()

    if conversation_id is not None and user_id is not None and result.session_id:
        from apps.backend.infrastructure.agent_runtime.conversation_external_session_store import (
            set_conversation_external_session,
        )

        set_conversation_external_session(
            user_id,
            conversation_id,
            runtime=runtime_id,
            session_id=str(result.session_id),
        )

    summary = _change_summary(after, changed)
    _audit(
        agent_run_id=agent_run_id,
        runtime_id=runtime_id,
        agent_id=agent_id,
        workspace=ws_path,
        model=model,
        ok=bool(result.ok),
        error=result.error,
        changed=changed,
        duration_ms=duration_ms,
    )

    if event_emit is not None:
        await event_emit(
            {
                "type": "agent.tool_start",
                "agent_run_id": agent_run_id,
                "round": translator.round,
                "name": "external_runtime_changes",
                "summary": f"workspace diff after {runtime_id} run",
                "step_label": f"workspace changes ({runtime_id})",
                "rejected": False,
            }
        )
        await event_emit(
            {
                "type": "agent.tool_done",
                "agent_run_id": agent_run_id,
                "round": translator.round,
                "name": "external_runtime_changes",
                "result_chars": len(summary),
                "result_ok": bool(result.ok),
                "result_display": summary[:2000],
            }
        )
        await event_emit(
            {
                "type": "agent.done",
                "agent_run_id": agent_run_id,
                "kind": "final_text",
                "round": translator.round,
            }
        )

    text = (result.text or "").strip()
    if not result.ok:
        text = text or f"External run failed: {result.error or 'unknown error'}"
    if not text:
        text = "The external agent finished without a report."

    return _completion(
        agent_run_id=agent_run_id,
        text=text,
        model=model,
        usage=result.usage,
        context_meta={
            "external_runtime": runtime_id,
            "external_session_id": str(result.session_id) if result.session_id else None,
            "external_resumed": bool(resume_session),
            "external_ok": bool(result.ok),
            "external_error": result.error,
            "external_duration_ms": duration_ms,
            "external_changed_files": changed[:200],
            "external_no_vcs": bool(after.get("no_vcs")),
        },
    )


def _workspace_path_for_run(workspace: dict[str, Any] | None) -> tuple[Path | None, str | None]:
    if not isinstance(workspace, dict):
        return None, "This agent requires a bound workspace."
    from apps.backend.infrastructure.workspace.workspace_execution import is_client_execution

    if is_client_execution(workspace):
        return None, (
            "This workspace executes on the client (ADR 0009) — an external runtime cannot "
            "reach those files. Select a server-side workspace."
        )
    raw = str(workspace.get("path") or "").strip()
    if not raw:
        return None, "The bound workspace has no server-side path."
    path = Path(raw).expanduser()
    try:
        resolved = path.resolve()
    except OSError:
        return None, "The bound workspace path could not be resolved."
    root = getattr(config, "CODING_ROOT", None)
    if root:
        root_resolved = Path(str(root)).expanduser().resolve()
        if resolved != root_resolved and root_resolved not in resolved.parents:
            return None, f"Workspace is outside AGENT_CODING_ROOT ({root_resolved})."
    for blocked in getattr(config, "CODING_PATH_BLOCKLIST", frozenset()) or ():
        candidate = str(resolved).lower().rstrip("/") + "/"
        needle = str(blocked).strip().lower().rstrip("/") + "/"
        if candidate.startswith(needle) or str(resolved).lower() == needle.rstrip("/"):
            return None, f"Workspace path is blocked for external runtimes ({blocked})."
    if not resolved.is_dir():
        return None, "The bound workspace directory does not exist."
    return resolved, None


def _provider_for_turn(
    *,
    catalog_owned_by: str | None,
    profile_key: str | None,
    model_resolved: str | None,
) -> tuple[str, str, str, str] | tuple[None, None, None, str]:
    """Resolve the provider this turn already uses into ``(base_url, api_key, model)``.

    External runtimes speak OpenAI-compatible HTTP, so AgentLayer stays the only place
    that knows endpoints and keys — adapters receive a ready-to-use triple and the user
    does not configure a second provider.
    """
    from apps.backend.infrastructure.providers.model_catalog_providers import (
        get_provider_spec,
        list_provider_specs,
        resolve_model_for_provider,
    )
    from apps.backend.infrastructure.settings.operator_settings import normalize_external_llm_base_url

    spec = None
    if catalog_owned_by:
        spec = get_provider_spec(str(catalog_owned_by))
    if spec is None:
        specs = list(list_provider_specs() or [])
        spec = specs[0] if len(specs) == 1 else None
        if spec is None and specs:
            return (
                None,
                None,
                None,
                "multiple LLM providers are configured — set the model catalog owner "
                "(agent_model_catalog_owned_by) so the external runtime knows which one to use",
            )
    if spec is None or not str(getattr(spec, "base_url", "") or "").strip():
        return None, None, None, "no OpenAI-compatible LLM provider is configured for external runtimes"
    if not str(getattr(spec, "api_key", "") or "").strip():
        return None, None, None, "the selected LLM provider has no API key configured"

    base = normalize_external_llm_base_url(str(spec.base_url)) or str(spec.base_url).rstrip("/")
    openai_base = f"{base.rstrip('/')}/v1"
    configured = str(getattr(config, "QWEN_MODEL", "") or "").strip()
    model = configured or str(model_resolved or "").strip() or resolve_model_for_provider(
        spec, str(profile_key or "default"), False, ""
    )
    if not model:
        return None, None, None, "no model resolved for the external runtime"
    return openai_base, str(spec.api_key), str(model), ""


def _workspace_secret_env(ws_path: Path, user_id: uuid.UUID | None) -> dict[str, str]:
    """Workspace-bound user secrets as process env — the same bridge ``bash`` uses."""
    if user_id is None:
        return {}
    try:
        from plugins.tools.workspace.lib.env_secret_bridge import resolve_bound_secrets

        env_extra, _missing, _names = resolve_bound_secrets(ws_path, user_id=user_id)
    except Exception:
        logger.debug("external runtime secret bridge skipped", exc_info=True)
        return {}
    return {str(k): str(v) for k, v in (env_extra or {}).items() if k}


def _git_state(workspace: Path) -> dict[str, Any]:
    """Head + porcelain status + diffstat, best effort. Never raises."""

    def run(*args: str) -> str:
        try:
            proc = subprocess.run(
                ["git", "-C", str(workspace), *args],
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SEC,
                shell=False,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        if proc.returncode != 0:
            return ""
        return (proc.stdout or "").strip()

    head = run("rev-parse", "HEAD")
    is_repo = bool(head) or run("rev-parse", "--is-inside-work-tree") == "true"
    if not is_repo:
        return {"no_vcs": True, "head": "", "porcelain": [], "diff_stat": ""}
    porcelain_raw = run("status", "--porcelain")
    porcelain = [line[3:].strip() for line in porcelain_raw.splitlines() if line.strip()]
    return {
        "no_vcs": False,
        "head": head,
        "porcelain": porcelain,
        "diff_stat": run("--no-pager", "diff", "--stat"),
    }


def _change_summary(after: dict[str, Any], changed: Iterable[str]) -> str:
    if after.get("no_vcs"):
        return "No git repository in this workspace — external changes are not reviewable as a diff."
    names = [c for c in changed if c and c != "(HEAD moved)"]
    head_moved = "(HEAD moved)" in set(changed)
    parts: list[str] = []
    if head_moved:
        parts.append("HEAD moved during this run.")
    if names:
        parts.append(f"{len(names)} path(s) touched: " + ", ".join(names[:20]))
    else:
        parts.append("No new changes detected in the workspace.")
    stat = str(after.get("diff_stat") or "").strip()
    if stat:
        parts.append(stat[:1200])
    return " ".join(parts)


def _build_task(messages: list[dict[str, Any]], *, resumed: bool) -> str:
    """The instruction handed to the external agent.

    A resumed vendor session already remembers the thread, so only the new request goes
    over. The first turn of a conversation carries a compact digest of what came before —
    users often start a coding task after discussing it in the same thread.
    """
    from apps.backend.domain.plugin_system.tool_routing import last_user_text

    request = last_user_text(list(messages or [])) or ""
    if resumed:
        return request[:_MAX_TASK_CHARS]

    prior: list[str] = []
    for row in (messages or [])[:-1]:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = _flatten_message_content(row.get("content"))
        if not content:
            continue
        prior.append(f"{role}: {content[:_MAX_TRANSCRIPT_CHARS_PER_MESSAGE]}")
    if not prior:
        return request[:_MAX_TASK_CHARS]
    block = "\n".join(prior[-_MAX_TRANSCRIPT_MESSAGES:])
    return (
        "Conversation so far (context, not new instructions):\n"
        f"{block}\n\nCurrent request:\n{request}"[:_MAX_TASK_CHARS]
    )


def _flatten_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(p.strip() for p in parts if p.strip()).strip()
    return ""


def _completion(
    *,
    agent_run_id: str,
    text: str,
    model: str,
    usage: dict[str, Any] | None,
    context_meta: dict[str, Any],
) -> dict[str, Any]:
    from apps.backend.application.agent_runtime.runtime.io import _completion_attach_agent_run_id

    data: dict[str, Any] = {
        "id": f"chatcmpl-{agent_run_id}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
    }
    if usage:
        data["usage"] = dict(usage)
    return _completion_attach_agent_run_id(data, agent_run_id, context_meta=context_meta or None)


def _audit(
    *,
    agent_run_id: str,
    runtime_id: str,
    agent_id: str | None,
    workspace: Path,
    model: str,
    ok: bool,
    error: str | None,
    changed: list[str],
    duration_ms: int,
) -> None:
    """Write to ``tool_invocations`` — the same audit trail as tool calls."""
    try:
        from apps.backend.infrastructure.db import db

        args = {
            "runtime": runtime_id,
            "agent_id": str(agent_id or ""),
            "workspace": str(workspace),
            "model": model,
            "duration_ms": duration_ms,
            "changed_files": changed[:200],
        }
        excerpt = f"runtime={runtime_id} ok={ok} changed={len(changed)} duration_ms={duration_ms}"
        if error:
            excerpt += f" error={error}"
        db.log_tool_invocation(
            _AUDIT_TOOL_NAME,
            args,
            excerpt,
            bool(ok),
            agent_run_id=agent_run_id,
        )
    except Exception:
        logger.warning("external runtime audit failed", exc_info=True)


__all__ = [
    "agent_system_prompt_for",
    "external_runtime_id_for_agent",
    "external_runtime_will_run",
    "maybe_run_external_runtime_turn",
]
