"""Slash command parsing and the help table.

Kept separate from the app so the command surface is inspectable (and testable) without
starting a terminal.
"""

from __future__ import annotations

from dataclasses import dataclass

# Specialists are reachable only as sub-runs: chat_completion forces any agent_id outside
# the chat-surface set back to `general`, so /agent coding would silently not work.
# See ADR 0008, "Agent selection is not an agent picker".
DELEGATABLE = ("coding", "coding_plan", "security_auditor")


@dataclass(frozen=True)
class Command:
    name: str
    args: str


COMMANDS: dict[str, str] = {
    "help": "show this list",
    "quit": "leave the TUI",
    "cancel": "abort the running turn (same as ctrl-c)",
    "continue": "resume after a step-mode pause",
    "delegate": "/delegate <agent> <task> — hand off to " + ", ".join(DELEGATABLE),
    "goal": "show the current goal, or /goal <text> to set one",
    "todos": "show the todo list",
    "plan": "/plan on|off — toggle plan mode",
    "model": "/model <id> — switch model, or list them",
    "models": "list models with provider reachability",
    "agents": "list chat-surface agents",
    "new": "start a fresh conversation",
    "resume": "/resume <id> — continue a saved conversation",
    "threads": "list conversations",
    "workspace": "list, /workspace create <name> [git url], or /workspace create --local <name> [path]",
    "bind": "/bind <id|name>, /bind --local [path], /bind off",
    "index": "/index [full|code|docs|symbols|text] to (re)build, /index status to inspect",
    "consent": "/consent [none|symbols|text] — what may leave this machine (ADR 0009)",
    "runtime": "context budget, MCP status, vision",
    "tools": "tools forwarded on the last turn",
    "stream": "/stream on|off — token streaming",
    "clear": "clear the transcript",
}


def parse(text: str) -> Command | None:
    """Return a command for input starting with ``/``, else ``None`` (it is a prompt)."""
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return None
    body = raw[1:].strip()
    if not body:
        return Command("help", "")
    head, _, rest = body.partition(" ")
    return Command(head.strip().lower(), rest.strip())


def completions(prefix: str) -> list[str]:
    """Command names matching a partially typed ``/pre``."""
    raw = (prefix or "").strip()
    if not raw.startswith("/"):
        return []
    stem = raw[1:].lower()
    return sorted(f"/{name}" for name in COMMANDS if name.startswith(stem))


def help_lines() -> list[str]:
    width = max(len(n) for n in COMMANDS) + 2
    return [f"/{name.ljust(width)}{desc}" for name, desc in sorted(COMMANDS.items())]


def delegation_prompt(agent: str, task: str) -> str:
    """Phrase a turn so the orchestrator delegates instead of answering directly."""
    return (
        f"Delegate to the {agent} agent: {task}\n"
        "Use the delegate tool — do not attempt this yourself."
    )
