from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from apps.backend.application.agent_runtime.use_cases.chat_errors import user_visible_llm_transport_error
from apps.backend.application.identity.use_cases.request_auth import get_user_for_bearer_token
from apps.backend.domain.shared.identity import reset_identity, set_identity
from apps.backend.domain.shared.http_identity import resolve_chat_identity
from apps.backend.application.agent_runtime.runtime.prompts import WorkspaceAccessDenied
from apps.backend.application.agent_runtime.use_cases.chat_completion import chat_completion

router = APIRouter()
logger = logging.getLogger(__name__)


def _bearer_user_role_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        return None
    user = get_user_for_bearer_token(token)
    return user.role.lower() if user else None

def _completion_to_sse_lines(completion: dict[str, Any]) -> bytes:
    """Build OpenAI-style SSE body from a full chat.completion JSON (Open WebUI sends stream=true)."""
    cid = completion.get("id") or f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = completion.get("created")
    if not isinstance(created, int):
        created = int(time.time())
    model = completion.get("model") or ""
    choice0 = (completion.get("choices") or [{}])[0]
    msg = choice0.get("message") if isinstance(choice0.get("message"), dict) else {}
    content = msg.get("content") if isinstance(msg, dict) else None
    if content is None:
        content = ""
    elif not isinstance(content, str):
        content = str(content)
    finish = choice0.get("finish_reason") or "stop"
    base = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
    }
    lines: list[bytes] = []
    lines.append(
        (
            "data: "
            + json.dumps(
                {
                    **base,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": content},
                            "finish_reason": None,
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n\n"
        ).encode()
    )
    lines.append(
        (
            "data: "
            + json.dumps(
                {
                    **base,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": finish,
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n\n"
        ).encode()
    )
    lines.append(b"data: [DONE]\n\n")
    return b"".join(lines)

@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    want_stream = bool(body.get("stream"))
    work = dict(body)
    work["stream"] = False

    user_id, tenant_id = resolve_chat_identity(request)
    id_token = set_identity(tenant_id, user_id)

    router_hdr = (request.headers.get("X-Agent-Router-Categories") or "").strip() or None
    tool_dom_hdr = (request.headers.get("X-Agent-Tool-Domain") or "").strip() or None
    model_prof = (request.headers.get("X-Agent-Model-Profile") or "").strip() or None
    model_ovr = (request.headers.get("X-Agent-Model-Override") or "").strip() or None
    user_tz = (request.headers.get("X-User-Timezone") or "").strip() or None

    try:
        result = await chat_completion(
            work,
            router_categories_header=router_hdr,
            tool_domain_header=tool_dom_hdr,
            model_profile_header=model_prof,
            model_override_header=model_ovr,
            user_timezone_header=user_tz,
            bearer_user_role=_bearer_user_role_from_request(request),
            stream_requested=want_stream,
        )
    except WorkspaceAccessDenied as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        detail, log_exc = user_visible_llm_transport_error(e)
        if log_exc:
            logger.exception("chat completion failed")
        else:
            logger.warning("chat completion failed: %s (%s)", detail, e)
        raise HTTPException(status_code=502, detail=detail) from e
    finally:
        reset_identity(id_token)

    if want_stream:
        if inspect.isasyncgen(result):
            return StreamingResponse(
                result,
                media_type="text/event-stream",
            )
        return StreamingResponse(
            iter([_completion_to_sse_lines(result)]),
            media_type="text/event-stream",
        )

    return result
