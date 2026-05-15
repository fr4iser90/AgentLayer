# Skill plugins (`plugins/skills`)

Skills are short instruction blocks merged into the chat **system** message (same idea as dropping a tool under `plugins/tools/`).

## Convention

Create a normal Python file anywhere under this tree (subfolders allowed). Files named `__init__.py` or starting with `_` are ignored.

Each skill module **must** define:

| Name | Type | Meaning |
|------|------|--------|
| `SKILL_ID` | `str` | Unique id (`[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}`). |
| `SKILL_BODY` | `str` | Markdown / plain text injected for matching agents. |

Optional:

| Name | Type | Meaning |
|------|------|--------|
| `SKILL_BODY_FILE` | `str` | Path **relative to this `.py` file** (no `..`). Used only if `SKILL_BODY` is empty. |
| `SKILL_AGENTS` | `tuple[str, ...]` or comma-separated `str` | If set and non-empty, only these `agent_id` values receive the skill. If omitted or empty, every agent listed in `AGENT_SKILLS_PROMPT_AGENT_IDS` may receive it. |

## Overrides

- **`AGENT_SKILL_DIRS`**: comma-separated extra roots to scan instead of this directory (same pattern as `AGENT_TOOL_DIRS` for tools).
- **`AGENT_SKILLS_PROMPT_FILE`**: optional extra markdown/text appended after plugin skills.
- **`AGENT_SKILLS_MAX_TOTAL_CHARS`**: hard cap for the combined skills block (default 48000).
