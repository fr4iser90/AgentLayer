"""Chat completion with tool-call loop."""
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

from apps.backend.domain.agent_io import *  # noqa: F403, E402
from apps.backend.domain.agent_prompts import *  # noqa: F403, E402
from apps.backend.domain.agent_tools import *  # noqa: F403, E402

# ``import *`` skips ``_``-prefixed names unless listed in ``__all__`` (see PEP 8).


async def chat_completion(
    body: dict[str, Any],
    *,
    router_categories_header: str | None = None,
    tool_domain_header: str | None = None,
    model_profile_header: str | None = None,
    model_override_header: str | None = None,
    user_timezone_header: str | None = None,
    bearer_user_role: str | None = None,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    control_queue: asyncio.Queue | None = None,
    cancel_event: asyncio.Event | None = None,
    stream_requested: bool = False,
    embedded_subagent: bool = False,
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
    if not embedded_subagent:
        dash_id = (
            str(dashboard_ctx.get("dashboard_id") or "").strip()
            if isinstance(dashboard_ctx, dict)
            else ""
        )
        if not agent_id and dash_id:
            agent_id = "dashboard"
        elif not agent_id:
            agent_id = "general"
        _chat_surface_agents = frozenset({"general", "dashboard", "creative"})
        if agent_id == "dashboard" and not dash_id:
            logger.info("chat_completion: dashboard agent requires agent_dashboard_context — using general")
            agent_id = "general"
        elif agent_id not in _chat_surface_agents:
            logger.info(
                "chat_completion: forcing agent_id %r -> general (use delegate for specialists)",
                agent_id,
            )
            agent_id = "general"
    parent_agent_run_id = body.pop("agent_parent_run_id", None)
    if isinstance(parent_agent_run_id, str):
        parent_agent_run_id = parent_agent_run_id.strip() or None
    else:
        parent_agent_run_id = None
    _pre_run_id = body.pop("agent_run_id", None)
    _active_task_body = body.pop("agent_active_task_id", None)
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
    _raw_plan_delegate_mode = body.pop("agent_plan_delegate_mode", None)
    _raw_delegate_mode = body.pop("agent_delegate_mode", None)
    agent_delegate_mode: str | None = None
    for raw in (_raw_delegate_mode, _raw_plan_delegate_mode):
        if isinstance(raw, str) and raw.strip():
            agent_delegate_mode = raw.strip()
            break
    _raw_delegate_paths = body.pop("agent_delegate_allowed_paths", None)
    delegate_allowed_paths: list[str] | None = None
    if isinstance(_raw_delegate_paths, list):
        delegate_allowed_paths = [str(p).strip() for p in _raw_delegate_paths if str(p).strip()]
    _raw_delegate_branch = body.pop("agent_delegate_required_branch", None)
    delegate_required_branch: str | None = None
    if isinstance(_raw_delegate_branch, str):
        delegate_required_branch = _raw_delegate_branch.strip() or None
    _handoff_collector = body.pop("agent_handoff_artifact_collector", None)

    from apps.backend.domain.identity import set_workspace, get_identity
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

    if not workspace_id and user_id:
        _raw_cid_pref = body.get("conversation_id")
        if _raw_cid_pref is not None:
            _cid_pref_s = str(_raw_cid_pref).strip()
            if _cid_pref_s:
                try:
                    from apps.backend.infrastructure.db import db as _db_pref

                    _cid_pref = uuid.UUID(_cid_pref_s)
                    with _db_pref.pool().connection() as conn:
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

    _role_for_agent = None
    if user_obj is not None:
        _role_for_agent = getattr(user_obj, "role", None)
    if _role_for_agent is None and user_id:
        try:
            from apps.backend.infrastructure.db import db as _role_db

            _role_for_agent = _role_db.user_role(user_id)
        except Exception:
            _role_for_agent = bearer_user_role
    if _role_for_agent is None:
        _role_for_agent = bearer_user_role

    if agent_id and not embedded_subagent:
        from apps.backend.domain.agent_access import user_may_invoke_agent

        ok_agent, agent_err = user_may_invoke_agent(_role_for_agent, agent_id)
        if not ok_agent:
            raise ValueError(agent_err)

    _is_admin = _is_elevated_admin(user_obj, bearer_user_role, user_id)

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
    if workspace and isinstance(workspace, dict):
        if workspace.get("id"):
            tool_context["workspace_id"] = str(workspace["id"])
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

    if isinstance(_pre_run_id, str) and _pre_run_id.strip():
        try:
            agent_run_id = str(uuid.UUID(_pre_run_id.strip()))
        except (ValueError, TypeError):
            agent_run_id = str(uuid.uuid4())
    else:
        agent_run_id = str(uuid.uuid4())
    tool_context["agent_run_id"] = agent_run_id
    _llm_wait_token = None
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

            from apps.backend.infrastructure.llm_concurrency import bind_llm_wait_notifier

            _llm_wait_token = bind_llm_wait_notifier(_notify_llm_slot_wait)
            tool_context["agent_subagent_notify"] = _agent_subagent_notify
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
    if isinstance(_handoff_collector, list):
        tool_context["handoff_artifact_collector"] = _handoff_collector
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
    if isinstance(_active_task_body, str) and _active_task_body.strip():
        _active_task_candidate = _active_task_body.strip()
    elif conversation_uuid is not None and user_id is not None:
        try:
            from apps.backend.infrastructure.db import db

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
        from apps.backend.domain.agent_run_persistence import (
            clear_conversation_active_task,
            resolve_valid_active_task_id,
        )

        active_task_id, _task_uuid_for_run = resolve_valid_active_task_id(
            tenant_id=int(tenant_id),
            user_id=user_id,
            candidate=_active_task_candidate,
        )
        if active_task_id is None and conversation_uuid is not None:
            if _active_task_candidate == _active_task_body or _active_task_candidate:
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
    _run_persisted = False
    _run_persist_warnings: list[str] = []
    if user_id is not None and tenant_id is not None:
        from apps.backend.infrastructure import agent_runs_store

        _run_row, _run_persist_warnings = agent_runs_store.insert_run_start_resilient(
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
        _run_persisted = bool(_run_row)
        for _w in _run_persist_warnings:
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

    from apps.backend.domain.tool_invocation_context import (
        reset_agent_run_id,
        reset_agent_task_id,
        set_agent_run_id,
        set_agent_task_id,
    )

    _run_ctx_tok = set_agent_run_id(agent_run_id if _run_persisted else None)
    _task_ctx_tok = set_agent_task_id(active_task_id)
    _run_finish_status = "succeeded"
    _run_finish_error: str | None = None

    try:

        max_tool_rounds_eff = (
            config.SUBAGENT_MAX_TOOL_ROUNDS
            if embedded_subagent
            else config.MAX_TOOL_ROUNDS
        )
        if not embedded_subagent and _raw_max_rounds is not None:
            try:
                client_v = int(_raw_max_rounds)
                if client_v <= 0:
                    max_tool_rounds_eff = config.MAX_TOOL_ROUNDS
                else:
                    upper = (
                        config.MAX_TOOL_ROUNDS
                        if config.MAX_TOOL_ROUNDS < config.MAX_TOOL_ROUNDS_CAP
                        else config.MAX_TOOL_ROUNDS_CAP
                    )
                    max_tool_rounds_eff = max(1, min(client_v, upper))
            except (TypeError, ValueError):
                pass

        _chat_history_raw = list(body.get("messages") or [])
        _context_prep_meta: dict[str, Any] = {}
        _compaction_attempt: tuple[str, dict[str, str], str, str] | None = None
        _prep_context_budget = None
        if config.CHAT_CONTEXT_PREP_ENABLED and _chat_history_raw:
            from apps.backend.infrastructure.chat_context import prepare_chat_history_for_llm
            from apps.backend.infrastructure.context_budget import resolve_context_budget
            from apps.backend.infrastructure.operator_settings import llm_chat_transport

            _prep_model, _, _prep_profile, _prep_override = resolve_effective_model(
                messages=_chat_history_raw,
                body_model=body.get("model"),
                profile_header=model_profile_header,
                override_header=model_override_header,
                bearer_user_role=bearer_user_role,
            )
            _prep_catalog = catalog_owned_by
            if not plain_completion:
                from apps.backend.domain.catalog_chat_llm import finalize_catalog_chat_llm

                _prep_model, _prep_catalog = finalize_catalog_chat_llm(
                    model=_prep_model,
                    profile_key=_prep_profile,
                    is_override=_prep_override,
                    catalog_owned_by=_prep_catalog,
                )
            if _prep_catalog:
                try:
                    _prep_attempts, _ = llm_chat_transport(
                        _prep_model,
                        _prep_profile,
                        _prep_override,
                        catalog_owned_by=_prep_catalog,
                    )
                    if _prep_attempts:
                        _compaction_attempt = _prep_attempts[0]
                except ValueError as e:
                    logger.warning("chat context compaction: LLM transport unavailable: %s", e)

            _prep_context_budget = resolve_context_budget(
                str(_prep_model or ""),
                catalog_owned_by=_prep_catalog,
            )

            _chat_history_raw, _ctx_meta = await prepare_chat_history_for_llm(
                _chat_history_raw,
                conversation_id=conversation_uuid,
                user_id=user_id if isinstance(user_id, uuid.UUID) else None,
                compaction_model=_prep_model,
                compaction_attempt=_compaction_attempt,
                context_budget=_prep_context_budget,
            )
            body["messages"] = _chat_history_raw
            _context_prep_meta = _ctx_meta.as_dict()
        tool_context["chat_context_meta"] = _context_prep_meta

        messages = _inject_system_prompt(list(body.get("messages") or []))
        from apps.backend.infrastructure.chat_secret_ingress import ingress_openai_messages_inplace

        ingress_openai_messages_inplace(messages, tenant_id=int(tenant_id), user_id=user_id)
        _ingested_audio: list[dict[str, Any]] = []
        if user_id is not None and tenant_id is not None and isinstance(user_id, uuid.UUID):
            from apps.backend.domain.chat_audio_attachments import (
                format_ingested_audio_system_block,
                ingest_chat_audio_attachments,
            )

            _ingested_audio = ingest_chat_audio_attachments(
                messages, tenant_id=int(tenant_id), user_id=user_id
            )
            _audio_block = format_ingested_audio_system_block(_ingested_audio)
            if _audio_block:
                messages = _append_system_block(messages, _audio_block)
        messages = _inject_dashboard_context(messages, dashboard_ctx)
        if agent_id:
            messages = _inject_agent_system_prompt(messages, agent_id)
        if agent_id == "general":
            from apps.backend.domain.embedded_subagent import (
                build_delegate_agents_catalog_snippet,
            )

            messages = _append_system_block(
                messages, build_delegate_agents_catalog_snippet(caller_is_admin=_is_admin)
            )
            from apps.backend.domain.agent_task_prompt import build_agent_tasks_context_snippet

            tasks_snip = build_agent_tasks_context_snippet(active_task_id=active_task_id)
            if tasks_snip:
                messages = _append_system_block(messages, tasks_snip)
        if agent_id in ("general", "dashboard") and user_id is not None and tenant_id is not None:
            from apps.backend.domain.media_chat_prompt import build_media_library_context_snippet

            _media_snip = build_media_library_context_snippet(
                user_id=user_id if isinstance(user_id, uuid.UUID) else None,
                tenant_id=int(tenant_id),
                ingested_audio=_ingested_audio,
                caller_is_admin=_is_admin,
            )
            if _media_snip:
                messages = _append_system_block(messages, _media_snip)
        if agent_id and agent_id in config.AGENT_SKILLS_PROMPT_AGENT_IDS:
            from apps.backend.infrastructure.skills_prompt import load_combined_skills_prompt

            skills_snip = load_combined_skills_prompt(agent_id)
            if skills_snip:
                messages = _append_system_block(messages, skills_snip)
        pf = body.get("tool_prefetch")
        if isinstance(pf, dict):
            _apply_tool_prefetch(messages, pf)
        messages = apply_user_persona_system(messages)
        from apps.backend.domain.current_time_context import apply_current_time_context

        messages = apply_current_time_context(
            messages,
            user_id,
            tenant_id,
            request_timezone=user_timezone_header,
        )
        messages = _inject_user_memory_context(messages, dashboard_ctx)
        messages = _inject_user_secrets_bootstrap(messages, user_id)
        messages = _inject_workspace_bound_context(
            messages, workspace, agent_id if isinstance(agent_id, str) else None
        )
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
        if not plain_completion:
            from apps.backend.domain.catalog_chat_llm import finalize_catalog_chat_llm

            model, catalog_owned_by = finalize_catalog_chat_llm(
                model=model,
                profile_key=profile_key,
                is_override=model_is_override,
                catalog_owned_by=catalog_owned_by,
            )
        tool_context["parent_effective_model"] = model
        if catalog_owned_by:
            tool_context["parent_model_catalog_owned_by"] = catalog_owned_by
        from apps.backend.infrastructure.context_budget import resolve_context_budget, usage_prompt_tokens
        from apps.backend.infrastructure.chat_context import apply_budget_to_meta, ContextPrepMeta, update_meta_from_provider_usage

        _context_budget = resolve_context_budget(
            str(model or ""),
            catalog_owned_by=catalog_owned_by if isinstance(catalog_owned_by, str) else None,
        )
        tool_context["_context_budget"] = _context_budget
        if _compaction_attempt is not None:
            tool_context["_compaction_model"] = str(model or "")
            tool_context["_compaction_attempt"] = _compaction_attempt
        if _context_budget is not None:
            _meta_obj = ContextPrepMeta()
            apply_budget_to_meta(_meta_obj, _context_budget)
            for key, val in _meta_obj.as_dict().items():
                if val is not None and val != "" and val != 0:
                    _context_prep_meta[key] = val
            tool_context["chat_context_meta"] = _context_prep_meta
            from apps.backend.infrastructure.context_budget import completion_quotas_from_budget

            _quotas = completion_quotas_from_budget(_context_budget)
            logger.info(
                "chat context budget: model=%r window=%d soft=%d hard=%d tools=%d max_tools=%d source=%s",
                model,
                _context_budget.context_window_tokens,
                _context_budget.soft_limit_tokens,
                _context_budget.hard_limit_tokens,
                _quotas.tools_budget_tokens,
                _quotas.max_tool_count,
                _context_budget.source,
            )
        elif str(model or "").strip():
            logger.warning(
                "chat context budget: no context window for model=%r provider=%r — "
                "set CHAT_CONTEXT_MODEL_BUDGET_OVERRIDES or ensure GET /v1/models exposes n_ctx",
                model,
                catalog_owned_by,
            )
        smart_route_reason = ""
        backend_override: Literal["provider", "provider_admin"] | None = None
        if isinstance(_raw_llm_be, str):
            lo = _raw_llm_be.strip().lower()
            if lo in ("provider",):
                backend_override = "provider"
            elif lo == "provider_admin":
                backend_override = "provider_admin"
        if backend_override is None and not plain_completion and smart_llm_routing_enabled():
            # Smart routing: 0–1 extra local router call, then one main completion — never two externals.
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
            logger.debug("chat_completion: agent_plain_completion (no tools forwarded to local provider)")
        else:
            merged_tools = _merge_tools(body.get("tools"))
        routed_category: str | None = None
        logger.debug("tool_domain before check: %r, agent_id=%r", tool_domain, agent_id)
        if agent_id:
            agent = get_agent_registry().get_agent(agent_id)
            if agent:
                tool_domain_agent = agent.get("tool_domain")
                tool_names_agent = agent.get("tool_names", [])
                if tool_domain_agent:
                    merged_tools = filter_merged_tools_by_domain(merged_tools, tool_domain_agent)
                if tool_names_agent:
                    allowed_tool_names = frozenset(tool_names_agent)
                    merged_tools = [
                        t
                        for t in merged_tools
                        if (n := _tool_spec_name(t)) is None or n in allowed_tool_names
                    ]
                logger.debug(
                    "agent %s: %d tools after allowlist (domain=%s, explicit_names=%s)",
                    agent_id,
                    len(merged_tools),
                    tool_domain_agent,
                    bool(tool_names_agent),
                )
            else:
                logger.warning("agent_id %r not found in registry, falling back to tool_domain", agent_id)
        elif tool_domain:
            merged_tools = filter_merged_tools_by_domain(merged_tools, tool_domain)
        cats = classify_user_tool_categories(last_user_text(messages))
        cats = cats | extra_cats_body | extra_cats_hdr
        merged_tools = filter_merged_tools_by_categories(merged_tools, cats)
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

        if config.AGENT_TOOLS_DENYLIST:
            deny = config.AGENT_TOOLS_DENYLIST
            merged_tools = [
                t
                for t in merged_tools
                if (n := _tool_spec_name(t)) is None or n not in deny
            ]
        tools_allowlist_count = len(merged_tools)

        ranking_user_text: str | None = None
        for msg in reversed(body.get("messages", [])):
            if msg.get("role") == "user":
                c = msg.get("content")
                ranking_user_text = c if isinstance(c, str) else None
                break

        from apps.backend.domain.agent_turn_hooks import turn_hooks_for_agent
        from apps.backend.domain.tool_forward_policy import (
            ToolForwardContext,
            apply_schema_modes_to_specs,
            build_tool_forward_plan,
            infer_model_tier,
        )

        turn_hooks = turn_hooks_for_agent(agent_id if isinstance(agent_id, str) else None)
        turn_hooks.prepare_tool_context(tool_context, ranking_user_text=ranking_user_text)

        _ctx_win = 0
        if _context_budget is not None:
            _ctx_win = int(_context_budget.context_window_tokens or 0)
        _model_tier = infer_model_tier(
            model_id=str(model or ""),
            catalog_owned_by=catalog_owned_by if isinstance(catalog_owned_by, str) else None,
        )
        _tf_plan = build_tool_forward_plan(
            ToolForwardContext(
                agent_id=agent_id if isinstance(agent_id, str) else None,
                model_id=str(model or ""),
                context_window_tokens=_ctx_win,
                model_tier=_model_tier,
                user_text=ranking_user_text or "",
                tool_specs=merged_tools,
                ranking_enabled=tools_ranking_enabled,
                full_schema_preference=tools_full_schema,
                category_routed=bool(cats),
            )
        )
        tools_for_request = apply_schema_modes_to_specs(
            _tf_plan.forward_specs,
            _tf_plan.schema_mode_per_tool,
            default_full_schema=tools_full_schema,
        )
        tools_pre_rank_count = tools_allowlist_count
        tools_rank_pool_count = int(_tf_plan.meta.get("rank_pool_count") or 0)
        tools_pinned_count = len(_tf_plan.pins_included)
        tools_ranked_count = max(0, len(tools_for_request) - tools_pinned_count)

        forward_names = list(_tf_plan.forward_names)
        if not config.AGENT_LOG_TOOL_PIPELINE and tools_for_request:
            logger.info(
                "tool forward: tier=%s window=%d allowlist=%d forward=%d pins=%s",
                _model_tier,
                _ctx_win,
                tools_allowlist_count,
                len(forward_names),
                _tf_plan.pins_included,
            )
        if config.AGENT_LOG_TOOL_PIPELINE:
            _log_agent_tools_pipeline(
                agent_run_id=agent_run_id,
                agent_id=agent_id if isinstance(agent_id, str) else None,
                allowlist_count=tools_allowlist_count,
                pre_rank_count=tools_pre_rank_count,
                rank_pool_count=tools_rank_pool_count,
                ranked_count=tools_ranked_count,
                pinned_count=tools_pinned_count,
                forward_count=len(forward_names),
                tools_full_schema=tools_full_schema,
                routed_category=routed_category,
                forward_names=forward_names,
                tools_for_request=tools_for_request,
            )
        elif tools_for_request:
            logger.info(
                "forwarding %d tools in chat request (llm_model_id=%s, category=%s): %s",
                len(forward_names),
                model,
                routed_category or "full",
                forward_names,
            )
        if not plain_completion and tools_for_request:
            messages = _append_tool_usage_discipline(
                messages,
                agent_id=agent_id,
                delegate_mode=agent_delegate_mode,
            )
        pause_between_rounds = _coerce_body_bool(body.get("agent_pause_between_rounds"), False)
        if pause_between_rounds and control_queue is None:
            pause_between_rounds = False

        options = {
            k: v
            for k, v in body.items()
            if k not in ("messages", "model", "tools", "stream", *_BODY_KEYS_STRIP_FROM_LLM)
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
                    timeout=config.LLM_CHAT_TIMEOUT_SEC,
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
                if m.get("type") == "secret_saved" and m.get("ok") is True:
                    sk = str(m.get("service_key") or "").strip().lower()
                    if sk:
                        messages.append(
                            {
                                "role": "system",
                                "content": (
                                    f"[User saved secret via UI] service_key={sk} — "
                                    "do not ask for this key again; retry the integration tool that failed."
                                ),
                            }
                        )
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
                    "type": "agent.context_update",
                    "agent_run_id": agent_run_id,
                    "context": dict(tool_context.get("chat_context_meta") or {}),
                }
            )
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
                    "workspace_bound": workspace_bound_from_conversation,
                    "agent_auto_routed": agent_auto_routed,
                    "context": tool_context.get("chat_context_meta") or None,
                }
            )

        chosen: tuple[str, dict[str, str], str, str] | None = None
        thrash_key: str | None = None
        thrash_count = 0
        doom_key: str | None = None
        doom_count = 0
        force_no_tools_round = False
        force_no_tools_reason: str | None = None  # "thrash" | "doom"

        async def _emit_context_ws(
            *,
            compacted: bool = False,
            phase: str = "loop",
            reason: str = "",
            round_num: int | None = None,
        ) -> None:
            if not event_emit:
                return
            ctx = dict(tool_context.get("chat_context_meta") or {})
            await event_emit(
                {
                    "type": "agent.context_update",
                    "agent_run_id": agent_run_id,
                    "context": ctx,
                }
            )
            if not compacted:
                return
            await event_emit(
                {
                    "type": "agent.context_compacted",
                    "agent_run_id": agent_run_id,
                    "phase": phase,
                    "reason": reason,
                    "round": round_num,
                    "context": ctx,
                    "provider_prompt_tokens": ctx.get("provider_prompt_tokens"),
                    "soft_limit_tokens": ctx.get("soft_limit_tokens"),
                    "context_window_tokens": ctx.get("context_window_tokens"),
                    "tool_rounds_dropped": ctx.get("tool_rounds_dropped"),
                    "budget_source": ctx.get("budget_source"),
                    "summary_active": ctx.get("summary_active"),
                }
            )

        async def _enforce_agent_context_budget(
            reason: str,
            provider_prompt_tokens: int | None,
            *,
            round_num: int | None = None,
        ) -> None:
            nonlocal _context_prep_meta
            from apps.backend.infrastructure.chat_context_loop import apply_agent_loop_context_budget

            budget = tool_context.get("_context_budget")
            new_msgs, loop_sum, patch = await apply_agent_loop_context_budget(
                messages,
                context_budget=budget,
                provider_prompt_tokens=provider_prompt_tokens,
                loop_summary=str(tool_context.get("agent_loop_context_summary") or ""),
                compaction_model=str(tool_context.get("_compaction_model") or model or ""),
                compaction_attempt=tool_context.get("_compaction_attempt"),
            )
            if new_msgs is not messages:
                messages[:] = new_msgs
            if loop_sum:
                tool_context["agent_loop_context_summary"] = loop_sum
            if provider_prompt_tokens is not None and provider_prompt_tokens > 0:
                tool_context["last_provider_prompt_tokens"] = provider_prompt_tokens
            compacted = bool(
                patch.get("loop_compaction_applied") or patch.get("trim_applied")
            )
            if compacted or patch:
                _context_prep_meta.update({k: v for k, v in patch.items() if v is not None})
            if compacted:
                _context_prep_meta["compaction_applied"] = True
                _context_prep_meta["loop_compaction_applied"] = bool(
                    patch.get("loop_compaction_applied")
                )
                logger.info("chat context budget (%s): %s", reason, patch)
            if provider_prompt_tokens is not None and budget is not None:
                _meta_obj = ContextPrepMeta()
                apply_budget_to_meta(_meta_obj, budget)
                update_meta_from_provider_usage(_meta_obj, budget, provider_prompt_tokens)
                for key in (
                    "provider_prompt_tokens",
                    "at_soft_limit",
                    "at_hard_limit",
                ):
                    _context_prep_meta[key] = getattr(_meta_obj, key)
            tool_context["chat_context_meta"] = _context_prep_meta
            if (
                compacted
                or provider_prompt_tokens is not None
                or _context_prep_meta.get("context_window_tokens")
            ):
                await _emit_context_ws(
                    compacted=compacted,
                    phase="loop",
                    reason=reason,
                    round_num=round_num,
                )

        if not plain_completion and tools_for_request:
            messages.append(
                {
                    "role": "system",
                    "content": _agent_tool_budget_system_message(max_tool_rounds_eff),
                }
            )
            await _enforce_agent_context_budget(
                "before_tool_loop",
                tool_context.get("last_provider_prompt_tokens"),
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
                if round_i > 0 and config.AGENT_TOOLS_CATALOG_AFTER_FIRST_ROUND and tools_for_round:
                    catalog_modes = {
                        n: "catalog"
                        for spec in _tf_plan.forward_specs
                        if isinstance(spec, dict)
                        and isinstance(spec.get("function"), dict)
                        and (n := str(spec["function"].get("name") or "").strip())
                    }
                    if catalog_modes:
                        tools_for_round = apply_schema_modes_to_specs(
                            _tf_plan.forward_specs,
                            catalog_modes,
                            default_full_schema=False,
                        )
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

            await _enforce_agent_context_budget(
                f"round_{round_i + 1}_pre_llm",
                tool_context.get("last_provider_prompt_tokens"),
                round_num=round_i + 1,
            )

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

            async def _emit_llm_reasoning_delta(s: str) -> None:
                if not s or event_emit is None:
                    return
                await event_emit(
                    {
                        "type": "agent.llm_delta",
                        "agent_run_id": agent_run_id,
                        "round": round_no,
                        "channel": "reasoning",
                        "reasoning_delta": s,
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
                turn_hooks.apply_payload_tool_choice(
                    payload_base,
                    tool_context,
                    allowed_names=allowed_names,
                    round_i=round_i,
                    max_rounds=max_tool_rounds_eff,
                )

            last_failover: httpx.HTTPStatusError | None = None
            last_transport_error: httpx.RequestError | None = None
            chosen: tuple[str, dict[str, str], str, str] | None = None
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
                            on_reasoning_delta=_emit_llm_reasoning_delta,
                            cancel_event=cancel_event,
                            timeout=config.LLM_CHAT_TIMEOUT_SEC,
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
                for attempt in attempts:
                    from apps.backend.infrastructure.llm_chat_attempt import unpack_llm_attempt

                    b_url, b_headers, b_model, b_provider = unpack_llm_attempt(attempt)
                    pl = dict(payload_base)
                    pl["model"] = b_model
                    try:
                        data, tools_omitted = await _thread_with_cancel(
                            cancel_event,
                            http_post_chat_completions,
                            b_url,
                            pl,
                            headers=b_headers,
                            timeout=config.LLM_CHAT_TIMEOUT_SEC,
                            concurrency_provider_id=b_provider or None,
                        )
                        chosen = attempt
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
                        if llm_backend == "provider_admin" and external_llm_should_failover(sc):
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
                            llm_backend == "provider_admin"
                            and last_failover.response.status_code == 429
                        ):
                            local_model = profile_default_model_id(profile_key)
                            attempts, llm_backend = llm_chat_transport(
                                local_model,
                                profile_key,
                                False,
                                backend_override="provider",
                                catalog_owned_by=None,
                            )
                            model = local_model
                            logger.warning(
                                "LLM external: all endpoints returned 429 (quota/rate limit); "
                                "falling back to local catalog provider for this request (llm_model_id=%s). Next rounds use local.",
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

            if not tool_calls and tools_for_round:
                recovered = turn_hooks.recover_tool_calls_from_message(
                    msg,
                    allowed_tool_names=allowed_names,
                    tools_for_round=tools_for_round,
                )
                if recovered:
                    from apps.backend.domain.assistant_display_sanitize import (
                        sanitize_assistant_display_text,
                    )

                    tool_calls = recovered
                    had_native_tool_calls = False
                    msg = dict(msg)
                    msg["tool_calls"] = recovered
                    raw_c = msg.get("content")
                    if isinstance(raw_c, str):
                        msg["content"] = sanitize_assistant_display_text(raw_c) or ""
                    choice0 = dict(choice0)
                    choice0["message"] = msg
                    ch_list = data.get("choices")
                    if isinstance(ch_list, list) and ch_list and isinstance(ch_list[0], dict):
                        ch_list[0] = choice0
                    logger.info(
                        "agent turn hook: recovered tool_call(s) from assistant text (round %d)",
                        round_i + 1,
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
                            timeout=config.LLM_CHAT_TIMEOUT_SEC,
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
                            timeout=config.LLM_CHAT_TIMEOUT_SEC,
                        )
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (400, 422):
                        logger.warning(
                            "Local provider rejected tool_choice=required (status=%s); keeping first completion. body~=%s",
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
                agent_run_id=agent_run_id,
                agent_id=agent_id if isinstance(agent_id, str) else None,
                round_i=round_i,
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
                _prompt_tok = usage_prompt_tokens(usage_out) if usage_out else None
                if _prompt_tok is not None:
                    await _enforce_agent_context_budget(
                        f"round_{round_i + 1}_post_llm",
                        _prompt_tok,
                        round_num=round_i + 1,
                    )
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
                if turn_hooks.sanitize_completion(data):
                    logger.info(
                        "agent turn hook: sanitized assistant display text (round %s/%s)",
                        round_i + 1,
                        max_tool_rounds_eff,
                    )
                nudge_content = turn_hooks.maybe_nudge_text_only_turn(
                    tool_context,
                    allowed_names=allowed_names,
                    round_i=round_i,
                )
                if nudge_content:
                    messages.append(msg)
                    messages.append({"role": "system", "content": nudge_content})
                    continue
                if event_emit:
                    await event_emit(
                        {
                            "type": "agent.done",
                            "agent_run_id": agent_run_id,
                            "kind": "final_text",
                            "round": round_i + 1,
                        }
                    )
                return _completion_attach_agent_run_id(
                    data,
                    agent_run_id,
                    context_meta=_context_prep_meta or None,
                    run_persisted=_run_persisted,
                    run_persist_warnings=_run_persist_warnings or None,
                )
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
                args_line = _format_normalized_tool_args_for_recap(name, args, max_len=200)
                validation_err = validate_tool_call_arguments(name, args)
                rejected = validation_err is not None
                if rejected:
                    result = format_tool_call_validation_error(validation_err)
                    ok_sum, err_sum = False, str(validation_err.get("message") or "invalid tool arguments")
                    logger.info(
                        "tool_exec rejected run_id=%s agent=%s round=%d tool=%s empty_or_invalid args",
                        _short_run_id(agent_run_id),
                        agent_id if isinstance(agent_id, str) else "-",
                        round_i + 1,
                        name,
                    )
                else:
                    logger.info(
                        "tool_exec run_id=%s agent=%s round=%d tool=%s %s",
                        _short_run_id(agent_run_id),
                        agent_id if isinstance(agent_id, str) else "-",
                        round_i + 1,
                        name,
                        args_line,
                    )
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
                    from apps.backend.domain.tool_step_label import format_tool_step_label_from_args

                    _tool_label: str | None = None
                    try:
                        _tool_label = get_registry().display_label_for_tool(name)
                    except Exception:
                        _tool_label = None
                    _step_label = format_tool_step_label_from_args(
                        name,
                        args,
                        tool_label=_tool_label,
                    )
                    _tool_start_ev: dict[str, Any] = {
                        "type": "agent.tool_start",
                        "agent_run_id": agent_run_id,
                        "round": round_i + 1,
                        "name": name,
                        "summary": args_line if not rejected else "rejected: empty or invalid arguments",
                        "step_label": _step_label,
                    }
                    if _tool_label:
                        _tool_start_ev["label"] = _tool_label
                    await event_emit(_tool_start_ev)
                if not rejected:
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
                                result = await _thread_with_cancel(
                                    cancel_event,
                                    execute_tool,
                                    name,
                                    args,
                                    context=tool_context,
                                )
                        else:
                            result = await _thread_with_cancel(
                                cancel_event,
                                execute_tool,
                                name,
                                args,
                                context=tool_context,
                            )
                    finally:
                        reset_tool_invocation_messages(tctx)
                    ok_sum, err_sum = _tool_result_summary(result)
                if (
                    name == "git_read"
                    and ok_sum
                    and str(
                        tool_context.get("agent_delegate_mode")
                        or tool_context.get("agent_plan_delegate_mode")
                        or ""
                    ).strip().lower()
                    == "git_forensics"
                ):
                    op = str(args.get("operation") or args.get("subcommand") or "").strip().lower()
                    if op in ("diff_stat", "diff-stat", "diff"):
                        tool_context["plan_git_diff_seen"] = True
                follow_hint = (
                    None
                    if name in PLANNER_NO_EXTRA_HINTS_AFTER_TOOL
                    else _tool_result_followup_hint(name, result)
                )
                if follow_hint:
                    messages.append({"role": "system", "content": follow_hint[:2500]})
                if ok_sum:
                    from apps.backend.domain.delegate_enforcement import (
                        extract_artifact_ids_from_tool_result,
                        extract_handoff_artifact_ids,
                    )

                    coll = tool_context.get("handoff_artifact_collector")
                    if isinstance(coll, list):
                        for aid in extract_artifact_ids_from_tool_result(result or ""):
                            if aid and aid not in coll:
                                coll.append(aid)
                    if str(tool_context.get("agent_id") or "") == "general":
                        if name == "delegate" and ok_sum:
                            sub_aid = str(args.get("agent_id") or "").strip()
                            refs = args.get("artifact_refs")
                            if sub_aid == "coding" and isinstance(refs, list) and refs:
                                tool_context.pop("orchestrator_pending_artifact_refs", None)
                        else:
                            pending = extract_handoff_artifact_ids(result or "")
                            if pending:
                                tool_context["orchestrator_pending_artifact_refs"] = pending
                record_schedule_tool_event(
                    round_num=round_i + 1,
                    tool_name=name,
                    args=args,
                    ok=ok_sum,
                    error=err_sum if not ok_sum else None,
                )
                if name == "workspace_verify":
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
                    await _emit_secret_prompt_from_tool_result(
                        name,
                        result,
                        event_emit=event_emit,
                        agent_run_id=agent_run_id,
                    )
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
                    hook_extras = turn_hooks.on_tool_done(
                        tool_context,
                        name=name,
                        result=result or "",
                        ok_sum=ok_sum,
                    )
                    if hook_extras:
                        ev_done.update(hook_extras)
                    media_ev = media_play_websocket_event(name, result)
                    if media_ev:
                        ev_done["media_play"] = {
                            k: v for k, v in media_ev.items() if k != "type"
                        }
                    await event_emit(ev_done)
                    if media_ev:
                        await event_emit(media_ev)
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
                param_recovery = (
                    None
                    if name in PLANNER_NO_EXTRA_HINTS_AFTER_TOOL
                    else _tool_parameter_recovery_hint(name, result or "")
                )
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

            await _enforce_agent_context_budget(
                f"round_{round_i + 1}_post_tools",
                tool_context.get("last_provider_prompt_tokens"),
                round_num=round_i + 1,
            )

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
        return _completion_attach_agent_run_id(
            data,
            agent_run_id,
            context_meta=_context_prep_meta or None,
            run_persisted=_run_persisted,
            run_persist_warnings=_run_persist_warnings or None,
        )
    finally:
        if _llm_wait_token is not None:
            from apps.backend.infrastructure.llm_concurrency import reset_llm_wait_notifier

            reset_llm_wait_notifier(_llm_wait_token)
        reset_agent_run_id(_run_ctx_tok)
        reset_agent_task_id(_task_ctx_tok)
        if user_id is not None and tenant_id is not None and _run_persisted:
            try:
                from apps.backend.infrastructure import agent_runs_store

                agent_runs_store.finish_run(
                    run_id=uuid.UUID(agent_run_id),
                    status=_run_finish_status,
                    error=_run_finish_error,
                )
            except Exception:
                logger.warning("agent_runs finish failed run_id=%s", agent_run_id, exc_info=True)
        reset_capability_confirmed(_cap_cf_tok)
        from apps.backend.domain.identity import reset_workspace
        if workspace_token:
            reset_workspace(workspace_token)
