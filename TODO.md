# RAG & Embeddings: Architektur-Analyse und Roadmap

Dieses Dokument fasst den **Ist-Zustand**, die **Lücken** (Ollama-Hardcoding, fehlende Workspace-Scopes im Doc-RAG) und einen **Umsetzungsplan** zusammen — damit alle Provider gleichberechtigt werden können, Indexing/Retrieval klar getrennt sind, und RAG pro Workspace optional per UI aktivierbar wird.

---

## 1. Executive Summary

| Bereich | Heute | Ziel |
|--------|--------|------|
| **Embeddings** | Nur **Ollama** (`POST …/api/embed` bzw. Legacy `/api/embeddings`), Basis-URL aus `OLLAMA_BASE_URL`, Modell aus `rag_ollama_model`. | **Einheitlicher Embedding-Provider** (Ollama, OpenAI-kompatibel `/v1/embeddings`, Azure, ggf. weitere) — **unabhängig** vom Chat-Completion-Provider. |
| **Doc-RAG (Produkt-Doku & Nutzer-Ingest)** | **Postgres + pgvector**, Tabellen `rag_documents` / `rag_chunks`; Scope **tenant + user_id**, Domains; `agentlayer_docs` tenant-weit via Allowlist. | Gleiches oder erweitertes Schema mit **`workspace_id`** (nullable = global/legacy), klarer **Indexing-Pipeline** + **Retrieval-API**. |
| **Code-Semantik (Coding-Agent)** | **Qdrant**-Collection, Filter **`workspace_id`** in Payload; Embeddings **wieder Ollama** in `code_index_qdrant._embed_text`. | Derselbe Embedding-Provider wie Doc-RAG; optional **eigene Collection pro Workspace** oder weiter **ein Collection + Filter** (Trade-off siehe §6). |
| **Memory / Graph** | Nutzt `ollama_embed_one` aus `apps/backend/api/rag.py`. | Auf gemeinsamen Embedding-Provider umstellen. |
| **Frontend** | RAG über Operator-Settings (`rag_*`), kein Workspace-Toggle für Doc-RAG. | UI: Workspace → „Semantic index“ / „RAG für dieses Projekt“ + Status (letzte Indexierung, Fehler). |

**Wichtig:** „Alle Provider gleich behandeln“ betrifft primär **Embeddings**, nicht zwingend die **Vektordatenbank**: Chat-Provider (OpenAI, Anthropic, …) und Embedding-API sind in der Praxis oft **getrennte Produkte/Keys**. Sauber ist: **ein abstraktes `EmbeddingClient`**, konfigurierbar pro Tenant oder global (Operator), optional Override pro Workspace.

---

## 2. Ist-Zustand (Code-Pfade)

### 2.1 Doc-RAG (Markdown, `agentlayer_docs`, Admin-Ingest)

- **Service:** `apps/backend/api/rag.py` — Chunking, `ollama_embed_one`, `ingest_for_user`, `search_for_identity`.
- **Öffentliche Fassade:** `apps/backend/infrastructure/rag.py` re-exportiert dieselben Funktionen.
- **HTTP:** `apps/backend/api/rag_api.py` — `POST /v1/admin/rag/ingest`, `…/ingest-docs`.
- **Bootstrap:** `apps/backend/domain/rag_docs_file_ingest.py` — läuft `docs/**/*.md` → Domain `agentlayer_docs`, **Ollama-Probe** vor Batch.
- **Tool:** `plugins/tools/capabilities/knowledge/rag/rag.py` — nur **Suche** (`rag_search`), keine Workspace-Bindung.
- **Persistenz:** `apps/backend/infrastructure/db/db.py` — `rag_document_and_chunks_insert`, `rag_vector_search` (Cosine `<=>`).
- **Konfiguration:** `apps/backend/infrastructure/operator_settings.py` — `rag_enabled`, `rag_ollama_model`, `rag_embedding_dim`, Chunk-Parameter, `rag_tenant_shared_domains`.

**Semantik:** Retrieval filtert nach `tenant_id` + `user_id` **oder** (bei Domain in `rag_tenant_shared_domains`) nur `tenant_id` + Domain — **kein** `project_workspaces.id`.

### 2.2 Code-Index + Qdrant

- **`apps/backend/infrastructure/code_index_qdrant.py`:** eigene `_embed_text` → wieder **nur Ollama** `/api/embed` (ohne die robusten Fallbacks aus `ollama_embed_one`).
- **Tools:** `index`, `semantic_search` — `workspace_id` aus Workspace-Kontext, Qdrant-Payload-Filter.

### 2.3 Memory

- **`apps/backend/api/memory.py`:** importiert `ollama_embed_one` — gleiche Ollama-Kopplung.

### 2.4 Workspaces (Domänenmodell)

- Tabelle **`project_workspaces`** (`schema_040_project_workspaces.py` u. a.) — `id`, `owner_user_id`, `path`, …
- Coding-Flow kennt **Workspace-Pfad und UUID**; Doc-RAG **nicht**.

---

## 3. Problemstellung (warum „hardcoded Ollama“ weh tut)

1. **Asymmetrie zum Chat-LLM:** Nutzer wählt z. B. OpenAI/Anthropic für Antworten — Embeddings laufen trotzdem über **Ollama** und `OLLAMA_BASE_URL`. Das ist operationell und mental ein **zweiter Stack**.
2. **Duplizierte / schwächere Pfade:** `code_index_qdrant._embed_text` ist **nicht** identisch zu `ollama_embed_one` (keine Legacy-Endpunkte, keine Dimensionsprüfung wie im RAG-Pfad).
3. **Dimension ist global:** `rag_embedding_dim` ist ein **einziges** Schema für pgvector-Spalte, Qdrant-Vektorgröße und Memory — ein Wechsel des Embedding-Modells erzwingt **Reindex/Migration**, ist aber aktuell nirgends als Workflow modelliert.
4. **Doc-RAG ist nicht projektgebunden:** Alles hängt an **Domain-Strings** und **User/Tenant**, nicht an `project_workspaces` — für „RAG pro Repo“ fehlt ein Schlüssel.

---

## 4. Begriffe: Indexing vs. Retrieval (sauber trennen)

| Schicht | Verantwortung | Heutige Module (Orientierung) |
|--------|----------------|-------------------------------|
| **Ingest / Indexing** | Rohtext holen → chunken → **embedden** → in Vector-Store schreiben (+ Metadaten). | `ingest_for_user`, `ingest_markdown_tree`, `index` + Qdrant upsert |
| **Retrieval** | Query embedden → ANN-Suche → Post-Filter (ACL, workspace, domain) → Ranking optional reranken. | `search_for_identity`, `rag_vector_search`, `QdrantCodeIndex.search` |
| **Embedding-Provider** | „String(s) → `list[float]`“ mit Timeout, Batch, Normalisierung, Dim-Check. | Soll **neu** zentral sein; heute: `ollama_embed_one` + Qdrant-Duplikat |

**Ziel:** Indexing und Retrieval rufen **dieselbe** Embedding-Abstraktion auf; keine direkten `httpx`-Calls zu Ollama außerhalb eines Adapters.

---

## 5. Zielbild: Embedding-Provider (alle „Provider“ gleich)

### 5.1 Minimales Interface (konzeptionell)

- `embed_one(text: str) -> list[float]`
- optional `embed_many(texts: list[str]) -> list[list[float]]` (Kosten/Latenz, OpenAI batch)

### 5.2 Backends (Priorität)

1. **Ollama** — bestehende URLs/Body-Varianten in **einem** Adapter (`ollama_embed_one` → refactor).
2. **OpenAI-kompatibel** — `POST {base}/v1/embeddings` mit `input` + `model` (viele Gateways, LM Studio, vLLM, Azure mit angepasster Base-URL).
3. **Azure OpenAI Embeddings** — oft separater Pfad (API-Version, Header); kann zweiter Adapter oder Konfiguration auf demselben HTTP-Client sein.

### 5.3 Konfiguration (Vorschlag)

Operator-Settings erweitern oder ersetzen durch etwas in der Art:

- `embedding_provider`: `ollama` | `openai_compat` | …
- `embedding_base_url`, `embedding_api_key` (secret, nicht in Logs), `embedding_model`
- `embedding_dim` (weiterhin konsistent mit DB/Qdrant)
- Optional: **`embedding_batch_size`**, Timeout

**Hinweis:** `rag_ollama_model` kann deprecated alias → `embedding_model` wenn `provider=ollama`.

Chat-Provider (`llm_primary_backend`, …) bleiben **orthogonal**; nur wenn ihr bewusst „ein Klick: alles von Anbieter X“ wollt, braucht ihr **Presets**, die sowohl Completion- als auch Embedding-Felder setzen.

---

## 6. Workspace-spezifisches RAG & Qdrant

### 6.1 Doc-RAG an Workspace binden

- **Schema:** `rag_documents.workspace_id UUID NULL REFERENCES project_workspaces(id) ON DELETE CASCADE`  
  - `NULL` = heutiges Verhalten (global/tenant/user-Domains) oder explizit „Plattform-Doku“.
- **Suche:** Filter erweitern: wenn Kontext **Workspace aktiv** → nur Chunks mit `workspace_id = :ws` **oder** explizit tenant-weite Domains ohne Workspace (Policy festlegen).
- **Tenant-shared:** `agentlayer_docs` kann `workspace_id IS NULL` bleiben (weiterhin für alle im Tenant).

### 6.2 Qdrant für Coding

- **Heute:** eine Collection, `workspace_id` im Payload — skaliert gut für den Start.
- **Später:** pro Workspace eigene Collection → einfacheres Löschen/Quota, höhere Isolation; mehr Ops-Komplexität.

Embeddings für Code-Index **müssen** nach Provider-Umstellung **dieselbe Dim** und idealerweise **dieselbe Modell-Familie** wie Doc-RAG nutzen, sonst sind Cross-Suche oder gemeinsame Ops schwerer.

---

## 7. Frontend (UI)

Kurzfristig:

- Workspace-Detail oder Coding-Panel: **Toggle** „Semantische Suche / RAG für dieses Workspace“ (speichert in `project_workspaces` JSON oder neue Spalten `rag_enabled`, `last_rag_index_at`, `rag_error`).
- Anzeige: angebundener Vector-Store (pgvector / Qdrant erreichbar), letzte Indexierung.

Mittelfristig:

- **„Indexierung starten“** (triggert Backend-Job: Workspace-Pfad einlesen, chunken, embedden, schreiben).
- Fortschritt / Fehler aus **Job-Tabelle** oder Polling — vermeidet Timeouts bei großen Repos.

---

## 8. Roadmap / Checkliste (umsetzbar in Phasen)

### Phase A — Technische Schulden (ohne Schema-Bruch)

- [ ] **Ein Embedding-Modul:** Alle Aufrufer (`rag.py`, `memory.py`, `code_index_qdrant.py`) nutzen **eine** Implementierung (Dim-Check, Retries, Timeouts).
- [ ] **Qdrant `_embed_text`** auf dieselbe Logik wie `ollama_embed_one` umstellen oder komplett durch zentrale Funktion ersetzen.
- [ ] **Tests:** Mock HTTP für `openai_compat` + Ollama-Payload-Varianten; Regression für `rag_vector_search` Filter.

### Phase B — Embedding-Provider abstrahieren

- [ ] Interface + Factory aus `operator_settings` / Env.
- [ ] **OpenAI-kompatibler** Embeddings-Adapter (`/v1/embeddings`).
- [ ] Operator-Settings + Admin-UI-Felder: Provider-Typ, Base-URL, Modell, Dim, API-Key-Handling (bestehende Secrets-Patterns im Projekt nutzen).
- [ ] **Dokumentation** (`docs/features/rag.md`): Pfade aktualisieren, Migration von `rag_ollama_model` beschreiben.

### Phase C — Workspace-Scope für Doc-RAG

- [ ] Migration: `rag_documents.workspace_id` (+ Index `(tenant_id, workspace_id, domain)`).
- [ ] Ingest-APIs: optional `workspace_id` (nur Owner/ACL).
- [ ] `rag_search` Tool: `workspace_id` aus **Agent-Kontext** (wie Coding-Tools), Filter in SQL.
- [ ] Frontend-Toggle + Anzeige Status.

### Phase D — Indexing als Job / besserer Agent-Flow

- [ ] Background-Job oder async Task für große Repos (statt synchroner HTTP nur).
- [ ] Idempotenz: Content-Hash pro Chunk/Datei (teilweise schon `content_sha256` auf Document-Ebene — ggf. feingranularer für Updates).
- [ ] Optional: **Hybrid-Suche** (BM25 + vector) später — nicht Blocker für Phase B/C.

### Phase E — Härtefälle

- [ ] **Modellwechsel:** Operator-Warnung wenn `embedding_dim` / bestehende Vektoren inkonsistent; Admin-„Reindex erzwingen“.
- [ ] **Kosten:** Rate-Limits / Batch für Cloud-Embeddings.
- [ ] **Multi-Tenant-Isolation:** API-Keys pro Tenant (falls später nötig) — aktuell eher Operator-weit.

---

## 9. Offene Designentscheidungen (bewusst nicht vorentschieden)

1. Soll **ein** Embedding-Setup für **gesamte Instanz** reichen, oder **pro Tenant** / **pro Workspace**?
2. Doc-RAG komplett nach **Qdrant** verlagern vs. **pgvector** behalten (ihr habt beides — Doppel-Ops vs. ein System)?
3. Soll `rag_search` für Coding **nur** Workspace-RAG sein, oder Weiterleitung an **Code-Qdrant** (zwei Retrieval-Backends hinter einem Tool)?

---

## 10. Referenz (Dateien)

| Thema | Pfad |
|-------|------|
| RAG Core | `apps/backend/api/rag.py` |
| RAG HTTP | `apps/backend/api/rag_api.py` |
| Doc-Ingest Tree | `apps/backend/domain/rag_docs_file_ingest.py` |
| RAG Tool | `plugins/tools/capabilities/knowledge/rag/rag.py` |
| Qdrant Code | `apps/backend/infrastructure/code_index_qdrant.py` |
| Coding Index Tool | `plugins/tools/capabilities/coding/coding_index.py` |
| Operator RAG-Keys | `apps/backend/infrastructure/operator_settings.py` |
| Feature-Doku | `docs/features/rag.md` |

---

*Stand: Analyse auf Basis des Repos (Mai 2026). Bei Schema-Änderungen bitte Migrationsversionen und `schema.sql` synchron halten.*
