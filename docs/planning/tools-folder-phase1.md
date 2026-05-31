---
doc_id: tools-folder-layout
tags: [tools, architecture]
---

## `plugins/tools/` layout

```
plugins/tools/
  integrations/
    mail/providers/     # brand config only (logic in apps/backend/domain/mail/)
    mail/tools/         # mail.search, mail.read, …
    github/
    weather/
    web_search/
    friends/
    browser/
  workspace/
    bind/               # workspace.list, create, bind
    files/              # read_file, write_file, edit, …
    shell/              # bash, workspace_verify
    search/             # search, semantic_search, retrieve_context, index, …
    lsp/
    planning/           # todo (in-turn checklist)
  platform/
    agents/             # delegate, task
    tasks/              # agent_tasks OS queue
    secrets/
    scheduler/
    tool_help/
    tool_factory/
    operator/
    conversation/
    project/
    files/              # host filesystem (admin)
    shared/
  knowledge/
    kb/
    memory/
    rag/
  personal/
    dashboard/
    shopping/
    pets/
    ideas/
    tasks/              # persisted todo boards
    rss/
    calendar/
    clocks/
  creative/
    build/
    image_editor/
  outdoor/
    fishing/
    hunting/
    survival/
  security/
    security_scan/
  agent_created/        # dynamic tools mount
```

No README files under `plugins/tools/`. Domain semantics: `docs/tools-domains.md`.
