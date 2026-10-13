"""Qwen Code adapter for the external agent runtime port.

Qwen Code is driven through its Python SDK (``qwen-code-sdk``), which spawns the ``qwen``
CLI per session and streams structured messages. Both the SDK and the binary are
optional: ``available()`` probes them and every failure path returns a result instead of
raising, so an uninstalled vendor changes nothing else in the product.

Provider pass-through: AgentLayer has already resolved ``(base_url, api_key, model)`` for
this turn. Qwen speaks OpenAI-compatible HTTP, so we materialize a private
``$HOME/.qwen/settings.json`` for the child process pointing at that endpoint
(``security.auth.selectedType: "openai"``) and hand the key over as process env only.

The child gets a **curated** environment (``PATH``, ``HOME``, locale, plus this
workspace's bound secrets) — never a copy of the backend environment, which holds the
database DSN and the secrets master key.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import shutil
import stat
from pathlib import Path
from typing import Any

from apps.backend.domain.agent_runtime.external_runtime import (
    PERMISSION_AUTO_EDIT,
    ExternalRunRequest,
    ExternalRunResult,
    ExternalRuntimeEvent,
    EventSink,
    clamp_permission_mode,
)
from apps.backend.infrastructure.platform.config import config

logger = logging.getLogger(__name__)

RUNTIME_ID = "qwen_code"
_SAFE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


class QwenCodeRuntime:
    """Runs one agent turn as a ``qwen`` session inside an AgentLayer workspace."""

    id = RUNTIME_ID
    supports_resume = True
    supports_write = True

    @property
    def default_permission_mode(self) -> str:
        """What ``run`` would actually use, so the catalog never advertises a wider mode."""
        return clamp_permission_mode(
            str(getattr(config, "QWEN_PERMISSION_MODE", PERMISSION_AUTO_EDIT)),
            "yolo" if bool(getattr(config, "EXTERNAL_RUNTIME_ALLOW_YOLO", False)) else PERMISSION_AUTO_EDIT,
        )

    def available(self) -> tuple[bool, str]:
        if not bool(getattr(config, "EXTERNAL_RUNTIME_ENABLED", False)):
            return False, "AGENT_EXTERNAL_RUNTIME_ENABLED is false"
        if not bool(getattr(config, "QWEN_RUNTIME_ENABLED", True)):
            return False, "AGENT_QWEN_ENABLED is false"
        binary = str(getattr(config, "QWEN_BIN", "qwen") or "qwen")
        resolved = binary if os.path.isabs(binary) else (shutil.which(binary) or "")
        if not resolved or not os.path.isfile(resolved):
            return False, f"qwen binary not found ({binary}); install @qwen-code/qwen-code"
        try:
            import qwen_code_sdk  # noqa: F401
        except Exception as exc:
            return False, f"qwen-code-sdk not importable: {exc}"
        return True, ""

    async def run(
        self,
        request: ExternalRunRequest,
        *,
        emit: EventSink,
        cancel_event: asyncio.Event | None = None,
    ) -> ExternalRunResult:
        try:
            from qwen_code_sdk import query  # type: ignore
        except Exception as exc:
            return ExternalRunResult(ok=False, error=f"qwen-code-sdk not importable: {exc}")

        if not request.base_url or not request.api_key:
            return ExternalRunResult(
                ok=False,
                error=(
                    "no OpenAI-compatible provider credentials for this turn — external runtimes "
                    "inherit AgentLayer's provider; configure an endpoint or set AGENT_QWEN_MODEL"
                ),
            )
        if not request.model:
            return ExternalRunResult(ok=False, error="no model resolved for this turn")

        try:
            run_home = _prepare_home(request)
        except OSError as exc:
            return ExternalRunResult(ok=False, error=f"cannot prepare qwen home: {exc}")

        mode = clamp_permission_mode(
            str(getattr(config, "QWEN_PERMISSION_MODE", PERMISSION_AUTO_EDIT)),
            "yolo" if bool(getattr(config, "EXTERNAL_RUNTIME_ALLOW_YOLO", False)) else PERMISSION_AUTO_EDIT,
        )
        options: dict[str, Any] = {
            "cwd": request.workspace_path,
            "path_to_qwen_executable": _binary_path(),
            "permission_mode": mode,
            "env": _child_env(request, run_home=run_home, api_key=str(request.api_key)),
        }
        options["model"] = str(request.model)
        if request.max_turns:
            options["max_session_turns"] = int(request.max_turns)
        if request.resume_session_id:
            options["resume"] = str(request.resume_session_id)
        if request.append_system_prompt:
            options["append_system_prompt"] = str(request.append_system_prompt)
        excluded = tuple(request.exclude_tools) or tuple(
            getattr(config, "QWEN_EXCLUDE_TOOLS", ()) or ()
        )
        if excluded:
            options["exclude_tools"] = [str(x) for x in excluded]

        session_id: str | None = None
        result_text = ""
        result_error: str | None = None
        usage: dict[str, Any] | None = None
        delta_chunks: list[str] = []
        cancelled = False
        timed_out = False

        await emit(ExternalRuntimeEvent(kind="status", text=f"qwen session in {Path(request.workspace_path).name}"))

        stream: Any = None
        cancel_watch: asyncio.Task[None] | None = None
        try:
            stream = query(request.task, options)
            if cancel_event is not None:
                cancel_watch = asyncio.create_task(_watch_cancel(cancel_event, stream))
            async with asyncio.timeout(float(request.timeout_sec)):
                async for message in stream:
                    if cancel_event is not None and cancel_event.is_set():
                        cancelled = True
                        break
                    session_id = _extract_session_id(message) or session_id
                    for event in _events_from_message(message):
                        if event.kind == "delta" and event.text:
                            delta_chunks.append(event.text)
                        await emit(event)
                    terminal = _terminal_from_message(message)
                    if terminal is not None:
                        result_text, result_error, usage = terminal
                        break
        except TimeoutError:
            timed_out = True
            result_error = f"qwen run exceeded {request.timeout_sec}s"
        except asyncio.CancelledError:
            cancelled = True
        except Exception as exc:
            logger.warning("qwen runtime run failed", exc_info=True)
            result_error = str(exc)[:500]
        finally:
            if cancel_watch is not None:
                cancel_watch.cancel()
                try:
                    await cancel_watch
                except (asyncio.CancelledError, Exception):
                    pass
            await _aclose(stream)

        if cancelled:
            await emit(ExternalRuntimeEvent(kind="status", text="cancelled"))
            return ExternalRunResult(ok=False, error="cancelled", session_id=session_id)
        if timed_out and not result_error:
            result_error = f"qwen run exceeded {request.timeout_sec}s"
        final_text = (result_text or "").strip() or "".join(delta_chunks).strip()
        if result_error and not final_text:
            return ExternalRunResult(ok=False, error=result_error, session_id=session_id)
        return ExternalRunResult(
            ok=not bool(result_error),
            text=final_text,
            session_id=session_id,
            usage=usage,
            error=result_error,
        )


def _binary_path() -> str:
    return str(getattr(config, "QWEN_BIN", "qwen") or "qwen")


def _safe_component(raw: str | None, fallback: str) -> str:
    cleaned = "".join(ch for ch in str(raw or "") if ch in _SAFE_CHARS)[:64].strip(".-")
    return cleaned or fallback


def _run_home(request: ExternalRunRequest) -> Path:
    base = Path(str(getattr(config, "EXTERNAL_RUNTIME_HOME", "/data/external_runtimes"))).expanduser()
    return base / "qwen" / _safe_component(request.user_id, "anon") / _safe_component(request.conversation_id, "default")


def _prepare_home(request: ExternalRunRequest) -> Path:
    """Create a private HOME whose ``.qwen/settings.json`` selects the AgentLayer provider."""
    home = _run_home(request)
    (home / ".qwen").mkdir(parents=True, exist_ok=True)
    home.chmod(stat.S_IRWXU)
    settings_path = home / ".qwen" / "settings.json"
    settings = {
        "modelProviders": {
            "openai": [
                {
                    "id": str(request.model),
                    "name": str(request.model),
                    "baseUrl": str(request.base_url),
                    "description": "AgentLayer provider pass-through",
                    "envKey": "OPENAI_API_KEY",
                }
            ]
        },
        "security": {"auth": {"selectedType": "openai"}},
        "model": {"name": str(request.model)},
    }
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    settings_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return home


def _child_env(request: ExternalRunRequest, *, run_home: Path, api_key: str) -> dict[str, str]:
    env: dict[str, str] = {
        "HOME": str(run_home),
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "TERM": "dumb",
        "OPENAI_API_KEY": api_key,
        "OPENAI_BASE_URL": str(request.base_url),
        "OPENAI_MODEL": str(request.model),
        "GIT_TERMINAL_PROMPT": "0",
    }
    for key, value in (request.env or {}).items():
        name = str(key or "").strip()
        if name and name not in {"HOME", "PATH"}:
            env[name] = str(value)
    return env


def _extract_session_id(message: Any) -> str | None:
    if isinstance(message, dict):
        raw = message.get("session_id") or (message.get("message") or {}).get("session_id")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _iter_content(message: dict[str, Any]) -> list[dict[str, Any]]:
    inner = message.get("message")
    if not isinstance(inner, dict):
        return []
    content = inner.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    return []


def _args_preview(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw[:240]
    try:
        return json.dumps(raw, ensure_ascii=False, sort_keys=True)[:240]
    except Exception:
        return str(raw)[:240]


def _events_from_message(message: Any) -> list[ExternalRuntimeEvent]:
    if not isinstance(message, dict):
        return []
    kind = str(message.get("type") or "")
    events: list[ExternalRuntimeEvent] = []
    if kind == "assistant":
        for block in _iter_content(message):
            block_type = str(block.get("type") or "")
            if block_type == "text" and block.get("text"):
                events.append(ExternalRuntimeEvent(kind="delta", text=str(block["text"])))
            elif block_type == "tool_use":
                events.append(
                    ExternalRuntimeEvent(
                        kind="tool_call",
                        tool=str(block.get("name") or "tool"),
                        call_id=str(block.get("id") or "") or None,
                        args_preview=_args_preview(block.get("input")),
                    )
                )
        return events
    if kind == "user":
        for block in _iter_content(message):
            if str(block.get("type") or "") == "tool_result":
                content = block.get("content")
                if isinstance(content, list):
                    content = " ".join(
                        str(item.get("text") or "") for item in content if isinstance(item, dict)
                    )
                text = str(content or "")
                failed = bool(block.get("is_error"))
                events.append(
                    ExternalRuntimeEvent(
                        kind="tool_result",
                        text=text[:4000],
                        ok=not failed,
                        error=text[:500] if failed else None,
                        call_id=str(block.get("tool_use_id") or "") or None,
                    )
                )
        return events
    return events


def _terminal_from_message(message: Any) -> tuple[str, str | None, dict[str, Any] | None] | None:
    """Return ``(text, error, usage)`` when this message ends the run, else ``None``."""
    if not isinstance(message, dict):
        return None
    if str(message.get("type") or "") != "result":
        return None
    usage_raw = message.get("usage")
    usage = dict(usage_raw) if isinstance(usage_raw, dict) else None
    if bool(message.get("is_error")):
        err = message.get("error")
        if isinstance(err, dict):
            err = err.get("message")
        text = str(message.get("result") or "").strip()
        return text, str(err or text or "qwen reported an error")[:500], usage
    return str(message.get("result") or "").strip(), None, usage


async def _watch_cancel(cancel_event: asyncio.Event, stream: Any) -> None:
    await cancel_event.wait()
    for name in ("interrupt", "close"):
        fn = getattr(stream, name, None)
        if not callable(fn):
            continue
        try:
            outcome = fn()
            if inspect.isawaitable(outcome):
                await outcome
        except Exception:
            logger.debug("qwen %s() during cancel failed", name, exc_info=True)


async def _aclose(stream: Any) -> None:
    close = getattr(stream, "aclose", None)
    if callable(close):
        try:
            await close()
        except Exception:
            logger.debug("closing qwen stream failed", exc_info=True)


QWEN_RUNTIME = QwenCodeRuntime()


def register() -> None:
    from apps.backend.domain.agent_runtime.external_runtime import register_external_runtime

    register_external_runtime(QWEN_RUNTIME)


register()
