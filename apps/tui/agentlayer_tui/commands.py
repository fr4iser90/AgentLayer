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

# First-arg completions for commands that have a closed set of tokens.
ARG_CHOICES: dict[str, tuple[str, ...]] = {
    "plan": ("on", "off"),
    "stream": ("on", "off"),
    "consent": ("none", "symbols", "text"),
    "index": ("full", "code", "docs", "symbols", "text", "status"),
    "delegate": DELEGATABLE,
    "bind": ("off", "--local"),
}


@dataclass(frozen=True)
class Command:
    name: str
    args: str


@dataclass(frozen=True)
class Suggestion:
    """One autocomplete row: ``insert`` goes into the prompt, ``label`` is shown in the UI."""

    insert: str
    label: str


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
    """Insert strings for a partially typed slash prefix (without trailing space)."""
    return [s.insert.rstrip() for s in suggest(prefix)]


def suggest(text: str) -> list[Suggestion]:
    """Suggestions for the current prompt value (command names or first-arg tokens)."""
    raw = text or ""
    if not raw.startswith("/"):
        return []

    body = raw[1:]
    if " " not in body:
        stem = body.lower()
        return [
            Suggestion(insert=f"/{name} ", label=f"/{name}  — {desc}")
            for name, desc in sorted(COMMANDS.items())
            if not stem or name.startswith(stem)
        ]

    name, _, rest = body.partition(" ")
    key = name.strip().lower()
    choices = ARG_CHOICES.get(key)
    if not choices:
        return []
    token = rest.strip()
    if " " in token:
        return []
    stem = token.lower()
    out: list[Suggestion] = []
    for choice in choices:
        if stem and not choice.lower().startswith(stem):
            continue
        # Trailing space when more input is expected (delegate task, local path).
        needs_more = key == "delegate" or (key == "bind" and choice == "--local")
        insert = f"/{key} {choice}" + (" " if needs_more else "")
        out.append(Suggestion(insert=insert, label=f"/{key} {choice}"))
    return out


def common_prefix(values: list[str]) -> str:
    if not values:
        return ""
    prefix = values[0]
    for value in values[1:]:
        while not value.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


def apply_tab(current: str, cycle_index: int = 0) -> tuple[str, int, list[Suggestion]]:
    """Tab-complete ``current``. Returns (new_value, next_cycle_index, visible suggestions).

    - One match → insert it.
    - Many matches → first extend to the common prefix; further tabs cycle full inserts.
    """
    matches = suggest(current)
    if not matches:
        return current, 0, []
    if len(matches) == 1:
        return matches[0].insert, 0, matches

    inserts = [m.insert for m in matches]
    shared = common_prefix(inserts)
    if shared and len(shared) > len(current):
        return shared, 0, matches

    idx = cycle_index % len(matches)
    return matches[idx].insert, (idx + 1) % len(matches), matches


def help_lines() -> list[str]:
    width = max(len(n) for n in COMMANDS) + 2
    return [f"/{name.ljust(width)}{desc}" for name, desc in sorted(COMMANDS.items())]


def format_suggest_panel(matches: list[Suggestion], *, limit: int = 12) -> str:
    """Multi-line panel text for the suggest strip."""
    if not matches:
        return ""
    shown = matches[:limit]
    lines = [m.label for m in shown]
    if len(matches) > limit:
        lines.append(f"  … +{len(matches) - limit} more  (tab to cycle)")
    elif len(matches) > 1:
        lines.append("  tab to complete / cycle")
    return "\n".join(lines)


def delegation_prompt(agent: str, task: str) -> str:
    """Phrase a turn so the orchestrator delegates instead of answering directly."""
    return (
        f"Delegate to the {agent} agent: {task}\n"
        "Use the delegate tool — do not attempt this yourself."
    )
