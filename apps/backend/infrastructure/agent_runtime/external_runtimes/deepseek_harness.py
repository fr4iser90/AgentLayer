"""DeepSeek Harness adapter — headless CLI via ``dsh --profile headless``.

Install: ``npm install -g --prefix $AGENT_EXTERNAL_RUNTIME_HOME/npm-global @deepseek-ai/dsh``.
Docs: https://www.deepseek.com/en/harness/
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
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

RUNTIME_ID = "deepseek_harness"
_SAFE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


class DeepSeekHarnessRuntime:
    """Runs one agent turn as ``dsh --profile headless`` inside an AgentLayer workspace."""

    id = RUNTIME_ID
    supports_resume = True
    supports_write = True

    @property
    def default_permission_mode(self) -> str:
        return clamp_permission_mode(
            PERMISSION_AUTO_EDIT,
            "yolo" if bool(getattr(config, "EXTERNAL_RUNTIME_ALLOW_YOLO", False)) else PERMISSION_AUTO_EDIT,
        )

    def available(self) -> tuple[bool, str]:
        from apps.backend.infrastructure.platform.config_external_runtimes import (
            dsh_runtime_enabled_effective,
            external_runtime_enabled_effective,
        )
        from apps.backend.infrastructure.agent_runtime.external_runtimes.coding_runtime_packages import (
            resolve_runtime_binary,
        )

        if not external_runtime_enabled_effective():
            return False, "external runtime disabled (env or operator setting)"
        if not dsh_runtime_enabled_effective():
            return False, "deepseek harness runtime disabled (env or operator setting)"
        resolved = resolve_runtime_binary(RUNTIME_ID) or ""
        if not resolved or not os.path.isfile(resolved):
            return False, "dsh binary not found; install @deepseek-ai/dsh (Admin → Coding runtimes)"
        return True, ""

    async def run(
        self,
        request: ExternalRunRequest,
        *,
        emit: EventSink,
        cancel_event: asyncio.Event | None = None,
    ) -> ExternalRunResult:
        from apps.backend.infrastructure.agent_runtime.external_runtimes.coding_runtime_packages import (
            resolve_runtime_binary,
        )

        binary = resolve_runtime_binary(RUNTIME_ID)
        if not binary:
            return ExternalRunResult(ok=False, error="dsh binary not found")

        if not request.base_url or not request.api_key:
            return ExternalRunResult(
                ok=False,
                error=(
                    "no OpenAI-compatible provider credentials for this turn — external runtimes "
                    "inherit AgentLayer's provider"
                ),
            )
        if not request.model:
            return ExternalRunResult(ok=False, error="no model resolved for this turn")

        try:
            run_home = _prepare_home(request)
        except OSError as exc:
            return ExternalRunResult(ok=False, error=f"cannot prepare dsh home: {exc}")

        env = _child_env(request, run_home=run_home, api_key=str(request.api_key), model=str(request.model))
        cmd = [binary, "--profile", "headless"]
        if request.resume_session_id:
            cmd.extend(["--session-id", str(request.resume_session_id)])
        # Prefer JSON event stream when the installed CLI supports it.
        cmd.append("--json")
        cmd.append(str(request.task))

        await emit(
            ExternalRuntimeEvent(
                kind="status",
                text=f"dsh headless in {Path(request.workspace_path).name}",
            )
        )

        session_id: str | None = request.resume_session_id
        delta_chunks: list[str] = []
        result_text = ""
        result_error: str | None = None
        cancelled = False
        timed_out = False
        exit_code: int | None = None

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=request.workspace_path,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            return ExternalRunResult(ok=False, error=f"failed to start dsh: {exc}")

        async def _read_stream(stream: asyncio.StreamReader | None, *, is_stderr: bool) -> None:
            nonlocal session_id, result_text, result_error
            if stream is None:
                return
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\n")
                if not text:
                    continue
                if is_stderr:
                    logger.debug("dsh stderr: %s", text[:500])
                    continue
                events, sid, final, err = _parse_stdout_line(text)
                if sid:
                    session_id = sid
                if final:
                    result_text = final
                if err:
                    result_error = err
                for event in events:
                    if event.kind == "delta" and event.text:
                        delta_chunks.append(event.text)
                    await emit(event)

        try:
            async with asyncio.timeout(float(request.timeout_sec)):
                readers = [
                    asyncio.create_task(_read_stream(proc.stdout, is_stderr=False)),
                    asyncio.create_task(_read_stream(proc.stderr, is_stderr=True)),
                ]
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        cancelled = True
                        proc.kill()
                        break
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=0.25)
                        break
                    except asyncio.TimeoutError:
                        continue
                await asyncio.gather(*readers, return_exceptions=True)
                exit_code = proc.returncode
        except TimeoutError:
            timed_out = True
            result_error = f"dsh run exceeded {request.timeout_sec}s"
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        except asyncio.CancelledError:
            cancelled = True
            try:
                proc.kill()
            except ProcessLookupError:
                pass

        if cancelled:
            await emit(ExternalRuntimeEvent(kind="status", text="cancelled"))
            return ExternalRunResult(ok=False, error="cancelled", session_id=session_id, exit_code=exit_code)
        if timed_out and not result_error:
            result_error = f"dsh run exceeded {request.timeout_sec}s"

        final_text = (result_text or "").strip() or "".join(delta_chunks).strip()
        if not final_text and exit_code not in (0, None) and not result_error:
            result_error = f"dsh exited with code {exit_code}"
        if result_error and not final_text:
            return ExternalRunResult(
                ok=False, error=result_error, session_id=session_id, exit_code=exit_code
            )
        return ExternalRunResult(
            ok=exit_code in (0, None) and not result_error,
            text=final_text,
            session_id=session_id,
            error=result_error,
            exit_code=exit_code,
        )


def _safe_component(raw: str | None, fallback: str) -> str:
    cleaned = "".join(ch for ch in str(raw or "") if ch in _SAFE_CHARS)[:64].strip(".-")
    return cleaned or fallback


def _run_home(request: ExternalRunRequest) -> Path:
    base = Path(str(getattr(config, "EXTERNAL_RUNTIME_HOME", "/data/external_runtimes"))).expanduser()
    return (
        base
        / "dsh"
        / _safe_component(request.user_id, "anon")
        / _safe_component(request.conversation_id, "default")
    )


def _prepare_home(request: ExternalRunRequest) -> Path:
    home = _run_home(request)
    home.mkdir(parents=True, exist_ok=True)
    home.chmod(stat.S_IRWXU)
    return home


def _child_env(
    request: ExternalRunRequest,
    *,
    run_home: Path,
    api_key: str,
    model: str,
) -> dict[str, str]:
    path_parts = [str(run_home / "bin")]
    npm_bin = Path(str(getattr(config, "EXTERNAL_RUNTIME_HOME", "/data/external_runtimes"))).expanduser() / "npm-global" / "bin"
    if npm_bin.is_dir():
        path_parts.append(str(npm_bin))
    existing = os.environ.get("PATH") or ""
    if existing:
        path_parts.append(existing)
    base_url = str(request.base_url or "").rstrip("/")
    if not base_url.endswith("/v1"):
        # OpenAI-compatible clients expect …/v1
        low = base_url.lower()
        if not low.endswith("/v1"):
            base_url = f"{base_url}/v1"
    env: dict[str, str] = {
        "HOME": str(run_home),
        "DSH_HOME": str(run_home),
        "PATH": os.pathsep.join(path_parts),
        "LANG": os.environ.get("LANG") or "C.UTF-8",
        "LC_ALL": os.environ.get("LC_ALL") or "C.UTF-8",
        "OPENAI_API_KEY": api_key,
        "OPENAI_BASE_URL": base_url,
        "OPENAI_MODEL": model,
        "OPENAI_API_BASE": base_url,
    }
    for key, value in (request.env or {}).items():
        if key and value is not None and key not in env:
            env[str(key)] = str(value)
    return env


def _parse_stdout_line(
    line: str,
) -> tuple[list[ExternalRuntimeEvent], str | None, str | None, str | None]:
    """Parse one stdout line: JSON event object or plain final text."""
    events: list[ExternalRuntimeEvent] = []
    session_id: str | None = None
    final: str | None = None
    error: str | None = None
    stripped = line.strip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            events.append(ExternalRuntimeEvent(kind="delta", text=line))
            return events, None, None, None
        if isinstance(obj, dict):
            sid = obj.get("session_id") or obj.get("sessionId") or obj.get("id")
            if isinstance(sid, str) and sid.strip():
                session_id = sid.strip()
            kind = str(obj.get("type") or obj.get("kind") or "").strip().lower()
            text = str(obj.get("text") or obj.get("content") or obj.get("delta") or "")
            if kind in {"error", "failed"}:
                error = text or str(obj.get("error") or "dsh error")
                events.append(ExternalRuntimeEvent(kind="error", text=error, error=error, ok=False))
            elif kind in {"tool", "tool_call", "tool_use"}:
                events.append(
                    ExternalRuntimeEvent(
                        kind="tool_call",
                        tool=str(obj.get("name") or obj.get("tool") or "tool"),
                        args_preview=str(obj.get("input") or obj.get("arguments") or "")[:500],
                    )
                )
            elif kind in {"tool_result", "tool_done"}:
                events.append(
                    ExternalRuntimeEvent(
                        kind="tool_result",
                        tool=str(obj.get("name") or obj.get("tool") or "tool"),
                        text=text[:2000],
                        ok=bool(obj.get("ok", True)),
                    )
                )
            elif kind in {"done", "result", "final"}:
                final = text or str(obj.get("result") or "")
                events.append(ExternalRuntimeEvent(kind="done", text=final))
            elif text:
                events.append(ExternalRuntimeEvent(kind="delta", text=text))
            return events, session_id, final, error
    # Non-JSON: treat as streaming / final text
    events.append(ExternalRuntimeEvent(kind="delta", text=line))
    return events, None, None, None


DSH_RUNTIME = DeepSeekHarnessRuntime()


def register() -> None:
    from apps.backend.domain.agent_runtime.external_runtime import register_external_runtime

    register_external_runtime(DSH_RUNTIME)


register()
