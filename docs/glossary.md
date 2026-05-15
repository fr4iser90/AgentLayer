---
doc_id: glossary
domain: agentlayer_docs
tags: [glossary]
---

## Glossary

### Agent / Planner / Executor

- **Planner**: the LLM + tool-call loop in `src/domain/agent.py` (`chat_completion`).
- **Executor**: deterministic tool execution in `src/domain/tool_executor.py` (no LLM).

### Tool / Package / Handler

- **Tool package**: one Python module (typically under `plugins/tools/**`) exporting `TOOLS` + `HANDLERS`.
- **Handler**: Python function used to execute a specific tool call (name matches the `TOOLS[].function.name`).

### Capability

Dot-separated `domain.action` strings controlling tool routing and policy gates. See ADRs:

- `docs/adr/0002-tool-capabilities-convention.md`
- `docs/adr/0003-capability-governance.md`

### Dashboard (Dashboard / Board)

Generic user-owned container with:

- `ui_layout`: UI blocks definition (grid + props)
- `data`: JSON storage for the blocks
- `access_role`: owner/editor/co_owner/viewer sharing model

Backend: `src/dashboard/db.py`, `src/dashboard/router.py`  
Frontend: `interfaces/agent-ui/src/pages/DashboardPage.tsx`

### wsfile:

Special URL prefix for dashboard uploads:

- Example: `wsfile:<uuid>`
- Used in gallery / hero blocks to reference uploaded files.

### KB vs RAG vs Memory

- **KB**: keyword/full-text notes (`user_kb_notes`), tool: `kb_*`.
- **RAG**: vector search over ingested documents (`rag_documents`/`rag_chunks`), tool: `rag_search`.
- **Memory**: opt-in persistent user memory (facts + semantic notes), tool: `memory_*`.

