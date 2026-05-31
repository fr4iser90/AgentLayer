"""
Periodic **scheduler** agent run (operator_settings, Admin → Interfaces).

One background thread; ticks call :func:`apps.backend.domain.agent.chat_completion` with
scheduler-specific body keys (``agent_llm_backend``, ``agent_max_tool_rounds``, …).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
import uuid
from typing import Any

import httpx

from apps.backend.core.config import config
from apps.backend.domain.agent import chat_completion
from apps.backend.domain.identity import reset_identity, set_identity
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)


def _clamp_int(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


_stop = threading.Event()
_thread: threading.Thread | None = None
_next_tick_monotonic: float = 0.0


def start_scheduler_worker() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_worker_loop, daemon=True, name="scheduler-worker")
    _thread.start()


def stop_scheduler_worker() -> None:
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=15)


def _extract_assistant_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        return ""
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        return ""
    c = msg.get("content")
    return c.strip() if isinstance(c, str) else ""


_SCHEDULER_OK_RE = re.compile(r"^\s*SCHEDULER_OK\s*$", re.IGNORECASE | re.DOTALL)


def _should_notify(
    text: str, notify_only_if_not_ok: bool
) -> tuple[bool, str]:
    """Return (notify, outbound_message)."""
    raw = (text or "").strip()
    if not notify_only_if_not_ok:
        return True, raw[:4000]
    if _SCHEDULER_OK_RE.match(raw):
        return False, ""
    if len(raw) < 400:
        try:
            j = json.loads(raw)
            if isinstance(j, dict):
                if j.get("notify") is False:
                    return False, ""
                if str(j.get("status", "")).lower() == "ok":
                    return False, ""
                m = j.get("message")
                if isinstance(m, str) and m.strip():
                    return True, m.strip()[:4000]
        except json.JSONDecodeError:
            pass
    return True, raw[:4000]


def _tool_names_from_packages(package_ids: set[str]) -> list[str]:
    from apps.backend.domain.plugin_system.registry import get_registry

    out: set[str] = set()
    for m in get_registry().tools_meta:
        pid = str(m.get("id") or "").strip()
        if pid in package_ids:
            for t in m.get("tools") or []:
                out.add(str(t))
    return sorted(out)


def _telegram_send_text(token: str, chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    with httpx.Client(timeout=45.0) as client:
        r = client.post(url, json={"chat_id": chat_id, "text": text[:4000]})
        r.raise_for_status()


async def _run_one_tick() -> None:
    r = operator_settings.fetch_operator_settings_row()
    if not r.get("scheduler_enabled"):
        return
    uid = r.get("scheduler_user_id")
    if uid is None:
        logger.warning("scheduler: enabled but scheduler_user_id is unset — skipping tick")
        return
    user_id = uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))
    tenant_id = db.user_tenant_id(user_id)
    role = db.user_role(user_id)

    if r.get("scheduler_pidea_enabled"):
        logger.debug("scheduler: scheduler_pidea_enabled is ignored in this version (MVP)")

    max_out = _clamp_int(r.get("scheduler_max_outbound_per_day"), 10, 0, 10_000)
    if max_out > 0 and db.scheduler_outbound_count_today_utc(user_id) >= max_out:
        logger.info("scheduler: daily outbound cap reached for user %s — skip tick", user_id)
        return

    tools_mode = operator_settings.normalize_scheduler_tools_mode(r.get("scheduler_tools_mode"))
    llm_be = operator_settings.normalize_scheduler_llm_backend(r.get("scheduler_llm_backend"))
    raw_model = r.get("scheduler_model")
    model = str(raw_model).strip() if raw_model else None
    max_rounds = r.get("scheduler_max_tool_rounds")
    max_rounds_i: int | None = None
    if max_rounds is not None:
        try:
            max_rounds_i = int(max_rounds)
        except (TypeError, ValueError):
            max_rounds_i = None

    instr = (str(r.get("scheduler_instructions") or "").strip())[:12000]
    sys_prompt = (
        "You are in SCHEDULER mode (background check). "
        "If there is nothing that needs the user's attention, reply with exactly one line: SCHEDULER_OK\n"
        "If something needs attention, reply with compact JSON: "
        '{"notify":true,"message":"...","severity":"low|medium|high"} '
        "or plain text.\n"
    )
    if instr:
        sys_prompt += "\nOperator instructions:\n" + instr

    body: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": "Run the scheduler check now."},
        ],
        "stream": False,
    }
    from apps.backend.domain.catalog_chat_llm import catalog_llm_body_extras

    try:
        llm = catalog_llm_body_extras(
            model=model,
            profile_key="agent",
        )
    except ValueError as exc:
        logger.warning("scheduler: no catalog LLM — skip tick: %s", exc)
        return
    body.update(llm)

    if max_rounds_i is not None:
        body["agent_max_tool_rounds"] = max_rounds_i

    if llm_be in ("provider", "provider_admin"):
        agent_be = scheduler_llm_backend_to_agent_override(llm_be)
        if agent_be is not None:
            body["agent_llm_backend"] = agent_be

    if tools_mode == "none":
        body["agent_plain_completion"] = True
    elif tools_mode == "allowlist":
        pkgs_raw = str(r.get("scheduler_allowed_tool_packages") or "").strip()
        pids = {x.strip().lower() for x in pkgs_raw.replace(";", ",").split(",") if x.strip()}
        names = _tool_names_from_packages(pids) if pids else []
        if names:
            body["agent_tool_name_allowlist"] = names
        else:
            logger.warning(
                "scheduler: tools_mode=allowlist but no matching packages — falling back to plain completion"
            )
            body["agent_plain_completion"] = True
    # full: default tools path

    id_tok = set_identity(tenant_id, user_id)
    try:
        data = await chat_completion(body, bearer_user_role=role if role in ("user", "admin") else None)
    finally:
        reset_identity(id_tok)

    text = _extract_assistant_text(data if isinstance(data, dict) else {})
    notify, outbound = _should_notify(
        text, bool(r.get("scheduler_notify_only_if_not_ok", True))
    )
    if not notify or not outbound.strip():
        logger.info("scheduler: ok (no notify) user=%s", user_id)
        return

    tok = (r.get("telegram_bot_token") or "").strip()
    tg_uid = db.user_telegram_user_id_get(user_id)
    if tok and tg_uid:
        try:
            _telegram_send_text(tok, int(str(tg_uid).strip()), f"Scheduler:\n{outbound}")
            db.scheduler_outbound_increment_utc(user_id)
            logger.info("scheduler: notified user=%s via Telegram", user_id)
        except Exception:
            logger.exception("scheduler: Telegram send failed user=%s", user_id)
    else:
        logger.info(
            "scheduler: notify (no Telegram link) user=%s text~=%s",
            user_id,
            outbound[:200],
        )


def _worker_loop() -> None:
    global _next_tick_monotonic
    logger.info("scheduler worker started")
    while not _stop.is_set():
        if _stop.wait(timeout=5.0):
            break
        try:
            row = operator_settings.fetch_operator_settings_row()
            if not row.get("scheduler_enabled"):
                _next_tick_monotonic = 0.0
                continue
            interval_m = _clamp_int(row.get("scheduler_interval_minutes"), 60, 5, 24 * 60)
            interval_s = float(interval_m * 60)
            now = time.monotonic()
            if _next_tick_monotonic == 0.0:
                _next_tick_monotonic = now + interval_s
            if now < _next_tick_monotonic:
                continue
            _next_tick_monotonic = now + interval_s
            asyncio.run(_run_one_tick())
        except Exception:
            logger.exception("scheduler tick failed")
    logger.info("scheduler worker stopped")
