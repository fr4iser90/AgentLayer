"""Run an embedded ``chat_completion`` as another agent (sub-agent)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any

logger = logging.getLogger(__name__)

def _delegatable_sets_from_registry() -> tuple[frozenset[str], frozenset[str]]:
    from apps.backend.domain.agent_registry import get_agent_registry

    reg = get_agent_registry()
    reg.ensure_loaded()
    standard: set[str] = set()
    admin_only: set[str] = set()
    for aid in reg.agent_ids():
        ag = reg.get_agent(aid) or {}
        if aid == "general":
            continue
        if ag.get("admin_only_delegatable"):
            admin_only.add(aid)
            continue
        if ag.get("delegatable"):
            standard.add(aid)
    return frozenset(standard), frozenset(admin_only)


def standard_delegatable_agent_ids() -> frozenset[str]:
    return _delegatable_sets_from_registry()[0]


def admin_only_delegatable_agent_ids() -> frozenset[str]:
    return _delegatable_sets_from_registry()[1]


def caller_is_admin(user_id: uuid.UUID | None) -> bool:
    if user_id is None:
        return False
    try:
        from apps.backend.infrastructure.db import db as _db

        return (_db.user_role(user_id) or "").strip().lower() == "admin"
    except Exception:
        return False


def effective_delegatable_agent_ids(*, caller_is_admin: bool = False) -> frozenset[str]:
    standard, admin_only = _delegatable_sets_from_registry()
    if caller_is_admin:
        return standard | admin_only
    return standard


def __getattr__(name: str):
    if name == "DELEGATABLE_AGENT_IDS":
        return standard_delegatable_agent_ids()
    if name == "ADMIN_ONLY_DELEGATABLE_AGENT_IDS":
        return admin_only_delegatable_agent_ids()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def build_delegate_agents_catalog_snippet(*, caller_is_admin: bool = False) -> str:
    """System-prompt block: which specialists exist and how to invoke them (no keyword routing)."""
    from apps.backend.domain.agent_registry import get_agent_registry

    reg = get_agent_registry()
    allowed_ids = effective_delegatable_agent_ids(caller_is_admin=caller_is_admin)
    lines = [
        "## Specialist sub-agents",
        "You cannot run shell, git push, or security_scan tools directly. "
        "When the user needs those capabilities, call **`delegate`** with "
        "`run_subagent: true`, a specialist `agent_id`, and a full `prompt`. "
        "Bind a workspace first (`create` / `bind`) — sub-agents inherit it (not required for operator). "
        "If `ssc_api_key` is listed as configured in the system context, do not ask the user to paste it.",
        "",
        "Available specialists:",
    ]
    for aid in sorted(allowed_ids):
        ag = reg.get_agent(aid)
        if not ag:
            continue
        name = ag.get("name") or aid
        desc = (ag.get("description") or "").strip().replace("\n", " ")
        if len(desc) > 240:
            desc = desc[:237] + "…"
        lines.append(f"- **{aid}** ({name}): {desc}")
    lines.append("")
    lines.append(
        "Pick the specialist by task (see descriptions above). "
        "For operator/platform settings (media library flags, interfaces): admins may "
        "`delegate` `agent_id=operator` — do not use coding for that. "
        "Pass `artifact_refs` when follow-up work needs prior sub-agent or tool outputs. "
        "Summarize the sub-agent result for the user (prefer `artifact_id` + short summary; "
        "do not paste raw `assistant_excerpt`). Use `task_*` tools for backlog."
    )
    return "\n".join(lines)


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


def _forward_subagent_tool_event(
    notify: Any,
    *,
    sub_run_id: str,
    agent_id: str,
    ev: dict[str, Any],
) -> None:
    """Map embedded sub-agent events to the parent WS (tool steps, deferred waits)."""
    if not callable(notify):
        return
    typ = ev.get("type")
    if typ in ("agent.deferred_wait", "agent.llm_slot_wait"):
        payload = dict(ev)
        payload.setdefault("type", typ)
        payload["subagent_run_id"] = sub_run_id
        payload["agent_id"] = agent_id
        notify(payload)
        return
    if typ not in ("agent.tool_start", "agent.tool_done"):
        return
    payload: dict[str, Any] = {
        "type": "agent.subagent_step",
        "subagent_run_id": sub_run_id,
        "agent_id": agent_id,
        "phase": "start" if typ == "agent.tool_start" else "done",
        "tool": ev.get("name"),
        "round": ev.get("round"),
    }
    if typ == "agent.tool_start":
        summary = ev.get("summary")
        if isinstance(summary, str) and summary.strip():
            payload["summary"] = summary.strip()
        step_label = ev.get("step_label")
        if isinstance(step_label, str) and step_label.strip():
            payload["step_label"] = step_label.strip()
        label = ev.get("label")
        if isinstance(label, str) and label.strip():
            payload["label"] = label.strip()
    else:
        result_ok = ev.get("result_ok")
        if result_ok is True:
            payload["ok"] = True
        elif result_ok is False:
            payload["ok"] = False
        result_error = ev.get("result_error")
        if isinstance(result_error, str) and result_error.strip():
            payload["error"] = result_error.strip()[:500]
    notify(payload)


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
    from apps.backend.domain.agent import chat_completion
    from apps.backend.domain.identity import get_identity, reset_identity, set_identity

    aid = (subagent_agent_id or "").strip()
    ctx = context or {}
    parent_tid, parent_uid = get_identity()
    u = ctx.get("user")
    if parent_uid is None and u is not None:
        uid = getattr(u, "id", None)
        if uid is not None:
            parent_uid = uid
            try:
                from apps.backend.infrastructure.db import db as _db

                parent_tid = _db.user_tenant_id(uid)
            except Exception:
                parent_tid = 1

    uid_check = parent_uid if isinstance(parent_uid, uuid.UUID) else None
    is_admin = caller_is_admin(uid_check)
    allowed_ids = effective_delegatable_agent_ids(caller_is_admin=is_admin)
    if aid not in allowed_ids:
        return json.dumps(
            {
                "ok": False,
                "error": f"agent_id must be one of: {', '.join(sorted(allowed_ids))}",
            },
            ensure_ascii=False,
        )

    from apps.backend.domain.agent_task_prompt import (
        enrich_delegate_prompt,
        infer_plan_delegate_mode,
        parse_delegate_mode,
    )
    from apps.backend.domain.delegate_enforcement import (
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
    if aid == "coding_plan":
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

    from apps.backend.core import config

    max_r = config.SUBAGENT_MAX_TOOL_ROUNDS
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
            from apps.backend.infrastructure.workspace_service import ensure_workspace

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
            from apps.backend.domain.agent_run_persistence import resolve_valid_active_task_id

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
    bench_run_raw = ctx.get("benchmark_run_id")
    if bench_run_raw:
        body["benchmark_run_id"] = str(bench_run_raw).strip()
    prid = ctx.get("agent_run_id")
    parent_cancel_thread = None
    if isinstance(prid, str) and prid.strip():
        from apps.backend.domain.agent_run_cancel import (
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
            return await chat_completion(
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
        from apps.backend.domain.identity import reset_benchmark_run_id, set_benchmark_run_id

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
    _subagent_timeout = config.SUBAGENT_TIMEOUT_SEC
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
                from apps.backend.domain.agent_tools import _strip_prose_fake_tool_markup
                from apps.backend.domain.delegate_enforcement import delegate_excerpt_is_actionable

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
                        from apps.backend.infrastructure import (
                            agent_artifacts_store,
                            agent_tasks_store,
                        )

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
