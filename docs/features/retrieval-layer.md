---
doc_id: feature-retrieval-layer
domain: agentlayer_docs
tags: [retrieval, rag, embeddings, coding, agents]
---

## What it is

The **retrieval layer** finds relevant context (code, docs, memory) and delivers it to the **chat LLM**. It is separate from the **reasoning layer** (provider + model from the UI catalog, e.g. llama.cpp).

Goals:

- Fewer tool rounds (one bundled search instead of grep → semantic → RAG in sequence)
- Better hits (hybrid signals, clear `path:line` citations)
- One embedding stack (`EMBEDDING_*` + `rag_embedding_model` / `rag_embedding_dim`)

## Architecture

```text
┌─────────────────────────────────────────┐
│  Chat LLM (Model dropdown)              │
│  Plans tools + writes answers           │
└─────────────────┬───────────────────────┘
                  │ tools[] + injected system text
┌─────────────────▼───────────────────────┐
│  Orchestration                          │
│  retrieve_context, memory inject, …     │
└─────────────────┬───────────────────────┘
                  │
    ┌─────────────┼─────────────┬──────────────┐
    ▼             ▼             ▼              ▼
  RAG         Code (Qdrant)   Grep/LSP      Memory
 pgvector     coding_semantic  coding_search  notes/graph
    │             │             │              │
    └─────────────┴─────────────┴──────────────┘
                  │
         Embedding API (EMBEDDING_BASE_URL)
```

| Layer | Responsibility | AgentLayer modules |
|--------|----------------|-------------------|
| **Ingest / index** | Chunk or symbol → embed → store | `ingest_for_user`, `coding_index`, memory note insert |
| **Retrieve** | Query → ANN / grep → filter → rank | `search_for_identity`, `QdrantCodeIndex.search`, `coding_search` |
| **Orchestrate** | Run multiple retrievers, merge JSON | `retrieve_context` tool |
| **Embed** | Text → vector | `embedding_client.embed_one` |

Chat uses **`LLAMA_CPP_*`** (or Ollama / external). Embeddings use **`EMBEDDING_*`** only. See [rag.md](./rag.md).

## Retrievers today

| Source | Backend | Tool / path |
|--------|---------|-------------|
| Doc RAG | Postgres + pgvector | `rag_search`, Admin ingest; **workspace `*.md`** via Reindex (scoped `workspace_id`) |
| Code semantic | Qdrant | `coding_semantic_search` (after `coding_index`) |
| Code keyword | ripgrep / walk | `coding_search` |
| Symbols | In-process index | `coding_symbols` |
| Code graph | Neo4j | `coding_graph` (call-graph, dependencies, type hierarchy, impact analysis; after `coding_index`) |
| LSP | Language server | `coding_lsp` |
| Memory notes | pgvector | Auto-inject + `memory_*` tools |
| Memory graph | pgvector + edges | Auto-inject when enabled |

## Unified tool (short-term): `retrieve_context`

**Tool:** `plugins/tools/capabilities/coding/retrieve_context.py`  
**Domain:** `coding` (available to **coding** / **coding_plan** agents)

One call runs selected backends in parallel (conceptually) and returns a single JSON bundle:

```json
{
  "ok": true,
  "query": "authentication middleware",
  "sources_requested": ["code_grep", "code_semantic", "docs"],
  "code_grep": { "matches": [{ "path": "...", "line": 12, "text": "..." }] },
  "code_semantic": { "results": [{ "name": "...", "file_path": "...", "score": 0.82 }] },
  "docs": { "hits": [{ "title": "...", "chunk": "...", "score": 0.71 }] },
  "graph": { "skipped": "not requested" },
  "memory": { "skipped": "not requested" },
  "next_steps": ["Use coding_read_file on the best path:line matches before editing."]
}
```

### Parameters

| Field | Description |
|-------|-------------|
| `query` | Natural-language or keyword search string (required) |
| `sources` | Subset of `code_grep`, `code_semantic`, `docs`, `memory`, `graph` (default: grep + semantic + docs) |
| `domain` | RAG domain for `docs` (default `agentlayer_docs`) |
| `grep_limit` | Cap grep matches (default 25, max 50) |
| `semantic_limit` | Cap Qdrant hits (default 12) |
| `docs_limit` | Cap RAG chunks (default 6) |
| `memory_limit` | Cap memory notes (default 4) |

Requires an active **workspace** for code sources. Docs/memory need RAG/memory enabled in operator settings.

**Prefer `retrieve_context` first** when exploring an unfamiliar area; then `coding_read_file` / `coding_lsp` on cited locations.

## Practices (theory → apply here)

### RAG (Retrieval-Augmented Generation)

Index chunks with metadata (`domain`, `title`, `source_uri`). At query time: embed query → nearest neighbors → pass chunks to the LLM. AgentLayer: [rag.md](./rag.md).

### Hybrid retrieval

Combine **dense** (embeddings) and **sparse** (grep/keywords). `retrieve_context` runs retrievers **in parallel** and merges hits with **RRF** in `fused_ranking`.

### Agentic RAG

Let the agent call retrieval tools when needed — or **prefetch** via `retrieve_context` / memory inject to save rounds. Do not assume the chat model “knows” to search without tools or injection.

### Re-ranking (medium-term)

Retrieve top‑50 → cross-encoder or LLM rerank → top‑5 for the prompt. Not implemented yet.

### Index tiers (coding)

| Tier | Mechanism | When |
|------|-----------|------|
| 0 | README, tree | Session start |
| 1 | `coding_search`, `coding_symbols` | Exact / structural |
| 2 | `coding_lsp` | Types, defs, refs |
| 3 | `coding_semantic_search` | “Where is X done?” |
| 4 | `coding_graph` (Neo4j) | Call-graph, dependencies, type hierarchy, impact analysis |
| 5 | `rag_search` / `docs` in `retrieve_context` | Product/runbook questions |

### Context engineering

- Cite `path:line` in tool output
- Read targeted files after retrieval (avoid repeated `list_dir` with empty `{}`)
- Align **`rag_embedding_dim`** with the embedding model for all stores (RAG, Qdrant, memory)

### Tool design

- **Broad retrieval tool** + **narrow edit tools** → fewer LLM rounds
- Optional **tool ranking** (`AGENT_TOOLS_RANKING_ENABLED`) uses the same embedding API to sort `tools[]`

## What is automatic vs tool-driven

| Mechanism | Automatic before LLM? | Chat model decides? |
|-----------|------------------------|---------------------|
| Memory facts + notes + graph | Yes (`_inject_user_memory_context`) | No |
| `retrieve_context` | No | Yes (must call tool) |
| `rag_search` | No | Yes |
| `coding_semantic_search` | No | Yes |

## Roadmap

| Phase | Item | Status |
|-------|------|--------|
| **Short** | `retrieve_context` (grep + semantic + docs + memory) | Done |
| **Short** | Document retrieval layer (this page) | Done |
| **Medium** | Workspace-scoped RAG ingest (per `project_workspaces`) | Done |
| **Short** | Per-workspace index/retrieval toggles + UI (`semantic_index_enabled`, `retrieval_enabled`) | Done |
| **Medium** | RRF in orchestrator (`fused_ranking`) | Done |
| **Medium** | Cross-encoder / LLM reranker | Planned |
| **Medium** | Session bootstrap snippet (index stats, repo map) | Done |
| **Medium** | Stale-index UI hint + optional index-on-attach (`AGENT_WORKSPACE_INDEX_ON_ATTACH`) | Done |
| **Medium** | Code graph (Neo4j): call-graph, dependency-graph, type hierarchy, impact analysis | Done |
| **Medium** | Incremental index on write (debounced, per-file Qdrant + Neo4j) | Done (env `AGENT_WORKSPACE_INDEX_ON_WRITE`; hooks on write tools) — see [`retrieval-incremental-index-roadmap.md`](../planning/retrieval-incremental-index-roadmap.md) |
| **Long** | LSP hits inside `retrieve_context` | Planned |
| **Long** | Query rewriting (HyDE / multi-query) | Planned |

See also `TODO.md` (RAG/workspace section) and [coding-workflow.md](./coding-workflow.md).

## Benchmarks

Measure Hit@k, tool-call count, and latency when changing retrieval:

```bash
python -m unittest tests.test_retrieval_benchmark -v
python scripts/run_retrieval_benchmark.py
RETRIEVAL_BENCH_LIVE=1 python scripts/run_retrieval_benchmark.py --live --json-out /tmp/bench.json
```

- **Fixture suite** (CI): `tests/benchmarks/fixtures/retrieval_mini` — real `coding_search` / `retrieve_context`, no Qdrant required.
- **Live suite** (`RETRIEVAL_BENCH_LIVE=1`): adds cases against the AgentLayer repo (semantic needs index + embeddings).

Strategies compared: **`unified`** (`retrieve_context`, 1 tool call) vs **`separate`** (per-source calls). Baseline gate: fixture Hit@k ≥ 80%.

## Troubleshooting

- **Empty `code_semantic`:** run `coding_index` on the workspace; check `QDRANT_URL` and `EMBEDDING_*`.
- **Empty `docs`:** `rag_enabled`, ingest (`ingest-docs` or Admin), correct `domain`.
- **Dim mismatch:** `rag_embedding_dim` must match model output and Postgres pgvector columns. Code index uses `code_symbols` or `code_symbols_<dim>` automatically when the legacy collection has another width (no upsert spam; switch back without re-index if that collection still exists).
- **Empty `graph`:** run `coding_index` first; check `NEO4J_URL` env var and Neo4j container health. Graph data is populated during `coding_index` alongside Qdrant.
- **Chat vs embed:** Model dropdown does not power RAG; use Embedding (RAG) + `EMBEDDING_*` in `.env`.
