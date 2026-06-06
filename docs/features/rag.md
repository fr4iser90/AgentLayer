---
doc_id: feature-rag
domain: agentlayer_docs
tags: [rag, pgvector, embeddings]
---

## What it is

RAG provides **semantic search** over ingested documents using:

- Postgres + `pgvector`
- embeddings from **`EMBEDDING_BASE_URL`** only (OpenAI-compatible `/v1/embeddings`; see below)

By default, vectors are scoped to **tenant + user** (private notes and uploads stay per user).

The domain **`agentlayer_docs`** is **tenant-wide**: after an admin ingests documentation, every user in that tenant can retrieve the same chunks with `rag_search(..., domain="agentlayer_docs")`. Configure the allowlist in **Admin → Interfaces** as **`rag_tenant_shared_domains`** (comma-separated; default includes `agentlayer_docs`; empty string disables tenant-wide domains).

## Where it lives

- Service: `src/api/rag.py`
- API router: `src/api/rag_api.py`
- Tool: `plugins/tools/capabilities/knowledge/rag/rag.py` (search only)
- Tables: `rag_documents`, `rag_chunks` (`src/infrastructure/db/migrations/sql/schema.sql`)

## Config

In **`operator_settings`** ( **Admin → Interfaces** or `GET/PATCH /v1/admin/operator-settings` ):

- **`rag_enabled`** — master switch for ingest and search
- **`rag_embedding_model`** — embedding **model id** (OpenAI-compatible `/v1/embeddings` at `EMBEDDING_BASE_URL`)
- **`rag_embedding_dim`** — `0` until the embedding model is probed; then matches the live model output and `rag_chunks.embedding` pgvector width (no hardcoded default — e.g. 768 for nomic-embed, 1024 for bge-m3). On model/dim change, pgvector columns are migrated automatically and stored vectors are purged (re-ingest docs).
- **`rag_chunk_size`**, **`rag_chunk_overlap`**, **`rag_top_k`**, **`rag_embed_timeout_sec`**
- **`rag_tenant_shared_domains`** — comma list; tenant-wide domains for search without per-user filter
- **`docs_root`** — optional filesystem root for startup / `ingest-docs` when body omits `docs_root` (default: `<repo>/docs` in the image)

### Environment: embedding HTTP (only these)

Set in `.env` (not used for chat; no Ollama/llama.cpp fallback):

- **`EMBEDDING_BASE_URL`** — OpenAI-compatible base (e.g. `https://host/v1`)
- **`EMBEDDING_API_HEADER_NAME`** — header for the secret (default `X-API-KEY`; use `Authorization` for Bearer)
- **`EMBEDDING_API_HEADER_VALUE`** — secret (no surrounding quotes in `.env`)
- **Admin → Interfaces → Memory & RAG** — alternative: `embedding_api_base_url`, `embedding_api_key`, `embedding_api_header_name` in `operator_settings` (env vars override when set)

Chunking, timeouts, model id (`rag_embedding_model`), and vector width remain in **operator_settings** (`rag_*`).

## Ingest (admin HTTP)

Both routes require a Bearer token for a user with **`role=admin`**:

- `POST /v1/admin/rag/ingest` — body: `text`, optional `domain`, `title`, `source_uri`
- `POST /v1/admin/rag/ingest-docs` — optional JSON: `docs_root`, `domain` (default `agentlayer_docs`), `purge_first` (default `false`), `incremental` (default `true`). Walks `*.md` under `docs_root`. **Incremental** (default): skip files whose `content_sha256` matches the DB row for the same `source_uri`; remove DB rows for files no longer on disk; full re-embed when embedding model/dim or chunk settings change (stored **ingest fingerprint** in `operator_settings`). Set `purge_first: true` for a full rebuild of that tenant + domain.

CLI helper (stdlib HTTP only):

- `scripts/reindex_agentlayer_docs.py` — uses `AGENT_BASE_URL`, `AGENT_ADMIN_TOKEN`, optional `AGENT_INGEST_DOCS_JSON`

On each API process start, the server **attempts** an **incremental** sync of `docs/**/*.md` into domain `agentlayer_docs` (no purge unless embedding/chunk config changed), using the oldest admin user as row owner, when a docs directory exists. If the embedding stack is not configured or the backend is unreachable, that pass is skipped or logged and the API still starts.

Recommended `domain` values:

- `agentlayer_docs` (repo docs, tenant-visible)
- `user_uploads`
- `manual_notes`

## Workspace-scoped doc RAG (coding projects)

When a **coding workspace** is bound, `retrieve_context` / `rag_search` search **only** Markdown indexed for that workspace (`rag_documents.workspace_id`). They do **not** mix in `agentlayer_docs` or other global domains.

- Enable **Docs RAG** on the workspace (Coding Agent header) and run **Reindex** — ingests `*.md` under the repo (skips `.git`, `node_modules`, etc.).
- Domain stored as `workspace_docs`; purge-on-reindex replaces prior workspace chunks.

Without a workspace, use `domain: "agentlayer_docs"` (tenant-wide product docs) or personal domains as before.

## Search

Tools:

- `rag_search({ query, domain?, limit? })` — RAG only; workspace-bound calls ignore `domain`
- `retrieve_context({ query, sources?, domain? })` — coding agents: grep + semantic code + docs (+ optional memory) in one JSON bundle

Use `domain: "agentlayer_docs"` when answering questions about AgentLayer product behavior from ingested markdown **and no project workspace is active**.

See [retrieval-layer.md](./retrieval-layer.md) for architecture, practices, and roadmap.

## Troubleshooting

- If you see embedding dim mismatch: align **`rag_embedding_dim`** in operator settings with the DB vector column and the model output size.
- If search returns nothing: ensure ingest happened, **`rag_enabled`** is on, and the embedding backend can serve **`rag_embedding_model`**.
- If `ingest-docs` reports missing directory: mount or copy `docs/` into the container, set **`docs_root`** in Interfaces, or pass `docs_root` in the request body.
