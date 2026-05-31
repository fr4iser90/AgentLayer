---
doc_id: feature-memory
domain: agentlayer_docs
tags: [memory, privacy, rag]
---

## What it is

Memory is **opt-in persistent storage** for user preferences and personal context.

It has three layers:

1. **Facts**: structured key/value JSON (authoritative)
2. **Notes**: free-form semantic notes (pgvector + embeddings)
3. **Graph** (optional, FMA-style MVP): **nodes** (compact label + summary + kind, **768-dim embedding** on the node text for semantic match) and **edges** (typed relations). Activation is **hybrid**: pgvector nearest-neighbor on the user message embedding **plus** keyword match on label/summary (so synonyms / paraphrases still surface nodes), then **up to N hops** along edges (operator setting, default 2), then injects `[User memory — graph]`. Does not replace RAG; it complements it for structured, long-horizon state.

The model does not “own” memory: all data lives in Postgres, and retrieval is injected into the system message.

## Where it lives

- Tables:
  - `user_memory_facts`
  - `user_memory_notes`
  - `user_memory_graph_nodes`, `user_memory_graph_edges`, `user_memory_graph_activation_log` (optional telemetry)
- Migration:
  - `src/infrastructure/db/migrations/versions/schema_008_user_memory.py`
  - `src/infrastructure/db/migrations/versions/schema_016_user_memory_graph.py`
  - `src/infrastructure/db/migrations/versions/schema_017_user_memory_graph_embedding.py`
  - `src/infrastructure/db/migrations/versions/schema_018_user_memory_graph_meta.py`
  - `src/infrastructure/db/migrations/versions/schema_019_user_memory_graph_activation_log.py`
  - `src/infrastructure/db/migrations/versions/schema_020_operator_settings_memory_graph.py` (graph knobs in `operator_settings`)
  - `src/infrastructure/db/migrations/versions/schema_021_operator_settings_memory_rag.py` (`memory_enabled` + RAG in `operator_settings`)
- DB functions:
  - `src/infrastructure/db/db.py` (`memory_fact_*`, `memory_note_*`)
- Service:
  - `src/api/memory.py`
- Tool:
  - `plugins/tools/capabilities/knowledge/memory/memory.py`
- Injection into chat:
  - `src/domain/agent.py` (`_inject_user_memory_context`)

## Opt-in writes (privacy)

Only store memory when the user explicitly asks (e.g. “remember …” / “merk dir …”).

Secrets are rejected (token/password/key-like patterns).

## Enabling (operators)

Do **not** rely on container environment variables for day-to-day configuration — that path is legacy and easy to get wrong.

- **Server kill-switch**: **Admin → Interfaces** → **`memory_enabled`** (stored in `operator_settings`). When off, memory REST APIs and injection are disabled regardless of tools.
- **Agent tools**: In the Web UI, open **Admin → Tools**, find the **memory** package under **Knowledge & memory**, and enable or disable it (plus role / tenant restrictions) like any other tool package. That controls whether chat requests expose the `memory_*` tool definitions to the model.
- **REST**: Authenticated users can also manage facts, notes, and graph nodes/edges via `POST/GET/DELETE /v1/user/memory/...` and `/v1/user/memory/graph/...` (see `docs/api/http.md`) when the deployment exposes that API.

### Operators (graph)

Configure in **Admin → Interfaces** (persisted in `operator_settings`, exposed on `GET /v1/admin/operator-settings` and updatable via `PATCH /v1/admin/operator-settings`):

- **`memory_graph_enabled`** (default: true): off disables graph APIs, tools, and prompt injection without touching facts/notes.
- **`memory_graph_max_hops`** (0–4, default `2`): expansion along edges after vector/keyword seeds.
- **`memory_graph_min_score`** (default `0.03`): decay × confidence × importance filter before injecting.
- **`memory_graph_max_bullets`** / **`memory_graph_max_prompt_chars`**: cap injected graph section size.

### Node metadata (Phase 2 fields)

- **confidence** (0–1), **source**, **last_verified**, **subject_key** (same key → conflict hints if multiple nodes match), **stability** (`volatile` / `normal` / `stable` — exponential decay by age), **priority** (ordering boost; **kind** `goal` gets an extra boost in scoring).

### Auto extraction

- `POST /v1/user/memory/graph/propose` or tool `graph_propose`: local chat model proposes JSON nodes/edges; optional `apply` to insert (embeddings computed per node).

### Observability (for later RL / tuning)

- **`memory_graph_log_activations`** (default: **off**): when **on**, each chat turn that injects graph context appends a row to `user_memory_graph_activation_log` with **node ids**, **SHA-256 of the normalized user message** (no raw text), and **per-node activation scores** in `meta` (see migration `schema_019`). Toggle via **Admin → Interfaces** / `PATCH` `memory_graph_log_activations`.
- `GET /v1/user/memory/graph/activation-log?limit=100` — recent events for the signed-in user.

## Scoping

Memory can be:

- global per user (`dashboard_id = NULL`)
- dashboard-scoped (`dashboard_id = <uuid>`)

Dashboard-scoped facts override global facts when keys conflict.

## Contracts

### Fact

- key: string (e.g. `language`, `preferred_answer_length`)
- value_json: JSON (typed)
- expires_at: optional ISO timestamp (auto filtered on retrieval)

### Note

- text: string
- tags: string[]
- embedding: computed via Ollama embeddings (same dim as RAG, typically 768)

## Example usage (tool calls)

Structured preference:

```json
{ "key": "preferred_output_language", "value_json": "de" }
```

Semantic note:

```json
{ "text": "User builds a homelab with multiple Jetson nodes and a Discord agent tool system.", "tags": ["homelab", "discord"] }
```

