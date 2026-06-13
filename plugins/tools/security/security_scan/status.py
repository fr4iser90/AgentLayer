"""GET /api/v1/scans/{id}/status — status check with optional auto deferred wait."""

from __future__ import annotations

from typing import Any, Callable

from plugins.tools.security.security_scan.common import (
    NO_WAIT_SUFFIX,
    agent_guidance_for_status,
    bool_arg,
    dump_ok,
    request,
    ssc_domain_attrs,
    ssc_status,
)

__version__ = "1.2.0"
_attrs = ssc_domain_attrs()
TOOL_ID = "ssc_status"
TOOL_BUCKET = _attrs["TOOL_BUCKET"]
TOOL_DOMAIN = _attrs["TOOL_DOMAIN"]
TOOL_CAPABILITIES = _attrs["TOOL_CAPABILITIES"]
TOOL_SECRETS_REQUIRED = _attrs["TOOL_SECRETS_REQUIRED"]
TOOL_USER_SECRET_FORMS = _attrs["TOOL_USER_SECRET_FORMS"]
TOOL_LABEL = "SimpleSecCheck: status"
TOOL_DESCRIPTION = "SimpleSecCheck scan status (one-shot or auto-wait in agent runs)."
# Router phrases: co-located status.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()

_TERMINAL_OK = frozenset({"ready", "completed", "done", "success"})
_TERMINAL_FAIL = frozenset({"failed", "cancelled", "error"})
_RUNNING = frozenset({"started", "scanning", "queued", "running", "pending"})


def _fetch_scan_status(scan_id: str) -> tuple[int, Any, str | None, int | None]:
    status_code, data = request("GET", f"/api/v1/scans/{scan_id}/status")
    if isinstance(data, dict) and data.get("ok") is False:
        return status_code, data, None, None
    st = ssc_status(data if isinstance(data, dict) else None)
    if st is None and isinstance(data, dict):
        st = str(data.get("scan_status") or "").strip().lower() or None
    estimated_sec = None
    if isinstance(data, dict):
        from apps.backend.domain.async_wait import parse_estimated_time_seconds

        estimated_sec = parse_estimated_time_seconds(data)
    return status_code, data, st, estimated_sec


def _status_payload(
    *,
    scan_id: str,
    http_status: int,
    data: Any,
    st: str | None,
    estimated_sec: int | None,
    deferred_wait: dict[str, Any] | None = None,
) -> dict[str, Any]:
    terminal = st in ("completed", "failed", "cancelled", "error") or st in _TERMINAL_OK
    still_running = st in _RUNNING if st else False
    payload: dict[str, Any] = {
        "ok": True,
        "http_status": http_status,
        "scan_id": scan_id,
        "status": st,
        "estimated_time_seconds": estimated_sec,
        "terminal": terminal,
        "still_running": still_running,
        "end_run_recommended": False,
        "progress": data.get("progress") if isinstance(data, dict) else None,
        "vulnerabilities_found": (
            data.get("vulnerabilities_found") if isinstance(data, dict) else None
        ),
        "scan": data,
        "agent_guidance": agent_guidance_for_status(
            st, data=data if isinstance(data, dict) else None
        ),
    }
    if deferred_wait:
        payload["deferred_wait"] = deferred_wait
    return payload


def _maybe_auto_deferred_wait(
    *,
    scan_id: str,
    st: str | None,
    estimated_sec: int | None,
    context: dict[str, Any],
) -> dict[str, Any] | None:
    from apps.backend.domain.async_wait import run_deferred_wait

    def poll_fn() -> tuple[dict[str, Any] | None, str | None]:
        _sc, dat, pst, _est = _fetch_scan_status(scan_id)
        if isinstance(dat, dict) and dat.get("ok") is False:
            return dat, pst
        if not isinstance(dat, dict):
            return {"ok": False, "error": "invalid poll response"}, pst
        return dat, pst

    return run_deferred_wait(
        wait_id=scan_id,
        estimated_sec=estimated_sec,
        context=context,
        initial_status=st,
        poll_fn=poll_fn,
        terminal_ok=_TERMINAL_OK,
        terminal_fail=_TERMINAL_FAIL,
        wait_label="security_scan",
    )


def status(arguments: dict[str, Any], context: dict | None = None) -> str:
    scan_id = str(arguments.get("scan_id") or arguments.get("id") or "").strip()
    if not scan_id:
        return dump_ok({"ok": False, "error": "scan_id is required"})
    skip_wait = bool_arg(arguments, "skip_wait", False)

    http_status, data, st, estimated_sec = _fetch_scan_status(scan_id)
    if isinstance(data, dict) and data.get("ok") is False:
        return dump_ok(data)

    still_running = st in _RUNNING if st else False
    if still_running and context and not skip_wait:
        wait_out = _maybe_auto_deferred_wait(
            scan_id=scan_id,
            st=st,
            estimated_sec=estimated_sec,
            context=context,
        )
        if isinstance(wait_out, dict) and wait_out.get("cancelled"):
            return dump_ok(
                {
                    "ok": False,
                    "cancelled": True,
                    "scan_id": scan_id,
                    "status": st,
                    "still_running": True,
                    "deferred_wait": wait_out,
                }
            )
        http_status, data, st, estimated_sec = _fetch_scan_status(scan_id)
        if isinstance(data, dict) and data.get("ok") is False:
            return dump_ok(data)
        dw_meta: dict[str, Any] = {"auto": True}
        if isinstance(wait_out, dict):
            dw_meta.update(
                {
                    k: wait_out[k]
                    for k in (
                        "waited_sec",
                        "poll_count",
                        "completed",
                        "timed_out",
                        "status",
                    )
                    if k in wait_out
                }
            )
        return dump_ok(
            _status_payload(
                scan_id=scan_id,
                http_status=http_status,
                data=data,
                st=st,
                estimated_sec=estimated_sec,
                deferred_wait=dw_meta,
            )
        )

    return dump_ok(
        _status_payload(
            scan_id=scan_id,
            http_status=http_status,
            data=data,
            st=st,
            estimated_sec=estimated_sec,
        )
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "status": status,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "status",
            "TOOL_DESCRIPTION": (
                "SimpleSecCheck scan status (progress, completed, failed). "
                "In agent runs, when still running, automatically deferred-waits "
                "(timer paused) until terminal — no status polling loop. "
                "Pass skip_wait=true for a one-shot peek only."
                + NO_WAIT_SUFFIX
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scan_id": {"type": "string", "TOOL_DESCRIPTION": "Scan UUID"},
                    "skip_wait": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "One-shot status only; skip auto deferred wait (default false)",
                    },
                },
                "required": ["scan_id"],
            },
        },
    },
]
