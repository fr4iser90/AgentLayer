"""
WebSocket chat: full-duplex control + real-time agent events per LLM/tool round.

Connect: ``GET /ws/v1/chat?token=<JWT_or_user_API_key>`` (or send ``Authorization: Bearer`` on handshake).

Client → server JSON:
  - ``{"type":"ping"}`` → ``{"type":"pong"}``
  - ``{"type":"cancel"}`` → aborts in-flight ``chat`` (sets cancel flag; next round raises)
  - ``{"type":"add_tools","names":["tool_fn_name",...]}`` → merge allowed tools before next LLM call
  - ``{"type":"continue_step"}`` → after ``agent.step_wait``, resume the tool/LLM loop (see ``agent_pause_between_rounds`` in chat body)
  - ``{"type":"permission_reply","request_id":"…","reply":"once"|"always"|"reject","message":"?"}`` →
        response to ``agent.permission_ask`` (``body.agent_permission_ask`` + agent plugins with ``AGENT_CODING_TOOLS_PERMISSION_ASK``) before a gated tool runs
  - ``{"type":"tool_result","request_id":"…","ok":true,"result":"…"}`` or
        ``{"type":"tool_result","request_id":"…","ok":false,"error":"…"}`` → result of ``agent.tool_invoke``
        (ADR 0009: client-executed workspace tools). Unknown ``request_id`` is ignored.
  - ``{"type":"client_capabilities","workspace_tools":["read_file","bash",…]}`` → tools this client
        can run locally; sent on connect and again on bind. The backend drops the rest from the
        forwarded set for a client-placed workspace.
  - ``{"type":"secret_saved","prompt_id":"…","service_key":"ssc_api_key","ok":true}`` → optional ack after the user saved via the in-chat secret card
  - ``{"type":"chat","body":{...},...}``
        body = OpenAI-style chat completion request (``stream`` ignored).
        Optional ``body.agent_model_catalog_owned_by``: normalized ``GET /v1/models`` row ``owned_by``
        (e.g. ``provider_1``, ``provider_db_1``, ``openrouter``, ``huggingface``) so chat uses the same stack as the dropdown. Unsupported
        values are ignored server-side until routing exists.
        Optional ``body.agent_permission_ask`` (bool): when true and the agent definition has ``coding_tools_permission_ask`` (from ``AGENT_CODING_TOOLS_PERMISSION_ASK`` on the plugin), the server may emit
        ``agent.permission_ask`` before executing gated workspace tools (bash, writes, edits); the client must answer with
        Optional ``body.agent_stream_llm`` (bool): when true, each LLM round uses HTTP streaming where supported and
        the server emits ``agent.llm_delta`` events (``delta`` text chunks) before ``agent.llm_round`` / tools.

Server → client JSON events (subset):
  - ``agent.session`` (optional ``context_injections``: list of ``{kind,label,body,chars,truncated}`` for UI badges), ``agent.context_update``, ``agent.context_compacted``, ``agent.llm_round_start``, ``agent.llm_delta`` (token chunks when ``agent_stream_llm``), ``agent.llm_round`` (optional ``usage`` when the LLM returns OpenAI-style token counts), ``agent.tool_start``,
    ``agent.tool_done``, ``agent.tool_invoke`` (ADR 0009: run this workspace tool locally, then reply with ``tool_result``), ``agent.goal``, ``agent.todos``, ``agent.secret_prompt``, ``agent.permission_ask``, ``agent.subagent_start``, ``agent.subagent_step``,
    ``agent.subagent_done``,
    ``agent.done``, ``agent.cancelled``
  - ``chat.completion`` — final OpenAI-shaped response (or error payload on failure)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from apps.backend.application.agent_runtime.runtime.prompts import AgentChatCancelled, WorkspaceAccessDenied
from apps.backend.application.agent_runtime.use_cases.chat_errors import user_visible_llm_transport_error
from apps.backend.application.agent_runtime.use_cases.chat_completion import chat_completion
from apps.backend.domain.shared.http_identity import resolve_chat_identity_ws
from apps.backend.domain.shared.identity import reset_identity, set_identity
from apps.backend.application.identity.use_cases.request_auth import get_user_for_bearer_token
from apps.backend.application.agent_runtime.use_cases.conversation_controller_services import (
    conversation_append_message,
    conversation_get,
    extract_bridge_reply,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _bearer_from_ws(websocket: WebSocket) -> str:
    q = (websocket.query_params.get("token") or "").strip()
    auth = (websocket.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        auth = auth[7:].strip()
    return q or auth


def _ws_connection_authorized(websocket: WebSocket) -> bool:
    """Require JWT or user API key (same material as HTTP Bearer)."""
    bearer = _bearer_from_ws(websocket)
    return bool(get_user_for_bearer_token(bearer))


def _normalize_msg_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    try:
        return json.dumps(content, ensure_ascii=False, sort_keys=True).strip()
    except (TypeError, ValueError):
        return str(content).strip()


def _last_user_content_from_work(work: dict[str, Any]) -> Any | None:
    messages = work.get("messages")
    if not isinstance(messages, list):
        return None
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "").strip() != "user":
            continue
        return msg.get("content")
    return None


def _ensure_ws_user_message(user_id: uuid.UUID, work: dict[str, Any]) -> None:
    """Persist the latest user prompt if the client refresh raced the pre-send PUT."""
    raw_cid = work.get("conversation_id")
    if raw_cid is None:
        return
    cid_s = str(raw_cid).strip()
    if not cid_s:
        return
    try:
        conv_id = uuid.UUID(cid_s)
    except ValueError:
        return
    user_content = _last_user_content_from_work(work)
    if user_content is None:
        return
    want = _normalize_msg_content(user_content)
    if not want:
        return
    try:
        conv = conversation_get(user_id, conv_id)
    except Exception:
        logger.exception("ws chat: conversation_get failed (conversation_id=%s)", conv_id)
        return
    if not conv:
        return
    existing = conv.get("messages") if isinstance(conv, dict) else None
    if not isinstance(existing, list):
        existing = []
    last_user = None
    for msg in reversed(existing):
        if isinstance(msg, dict) and str(msg.get("role") or "").strip() == "user":
            last_user = msg
            break
    if last_user is not None and _normalize_msg_content(last_user.get("content")) == want:
        return
    try:
        if conversation_append_message(user_id, conv_id, role="user", content=user_content):
            logger.info(
                "ws chat: persisted missing user message (conversation_id=%s)",
                conv_id,
            )
    except Exception:
        logger.exception(
            "ws chat: failed to persist user message (conversation_id=%s)",
            conv_id,
        )


def _persist_ws_assistant_completion(
    user_id: uuid.UUID,
    work: dict[str, Any],
    data: Any,
) -> None:
    """When the client disconnects mid-turn, still save the final assistant reply."""
    raw_cid = work.get("conversation_id")
    if raw_cid is None:
        return
    cid_s = str(raw_cid).strip()
    if not cid_s:
        return
    try:
        conv_id = uuid.UUID(cid_s)
    except ValueError:
        return
    if not isinstance(data, dict):
        return
    reply = extract_bridge_reply(data)
    if (
        not reply.strip()
        or reply.startswith("AgentLayer error:")
        or reply.startswith("Unexpected response:")
    ):
        return
    try:
        if conversation_append_message(user_id, conv_id, role="assistant", content=reply):
            logger.info(
                "ws chat: persisted assistant after client disconnect (conversation_id=%s)",
                conv_id,
            )
        else:
            logger.warning(
                "ws chat: failed to persist assistant after disconnect (conversation_id=%s)",
                conv_id,
            )
    except Exception:
        logger.exception(
            "ws chat: exception persisting assistant after disconnect (conversation_id=%s)",
            conv_id,
        )


@router.websocket("/ws/v1/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    if not _ws_connection_authorized(websocket):
        try:
            await websocket.send_json({"type": "error", "detail": "unauthorized"})
        except Exception:
            logger.debug("ws unauthorized send failed", exc_info=True)
        await websocket.close(code=4401)
        return

    try:
        user_id, tenant_id = resolve_chat_identity_ws(websocket)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        try:
            await websocket.send_json({"type": "error", "detail": detail})
        except Exception:
            logger.debug("ws identity error send failed", exc_info=True)
        await websocket.close(code=4401)
        return
    control_queue: asyncio.Queue = asyncio.Queue()
    cancel_event = asyncio.Event()
    pump_stop = asyncio.Event()
    session_workspace_tools: set[str] = set()
    client_connected = True

    def _apply_client_capabilities(msg: dict[str, Any]) -> None:
        raw = msg.get("workspace_tools")
        if not isinstance(raw, list):
            return
        session_workspace_tools.clear()
        session_workspace_tools.update(str(x).strip() for x in raw if str(x).strip())

    async def emit(ev: dict[str, Any]) -> bool:
        nonlocal client_connected
        try:
            await websocket.send_json(ev)
            return True
        except Exception:
            client_connected = False
            logger.debug("ws emit failed", exc_info=True)
            return False

    async def pump_incoming() -> None:
        nonlocal client_connected
        try:
            while not pump_stop.is_set():
                try:
                    msg = await websocket.receive_json()
                except json.JSONDecodeError:
                    await emit({"type": "error", "detail": "invalid JSON"})
                    continue
                except WebSocketDisconnect:
                    raise
                if not isinstance(msg, dict):
                    await emit({"type": "error", "detail": "JSON object expected"})
                    continue
                t = msg.get("type")
                if t == "ping":
                    await emit({"type": "pong"})
                    continue
                # Apply cancel immediately so in-flight LLM streams / tool loops can abort
                # without waiting for the next drain_control_queue() between rounds.
                if t == "cancel":
                    cancel_event.set()
                await control_queue.put(msg)
        except WebSocketDisconnect:
            # Do not cancel the in-flight turn on refresh/navigation disconnect —
            # the run continues and completion is persisted server-side if emit fails.
            client_connected = False
            logger.debug("ws client disconnected; turn continues until cancel or completion")
        except Exception:
            logger.exception("ws pump_incoming failed")
            cancel_event.set()
            client_connected = False

    pump_task = asyncio.create_task(pump_incoming())

    try:
        while True:
            if pump_stop.is_set():
                break
            try:
                first = await asyncio.wait_for(control_queue.get(), timeout=3600.0)
            except asyncio.TimeoutError:
                await emit({"type": "error", "detail": "idle timeout"})
                break
            if not isinstance(first, dict):
                continue
            ft = first.get("type")
            if ft == "ping":
                await emit({"type": "pong"})
                continue
            if ft == "client_capabilities":
                _apply_client_capabilities(first)
                continue
            if ft in (
                "tool_result",
                "permission_reply",
                "cancel",
                "add_tools",
                "continue_step",
                "secret_saved",
            ):
                # Stray control frames between turns: ignore rather than fail the next chat.
                continue
            if ft != "chat":
                await emit({"type": "error", "detail": "expected type=chat to start a turn"})
                continue

            body = first.get("body")
            if not isinstance(body, dict):
                await emit({"type": "error", "detail": "chat.body must be an object"})
                continue

            work = dict(body)
            work["stream"] = False
            r_hdr = first.get("router_categories_header")
            d_hdr = first.get("tool_domain_header")
            router_hdr = str(r_hdr).strip() if isinstance(r_hdr, str) and r_hdr.strip() else None
            tool_dom_hdr = str(d_hdr).strip() if isinstance(d_hdr, str) and d_hdr.strip() else None
            mp = first.get("model_profile_header")
            mo = first.get("model_override_header")
            wh = websocket.headers
            model_prof = (
                str(mp).strip() if isinstance(mp, str) and mp.strip() else None
            ) or (wh.get("x-agent-model-profile") or "").strip() or None
            model_ovr = (
                str(mo).strip() if isinstance(mo, str) and mo.strip() else None
            ) or (wh.get("x-agent-model-override") or "").strip() or None
            utz = first.get("user_timezone_header")
            user_tz = (
                str(utz).strip() if isinstance(utz, str) and utz.strip() else None
            ) or (wh.get("x-user-timezone") or "").strip() or None
            bearer = _bearer_from_ws(websocket)
            ws_user = get_user_for_bearer_token(bearer) if bearer else None
            bearer_role = ws_user.role.lower() if ws_user else None

            id_token = set_identity(tenant_id, user_id)
            cancel_event.clear()
            try:
                await asyncio.to_thread(_ensure_ws_user_message, user_id, work)
                data = await chat_completion(
                    work,
                    router_categories_header=router_hdr,
                    tool_domain_header=tool_dom_hdr,
                    model_profile_header=model_prof,
                    model_override_header=model_ovr,
                    user_timezone_header=user_tz,
                    bearer_user_role=bearer_role,
                    event_emit=emit,
                    control_queue=control_queue,
                    cancel_event=cancel_event,
                    client_workspace_tools=frozenset(session_workspace_tools),
                )
            except AgentChatCancelled:
                await emit({"type": "agent.aborted", "detail": "cancelled"})
                await emit(
                    {
                        "type": "chat.completion",
                        "error": True,
                        "detail": "cancelled",
                    }
                )
            except WorkspaceAccessDenied as e:
                await emit({"type": "error", "detail": str(e), "http_status": 403})
            except ValueError as e:
                await emit({"type": "error", "detail": str(e)})
            except Exception as e:
                detail, log_exc = user_visible_llm_transport_error(e)
                if log_exc:
                    logger.exception("ws chat_completion failed")
                else:
                    logger.warning("ws chat_completion failed: %s (%s)", detail, e)
                await emit({"type": "error", "detail": detail})
            else:
                delivered = await emit({"type": "chat.completion", "data": data})
                # Only server-persist when the completion frame never reached the client,
                # so a live client + persistDetachedAgentCompletion cannot double-append.
                if not delivered:
                    await asyncio.to_thread(
                        _persist_ws_assistant_completion, user_id, work, data
                    )
            finally:
                reset_identity(id_token)
            if not client_connected and control_queue.empty():
                # Client gone and no queued control frames: end the WS loop.
                break
    finally:
        pump_stop.set()
        pump_task.cancel()
        try:
            await pump_task
        except asyncio.CancelledError:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
