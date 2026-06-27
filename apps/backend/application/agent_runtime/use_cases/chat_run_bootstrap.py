"""Bootstrap workspace, identity, and run state for chat completion."""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from apps.backend.infrastructure.platform.config import config
from apps.backend.application.agent_runtime.dependencies import (
    agent_runs_store,
    bind_llm_wait_notifier,
    db,
    ensure_workspace,
    maybe_schedule_index_on_attach,
)
from apps.backend.application.agent_runtime.runtime.io import *  # noqa: F403
from apps.backend.application.agent_runtime.runtime.prompts import *  # noqa: F403
from apps.backend.application.agent_runtime.runtime.tool_loop import *  # noqa: F403
from apps.backend.domain.plugin_system.tool_routing import last_user_text

logger = logging.getLogger(__name__)


@dataclass
class ChatRunBootstrap:
    workspace_id: Any
    workspace: dict[str, Any] | None
    workspace_token: Any
    tenant_id: Any
    user_id: Any
    cfg_tid: int | None
    router_strict_default: bool
    catalog_after_first_round: bool
    tool_choice_required_retry: bool
    user_obj: Any
    is_admin: bool
    tool_context: dict[str, Any]
    agent_run_id: str
    bench_run_ctx_token: Any
    parent_cancel_bridge_task: asyncio.Task[None] | None
    llm_wait_token: Any
    conversation_uuid: uuid.UUID | None
    active_task_id: str | None
    run_persisted: bool
    run_persist_warnings: list[str]
    run_ctx_token: Any
    task_ctx_token: Any
    run_finish_status: str
    run_finish_error: str | None
    workspace_auto_created: bool
    workspace_bound_from_conversation: bool
    agent_auto_routed: bool


async def bootstrap_chat_run(
    *,
    body: dict[str, Any],
    agent_id: str | None,
    embedded_subagent: bool,
    bearer_user_role: str | None,
    agent_storage_images: list[dict[str, Any]],
    pre_run_id: Any,
    parent_agent_run_id: str | None,
    cancel_event: asyncio.Event | None,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    agent_unattended: bool,
    agent_delegate_mode: str | None,
    delegate_allowed_paths: list[str] | None,
    delegate_required_branch: str | None,
    handoff_collector: Any,
    active_task_body: Any,
    agent_require_workspace_verify: bool,
) -> ChatRunBootstrap:
    from apps.backend.domain.shared.identity import set_workspace, get_identity
    workspace_id = body.pop("workspace_id", None)
    workspace = None
    workspace_token = None
    _bootstrap_messages = list(body.get("messages") or [])
    _bootstrap_last_user = last_user_text(_bootstrap_messages)
    agent_auto_routed = False
    workspace_auto_created = False
    workspace_bound_from_conversation = False

    # Get user from identity context (tenant_id, user_id)
    tenant_id, user_id = get_identity()

    cfg_tid = int(tenant_id) if tenant_id is not None else None
    _router_strict_default = bool(config.AGENT_ROUTER_STRICT_DEFAULT)
    _catalog_after_first_round = bool(config.AGENT_TOOLS_CATALOG_AFTER_FIRST_ROUND)
    _tool_choice_required_retry = bool(config.AGENT_TOOL_CHOICE_REQUIRED_RETRY)

    if not workspace_id and user_id:
        _raw_cid_pref = body.get("conversation_id")
        if _raw_cid_pref is not None:
            _cid_pref_s = str(_raw_cid_pref).strip()
            if _cid_pref_s:
                try:
                    _cid_pref = uuid.UUID(_cid_pref_s)
                    with db.pool().connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                SELECT pref_workspace_id FROM chat_conversations
                                WHERE id = %s AND user_id = %s
                                """,
                                (_cid_pref, user_id),
                            )
                            _pw = cur.fetchone()
                        conn.commit()
                    if _pw and _pw[0]:
                        workspace_id = str(_pw[0])
                        workspace_bound_from_conversation = True
                except (ValueError, TypeError):
                    pass
                except Exception as e:
                    logger.debug("pref_workspace load skipped: %s", e)

    # Load DB user first so workspace resolution (e.g. agentlayer-self gates) sees real role.
    user_obj = None
    if user_id:
        try:
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

    _role_for_agent = None
    if user_obj is not None:
        _role_for_agent = getattr(user_obj, "role", None)
    if _role_for_agent is None and user_id:
        try:
            _role_for_agent = db.user_role(user_id)
        except Exception:
            _role_for_agent = bearer_user_role
    if _role_for_agent is None:
        _role_for_agent = bearer_user_role

    if agent_id and not embedded_subagent:
        from apps.backend.domain.agent_runtime.access import user_may_invoke_agent

        ok_agent, agent_err = user_may_invoke_agent(_role_for_agent, agent_id)
        if not ok_agent:
            raise ValueError(agent_err)

    is_admin = _is_elevated_admin(user_obj, bearer_user_role, user_id)

    if workspace_id and user_id:
        try:
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
    elif user_id and not workspace_id and _extract_https_git_url(_bootstrap_last_user):
        ws_auto = _try_auto_create_workspace_from_git_url(
            agent_id=agent_id if isinstance(agent_id, str) else None,
            user_id=user_id,
            user_obj=user_obj,
            last_user_text=_bootstrap_last_user,
            embedded_subagent=embedded_subagent,
        )
        if ws_auto:
            workspace = ws_auto
            workspace_id = str(ws_auto.get("id") or "")
            workspace_auto_created = True

    _raise_if_workspace_inaccessible(
        workspace_id=workspace_id,
        user_id=user_id,
        workspace=workspace if isinstance(workspace, dict) else None,
        agent_id=agent_id if isinstance(agent_id, str) else None,
    )

    workspace_token = set_workspace(workspace)

    # Prepare context dict for tools (DDD-style, with real objects)
    tool_context: dict[str, Any] = {"user": user_obj}
    if agent_storage_images:
        tool_context["agent_storage_images_pending"] = [dict(x) for x in agent_storage_images]
        tool_context["agent_storage_images_uploaded"] = 0
    if workspace and isinstance(workspace, dict):
        if workspace.get("id"):
            tool_context["workspace_id"] = str(workspace["id"])
        _p = workspace.get("path")
        if isinstance(_p, str) and _p.strip():
            tool_context["workspace"] = workspace
        if agent_id in ("coding", "coding_plan"):
            try:
                maybe_schedule_index_on_attach(workspace)
            except Exception as e:
                logger.debug("index-on-attach skipped: %s", e)
    if cancel_event is not None:
        tool_context["cancel_event"] = cancel_event

    if isinstance(pre_run_id, str) and pre_run_id.strip():
        try:
            agent_run_id = str(uuid.UUID(pre_run_id.strip()))
        except (ValueError, TypeError):
            agent_run_id = str(uuid.uuid4())
    else:
        agent_run_id = str(uuid.uuid4())
    tool_context["agent_run_id"] = agent_run_id
    tool_context["embedded_subagent"] = embedded_subagent
    parent_cancel_bridge_task: asyncio.Task[None] | None = None
    if not embedded_subagent:
        from apps.backend.domain.agent_runtime.run_cancel import register_parent_cancel

        register_parent_cancel(agent_run_id)
        if cancel_event is not None:

            async def _propagate_cancel_to_subagents() -> None:
                await cancel_event.wait()
                from apps.backend.domain.agent_runtime.run_cancel import signal_parent_cancel

                signal_parent_cancel(agent_run_id)

            parent_cancel_bridge_task = asyncio.create_task(_propagate_cancel_to_subagents())
    elif parent_agent_run_id:
        from apps.backend.domain.agent_runtime.run_cancel import link_run_to_cancel_root

        link_run_to_cancel_root(agent_run_id, parent_agent_run_id)
    llm_wait_token = None
    if event_emit is not None:
        try:
            _loop = asyncio.get_running_loop()

            def _agent_subagent_notify(payload: dict[str, Any]) -> None:
                ev = dict(payload)
                ev.setdefault("parent_agent_run_id", agent_run_id)
                ev.setdefault("agent_run_id", agent_run_id)
                asyncio.run_coroutine_threadsafe(event_emit(ev), _loop)

            def _notify_llm_slot_wait(payload: dict[str, Any]) -> None:
                ev = dict(payload)
                ev.setdefault("parent_agent_run_id", agent_run_id)
                ev.setdefault("agent_run_id", agent_run_id)
                asyncio.run_coroutine_threadsafe(event_emit(ev), _loop)

            def _deferred_wait_notify(payload: dict[str, Any]) -> None:
                ev = dict(payload)
                ev.setdefault("type", "agent.deferred_wait")
                ev.setdefault("parent_agent_run_id", agent_run_id)
                ev.setdefault("agent_run_id", agent_run_id)
                asyncio.run_coroutine_threadsafe(event_emit(ev), _loop)

            llm_wait_token = bind_llm_wait_notifier(_notify_llm_slot_wait)
            tool_context["agent_subagent_notify"] = _agent_subagent_notify
            tool_context["deferred_wait_notify"] = _deferred_wait_notify
        except RuntimeError:
            pass
    tool_context["workspace_verify_succeeded"] = False
    tool_context["permission_always_allow_tools"] = set()
    _abf = _agent_behavior_flags(agent_id if isinstance(agent_id, str) else None)
    tool_context["agent_coding_tools_permission_ask"] = _abf["coding_tools_permission_ask"]
    tool_context["agent_unattended"] = agent_unattended
    if isinstance(agent_id, str) and agent_id.strip():
        tool_context["agent_id"] = agent_id.strip()
    if agent_delegate_mode:
        tool_context["agent_delegate_mode"] = agent_delegate_mode
        if agent_delegate_mode == "git_forensics":
            tool_context["agent_plan_delegate_mode"] = agent_delegate_mode
    if delegate_allowed_paths:
        tool_context["agent_delegate_allowed_paths"] = delegate_allowed_paths
    if delegate_required_branch:
        tool_context["agent_delegate_required_branch"] = delegate_required_branch
    if isinstance(handoff_collector, list):
        tool_context["handoff_artifact_collector"] = handoff_collector
    _raw_conversation_id = body.pop("conversation_id", None)
    conversation_uuid: uuid.UUID | None = None
    if _raw_conversation_id is not None:
        _cid_s = str(_raw_conversation_id).strip()
        if _cid_s:
            tool_context["conversation_id"] = _cid_s
            try:
                conversation_uuid = uuid.UUID(_cid_s)
            except (ValueError, TypeError):
                conversation_uuid = None
    active_task_id: str | None = None
    _task_uuid_for_run: uuid.UUID | None = None
    _active_task_candidate: str | None = None
    if isinstance(active_task_body, str) and active_task_body.strip():
        _active_task_candidate = active_task_body.strip()
    elif conversation_uuid is not None and user_id is not None:
        try:
            with db.pool().connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT active_task_id FROM chat_conversations WHERE id = %s AND user_id = %s",
                        (conversation_uuid, user_id),
                    )
                    row = cur.fetchone()
                conn.commit()
            if row and row[0]:
                _active_task_candidate = str(row[0])
        except Exception:
            pass
    if _active_task_candidate and user_id is not None and tenant_id is not None:
        from apps.backend.domain.agent_runtime.run_persistence import (
            clear_conversation_active_task,
            resolve_valid_active_task_id,
        )

        active_task_id, _task_uuid_for_run = resolve_valid_active_task_id(
            tenant_id=int(tenant_id),
            user_id=user_id,
            candidate=_active_task_candidate,
        )
        if active_task_id is None and conversation_uuid is not None:
            if _active_task_candidate == active_task_body or _active_task_candidate:
                clear_conversation_active_task(
                    conversation_id=conversation_uuid, user_id=user_id
                )
    elif _active_task_candidate:
        active_task_id = _active_task_candidate
        try:
            _task_uuid_for_run = uuid.UUID(_active_task_candidate)
        except (ValueError, TypeError):
            _task_uuid_for_run = None
    else:
        _task_uuid_for_run = None
    if active_task_id:
        tool_context["agent_task_id"] = active_task_id
    if (
        workspace_auto_created
        and workspace
        and isinstance(workspace, dict)
        and workspace.get("id")
        and conversation_uuid is not None
        and user_id is not None
    ):
        try:
            from apps.backend.domain.workspace.workspace_common import (
                persist_conversation_workspace,
            )

            persist_conversation_workspace(
                tool_context,
                str(workspace["id"]),
                user_id,
            )
        except Exception as e:
            logger.debug("auto-create conversation workspace persist skipped: %s", e)
    _ws_uuid_for_run: uuid.UUID | None = None
    if workspace_id:
        try:
            _ws_uuid_for_run = uuid.UUID(str(workspace_id).strip())
        except (ValueError, TypeError):
            _ws_uuid_for_run = None
    _parent_run_uuid: uuid.UUID | None = None
    if parent_agent_run_id:
        try:
            _parent_run_uuid = uuid.UUID(parent_agent_run_id)
        except (ValueError, TypeError):
            _parent_run_uuid = None
    run_persisted = False
    run_persist_warnings: list[str] = []
    if user_id is not None and tenant_id is not None:
        _run_row, run_persist_warnings = agent_runs_store.insert_run_start_resilient(
            run_id=uuid.UUID(agent_run_id),
            tenant_id=int(tenant_id),
            user_id=user_id,
            agent_id=agent_id if isinstance(agent_id, str) else None,
            task_id=_task_uuid_for_run,
            parent_run_id=_parent_run_uuid,
            conversation_id=conversation_uuid,
            workspace_id=_ws_uuid_for_run,
            embedded_subagent=embedded_subagent,
        )
        run_persisted = bool(_run_row)
        for _w in run_persist_warnings:
            logger.warning("agent_run persist: %s", _w)
    parent_short = _short_run_id(parent_agent_run_id) if parent_agent_run_id else None
    logger.info(
        "run_start run_id=%s agent=%s parent=%s workspace=%s unattended=%s",
        _short_run_id(agent_run_id),
        agent_id or "-",
        parent_short or "-",
        _normalize_workspace_id_for_gate(workspace_id),
        agent_unattended,
    )

    if agent_require_workspace_verify:
        if not workspace or not isinstance(workspace, dict):
            raise ValueError(
                "agent_require_workspace_verify requires workspace_id to resolve to an accessible workspace."
            )

    from apps.backend.domain.tools.invocation_context import (
        reset_agent_run_id,
        reset_agent_task_id,
        set_agent_run_id,
        set_agent_task_id,
    )

    run_ctx_tok = set_agent_run_id(agent_run_id if run_persisted else None)
    task_ctx_tok = set_agent_task_id(active_task_id)
    run_finish_status = "succeeded"
    run_finish_error: str | None = None

    return ChatRunBootstrap(
        workspace_id=workspace_id,
        workspace=workspace if isinstance(workspace, dict) else None,
        workspace_token=workspace_token,
        tenant_id=tenant_id,
        user_id=user_id,
        cfg_tid=cfg_tid,
        router_strict_default=_router_strict_default,
        catalog_after_first_round=_catalog_after_first_round,
        tool_choice_required_retry=_tool_choice_required_retry,
        user_obj=user_obj,
        is_admin=is_admin,
        tool_context=tool_context,
        agent_run_id=agent_run_id,
        bench_run_ctx_token=None,
        parent_cancel_bridge_task=parent_cancel_bridge_task,
        llm_wait_token=llm_wait_token,
        conversation_uuid=conversation_uuid,
        active_task_id=active_task_id,
        run_persisted=run_persisted,
        run_persist_warnings=run_persist_warnings,
        run_ctx_token=run_ctx_tok,
        task_ctx_token=task_ctx_tok,
        run_finish_status=run_finish_status,
        run_finish_error=run_finish_error,
        workspace_auto_created=workspace_auto_created,
        workspace_bound_from_conversation=workspace_bound_from_conversation,
        agent_auto_routed=agent_auto_routed,
    )


__all__ = ["ChatRunBootstrap", "bootstrap_chat_run"]
