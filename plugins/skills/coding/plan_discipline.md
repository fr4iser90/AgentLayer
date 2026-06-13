---
skill_id: coding_plan_discipline
agents: coding_plan
---

## **Plan** discipline (Plan-style)

- **Read-only:** no ``bash``, no ``git_sync``/``git_push``, no edit tools (``write_file``, ``edit``, ``replace``, ``apply_patch``). Use Build (``coding``) or ``delegate`` with ``agent_id=coding`` for shell and writes.
- Default stance: **analyze first**, then a markdown handoff for Build.
- **Git / sub-agent debug:** use ``git_read`` (status, log, branch, diff_stat) and ``read_file`` on named paths — **not** repo-wide ``search`` without ``path_prefix``.
- **Search on Plan:** ``search`` requires ``path_prefix`` scoped to a subdirectory; use ``retrieve_context`` for open exploration.
- Reuse existing tool results in the transcript — no identical tool+arguments spam.
- **Final answer (mandatory):** after ``read_file`` / ``search``, your last message must include **file path** and a **verbatim excerpt** from the tool output (e.g. ``README.md: Hello World!``). Never end with only ``[read_file]`` or “I read the file” without quoted content.
