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
  - ``agent.session``, ``agent.context_update``, ``agent.context_compacted``, ``agent.llm_round_start``, ``agent.llm_delta`` (token chunks when ``agent_stream_llm``), ``agent.llm_round`` (optional ``usage`` when the LLM returns OpenAI-style token counts), ``agent.tool_start``,
    ``agent.tool_done``, ``agent.secret_prompt``, ``agent.permission_ask``, ``agent.subagent_start``, ``agent.subagent_step``,
    ``agent.subagent_done``,
    ``agent.done``, ``agent.cancelled``
  - ``chat.completion`` — final OpenAI-shaped response (or error payload on failure)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from apps.backend.domain.agent import AgentChatCancelled, WorkspaceAccessDenied, chat_completion
from apps.backend.domain.http_identity import resolve_chat_identity_ws
from apps.backend.domain.identity import reset_identity, set_identity
from apps.backend.infrastructure.auth import get_user_for_bearer_token
from apps.backend.infrastructure.llm_user_errors import user_visible_llm_transport_error

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

    async def emit(ev: dict[str, Any]) -> None:
        try:
            await websocket.send_json(ev)
        except Exception:
            logger.debug("ws emit failed", exc_info=True)

    async def pump_incoming() -> None:
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
            cancel_event.set()
        except Exception:
            logger.exception("ws pump_incoming failed")
            cancel_event.set()

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
                await emit({"type": "chat.completion", "data": data})
            finally:
                reset_identity(id_token)
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
