#!/usr/bin/env python3
"""Live check for the TUI client (ADR 0008, milestones 1-4).

Drives the real Textual app headlessly against a running backend: mints a key, connects the
websocket, exercises the workspace commands (list, create, bind, index), runs a turn that
forces tool calls plus a goal/todo update, and asserts the transcript and the goal strip
actually rendered. Writes an SVG screenshot for eyeballing.

Run with an interpreter that has textual installed, e.g.
    /tmp/al-tui-venv/bin/python scripts/verify_tui_client.py
"""

from __future__ import annotations

import asyncio
import secrets
import socket
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "apps" / "tui"))

from textual.widgets import Input, Static  # noqa: E402

from agentlayer_tui import commands  # noqa: E402
from agentlayer_tui.app import AgentLayerTui  # noqa: E402
from agentlayer_tui.client import RestClient  # noqa: E402
from agentlayer_tui.config import Settings  # noqa: E402
from tests.e2e.support.helpers import admin_credentials, base_url, load_e2e_env  # noqa: E402

SHOT = REPO / "docs" / "assets" / "tui-milestone4.svg"
SHOT_WS = REPO / "docs" / "assets" / "tui-workspaces.svg"
WS_NAME = f"tui-verify-{secrets.token_hex(3)}"
PROMPT = (
    "First call goal_create with the objective 'Ship the TUI client'. Then call todo_write with "
    "exactly three todos: 'render tool lines' (completed), 'goal strip' (in_progress) and "
    "'permission prompts' (pending). Then delegate a one-sentence repository summary to the "
    "coding agent. Answer with one short sentence when done."
)

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{f' — {detail}' if detail else ''}")
    if not ok:
        failures.append(label)


async def _mint(settings: Settings) -> tuple[str, str, str]:
    """Returns (key, key_id, access_token) so the run can revoke what it created."""
    rest = RestClient(settings)
    try:
        email, password = admin_credentials()
        token = await rest.login(email, password)
        name = f"tui-verify@{socket.gethostname()}"
        key = await rest.mint_api_key(token, name)
        rows = [r for r in await rest.list_api_keys(token) if r.get("name") == name]
        newest = max(rows, key=lambda r: str(r.get("created_at") or ""), default={})
        return key, str(newest.get("id") or ""), token
    finally:
        await rest.aclose()


async def _revoke(settings: Settings, key_id: str, token: str) -> bool:
    rest = RestClient(settings)
    try:
        return await rest.revoke_api_key(token, key_id)
    finally:
        await rest.aclose()


async def _delete_workspace(settings: Settings, workspace_id: str) -> bool:
    """Not part of the TUI's own surface, so it goes straight at the endpoint."""
    import httpx

    async with httpx.AsyncClient(base_url=settings.base_url, timeout=60) as http:
        r = await http.delete(
            f"/v1/workspaces/{workspace_id}",
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )
        return r.status_code == 200


def _transcript(app: AgentLayerTui) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for widget in app.query("#transcript Static").results(Static):
        classes = " ".join(sorted(widget.classes))
        rows.append((classes, str(widget.content)))
    return rows


async def main() -> int:
    load_e2e_env()
    settings = Settings(base_url=base_url(), model="Qwen3-Coder-30B-A3B-Instruct-UD-Q5_K_XL")
    print("auth")
    try:
        settings.api_key, key_id, access_token = await _mint(settings)
    except Exception as e:  # noqa: BLE001
        check("mint an API key for the TUI", False, str(e))
        return 1
    check("mint an API key for the TUI", bool(settings.api_key))

    app = AgentLayerTui(settings)
    created_id = ""
    print("connect")
    async with app.run_test(size=(118, 34)) as pilot:
        await pilot.pause()
        for _ in range(60):
            if app._socket.connected:
                break
            await pilot.pause(0.25)
        check("websocket connects with the key", app._socket.connected)
        rows = _transcript(app)
        check(
            "startup reports a connection, not an error",
            any("connected" in text for _, text in rows),
            next((t for c, t in rows if "error" in c), ""),
        )

        print("keys and commands")
        await pilot.press("ctrl+c")
        await pilot.pause()
        check("ctrl-c cancels instead of quitting the app", app.is_running)

        prompt_input = app.query_one("#prompt", Input)
        prompt_input.value = "/hel"
        await pilot.press("tab")
        await pilot.pause()
        check("tab completes a slash command", prompt_input.value.strip() == "/help",
              prompt_input.value)

        prompt_input.value = ""
        await app._run_command(commands.parse("/help"))
        await pilot.pause()
        check(
            "/help lists the commands",
            sum(1 for _, t in _transcript(app) if t.startswith("/")) >= 10,
        )
        app.action_clear()

        print("workspaces")
        await app._run_command(commands.parse("/index"))
        await pilot.pause()
        check(
            "/index without a binding says what to do first",
            any("bind a workspace first" in t for _, t in _transcript(app)),
        )
        app.action_clear()

        await app._run_command(commands.parse("/workspace"))
        await pilot.pause()
        listing = [t for _, t in _transcript(app)]
        check(
            "/workspace lists workspaces with a flag legend",
            any("flags:" in t for t in listing),
            f"{len(listing)} rows",
        )
        app.action_clear()

        await app._run_command(commands.parse(f"/workspace create {WS_NAME}"))
        await pilot.pause()
        check(
            f"/workspace create makes and binds {WS_NAME}",
            app._workspace_name == WS_NAME and bool(app._workspace_id),
            f"{app._workspace_name} {app._workspace_id[:8]}",
        )
        check(
            "the binding shows in the title bar",
            f"ws:{WS_NAME}" in str(app.query_one("#title", Static).content),
        )
        created_id = app._workspace_id
        convs = await app._rest.conversations()
        mine = next((c for c in convs if str(c.get("id")) == app._conversation_id), {})
        check(
            "binding persisted as the conversation's workspace preference",
            str(mine.get("workspace_id") or "") == created_id,
            str(mine.get("workspace_id")),
        )
        app.action_clear()

        await app._run_command(commands.parse("/bind zzz-no-such-workspace"))
        await pilot.pause()
        check(
            "/bind on an unknown name refuses instead of unbinding",
            any("no workspace matches" in t for _, t in _transcript(app))
            and app._workspace_id == created_id,
        )
        app.action_clear()

        await app._run_command(commands.parse(f"/bind {created_id[:8]}"))
        await pilot.pause()
        check(
            "/bind accepts a short id like the one /workspace prints",
            app._workspace_id == created_id,
        )
        app.action_clear()

        await app._run_command(commands.parse("/index status"))
        await pilot.pause()
        status = "\n".join(t for _, t in _transcript(app))
        print("  status:", status.replace("\n", " | ")[:160])
        check("/index status renders the index block", "index " in status and "flags" in status)
        app.action_clear()

        await app._run_command(commands.parse("/index everything"))
        await pilot.pause()
        check(
            "/index rejects an unknown mode",
            any("full, code or docs" in t for _, t in _transcript(app)),
        )
        app.action_clear()

        await app._run_command(commands.parse("/index code"))
        await pilot.pause()
        index_rows = [t for _, t in _transcript(app)]
        print("  index:", " | ".join(r[:80] for r in index_rows))
        check(
            "/index code starts a job or explains why it cannot",
            any("started" in t or "already running" in t or "off for this workspace" in t
                for t in index_rows),
            " ".join(index_rows)[:120],
        )
        app.action_clear()

        # A shot of the workspace surface itself: the list with its bound marker, then status.
        await app._run_command(commands.parse("/workspace"))
        await app._run_command(commands.parse("/index status"))
        await pilot.pause()
        SHOT_WS.parent.mkdir(parents=True, exist_ok=True)
        app.save_screenshot(str(SHOT_WS))
        check("workspace screenshot written", SHOT_WS.is_file(), str(SHOT_WS))
        app.action_clear()

        print("turn")
        await app._start_turn(PROMPT, echo="/delegate coding …")
        for _ in range(900):  # up to ~7.5 min for a real multi-round turn
            if not app._busy:
                break
            await pilot.pause(0.5)
        check("turn finished (not still busy)", not app._busy)

        rows = _transcript(app)
        kinds = " ".join(c for c, _ in rows)
        texts = [t for _, t in rows]
        check("the prompt is echoed as a user line", any("user" in c for c, _ in rows))
        check(
            "tool activity rendered",
            "tool_start" in kinds or "tool_done" in kinds,
            f"{len(rows)} rows",
        )
        check("a tool result was rendered", "tool_done" in kinds or "tool_error" in kinds)
        check(
            "delegation nested under the parent turn",
            any("sub_start" in c or "sub_done" in c for c, _ in rows)
            or any("\u2502" in t for t in texts),
        )
        check("an assistant answer rendered", any("assistant" in c for c, _ in rows))
        check(
            "with a workspace bound, nothing complains that coding has none",
            not any("workspace bound" in t.lower() for t in texts),
            next((t for t in texts if "workspace bound" in t.lower()), "")[:120],
        )
        answer = next((t for c, t in rows if "assistant" in c), "")
        check(
            "streamed answer kept its word spacing",
            len(answer.split()) > 3,
            answer[:80],
        )

        strip = str(app.query_one("#strip", Static).content)
        print("  strip:", strip.replace("\n", " | ")[:150])
        check("goal strip shows an objective", "Goal  —" not in strip.splitlines()[0])
        check("todo strip shows items", "Todos  —" not in strip.splitlines()[1])

        print("permission prompt")
        replies: list[tuple[str, str]] = []

        async def _record(request_id: str, reply: str) -> None:
            replies.append((request_id, reply))

        app._socket.send_permission = _record  # type: ignore[method-assign]
        app._handle(
            {
                "type": "agent.permission_ask",
                "request_id": "probe-1",
                "tool_name": "bash",
                "args_preview": '{"cmd": "rm -rf /tmp/nope"}',
                "round": 2,
            }
        )
        await pilot.pause()
        check("permission prompt opens a modal", len(app.screen_stack) > 1)
        await pilot.press("y")
        for _ in range(20):
            if replies:
                break
            await pilot.pause(0.1)
        check("answering it replies on the socket", replies == [("probe-1", "once")], str(replies))
        check("modal closes after the reply", len(app.screen_stack) == 1)

        SHOT.parent.mkdir(parents=True, exist_ok=True)
        app.save_screenshot(str(SHOT))
        check("screenshot written", SHOT.is_file(), str(SHOT))

        # Clear the preference before deleting the workspace it points at.
        await app._run_command(commands.parse("/bind off"))
        await pilot.pause()
        check(
            "/bind off releases the workspace",
            not app._workspace_id
            and "ws:" not in str(app.query_one("#title", Static).content),
        )

        for classes, text in rows:
            if "error" in classes:
                print("  error row:", text[:160])

    # Reruns would otherwise pile up one workspace and one key per run.
    if created_id:
        check("the run deletes the workspace it created", await _delete_workspace(settings, created_id))
    if key_id:
        check("the run revokes its own key", await _revoke(settings, key_id, access_token))

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
