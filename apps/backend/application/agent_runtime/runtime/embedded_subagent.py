"""Run an embedded ``chat_completion`` as another agent (sub-agent)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, Awaitable, Callable

from apps.backend.application.agent_runtime.dependencies import (
    agent_artifacts_store,
    agent_config_effective,
    agent_tasks_store,
    db,
    ensure_workspace,
)

logger = logging.getLogger(__name__)

EmbeddedChatCompletion = Callable[..., Awaitable[Any]]
_chat_completion_handler: EmbeddedChatCompletion | None = None


def register_embedded_chat_completion(handler: EmbeddedChatCompletion) -> None:
    global _chat_completion_handler
    _chat_completion_handler = handler


def _require_chat_completion_handler() -> EmbeddedChatCompletion:
    if _chat_completion_handler is None:
        raise RuntimeError("embedded chat completion handler not registered")
    return _chat_completion_handler

from apps.backend.domain.agent_runtime.subagent_catalog import (  # noqa: E402
    __getattr__,
    admin_only_delegatable_agent_ids,
    build_delegate_agents_catalog_snippet,
    caller_is_admin,
    effective_delegatable_agent_ids,
    standard_delegatable_agent_ids,
)


def _parent_llm_from_context(context: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Model + catalog provider from the parent chat turn (Web UI), not env defaults."""
    ctx = context or {}
    model = ctx.get("parent_effective_model")
    if isinstance(model, str):
        model = model.strip() or None
    else:
        model = None
    owned = ctx.get("parent_model_catalog_owned_by")
    if isinstance(owned, str):
        owned = owned.strip() or None
    else:
        owned = None
    return model, owned


from apps.backend.domain.agent_runtime.subagent_events import _forward_subagent_tool_event  # noqa: E402


def run_embedded_subagent_sync(
    *,
    subagent_agent_id: str,
    prompt: str,
    context: dict[str, Any] | None,
    tool_name: str,
    description: str,
    max_rounds: int | None = None,
    tool_allowlist: list[str] | None = None,
    artifact_refs: list[Any] | None = None,
    requirements: list[Any] | None = None,
    task_id: str | None = None,
) -> str:
    from apps.backend.domain.shared.identity import get_identity, reset_identity, set_identity

    aid = (subagent_agent_id or "").strip()
    ctx = context or {}
    parent_tid, parent_uid = get_identity()
    u = ctx.get("user")
    if parent_uid is None and u is not None:
        uid = getattr(u, "id", None)
        if uid is not None:
            parent_uid = uid
            try:
                parent_tid = db.user_tenant_id(uid)
            except Exception:
                parent_tid = 1

    uid_check = parent_uid if isinstance(parent_uid, uuid.UUID) else None
    is_admin = caller_is_admin(uid_check)

    tid: int | None = None
    if parent_tid is not None:
        try:
            tid = int(parent_tid)
        except (TypeError, ValueError):
            tid = None
    if tid is None and context and context.get("tenant_id") is not None:
        try:
            tid = int(context["tenant_id"])
        except (TypeError, ValueError):
            tid = None

    allowed_ids = effective_delegatable_agent_ids(caller_is_admin=is_admin, tenant_id=tid, user_id=uid_check)
    if aid not in allowed_ids:
        return json.dumps(
            {
                "ok": False,
                "error": f"agent_id must be one of: {', '.join(sorted(allowed_ids))}",
            },
            ensure_ascii=False,
        )

    from apps.backend.domain.agent_runtime.task_prompt import (
        enrich_delegate_prompt,
        infer_plan_delegate_mode,
        parse_delegate_mode,
    )
    from apps.backend.domain.delegation.enforcement import (
        load_delegate_allowed_paths,
        parse_requirement_value,
        subagent_reject_reason,
    )

    prompt = (prompt or "").strip()
    if not prompt:
        return json.dumps({"ok": False, "error": "prompt is required"}, ensure_ascii=False)
    refs = artifact_refs
    if refs is None:
        raw_refs = ctx.get("delegate_artifact_refs")
        if isinstance(raw_refs, list):
            refs = raw_refs
    reqs = requirements
    if reqs is None:
        raw_req = ctx.get("delegate_requirements")
        if isinstance(raw_req, list):
            reqs = raw_req

    reject = subagent_reject_reason(
        agent_id=aid,
        requirements=reqs,
        artifact_refs=refs,
    )
    if reject:
        return json.dumps({"ok": False, "error": reject}, ensure_ascii=False)

    delegate_mode = parse_delegate_mode(reqs)
    if delegate_mode and not agent_config_effective.delegate_mode_allowed(delegate_mode, tenant_id=tid):
        return json.dumps(
            {"ok": False, "error": f"delegate mode {delegate_mode!r} is not allowed by harness config"},
            ensure_ascii=False,
        )
    if aid == "coding_plan":
        if agent_config_effective.delegate_infer_git_forensics(tenant_id=tid):
            delegate_mode = delegate_mode or infer_plan_delegate_mode(prompt, reqs)
        if delegate_mode == "git_forensics" and not parse_delegate_mode(reqs):
            reqs = list(reqs or []) + ["mode: git_forensics"]
    if parent_tid is not None:
        prompt = enrich_delegate_prompt(
            tenant_id=int(parent_tid),
            base_prompt=prompt,
            artifact_refs=refs,
            requirements=reqs,
        )

    if tid is None:
        try:
            from apps.backend.domain.shared.identity import get_identity

            tid_raw, _uid = get_identity()
            tid = int(tid_raw) if tid_raw is not None else None
        except Exception:
            tid = None

    max_r = agent_config_effective.subagent_max_tool_rounds(tenant_id=tid)
    if max_rounds is not None:
        logger.debug(
            "ignoring agent_delegate max_rounds=%r — server uses SUBAGENT_MAX_TOOL_ROUNDS=%s",
            max_rounds,
            max_r,
        )

    parent_model, parent_catalog = _parent_llm_from_context(context)
    if not parent_model or not parent_catalog:
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "Sub-agent needs the parent chat model from the UI (model + provider). "
                    "Re-select the model in the chat composer and retry; "
                    "embedded runs require an explicit model from the catalog (no env default)."
                ),
            },
            ensure_ascii=False,
        )

    body: dict[str, Any] = {
        "model": parent_model,
        "agent_model_catalog_owned_by": parent_catalog,
        "messages": [{"role": "user", "content": prompt}],
        "agent_id": aid,
        "agent_max_tool_rounds": max_r,
        "agent_plain_completion": False,
        "agent_unattended": True,
    }
    handoff_collector: list[str] = []
    body["agent_handoff_artifact_collector"] = handoff_collector
    if tool_allowlist:
        body["agent_tool_name_allowlist"] = list(tool_allowlist)
    if delegate_mode:
        body["agent_delegate_mode"] = delegate_mode
        if delegate_mode == "git_forensics":
            body["agent_plan_delegate_mode"] = delegate_mode
    if delegate_mode == "fix_from_artifact" and aid == "coding" and parent_tid is not None:
        allowed_paths = load_delegate_allowed_paths(
            tenant_id=int(parent_tid),
            artifact_refs=refs,
            max_artifacts=agent_config_effective.delegate_max_artifact_refs(tenant_id=tid),
        )
        if not allowed_paths:
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        "fix_from_artifact: referenced artifacts contain no file paths "
                        "(paths, high_paths, or findings[].path). Re-run the specialist scan or "
                        "delegate to coding without mode: fix_from_artifact for open-ended fixes."
                    ),
                },
                ensure_ascii=False,
            )
        body["agent_delegate_allowed_paths"] = allowed_paths
        branch = parse_requirement_value(reqs, "branch")
        if branch:
            body["agent_delegate_required_branch"] = branch

    sub_run_id = str(uuid.uuid4())
    ws = ctx.get("workspace")
    if not (isinstance(ws, dict) and ws.get("path")) and ctx.get("workspace_id") and parent_uid is not None:
        try:
            u = ctx.get("user")
            if u is None:

                class _UserLike:
                    def __init__(self, uid: Any):
                        self.id = uid
                        self.role = "user"

                u = _UserLike(parent_uid)
            materialized = ensure_workspace(str(ctx["workspace_id"]).strip(), u)
            if materialized:
                ws = materialized
                ctx = dict(ctx)
                ctx["workspace"] = materialized
        except Exception:
            pass
    ws_uuid: uuid.UUID | None = None
    if isinstance(ws, dict) and ws.get("id"):
        body["workspace_id"] = str(ws["id"])
        try:
            ws_uuid = uuid.UUID(str(ws["id"]))
        except (ValueError, TypeError):
            ws_uuid = None
    elif ctx.get("workspace_id"):
        body["workspace_id"] = str(ctx["workspace_id"]).strip()
        try:
            ws_uuid = uuid.UUID(str(ctx["workspace_id"]).strip())
        except (ValueError, TypeError):
            ws_uuid = None

    tid_task = task_id or ctx.get("agent_task_id")
    task_uuid: uuid.UUID | None = None
    if isinstance(tid_task, str) and tid_task.strip():
        if parent_tid is not None and parent_uid is not None:
            from apps.backend.domain.agent_runtime.run_persistence import resolve_valid_active_task_id

            _valid_task, task_uuid = resolve_valid_active_task_id(
                tenant_id=int(parent_tid),
                user_id=parent_uid,
                candidate=tid_task.strip(),
            )
            if _valid_task:
                body["agent_active_task_id"] = _valid_task
        else:
            try:
                task_uuid = uuid.UUID(tid_task.strip())
                body["agent_active_task_id"] = tid_task.strip()
            except (ValueError, TypeError):
                task_uuid = None

    body["agent_run_id"] = sub_run_id
    from apps.backend.domain.shared.identity import get_benchmark_run_id

    bench_run_raw = get_benchmark_run_id()
    prid = ctx.get("agent_run_id")
    parent_cancel_thread = None
    if isinstance(prid, str) and prid.strip():
        from apps.backend.domain.agent_runtime.run_cancel import (
            link_run_to_cancel_root,
            root_cancel_event,
        )

        link_run_to_cancel_root(sub_run_id, prid.strip())
        parent_cancel_thread = root_cancel_event(sub_run_id)
    if isinstance(prid, str) and prid.strip():
        body["agent_parent_run_id"] = prid.strip()
    notify = ctx.get("agent_subagent_notify")
    detail = (description or aid).strip()[:200]
    if callable(notify):
        notify(
            {
                "type": "agent.subagent_start",
                "subagent_run_id": sub_run_id,
                "agent_id": aid,
                "tool_name": tool_name,
                "detail": detail,
            }
        )

    def _subagent_event_bridge(ev: dict[str, Any]) -> None:
        _forward_subagent_tool_event(
            notify, sub_run_id=sub_run_id, agent_id=aid, ev=ev
        )

    async def _subagent_event_emit(ev: dict[str, Any]) -> None:
        _subagent_event_bridge(ev)

    async def _runner() -> dict[str, Any]:
        sub_cancel = asyncio.Event()
        bridge_task: asyncio.Task[None] | None = None
        if parent_cancel_thread is not None:
            if parent_cancel_thread.is_set():
                sub_cancel.set()
            else:

                async def _bridge_parent_cancel() -> None:
                    while not parent_cancel_thread.is_set():
                        await asyncio.sleep(0.2)
                    sub_cancel.set()

                bridge_task = asyncio.create_task(_bridge_parent_cancel())
        try:
            return await _require_chat_completion_handler()(
                body,
                event_emit=_subagent_event_emit if callable(notify) else None,
                control_queue=None,
                cancel_event=sub_cancel,
                embedded_subagent=True,
            )
        finally:
            if bridge_task is not None:
                bridge_task.cancel()
                try:
                    await bridge_task
                except asyncio.CancelledError:
                    pass

    def _thread_entry() -> dict[str, Any]:
        from apps.backend.domain.shared.identity import reset_benchmark_run_id, set_benchmark_run_id

        id_tok = None
        bench_tok = None
        if parent_uid is not None:
            id_tok = set_identity(parent_tid, parent_uid)
        if bench_run_raw:
            try:
                bench_tok = set_benchmark_run_id(uuid.UUID(str(bench_run_raw).strip()))
            except (ValueError, TypeError):
                bench_tok = None
        try:
            return asyncio.run(_runner())
        finally:
            if bench_tok is not None:
                reset_benchmark_run_id(bench_tok)
            if id_tok is not None:
                reset_identity(id_tok)

    ok = False
    err_msg: str | None = None
    excerpt_len = 0
    finish_reason: str | None = None
    problems: list[str] = []
    _subagent_timeout = agent_config_effective.subagent_timeout_sec(tenant_id=tid)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            _future = pool.submit(_thread_entry)
            if _subagent_timeout is None:
                data = _future.result()
            else:
                data = _future.result(timeout=_subagent_timeout)
        if not isinstance(data, dict):
            err_msg = f"sub-agent returned unexpected payload type: {type(data).__name__}"
            problems.append(err_msg)
            result = json.dumps(
                {
                    "ok": False,
                    "error": err_msg,
                    "problems": problems,
                    "subagent_run_id": sub_run_id,
                    "agent_id": aid,
                    "hint": (
                        "Report these problems to the user. Do not claim the sub-agent completed the work."
                    ),
                },
                ensure_ascii=False,
            )
        elif data.get("error"):
            err_msg = str(data.get("error") or "sub-agent error")[:800]
            problems.append(err_msg)
            ctx_meta = data.get("agentlayer_context") or {}
            if isinstance(ctx_meta, dict):
                for w in ctx_meta.get("run_persist_warnings") or []:
                    if isinstance(w, str) and w.strip():
                        problems.append(w.strip())
                if ctx_meta.get("run_persisted") is False:
                    problems.append(
                        "agent run was not persisted (audit/trace incomplete)"
                    )
            result = json.dumps(
                {
                    "ok": False,
                    "error": err_msg,
                    "problems": problems,
                    "subagent_run_id": sub_run_id,
                    "agent_id": aid,
                    "hint": (
                        "Report these problems to the user. Do not claim the sub-agent completed the work."
                    ),
                },
                ensure_ascii=False,
            )
        else:
            ctx_meta = data.get("agentlayer_context") or {}
            if isinstance(ctx_meta, dict):
                for w in ctx_meta.get("run_persist_warnings") or []:
                    if isinstance(w, str) and w.strip():
                        problems.append(w.strip())
                if ctx_meta.get("run_persisted") is False:
                    problems.append(
                        "agent run was not persisted (audit/trace incomplete)"
                    )
            ch0 = (data.get("choices") or [{}])[0]
            msg = ch0.get("message") or {}
            content = msg.get("content") or ""
            if not isinstance(content, str):
                content = str(content) if content is not None else ""
            content = content.strip()
            excerpt_len = len(content)
            finish_reason = ch0.get("finish_reason")
            if not content:
                err_msg = "sub-agent finished with empty assistant content"
                if finish_reason:
                    err_msg += f" (finish_reason={finish_reason})"
                problems.append(err_msg)
                result = json.dumps(
                    {
                        "ok": False,
                        "error": err_msg,
                        "problems": problems,
                        "subagent_run_id": sub_run_id,
                        "agent_id": aid,
                        "finish_reason": finish_reason,
                        "hint": (
                            "Tell the user the sub-agent did not produce output and why. "
                            "Retry with agent_delegate or fix workspace/model issues."
                        ),
                    },
                    ensure_ascii=False,
                )
            else:
                from apps.backend.application.agent_runtime.runtime.tool_loop import _strip_prose_fake_tool_markup
                from apps.backend.domain.delegation.enforcement import delegate_excerpt_is_actionable

                excerpt = _strip_prose_fake_tool_markup(content)[:12000].strip()
                if not excerpt or not delegate_excerpt_is_actionable(excerpt):
                    err_msg = (
                        "sub-agent did not return a usable plain-text answer "
                        "(tool-call markup, instructions only, or empty after cleanup)"
                    )
                    if finish_reason:
                        err_msg += f" (finish_reason={finish_reason})"
                    problems.append(err_msg)
                    result = json.dumps(
                        {
                            "ok": False,
                            "error": err_msg,
                            "problems": problems,
                            "assistant_excerpt": content[:2000],
                            "subagent_run_id": sub_run_id,
                            "agent_id": aid,
                            "finish_reason": finish_reason,
                            "hint": (
                                "The specialist did not finish with a clear answer for the user. "
                                "Retry delegate with a simpler prompt (repo-relative paths like README.md)."
                            ),
                        },
                        ensure_ascii=False,
                    )
                else:
                    ok = True
                    artifact_id: str | None = None
                    if parent_uid is not None and parent_tid is not None and excerpt:
                        try:
                            art = agent_artifacts_store.create_artifact(
                                tenant_id=int(parent_tid),
                                created_by_user_id=parent_uid,
                                kind="subagent_report",
                                summary=(description or aid)[:500],
                                content={
                                    "text": excerpt,
                                    "assistant_excerpt": excerpt,
                                    "agent_id": aid,
                                },
                                workspace_id=ws_uuid,
                                created_by_task_id=task_uuid,
                                created_by_run_id=uuid.UUID(sub_run_id),
                            )
                            artifact_id = str(art.get("id") or "")
                            if task_uuid and artifact_id:
                                agent_tasks_store.update_task(
                                    task_id=task_uuid,
                                    tenant_id=int(parent_tid),
                                    append_artifact_ref=artifact_id,
                                    status="in_progress",
                                )
                        except Exception as art_exc:
                            problems.append(f"artifact persist failed: {art_exc}"[:400])
                    detail = (
                        "Sub-agent finished with a usable answer in assistant_excerpt. "
                        "Summarize it for the user."
                    )
                    if problems:
                        detail += " Problems: " + "; ".join(problems)
                    payload: dict[str, Any] = {
                        "ok": True,
                        "mode": "embedded_subagent",
                        "agent_id": aid,
                        "assistant_excerpt": excerpt,
                        "finish_reason": finish_reason,
                        "subagent_run_id": sub_run_id,
                        "detail": detail,
                    }
                    if problems:
                        payload["problems"] = problems
                    if handoff_collector:
                        payload["handoff_artifact_ids"] = list(handoff_collector)
                    if artifact_id:
                        payload["artifact_id"] = artifact_id
                        payload["artifact_summary"] = (description or aid)[:500]
                    result = json.dumps(payload, ensure_ascii=False)
    except FuturesTimeout:
        _t = _subagent_timeout if _subagent_timeout is not None else 0
        err_msg = f"sub-agent timed out after {_t:g}s"
        problems = [err_msg]
        result = json.dumps(
            {
                "ok": False,
                "error": err_msg,
                "problems": problems,
                "subagent_run_id": sub_run_id,
                "agent_id": aid,
                "hint": "Tell the user the sub-agent timed out; suggest retry or smaller scope.",
            },
            ensure_ascii=False,
        )
    except Exception as e:
        err_msg = f"sub-agent failed: {e}"[:800]
        problems = [err_msg]
        result = json.dumps(
            {
                "ok": False,
                "error": err_msg,
                "problems": problems,
                "subagent_run_id": sub_run_id,
                "agent_id": aid,
                "hint": "Tell the user what failed and why; do not claim success.",
            },
            ensure_ascii=False,
        )
    finally:
        if callable(notify):
            notify(
                {
                    "type": "agent.subagent_done",
                    "subagent_run_id": sub_run_id,
                    "agent_id": aid,
                    "tool_name": tool_name,
                    "ok": ok,
                    "detail": err_msg or (f"finished ({excerpt_len} chars)" if ok else "finished"),
                    "problems": problems or None,
                    "result_chars": excerpt_len if ok else None,
                }
            )
    return result
