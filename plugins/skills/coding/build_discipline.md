---
skill_id: coding_build_discipline
agents: coding
---

## **Build** discipline (this stack)

- Use only ``coding_*`` / ``project_explain`` from **tools[]** — no registry meta tools.
- Map work to permission groups (read, list, glob, grep, edit, bash, task, lsp) as in your system prompt; call with complete JSON.
- Prefer ``read_file``, ``search``, and ``glob`` over shell for reads/search; prefer ``git_sync`` for git pull/fetch.
- Destructive tools may require UI approval when enabled — **ask** semantics for **edit** / **bash** when the client enables them.
- Do not re-list or re-read the same path when that output is already in the transcript; proceed to edit, bash, or a new path.
