---
doc_id: docs-index
domain: agentlayer_docs
tags: [docs, overview]
---

## AgentLayer docs

This folder is written for **humans** and for **RAG ingestion**.

### Principles (RAG-friendly)

- **Conventions:** [`docs/CONVENTIONS.md`](./CONVENTIONS.md) — layout, style, scheduler doc modes (`respect` / `bootstrap`).
- **Doc profile (agent memory):** [`docs/DOC_PROFILE.md`](./DOC_PROFILE.md) — doc roots and inventory; updated by doc maintenance schedules.

- **Small, self-contained sections**: each section should answer *one* question.
- **Stable headings**: use consistent `##` sections across pages.
- **Concrete anchors**: always include file paths, function names, and endpoint paths.
- **Examples**: include short JSON examples for data contracts.

### Planning

- **Coding agent roadmap & backlog** (guardrails, epics, Git phases): [`docs/planning/coding-agent-roadmap.md`](./planning/coding-agent-roadmap.md)
- **Coding agent vs. external reference (gap analysis):** [`docs/planning/coding-agent-external-gap-analysis.md`](./planning/coding-agent-external-gap-analysis.md)
- **Chat secret ingress — where to hook in code:** [`docs/planning/chat-secret-ingress-integration-analysis.md`](./planning/chat-secret-ingress-integration-analysis.md)

### Agents (product)

- **Operator agent (admin-only, current tools, planned tools):** [`docs/features/operator-agent.md`](./features/operator-agent.md)
- **Agent plugins + tool allowlists (`TOOL_DOMAIN`, capabilities, patterns):** [`docs/features/agent-registry-and-allowlists.md`](./features/agent-registry-and-allowlists.md)

### Start here

- **Architecture**: [`docs/architecture/overview.md`](./architecture/overview.md)
- **Tool system**: [`docs/architecture/tools.md`](./architecture/tools.md)
- **Dashboards**: [`docs/features/dashboards.md`](./features/dashboards.md)
- **Memory**: [`docs/features/memory.md`](./features/memory.md)
- **RAG**: [`docs/features/rag.md`](./features/rag.md)
- **Retrieval layer** (RAG + code + memory orchestration): [`docs/features/retrieval-layer.md`](./features/retrieval-layer.md)
- **Discord**: [`docs/features/discord.md`](./features/discord.md)
- **HTTP API**: [`docs/api/http.md`](./api/http.md)
- **Ops runbooks**: [`docs/runbooks/`](./runbooks/)
- **Workspace persistence (Docker)**: [`docs/runbooks/workspace-persistence.md`](./runbooks/workspace-persistence.md)
- **Glossary**: [`docs/glossary.md`](./glossary.md)

### Benchmarks & agent tuning

- **Agent tuning platform (start here)**: [`docs/benchmarks/PLANNING.md`](./benchmarks/PLANNING.md)
- **LLM agent benchmark (harness, isolation)**: [`docs/benchmarks/agent-llm-benchmark.md`](./benchmarks/agent-llm-benchmark.md)
- **Agent tuning master plan**: [`docs/benchmarks/agent-tuning-platform.md`](./benchmarks/agent-tuning-platform.md)
- **Tuning interfaces + value schemas**: [`docs/benchmarks/tuning-interfaces.md`](./benchmarks/tuning-interfaces.md)
- **Knob registry (v2)**: [`docs/benchmarks/knob-registry.yaml`](./benchmarks/knob-registry.yaml)
- **OpenAPI (planned admin APIs)**: [`docs/benchmarks/schemas/openapi.yaml`](./benchmarks/schemas/openapi.yaml)
- **Failure pattern taxonomy**: [`docs/benchmarks/pattern-analysis-roadmap.md`](./benchmarks/pattern-analysis-roadmap.md)
- **Status / checklist**: [`docs/benchmarks/todo.md`](./benchmarks/todo.md)

### ADRs (decisions)

You already have ADRs under [`docs/adr/`](./adr/):

- [`0001-tool-and-agent-architecture.md`](./adr/0001-tool-and-agent-architecture.md)
- [`0002-tool-capabilities-convention.md`](./adr/0002-tool-capabilities-convention.md)
- [`0003-capability-governance.md`](./adr/0003-capability-governance.md)
- [`0004-scheduler-data-model.md`](./adr/0004-scheduler-data-model.md)
- [`0005-agentlayer-self-workspace-contract.md`](./adr/0005-agentlayer-self-workspace-contract.md)
- [`0006-chat-secret-ingress-pipeline.md`](./adr/0006-chat-secret-ingress-pipeline.md) — chat → vault → placeholders → operator apply (proposed)

