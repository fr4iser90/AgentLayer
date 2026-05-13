---
doc_id: docs-index
domain: agentlayer_docs
tags: [docs, overview]
---

## AgentLayer docs

This folder is written for **humans** and for **RAG ingestion**.

### Principles (RAG-friendly)

- **Small, self-contained sections**: each section should answer *one* question.
- **Stable headings**: use consistent `##` sections across pages.
- **Concrete anchors**: always include file paths, function names, and endpoint paths.
- **Examples**: include short JSON examples for data contracts.

### Planning

- **Coding agent roadmap & backlog** (guardrails, epics, Git phases): [`docs/planning/coding-agent-roadmap.md`](./planning/coding-agent-roadmap.md)

### Start here

- **Architecture**: [`docs/architecture/overview.md`](./architecture/overview.md)
- **Tool system**: [`docs/architecture/tools.md`](./architecture/tools.md)
- **Dashboards**: [`docs/features/dashboards.md`](./features/dashboards.md)
- **Memory**: [`docs/features/memory.md`](./features/memory.md)
- **RAG**: [`docs/features/rag.md`](./features/rag.md)
- **Discord**: [`docs/features/discord.md`](./features/discord.md)
- **HTTP API**: [`docs/api/http.md`](./api/http.md)
- **Ops runbooks**: [`docs/runbooks/`](./runbooks/)
- **Workspace persistence (Docker)**: [`docs/runbooks/workspace-persistence.md`](./runbooks/workspace-persistence.md)
- **Glossary**: [`docs/glossary.md`](./glossary.md)

### ADRs (decisions)

You already have ADRs under [`docs/adr/`](./adr/):

- [`0001-tool-and-agent-architecture.md`](./adr/0001-tool-and-agent-architecture.md)
- [`0002-tool-capabilities-convention.md`](./adr/0002-tool-capabilities-convention.md)
- [`0003-capability-governance.md`](./adr/0003-capability-governance.md)
- [`0004-scheduler-data-model.md`](./adr/0004-scheduler-data-model.md)
- [`0005-agentlayer-self-workspace-contract.md`](./adr/0005-agentlayer-self-workspace-contract.md)

