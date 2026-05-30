"""Run an embedded ``chat_completion`` as another agent (sub-agent)."""

from __future__ import annotations

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any

DELEGATABLE_AGENT_IDS = frozenset({"coding", "coding_plan", "security_auditor"})

_PLAN_READONLY_TOOLS = [
    "coding_list_dir",
    "coding_read_file",
    "coding_glob",
    "retrieve_context",
    "coding_search",
    "coding_git_read",
    "coding_semantic_search",
    "coding_symbols",
    "coding_lsp",
    "project_explain",
]


def build_delegate_agents_catalog_snippet() -> str:
    """System-prompt block: which specialists exist and how to invoke them (no keyword routing)."""
    from apps.backend.domain.agent_registry import get_agent_registry

    reg = get_agent_registry()
    lines = [
        "## Specialist sub-agents",
        "You cannot run shell, git push, or security_scan tools directly. "
        "When the user needs those capabilities, call **`agent_delegate`** with "
        "`run_subagent: true`, a specialist `agent_id`, and a full `prompt`. "
        "Bind a workspace first (`workspace_create` / `workspace_bind`) — sub-agents inherit it. "
        "If `ssc_api_key` is listed as configured in the system context, do not ask the user to paste it.",
        "",
        "Available specialists:",
    ]
    for aid in ("security_auditor", "coding", "coding_plan"):
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
        "Pick the specialist by task (SSC/findings → security_auditor; "
        "edits/bash/push → coding; read-only exploration → coding_plan). "
        "Summarize the sub-agent result for the user (prefer `artifact_id` + short summary; "
        "do not paste raw `assistant_excerpt`). Use `task_*` tools for backlog, `artifact_refs` on delegate."
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
    if aid not in DELEGATABLE_AGENT_IDS:
        return json.dumps(
            {
                "ok": False,
                "error": f"agent_id must be one of: {', '.join(sorted(DELEGATABLE_AGENT_IDS))}",
            },
            ensure_ascii=False,
        )

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

    from apps.backend.domain.agent_task_prompt import enrich_delegate_prompt

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
    if parent_tid is not None:
        prompt = enrich_delegate_prompt(
            tenant_id=int(parent_tid),
            base_prompt=prompt,
            artifact_refs=refs,
            requirements=reqs,
        )

    from apps.backend.core import config

    max_r = config.MAX_TOOL_ROUNDS
    if max_rounds is not None:
        try:
            client_v = int(max_rounds)
            if client_v <= 0:
                max_r = config.MAX_TOOL_ROUNDS
            else:
                max_r = max(1, min(client_v, config.MAX_TOOL_ROUNDS))
        except (TypeError, ValueError):
            pass

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
    if aid == "coding_plan" and tool_allowlist is None:
        body["agent_tool_name_allowlist"] = list(_PLAN_READONLY_TOOLS)
    elif tool_allowlist:
        body["agent_tool_name_allowlist"] = list(tool_allowlist)

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
        body["agent_active_task_id"] = tid_task.strip()
        try:
            task_uuid = uuid.UUID(tid_task.strip())
        except (ValueError, TypeError):
            task_uuid = None

    body["agent_run_id"] = sub_run_id
    # Parent cancel_event is bound to the main asyncio loop; never pass it into
    # asyncio.run() in this worker thread (causes "bound to a different event loop").
    ce = None
    prid = ctx.get("agent_run_id")
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

    async def _runner() -> dict[str, Any]:
        return await chat_completion(
            body,
            event_emit=None,
            control_queue=None,
            cancel_event=ce,
            embedded_subagent=True,
        )

    def _thread_entry() -> dict[str, Any]:
        id_tok = None
        if parent_uid is not None:
            id_tok = set_identity(parent_tid, parent_uid)
        try:
            return asyncio.run(_runner())
        finally:
            if id_tok is not None:
                reset_identity(id_tok)

    ok = False
    err_msg: str | None = None
    excerpt_len = 0
    finish_reason: str | None = None
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            data = pool.submit(_thread_entry).result(timeout=600.0)
        ch0 = (data.get("choices") or [{}])[0]
        msg = ch0.get("message") or {}
        content = msg.get("content") or ""
        if not isinstance(content, str):
            content = str(content) if content is not None else ""
        content = content.strip()
        excerpt_len = len(content)
        finish_reason = ch0.get("finish_reason")
        ok = True
        excerpt = content[:12000]
        artifact_id: str | None = None
        if parent_uid is not None and parent_tid is not None and excerpt:
            from apps.backend.infrastructure import agent_artifacts_store, agent_tasks_store

            art = agent_artifacts_store.create_artifact(
                tenant_id=int(parent_tid),
                created_by_user_id=parent_uid,
                kind="subagent_report",
                summary=(description or aid)[:500],
                content={"text": excerpt, "assistant_excerpt": excerpt, "agent_id": aid},
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
        payload: dict[str, Any] = {
            "ok": True,
            "mode": "embedded_subagent",
            "agent_id": aid,
            "assistant_excerpt": excerpt,
            "finish_reason": finish_reason,
            "subagent_run_id": sub_run_id,
            "detail": "Sub-agent finished. Prefer artifact_id summary for the user; do not paste raw excerpt verbatim.",
        }
        if artifact_id:
            payload["artifact_id"] = artifact_id
            payload["artifact_summary"] = (description or aid)[:500]
        result = json.dumps(payload, ensure_ascii=False)
    except FuturesTimeout:
        err_msg = "sub-agent timed out after 600s"
        result = json.dumps({"ok": False, "error": err_msg}, ensure_ascii=False)
    except Exception as e:
        err_msg = f"sub-agent failed: {e}"[:800]
        result = json.dumps({"ok": False, "error": err_msg}, ensure_ascii=False)
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
                    "result_chars": excerpt_len if ok else None,
                }
            )
    return result
