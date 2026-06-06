---
doc_id: runbook-troubleshooting
domain: agentlayer_docs
tags: [runbook, troubleshooting]
---

## RAG returns nothing

**Checks**

- **`rag_enabled`** on in **Admin → Interfaces** (`operator_settings`)
- Docs ingested via `POST /v1/admin/rag/ingest` or batch `POST /v1/admin/rag/ingest-docs`
- **`rag_embedding_dim`** matches the embedding model output and the pgvector column (`vector(N)`; default deployment width 1024 after schema_050). Changing the model in Admin auto-probes dim and migrates pgvector when needed.

## Discord gateway DNS failures

**Symptom**

- `Temporary failure in name resolution` for `gateway.discord.gg`

**Cause**

- Container/host DNS instability

**Fix**

- Fix Docker DNS / resolv.conf / network; retry worker

## Dashboard uploads not visible

**Checks**

- `dashboard_files` table exists (migration)
- upload dir configured and writable
- `wsfile:` URLs rendered in `DashboardBlocks.tsx` (`GalleryImage`)

