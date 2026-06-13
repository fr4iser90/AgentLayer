# Skill plugins (`plugins/skills`)

Skills are short instruction blocks merged into the chat **system** message (same idea as dropping a tool under `plugins/tools/`).

## Convention (markdown — preferred)

Create a `.md` file anywhere under this tree (subfolders allowed). Files named `README.md` or starting with `_` are ignored.

Each skill file **must** start with YAML frontmatter:

```markdown
---
skill_id: orchestrator_delegate
agents: general
---

## Your skill body (markdown)
```

| Frontmatter key | Meaning |
|-----------------|--------|
| `skill_id` | Unique id (`[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}`). |
| `agents` | Optional. Comma-separated string or YAML list — only these `agent_id` values receive the skill. Omit to apply to every agent that loads skills (any tool-using chat). |
| `exclude_agents` | Optional. Skip these agent ids even when `agents` is omitted. |
| `when_delegate_mode` | Optional. Include only when the run's delegate mode matches (e.g. `fix_from_artifact`). |

Everything after the closing `---` is injected as markdown for matching agents.

Skills load for **every agent with tools** (not plain chat). Filter with frontmatter — no hardcoded discipline in `apps/backend/domain/`.

**Secrets (two layers):**
1. **Runtime bootstrap** (`user_secrets_bootstrap` in planner) — per user, lists configured key *names* only. Injected for all signed-in chats so orchestrator knows what exists.
2. **Skills** — *how* to act: `secrets_orchestrator` (general), `secrets_handling` (coding, security_auditor). Math/research/etc. get neither.

## Alternative (Python)

For inline one-liners you can still use a `.py` file with `SKILL_ID`, `SKILL_BODY`, and optional `SKILL_AGENTS`. Do **not** pair a `.py` stub with a separate `.md` — use frontmatter markdown instead.

## Layout

Organize skills by domain (subfolders), e.g.:

- `orchestrator/` — workflows for `general` (`agents: general`)
- `coding/` — plan/build discipline for `coding_plan` / `coding`
- `security/` — SSC discipline for `security_auditor`
- `dashboard/` — layout discipline for `dashboard`
- `shared/` — `tool_usage` (exclude `general`); `secrets_handling` only for agents with save/request secret tools
- `orchestrator/secrets_orchestrator.md` — `general` only (status + delegate, no save tools)

`tool_discipline_preset` in `agent.yaml` is only for turn hooks; all discipline text belongs here.

## Overrides

- **`AGENT_SKILL_DIRS`**: comma-separated extra roots to scan instead of this directory (same pattern as `AGENT_TOOL_DIRS` for tools).
- **`AGENT_SKILLS_PROMPT_FILE`**: optional extra markdown/text appended after plugin skills.
- **`AGENT_SKILLS_MAX_TOTAL_CHARS`**: hard cap for the combined skills block (default 48000).
