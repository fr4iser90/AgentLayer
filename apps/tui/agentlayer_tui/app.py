"""The Textual application: transcript, goal strip, prompt line."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import asyncio
import json

from rich.markup import escape
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Static

from . import commands
from .client import AgentLayerError, ChatSocket, RestClient, chat_body
from .config import Settings
from .events import (
    Line,
    PermissionRequest,
    ToolInvoke,
    TurnState,
    answer_from_completion,
    goal_strip,
    interpret,
)
from .jail import bind_refusal_reason
from .symbol_scan import scan_markdown, scan_symbols
from .local_exec import ADVERTISED_TOOLS, GATED_TOOLS, execute
from .workspaces import (
    format_index_status,
    format_workspace_rows,
    is_client_workspace,
    normalize_index_mode,
    resolve_workspace,
    short_id,
    take_flag,
)


class PermissionScreen(ModalScreen[str]):
    """Answer ``agent.permission_ask`` before a gated workspace tool runs."""

    BINDINGS = [
        Binding("y", "reply('once')", "allow once"),
        Binding("a", "reply('always')", "always"),
        Binding("n", "reply('reject')", "reject"),
        Binding("escape", "reply('reject')", "reject"),
    ]

    def __init__(self, request: PermissionRequest) -> None:
        super().__init__()
        self._request = request

    def compose(self) -> ComposeResult:
        req = self._request
        preview = req.args_preview[:600] or "(no arguments)"
        yield Static(
            f"[b]{escape(req.tool_name)}[/b] wants to run"
            + (f" (round {req.round})" if req.round else ""),
            classes="perm-title",
        )
        yield Static(preview, classes="perm-args", markup=False)
        with Horizontal(classes="perm-buttons"):
            yield Button("Allow once (y)", variant="primary", id="once")
            yield Button("Always (a)", id="always")
            yield Button("Reject (n)", variant="error", id="reject")

    def action_reply(self, reply: str) -> None:
        self.dismiss(reply)

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id or "reject")


class AgentLayerTui(App[None]):
    # Mouse-drag selects transcript text; ctrl+c copies a selection, otherwise cancels the turn.
    ALLOW_SELECT = True

    CSS = """
    Screen { layers: base overlay; }
    #transcript { height: 1fr; padding: 0 1; }
    .line { width: 100%; }
    .user { color: $text; text-style: bold; margin-top: 1; }
    .assistant { color: $text; margin-top: 1; }
    .reasoning { color: $text-muted; text-style: italic; }
    .tool_start { color: $accent; }
    .tool_done { color: $success; }
    .tool_error { color: $error; }
    .sub_start { color: $accent; text-style: bold; }
    .sub_done { color: $success; }
    .goal { color: $warning; }
    .info, .dim { color: $text-muted; }
    .warn { color: $warning; }
    .error { color: $error; text-style: bold; }
    #strip { height: 2; padding: 0 1; background: $panel; color: $text-muted; }
    #hint { height: 1; padding: 0 1; color: $text-muted; }
    #prompt { border: none; background: $surface; }
    PermissionScreen { align: center middle; }
    PermissionScreen > Static { width: 80%; }
    .perm-title { padding: 1 2 0 2; background: $panel; }
    .perm-args { padding: 0 2 1 2; background: $panel; color: $text-muted; }
    .perm-buttons { width: 80%; height: auto; background: $panel; padding: 0 2 1 2; }
    """

    BINDINGS = [
        Binding("ctrl+c", "cancel_turn", "copy / cancel", priority=True, show=True),
        Binding("ctrl+shift+c", "copy_selection", "copy", show=True),
        Binding("ctrl+d", "quit", "quit", priority=True, show=True),
        Binding("ctrl+l", "clear", "clear", show=False),
        # priority, or the focused Input swallows tab for focus navigation. There is only one
        # input to focus, so nothing is lost.
        Binding("tab", "complete", "complete", priority=True, show=False),
    ]

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._rest = RestClient(settings)
        self._socket = ChatSocket(settings)
        self._state = TurnState()
        self._history: list[dict[str, str]] = []
        self._keyed: dict[str, Static] = {}
        self._answer_widget: Static | None = None
        self._reasoning_widget: Static | None = None
        self._busy = False
        self._last_tools: list[str] = []
        self._conversation_id = ""
        self._workspace_id = ""
        self._workspace_name = ""
        self._workspace_local = False
        self._workspace_path = ""
        self._local_always: set[str] = set()

    # ---------------------------------------------------------------- layout

    def compose(self) -> ComposeResult:
        # markup=False throughout: agent output is data, not Textual markup, and escaping it
        # would leak backslashes into anything containing brackets.
        yield Static(self._title_text(), id="title", markup=False)
        yield VerticalScroll(id="transcript")
        yield Static("", id="strip", markup=False)
        yield Static("", id="hint", markup=False)
        yield Input(placeholder="Ask, or /help", id="prompt")
        yield Footer()

    def _title_text(self) -> str:
        s = self._settings
        bits = [s.base_url, s.model or "default model", s.agent_id or "general"]
        if self._workspace_name or self._workspace_id:
            label = f"ws:{self._workspace_name or short_id(self._workspace_id)}"
            if self._workspace_local:
                label += " (local)"
            bits.append(label)
        return "  AgentLayer  \u00b7  " + "  \u00b7  ".join(bits)

    async def on_mount(self) -> None:
        self._refresh_strip()
        self.query_one("#prompt", Input).focus()
        self._append(Line("info", "connecting\u2026"))
        try:
            await self._socket.connect()
        except AgentLayerError as e:
            self._append(Line("error", str(e)))
            self._set_hint("not connected")
            return
        self._append(Line("info", "connected. /help for commands."))
        try:
            await self._socket.send_client_capabilities(sorted(ADVERTISED_TOOLS))
        except AgentLayerError as e:
            self._append(Line("warn", f"could not advertise local tools: {e}"))
        self.run_worker(self._consume_events(), exclusive=False, name="events")
        await self._load_runtime_snapshot()

    async def on_unmount(self) -> None:
        await self._socket.close()
        await self._rest.aclose()

    # ------------------------------------------------------------ transcript

    def _append(self, line: Line) -> Static:
        indent = "  \u2502 " * line.depth
        widget = Static(f"{indent}{line.text}", classes=f"line {line.kind}", markup=False)
        transcript = self.query_one("#transcript", VerticalScroll)
        transcript.mount(widget)
        if line.key:
            self._keyed[line.key] = widget
        transcript.scroll_end(animate=False)
        return widget

    def _apply_line(self, line: Line) -> None:
        """Rewrite the row a key already owns, so a tool result lands on its own line."""
        if line.key and line.key in self._keyed:
            indent = "  \u2502 " * line.depth
            widget = self._keyed[line.key]
            widget.update(f"{indent}{line.text}")
            widget.set_classes(f"line {line.kind}")
            return
        self._append(line)

    def _set_hint(self, text: str) -> None:
        self.query_one("#hint", Static).update(text)

    def _refresh_strip(self) -> None:
        rows = goal_strip(self._state)
        self.query_one("#strip", Static).update("\n".join(rows))

    def action_clear(self) -> None:
        self.query_one("#transcript", VerticalScroll).remove_children()
        self._keyed.clear()
        self._answer_widget = None
        self._reasoning_widget = None

    def action_complete(self) -> None:
        prompt = self.query_one("#prompt", Input)
        matches = commands.completions(prompt.value)
        if len(matches) == 1:
            prompt.value = matches[0] + " "
            prompt.cursor_position = len(prompt.value)
        elif matches:
            self._append(Line("dim", "  ".join(matches)))

    # ----------------------------------------------------------------- turns

    @on(Input.Submitted, "#prompt")
    async def _submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        command = commands.parse(text)
        if command is not None:
            await self._run_command(command)
            return
        await self._start_turn(text)

    async def _start_turn(self, prompt: str, *, echo: str | None = None) -> None:
        if self._busy:
            self._append(Line("warn", "a turn is already running — ctrl-c cancels it"))
            return
        if not self._socket.connected:
            self._append(Line("error", "not connected"))
            return
        if not await self._ensure_conversation():
            return
        self._append(Line("user", f"\u203a {echo or prompt}"))
        self._state.reset_turn()
        self._keyed.clear()
        self._answer_widget = None
        self._reasoning_widget = None
        self._busy = True
        self._set_hint("thinking\u2026")
        body = chat_body(
            self._settings,
            prompt,
            history=self._history,
            conversation_id=self._conversation_id,
            workspace_id=self._workspace_id,
        )
        self._history.append({"role": "user", "content": prompt})
        try:
            await self._socket.send_chat(body)
        except AgentLayerError as e:
            self._busy = False
            self._append(Line("error", str(e)))

    async def _ensure_conversation(self) -> bool:
        """Created lazily on the first turn: the goal and todo tools need a saved thread,
        and creating one on startup would litter the thread list with empty chats."""
        if self._conversation_id:
            return True
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            self._conversation_id = await self._rest.create_conversation(
                f"TUI {stamp}",
                agent_id=self._settings.agent_id,
                workspace_id=self._workspace_id,
            )
        except Exception as e:  # noqa: BLE001
            self._append(Line("error", f"could not start a conversation: {e}"))
            return False
        self._append(Line("dim", f"conversation {self._conversation_id[:8]}"))
        return True

    def _copy_selection(self) -> bool:
        """Copy highlighted transcript text. Returns True when there was a selection."""
        selected = self.screen.get_selected_text()
        if not selected:
            return False
        self.copy_to_clipboard(selected)
        preview = selected.replace("\n", " ")[:48]
        self._set_hint(f"copied {len(selected)} chars: {preview}")
        return True

    def action_copy_selection(self) -> None:
        if not self._copy_selection():
            self._set_hint("select text first (drag with the mouse)")

    async def action_cancel_turn(self) -> None:
        if self._copy_selection():
            return
        if not self._busy:
            self._set_hint("nothing running")
            return
        try:
            await self._socket.send_cancel()
            self._set_hint("cancelling\u2026")
        except AgentLayerError as e:
            self._append(Line("error", str(e)))

    # ---------------------------------------------------------------- events

    async def _consume_events(self) -> None:
        try:
            async for msg in self._socket.events():
                self._handle(msg)
        except Exception as e:  # noqa: BLE001 — a dead socket must be visible, not silent
            self._append(Line("error", f"connection lost: {e}"))
            self._busy = False
            self._set_hint("disconnected")

    def _handle(self, msg: dict[str, Any]) -> None:
        update = interpret(msg, self._state)

        for line in update.lines:
            self._apply_line(line)

        if update.delta:
            self._state.answer += update.delta
            if self._answer_widget is None:
                self._answer_widget = self._append(Line("assistant", ""))
            self._answer_widget.update(self._state.answer)
            self.query_one("#transcript", VerticalScroll).scroll_end(animate=False)

        if update.reasoning_delta:
            self._state.reasoning += update.reasoning_delta
            if self._reasoning_widget is None:
                self._reasoning_widget = self._append(Line("reasoning", ""))
            self._reasoning_widget.update(self._state.reasoning[-2000:])

        if update.strip_changed:
            self._refresh_strip()

        if update.wait_hint:
            self._set_hint(update.wait_hint)
        elif update.clear_wait_hint and self._busy:
            self._set_hint("thinking\u2026")

        if update.permission is not None:
            self._ask_permission(update.permission)

        if update.tool_invoke is not None:
            self.run_worker(self._run_local_tool(update.tool_invoke), exclusive=False)

        if update.completion is not None:
            self._finish(update.completion)
        elif update.finished:
            self._busy = False
            self._set_hint(update.error or "")

    def _finish(self, completion: dict[str, Any]) -> None:
        self._busy = False
        self._set_hint("")
        final = answer_from_completion(completion)
        text = self._state.answer.strip() or final
        if text:
            if self._answer_widget is None:
                self._answer_widget = self._append(Line("assistant", ""))
            self._answer_widget.update(text)
            self._history.append({"role": "assistant", "content": text})
        tools = completion.get("forwarded_tools")
        if isinstance(tools, list):
            self._last_tools = [str(t) for t in tools]
        self.query_one("#transcript", VerticalScroll).scroll_end(animate=False)

    def _ask_permission(self, request: PermissionRequest) -> None:
        async def reply(answer: str | None) -> None:
            chosen = answer or "reject"
            try:
                await self._socket.send_permission(request.request_id, chosen)
            except AgentLayerError as e:
                self._append(Line("error", str(e)))
                return
            self._append(Line("warn", f"{request.tool_name}: {chosen}"))

        self.push_screen(PermissionScreen(request), reply)

    async def _run_local_tool(self, invoke: ToolInvoke) -> None:
        """Execute an ``agent.tool_invoke`` against the bound local directory and reply."""

        async def reply(*, ok: bool, result: str = "", error: str = "") -> None:
            try:
                await self._socket.send_tool_result(
                    invoke.request_id, ok=ok, result=result, error=error
                )
            except AgentLayerError as e:
                self._append(Line("error", str(e)))

        if not invoke.request_id:
            return
        if not self._workspace_local or not self._workspace_path:
            await reply(ok=False, error="unsupported")
            self._append(Line("warn", f"{invoke.tool_name}: no local workspace bound"))
            return
        root = Path(self._workspace_path)
        if invoke.tool_name in GATED_TOOLS and invoke.tool_name not in self._local_always:
            preview = json.dumps(invoke.arguments, ensure_ascii=False, default=str)[:2000]
            request = PermissionRequest(
                request_id=invoke.request_id,
                tool_name=invoke.tool_name,
                args_preview=preview,
                round=invoke.round,
            )
            chosen = await self.push_screen_wait(PermissionScreen(request))
            answer = chosen or "reject"
            if answer == "always":
                self._local_always.add(invoke.tool_name)
            if answer not in ("once", "always"):
                await reply(ok=False, error="User rejected permission for this tool call.")
                self._append(Line("warn", f"{invoke.tool_name}: rejected"))
                return
            self._append(Line("warn", f"{invoke.tool_name}: {answer}"))
        payload = await asyncio.to_thread(execute, invoke.tool_name, invoke.arguments, root)
        try:
            parsed = json.loads(payload)
            ok = bool(parsed.get("ok")) if isinstance(parsed, dict) else True
        except (TypeError, ValueError):
            ok = True
        await reply(ok=True, result=payload)
        mark = "ok" if ok else "failed"
        self._append(Line("tool_done" if ok else "tool_error", f"{invoke.tool_name} {mark} (local)"))

    # -------------------------------------------------------------- commands

    async def _run_command(self, command: commands.Command) -> None:
        name, args = command.name, command.args

        if name in ("quit", "exit", "q"):
            self.exit()
            return

        if name == "help":
            for line in commands.help_lines():
                self._append(Line("dim", line))
            return

        if name == "clear":
            self.action_clear()
            return

        if name == "cancel":
            await self.action_cancel_turn()
            return

        if name == "continue":
            await self._socket.send_continue()
            self._set_hint("resuming\u2026")
            return

        if name == "stream":
            self._settings.stream = args.strip().lower() not in ("off", "false", "0", "no")
            self._append(Line("info", f"streaming {'on' if self._settings.stream else 'off'}"))
            return

        if name == "new":
            self._history.clear()
            self._state = TurnState()
            self._conversation_id = ""
            self.action_clear()
            self._refresh_strip()
            kept = f", still on {self._workspace_name}" if self._workspace_id else ""
            self._append(
                Line("info", f"new conversation (created on the next message{kept})")
            )
            return

        if name == "resume":
            if not args.strip():
                self._append(Line("warn", "/resume <conversation id>"))
                return
            await self._resume(args.strip())
            return

        if name == "tools":
            if self._last_tools:
                self._append(Line("dim", ", ".join(sorted(self._last_tools))))
            else:
                self._append(Line("dim", "no tool list yet — run a turn first"))
            return

        if name == "delegate":
            agent, _, task = args.partition(" ")
            agent = agent.strip()
            if not agent or not task.strip():
                self._append(Line("warn", commands.COMMANDS["delegate"]))
                return
            if agent not in commands.DELEGATABLE:
                self._append(
                    Line("warn", f"delegatable: {', '.join(commands.DELEGATABLE)}")
                )
                return
            await self._start_turn(
                commands.delegation_prompt(agent, task.strip()),
                echo=f"/delegate {agent} {task.strip()}",
            )
            return

        if name == "goal":
            if args.strip():
                await self._start_turn(
                    f"Create a conversation goal with this objective and then start on it: "
                    f"{args.strip()}",
                    echo=f"/goal {args.strip()}",
                )
                return
            self._refresh_strip()
            self._append(Line("dim", " | ".join(goal_strip(self._state))))
            return

        if name == "todos":
            if not self._state.todos:
                self._append(Line("dim", "no todos"))
            for todo in self._state.todos:
                status = str(todo.get("status") or "pending")
                self._append(Line("dim", f"[{status}] {todo.get('content')}"))
            return

        if name == "plan":
            want = args.strip().lower() not in ("off", "false", "0", "no")
            await self._start_turn(
                f"{'Enter' if want else 'Leave'} plan mode now using the plan mode tool.",
                echo=f"/plan {'on' if want else 'off'}",
            )
            return

        if name in ("workspace", "ws"):
            await self._cmd_workspace(args)
            return

        if name == "bind":
            await self._cmd_bind(args)
            return

        if name == "index":
            await self._cmd_index(args)
            return

        if name == "consent":
            await self._cmd_consent(args)
            return

        await self._run_rest_command(name, args)

    async def _resume(self, query: str) -> None:
        """``/threads`` prints eight-character ids, so accept a prefix as well as a full uuid."""
        try:
            convs = await self._rest.conversations()
        except Exception as e:  # noqa: BLE001
            self._append(Line("error", f"{type(e).__name__}: {e}"))
            return
        match = next((c for c in convs if str(c.get("id")) == query), None)
        if match is None:
            hits = [c for c in convs if str(c.get("id") or "").startswith(query)]
            if len(hits) > 1:
                self._append(Line("warn", f"{len(hits)} conversations start with {query!r}:"))
                for conv in hits:
                    self._append(
                        Line("dim", f"  {str(conv.get('id'))[:12]}  {conv.get('title') or ''}")
                    )
                return
            match = hits[0] if hits else None
        if match is None:
            self._append(Line("warn", f"no conversation matches {query!r} \u2014 /threads"))
            return

        self._conversation_id = str(match.get("id"))
        self._history.clear()
        self._state = TurnState()
        self.action_clear()
        title = str(match.get("title") or "(untitled)")
        self._append(Line("info", f"resumed {self._conversation_id[:8]}  {title}"))
        await self._adopt_workspace(str(match.get("workspace_id") or ""))
        await self._load_runtime_snapshot()

    # ------------------------------------------------------------ workspaces

    def _local_bind_path(self, raw: str) -> tuple[str, str | None]:
        """Resolve a ``--local`` path and refuse home, ``/``, and system trees."""
        path = (raw or "").strip() or str(Path.cwd())
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = candidate.resolve()
        else:
            try:
                candidate = candidate.resolve()
            except OSError as e:
                return path, str(e)
        reason = bind_refusal_reason(candidate)
        if reason:
            return str(candidate), reason
        return str(candidate), None

    async def _adopt_workspace(self, workspace_id: str) -> None:
        """Mirror a conversation's stored binding locally, naming it if we can."""
        self._workspace_id = workspace_id
        self._workspace_name = ""
        self._workspace_local = False
        self._workspace_path = ""
        if workspace_id:
            try:
                for row in await self._rest.workspaces():
                    if str(row.get("id")) == workspace_id:
                        self._workspace_name = str(row.get("name") or "")
                        self._workspace_local = is_client_workspace(row)
                        self._workspace_path = str(row.get("path") or "")
                        break
            except Exception:  # noqa: BLE001 — a name is cosmetic, the id is what matters
                pass
            where = " (local)" if self._workspace_local else ""
            self._append(
                Line("dim", f"workspace {self._workspace_name or short_id(workspace_id)}{where}")
            )
        self.query_one("#title", Static).update(self._title_text())

    async def _cmd_workspace(self, args: str) -> None:
        verb, _, rest = args.partition(" ")
        try:
            if verb.strip().lower() == "create":
                local, rest = take_flag(rest, "--local")
                if local:
                    name, _, raw_path = rest.partition(" ")
                    if not name:
                        self._append(
                            Line("warn", "/workspace create --local <name> [absolute path]")
                        )
                        return
                    path, err = self._local_bind_path(raw_path.strip() or str(Path.cwd()))
                    if err:
                        self._append(Line("warn", err))
                        return
                    row = await self._rest.create_workspace(
                        name, execution_mode="client", path=path
                    )
                    self._append(
                        Line(
                            "info",
                            f"created local {short_id(row.get('id'))}  {row.get('name')}  {path}",
                        )
                    )
                    await self._bind_row(row)
                    return
                name, _, git_url = rest.strip().partition(" ")
                if not name:
                    self._append(Line("warn", "/workspace create <name> [git url]"))
                    return
                row = await self._rest.create_workspace(name, git_url=git_url.strip())
                self._append(
                    Line("info", f"created {short_id(row.get('id'))}  {row.get('name')}")
                )
                await self._bind_row(row)
                return
            rows = await self._rest.workspaces()
            for line in format_workspace_rows(rows, self._workspace_id):
                self._append(Line("dim", line))
        except AgentLayerError as e:
            self._append(Line("error", str(e)))
        except Exception as e:  # noqa: BLE001
            self._append(Line("error", f"{type(e).__name__}: {e}"))

    async def _cmd_bind(self, args: str) -> None:
        query = args.strip()
        if not query:
            if self._workspace_id:
                self._append(
                    Line("dim", f"bound to {self._workspace_name} ({short_id(self._workspace_id)})")
                )
            else:
                self._append(Line("dim", "nothing bound — /workspace to list"))
            return

        local, local_path = take_flag(query, "--local")
        if local:
            path, err = self._local_bind_path(local_path or str(Path.cwd()))
            if err:
                self._append(Line("warn", err))
                return
            try:
                rows = await self._rest.workspaces()
            except Exception as e:  # noqa: BLE001
                self._append(Line("error", f"{type(e).__name__}: {e}"))
                return
            match = next(
                (
                    r
                    for r in rows
                    if is_client_workspace(r) and str(r.get("path") or "") == path
                ),
                None,
            )
            if match is None:
                name = Path(path).name or "local"
                try:
                    match = await self._rest.create_workspace(
                        name, execution_mode="client", path=path
                    )
                except AgentLayerError as e:
                    self._append(Line("error", str(e)))
                    return
                self._append(
                    Line("info", f"created local {short_id(match.get('id'))}  {name}  {path}")
                )
            await self._bind_row(match)
            return

        if query.lower() in ("off", "none", "clear"):
            if not await self._ensure_conversation():
                return
            await self._rest.bind_workspace(self._conversation_id, None)
            self._workspace_id = self._workspace_name = ""
            self._workspace_local = False
            self._workspace_path = ""
            self._append(Line("info", "unbound"))
            self.query_one("#title", Static).update(self._title_text())
            return

        try:
            rows = await self._rest.workspaces()
        except Exception as e:  # noqa: BLE001
            self._append(Line("error", f"{type(e).__name__}: {e}"))
            return
        match, candidates = resolve_workspace(rows, query)
        if match is None:
            if candidates:
                self._append(Line("warn", f"{len(candidates)} matches — be more specific:"))
                for row in candidates:
                    self._append(Line("dim", f"  {short_id(row.get('id'))}  {row.get('name')}"))
            else:
                self._append(Line("warn", f"no workspace matches {query!r}"))
            return
        await self._bind_row(match)

    async def _bind_row(self, row: dict[str, Any]) -> None:
        if not await self._ensure_conversation():
            return
        workspace_id = str(row.get("id") or "")
        if not workspace_id:
            self._append(Line("error", "workspace has no id"))
            return
        ok = await self._rest.bind_workspace(self._conversation_id, workspace_id)
        self._workspace_id = workspace_id
        self._workspace_name = str(row.get("name") or "")
        self._workspace_local = is_client_workspace(row)
        self._workspace_path = str(row.get("path") or "")
        self.query_one("#title", Static).update(self._title_text())
        if self._workspace_local:
            try:
                await self._socket.send_client_capabilities(sorted(ADVERTISED_TOOLS))
            except AgentLayerError:
                pass
        if ok:
            extra = "  local" if self._workspace_local else ""
            self._append(
                Line("info", f"bound {self._workspace_name} ({short_id(workspace_id)}){extra}")
            )
        else:
            # The turn still gets workspace_id in its body, so coding works this session.
            self._append(Line("warn", "bound for this session only \u2014 saving the preference failed"))

    async def _cmd_index(self, args: str) -> None:
        if not self._workspace_id:
            self._append(Line("warn", "bind a workspace first — /workspace, then /bind <name>"))
            return
        arg = args.strip().lower()
        try:
            if arg in ("status", "state", "?"):
                for line in format_index_status(await self._rest.index_status(self._workspace_id)):
                    self._append(Line("dim", line))
                return
            if self._workspace_local:
                await self._cmd_index_local(arg)
                return
            mode = normalize_index_mode(arg)
            if mode is None or mode in ("symbols", "text"):
                self._append(Line("warn", "mode must be full, code or docs"))
                return
            result = await self._rest.index_workspace(self._workspace_id, mode)
            if result.get("already_running"):
                self._append(Line("info", f"index ({mode}) already running"))
            elif result.get("started"):
                self._append(Line("info", f"index ({mode}) started — /index status to follow"))
            else:
                self._append(Line("warn", f"index ({mode}) did not start"))
        except AgentLayerError as e:
            self._append(Line("error", str(e)))
        except Exception as e:  # noqa: BLE001
            self._append(Line("error", f"{type(e).__name__}: {e}"))

    async def _cmd_index_local(self, arg: str) -> None:
        """Scan this machine and upload. The server never sees the tree."""
        root = Path(self._workspace_path) if self._workspace_path else Path.cwd()
        mode = (arg or "symbols").strip().lower()
        if mode in ("", "code"):
            mode = "symbols"
        if mode == "docs":
            mode = "text"
        if mode == "full":
            await self._upload_local_symbols(root)
            await self._upload_local_text(root)
            return
        if mode == "symbols":
            await self._upload_local_symbols(root)
            return
        if mode == "text":
            await self._upload_local_text(root)
            return
        self._append(Line("warn", "local index mode must be symbols, text, or full"))

    async def _upload_local_symbols(self, root: Path) -> None:
        self._append(Line("dim", f"scanning symbols under {root} …"))
        files, errors = scan_symbols(root)
        for err in errors[:8]:
            self._append(Line("warn", err))
        result = await self._rest.upload_index_symbols(self._workspace_id, files)
        inner = result.get("result") if isinstance(result.get("result"), dict) else result
        n = inner.get("files") if isinstance(inner, dict) else len(files)
        q = inner.get("qdrant_indexed") if isinstance(inner, dict) else "?"
        self._append(Line("info", f"uploaded {n} file(s), {q} symbols embedded"))

    async def _upload_local_text(self, root: Path) -> None:
        self._append(Line("dim", f"scanning markdown under {root} …"))
        docs, errors = scan_markdown(root)
        for err in errors[:8]:
            self._append(Line("warn", err))
        if not docs:
            self._append(Line("warn", "no markdown files to upload"))
            return
        result = await self._rest.upload_index_text(self._workspace_id, docs)
        inner = result.get("result") if isinstance(result.get("result"), dict) else result
        n = inner.get("files_ingested") if isinstance(inner, dict) else len(docs)
        self._append(Line("info", f"uploaded {n} markdown file(s) for docs RAG"))

    async def _cmd_consent(self, args: str) -> None:
        if not self._workspace_id:
            self._append(Line("warn", "bind a workspace first — /workspace, then /bind <name>"))
            return
        want = args.strip().lower()
        try:
            if not want:
                status = await self._rest.index_status(self._workspace_id)
                have = status.get("index_consent_effective") or status.get("index_consent") or "?"
                cap = status.get("index_consent_operator_max") or "?"
                self._append(Line("dim", f"index_consent={have}  operator max={cap}"))
                self._append(Line("dim", "set with /consent none|symbols|text — the server may refuse a raise"))
                return
            if want not in ("none", "symbols", "text"):
                self._append(Line("warn", "consent must be none, symbols, or text"))
                return
            row = await self._rest.patch_workspace(self._workspace_id, index_consent=want)
            have = row.get("index_consent_effective") or row.get("index_consent") or want
            cap = row.get("index_consent_operator_max")
            extra = f"  (operator max {cap})" if cap else ""
            self._append(Line("info", f"index_consent={have}{extra}"))
        except AgentLayerError as e:
            self._append(Line("error", str(e)))
        except Exception as e:  # noqa: BLE001
            self._append(Line("error", f"{type(e).__name__}: {e}"))

    async def _run_rest_command(self, name: str, args: str) -> None:
        """Commands that need the HTTP API."""
        try:
            if name == "agents":
                for agent in await self._rest.agents():
                    aid = str(agent.get("id") or agent.get("agent_id") or "?")
                    desc = str(agent.get("description") or agent.get("name") or "")
                    self._append(Line("dim", f"{aid:<18}{desc[:80]}"))
                return

            if name in ("model", "models"):
                if name == "model" and args.strip():
                    self._settings.model = args.strip()
                    self.query_one("#title", Static).update(self._title_text())
                    self._append(Line("info", f"model: {self._settings.model}"))
                    return
                for model in await self._rest.models():
                    mid = str(model.get("id") or "?")
                    owner = str(model.get("owned_by") or "")
                    self._append(Line("dim", f"{mid:<46}{owner}"))
                return

            if name == "threads":
                for conv in await self._rest.conversations():
                    self._append(
                        Line("dim", f"{str(conv.get('id'))[:8]}  {conv.get('title') or '(untitled)'}")
                    )
                return

            if name == "runtime":
                snapshot = await self._rest.runtime(model=self._settings.model)
                budget = snapshot.get("context_budget") or {}
                mcp = snapshot.get("mcp") or {}
                self._append(
                    Line(
                        "dim",
                        f"context window {budget.get('context_window_tokens', '?')} tokens, "
                        f"soft limit {budget.get('soft_limit_tokens', '?')}, "
                        f"source {budget.get('budget_source', '?')}",
                    )
                )
                if isinstance(mcp, dict) and mcp:
                    self._append(Line("dim", f"mcp: {mcp.get('status', mcp)}"))
                return

            self._append(Line("warn", f"unknown command /{name} — /help"))
        except AgentLayerError as e:
            self._append(Line("error", str(e)))
        except Exception as e:  # noqa: BLE001 — HTTP errors belong on screen, not in a log
            self._append(Line("error", f"{type(e).__name__}: {e}"))

    async def _load_runtime_snapshot(self) -> None:
        """``/v1/chat/runtime`` is the natural startup call: budget, MCP, goal in one response."""
        try:
            snapshot = await self._rest.runtime(
                model=self._settings.model, conversation_id=self._conversation_id
            )
        except Exception:  # noqa: BLE001 — a missing snapshot must not block the prompt
            return
        goal_block = snapshot.get("conversation_goal")
        if isinstance(goal_block, dict):
            goal = goal_block.get("goal")
            self._state.goal = goal if isinstance(goal, dict) else None
            todos = goal_block.get("todos")
            self._state.todos = [t for t in todos if isinstance(t, dict)] if isinstance(todos, list) else []
            self._state.plan_mode = bool(goal_block.get("plan_mode"))
            self._refresh_strip()
        budget = snapshot.get("context_budget")
        if isinstance(budget, dict) and budget.get("context_window_tokens"):
            self._append(
                Line("info", f"context window {budget['context_window_tokens']} tokens")
            )
