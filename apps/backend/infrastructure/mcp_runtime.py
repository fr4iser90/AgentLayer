"""MCP (Model Context Protocol) stdio clients: discover tools and invoke them in the chat tool loop."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import apps.backend.core.config as _cfg

logger = logging.getLogger(__name__)

_SERVER_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$")
_MCP_PREFIX = "mcp__"
_EXEC = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mcp_stdio")


@dataclass(frozen=True)
class McpStdioServer:
    server_id: str
    command: str
    args: list[str]
    env: dict[str, str] | None
    cwd: str | None


def _b64url_decode_padded(segment: str) -> str:
    pad = (-len(segment)) % 4
    if pad:
        segment = segment + ("=" * pad)
    return base64.urlsafe_b64decode(segment.encode("ascii")).decode("utf-8")


def mcp_openai_function_name(server_id: str, tool_name: str) -> str:
    b64 = base64.urlsafe_b64encode(tool_name.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{_MCP_PREFIX}{server_id}__{b64}"


def parse_mcp_openai_function_name(name: str) -> tuple[str, str] | None:
    n = (name or "").strip()
    if not n.startswith(_MCP_PREFIX):
        return None
    rest = n[len(_MCP_PREFIX) :]
    if "__" not in rest:
        return None
    sid, b64 = rest.split("__", 1)
    if not sid or not b64 or not _SERVER_ID_RE.match(sid):
        return None
    try:
        tool = _b64url_decode_padded(b64)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None
    if not tool:
        return None
    return sid, tool


def _parse_servers_payload(data: Any) -> list[McpStdioServer]:
    if not isinstance(data, list):
        raise ValueError("MCP servers config must be a JSON array")
    out: list[McpStdioServer] = []
    for i, row in enumerate(data):
        if not isinstance(row, dict):
            raise ValueError(f"MCP server entry {i} must be an object")
        sid = str(row.get("id") or "").strip()
        cmd = str(row.get("command") or "").strip()
        args = row.get("args")
        if not sid or not cmd:
            raise ValueError(f"MCP server entry {i} needs non-empty id and command")
        if not _SERVER_ID_RE.match(sid):
            raise ValueError(
                f"MCP server id {sid!r} must match {_SERVER_ID_RE.pattern} (no underscores)"
            )
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise ValueError(f"MCP server {sid!r}: args must be a list of strings")
        env_raw = row.get("env")
        env: dict[str, str] | None = None
        if env_raw is not None:
            if not isinstance(env_raw, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in env_raw.items()
            ):
                raise ValueError(f"MCP server {sid!r}: env must be an object of string keys/values")
            env = {str(k): str(v) for k, v in env_raw.items()}
        cwd_raw = row.get("cwd")
        cwd = str(cwd_raw).strip() if isinstance(cwd_raw, str) and cwd_raw.strip() else None
        out.append(McpStdioServer(server_id=sid, command=cmd, args=list(args), env=env, cwd=cwd))
    return out


def load_mcp_stdio_servers() -> list[McpStdioServer]:
    raw: str | None = None
    fp = (_cfg.AGENT_MCP_SERVERS_FILE or "").strip()
    if fp:
        path = Path(fp).expanduser()
        raw = path.read_text(encoding="utf-8")
    elif (_cfg.AGENT_MCP_SERVERS_JSON or "").strip():
        raw = _cfg.AGENT_MCP_SERVERS_JSON.strip()
    if not raw or not raw.strip():
        return []
    data = json.loads(raw)
    return _parse_servers_payload(data)


def _workspace_mcp_stdio_dicts() -> list[dict[str, Any]] | None:
    """Non-empty list from :func:`apps.backend.domain.identity.get_workspace` → workspace-only MCP."""
    from apps.backend.domain.identity import get_workspace

    ws = get_workspace()
    if not isinstance(ws, dict):
        return None
    raw = ws.get("mcp_stdio_servers")
    if isinstance(raw, list) and len(raw) > 0:
        return list(raw)
    return None


def _mcp_stdio_servers_effective() -> list[McpStdioServer]:
    """Workspace JSON (non-empty) replaces global ``AGENT_MCP_*`` for the current chat identity."""
    wr = _workspace_mcp_stdio_dicts()
    if wr is not None:
        try:
            return _parse_servers_payload(wr)
        except Exception as e:
            logger.warning("workspace MCP config invalid: %s", e)
            return []
    if not _cfg.AGENT_MCP_ENABLED:
        return []
    try:
        return load_mcp_stdio_servers()
    except Exception as e:
        logger.warning("MCP server config invalid: %s", e)
        return []


def _mcp_import_ok() -> bool:
    try:
        import mcp  # noqa: F401
    except ImportError:
        return False
    return True


def _serialize_call_tool_result(result: Any) -> dict[str, Any]:
    from mcp import types as mcp_types

    blocks: list[Any] = []
    for block in result.content or []:
        if isinstance(block, mcp_types.TextContent):
            blocks.append({"type": "text", "text": block.text})
        elif isinstance(block, mcp_types.ImageContent):
            blocks.append(
                {
                    "type": "image",
                    "mimeType": block.mimeType,
                    "data_len": len(block.data) if block.data else 0,
                }
            )
        elif isinstance(block, mcp_types.AudioContent):
            blocks.append({"type": "audio", "mimeType": block.mimeType})
        else:
            try:
                blocks.append(block.model_dump(mode="json", exclude_none=True))
            except Exception:
                blocks.append({"type": "unknown", "repr": repr(block)})
    out: dict[str, Any] = {
        "ok": not bool(getattr(result, "isError", False)),
        "content": blocks,
    }
    sc = getattr(result, "structuredContent", None)
    if sc is not None:
        out["structuredContent"] = sc
    return out


async def _list_tools_for_server(srv: McpStdioServer) -> list[Any]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    sp = StdioServerParameters(
        command=srv.command,
        args=srv.args,
        env=srv.env,
        cwd=srv.cwd,
    )
    tmo = float(_cfg.AGENT_MCP_LIST_TIMEOUT_SEC)
    async with asyncio.timeout(tmo):
        async with stdio_client(sp) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.list_tools()
                return list(res.tools)


async def _call_tool_on_server(
    srv: McpStdioServer, tool_name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    sp = StdioServerParameters(
        command=srv.command,
        args=srv.args,
        env=srv.env,
        cwd=srv.cwd,
    )
    tmo = float(_cfg.AGENT_MCP_CALL_TIMEOUT_SEC)
    async with asyncio.timeout(tmo):
        async with stdio_client(sp) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    tool_name,
                    arguments,
                    read_timeout_seconds=timedelta(seconds=tmo),
                )
                return _serialize_call_tool_result(result)


async def mcp_runtime_status(*, workspace_stdio: list[Any] | None = None) -> dict[str, Any]:
    """
    Lightweight status for HTTP/UI: whether MCP is configured, importable, and per-server health.

    ``connected`` means ``list_tools`` succeeded for that server (stdio subprocess came up).

    When ``workspace_stdio`` is a non-empty list, health checks use only those servers (``scope`` = ``workspace``).
    """
    has_ws = isinstance(workspace_stdio, list) and len(workspace_stdio) > 0
    out: dict[str, Any] = {
        "enabled": bool(_cfg.AGENT_MCP_ENABLED) or has_ws,
        "import_ok": _mcp_import_ok(),
        "agent_ids": list(_cfg.AGENT_MCP_AGENT_IDS),
        "servers": [],
        "scope": "workspace" if has_ws else "global",
    }
    if not out["import_ok"]:
        return out
    if not has_ws and not _cfg.AGENT_MCP_ENABLED:
        return out
    try:
        servers = _parse_servers_payload(workspace_stdio) if has_ws else load_mcp_stdio_servers()
    except Exception as e:
        out["config_error"] = str(e)
        return out
    for srv in servers:
        row: dict[str, Any] = {
            "id": srv.server_id,
            "command": srv.command,
            "args": list(srv.args),
            "cwd": srv.cwd,
        }
        try:
            tools = await _list_tools_for_server(srv)
            row["connected"] = True
            row["tool_count"] = len(tools)
            row["error"] = None
        except Exception as e:
            row["connected"] = False
            row["tool_count"] = 0
            row["error"] = str(e)[:500]
        out["servers"].append(row)
    return out


async def gather_mcp_chat_tool_specs_async() -> list[dict[str, Any]]:
    if not _mcp_import_ok():
        return []
    servers = _mcp_stdio_servers_effective()
    if not servers:
        return []
    max_tools = max(1, int(_cfg.AGENT_MCP_MAX_TOOLS))
    specs: list[dict[str, Any]] = []
    for srv in servers:
        try:
            tools = await _list_tools_for_server(srv)
        except Exception as e:
            logger.warning("MCP list_tools failed for server %r: %s", srv.server_id, e)
            continue
        for t in tools:
            if len(specs) >= max_tools:
                logger.info(
                    "MCP tool cap %d reached; skipping further tools (server=%s)",
                    max_tools,
                    srv.server_id,
                )
                return specs
            orig_name = (t.name or "").strip()
            if not orig_name:
                continue
            fn = mcp_openai_function_name(srv.server_id, orig_name)
            desc = (t.description or "").strip() or f"MCP tool {orig_name!r} on server {srv.server_id!r}"
            hint = (
                f"[MCP server={srv.server_id} tool={orig_name}] {desc}\n\n"
                "Pass arguments as a single JSON object matching inputSchema."
            )
            schema = t.inputSchema if isinstance(t.inputSchema, dict) else {"type": "object", "properties": {}}
            specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": fn,
                        "TOOL_DESCRIPTION": hint,
                        "parameters": schema,
                    },
                }
            )
    return specs


async def _invoke_async(openai_fn_name: str, arguments: dict[str, Any]) -> str:
    parsed = parse_mcp_openai_function_name(openai_fn_name)
    if not parsed:
        return json.dumps({"ok": False, "error": "invalid MCP tool name"}, ensure_ascii=False)
    sid, tool_name = parsed
    servers = _mcp_stdio_servers_effective()
    if not servers:
        return json.dumps({"ok": False, "error": "MCP not configured"}, ensure_ascii=False)
    srv = next((s for s in servers if s.server_id == sid), None)
    if srv is None:
        return json.dumps(
            {"ok": False, "error": f"unknown MCP server id {sid!r}"},
            ensure_ascii=False,
        )
    try:
        payload = await _call_tool_on_server(srv, tool_name, dict(arguments or {}))
        return json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        logger.warning("MCP call_tool failed %s/%s: %s", sid, tool_name, e)
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


def mcp_invoke_tool_sync(openai_fn_name: str, arguments: dict[str, Any]) -> str:
    """Run MCP tool invocation in a fresh event loop (avoids nested asyncio when called from sync run_tool)."""

    def _run() -> str:
        return asyncio.run(_invoke_async(openai_fn_name, arguments))

    timeout = max(5, int(_cfg.AGENT_MCP_CALL_TIMEOUT_SEC) + 15)
    fut = _EXEC.submit(_run)
    return fut.result(timeout=timeout)
