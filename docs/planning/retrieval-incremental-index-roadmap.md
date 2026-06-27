---
doc_id: planning-retrieval-incremental-index-roadmap
domain: agentlayer_docs
tags: [planning, retrieval, coding-agent, qdrant, neo4j, index]
---

# Retrieval & Code-Index — Langfristiger Weg (3 Stufen)

**Status:** Stufe A/B/C umgesetzt (incremental index, per-workspace policies, git-pull + nightly reindex).  
**Kontext:** Heute sind **grep/read live**, **Qdrant + Neo4j** nur nach **`index` / UI-Reindex** aktuell. Graph ist **nicht** Default in `retrieve_context`.  
**Verwandt:** [`docs/features/retrieval-layer.md`](../features/retrieval-layer.md), [`docs/planning/coding-agent-roadmap.md`](./coding-agent-roadmap.md), [`docs/TODO-future.md`](../TODO-future.md).

---

## Leitlinie (alle Stufen)

| Prinzip | Bedeutung |
|---------|-----------|
| **Working copy = Wahrheit** | Text über `read_file`, `search` (live). |
| **Index = Cache** | Qdrant (Semantik) + Neo4j (Graph) mit klarer Refresh-Policy. |
| **Git = Diff/Review** | `git/changes`, `coding_git_*` — **nicht** im Graph spiegeln. |
| **Hybrid + inkrementell** | Nicht „immer Full-Reindex“, nicht „nur grep“. |

**Big-Player-Zielrichtung**

| Player | Kern | AgentLayer-Ziel |
|--------|------|-----------------|
| Claude Code | file-first, git, wenig persistenter Graph | grep/read default; Graph **opt-in** |
| Cursor | Hintergrund-Index, oft inkrementell bei Save | **Stufe A** (post-write incremental) |
| Sourcegraph | globaler Graph + async rebuild | **Stufe C** (optional, Enterprise) |

**Priorität #1 (wenn nur eine Sache):** Post-write **incremental index** (debounced, pro Datei) → Qdrant + `upsert_file_graph`.

---

## Stufe A — Default (für alle, wenig Überraschungen)

### Zielverhalten

- **Orientierung:** `retrieve_context` Default bleibt `code_grep` + `code_semantic` + `docs` (wie heute).
- **Nach Write/Patch:** still im Hintergrund **nur geänderte Dateien** re-indexen (Qdrant + Neo4j `upsert_file_graph`), **debounced** (z. B. 2–5 s nach letztem Edit).
- **Graph:** weiter separat (`graph`) oder optional `retrieve_context` mit `sources: ["graph"]` — **nicht** zwingend in RRF; nach Incremental-Index konsistent.

### Was wir dafür ändern müssen

#### 1) Incremental-Index-Kern (Backend)

| Bereich | Datei / Modul | Änderung |
|---------|---------------|----------|
| **Single-file / multi-file scan** | `plugins/tools/capabilities/coding/coding_index_lib.py` | API: `scan_paths(root, paths: list[str])` oder `scan_file(path)` statt nur Full-`scan(root, max_files)`. Tree-sitter + `sha256` pro File. |
| **Qdrant upsert pro File** | `apps/backend/infrastructure/code_index_qdrant.py` | `index_symbols` für eine Datei; optional alte Points für `file_path` löschen vor Upsert. |
| **Neo4j pro File** | `apps/backend/infrastructure/code_graph_neo4j.py` | Bereits `upsert_file_graph` — aus Incremental-Pfad aufrufen (+ `resolve_import_relationships` mit `indexed_paths`). |
| **Orchestrierung** | **neu** z. B. `apps/backend/infrastructure/workspace_index_incremental.py` | `enqueue(workspace_id, paths[])`, debounce-Timer, Worker-Thread/async job; ruft Scan + Qdrant + Neo4j; Fehler in `last_index_error` / per-file stats. |
| **Full vs partial** | `apps/backend/infrastructure/workspace_retrieval.py` | `run_semantic_index` optional `paths: list[str] | None`; bei `paths` kein Full-Walk. Job-Status: `phase=incremental`, `files_done/total`. |

#### 2) Hooks nach Agent-Writes

| Tool | Datei | Hook |
|------|-------|------|
| Write | `plugins/tools/capabilities/coding/coding_write_file.py` | Nach erfolgreichem Write: `relative_path` → `enqueue_incremental_index(context, [path])` |
| Edit | `plugins/tools/capabilities/coding/coding_edit.py` | dito |
| Replace | `plugins/tools/capabilities/coding/coding_replace.py` | dito |
| Patch | `plugins/tools/capabilities/coding/coding_apply_patch.py` | Alle touched paths aus Patch-Result |
| Optional | `apps/backend/domain/plugin_system/tools.py::run_tool` | Generischer Post-Tool-Hook (wenn zentraler als 4 Duplikate) |

**Voraussetzungen im `tool_context`:** `workspace.id`, `workspace.path`, Flags `semantic_index_enabled`, Neo4j verfügbar.

#### 3) Konfiguration (Minimal für A)

| Ort | Änderung |
|-----|----------|
| `apps/backend/infrastructure/config.py` | `AGENT_WORKSPACE_INDEX_ON_WRITE` = `off` \| `debounced` \| `immediate` (Default: **`debounced`**); `AGENT_WORKSPACE_INDEX_DEBOUNCE_SEC` (Default 3). |
| Operator (später Stufe B) | `workspace_index_on_write` in `operator_settings` + Migration. |

Für **Stufe A** reicht zunächst **nur Env**; Operator-UI kann in Stufe B folgen.

#### 4) UI / Observability (klein)

| Ort | Änderung |
|-----|----------|
| `apps/frontend/.../WorkspaceRetrievalBar.tsx` | Optional: „Background index…“ wenn incremental job läuft (gleicher Job-Store wie Full-Reindex). |
| `workspace_retrieval.index_status_payload` | `last_incremental_at`, `incremental_pending_files` (optional). |
| Logs | `logger.info` mit `workspace_id`, paths count, duration. |

#### 5) Tests

| Test | Inhalt |
|------|--------|
| `tests/test_workspace_index_incremental.py` | Mock FS: edit file → enqueue → nach debounce Qdrant/Neo4j mock aufgerufen. |
| `tests/test_coding_write_triggers_index.py` | Tool-Handler ruft enqueue (mock). |

#### 6) Doku

| Datei | Inhalt |
|-------|--------|
| `docs/features/retrieval-layer.md` | Abschnitt „Incremental index on write“; Stale-Hinweis anpassen. |
| `plugins/agents/coding.py` | 1–2 Zeilen: nach großen Renames ggf. Full-Reindex; Impact → `graph` nach Index. |

### Stufe A — Explizit **nicht** in Scope

- [ ] Graph in `fused_ranking` (RRF)
- [ ] File-level stale in DB
- [ ] Webhooks / nightly full reindex
- [ ] Diff-State in Neo4j

---

## Stufe B — Operator/User steuerbar

### Zielverhalten

Policy **pro Workspace** (und Operator-Default), nicht nur Env.

| Einstellung | Werte | Bedeutung |
|-------------|-------|-----------|
| **Index on write** | `off` / `debounced` / `immediate` | Nur touched files |
| **Index on attach** | (existiert) `AGENT_WORKSPACE_INDEX_ON_ATTACH` | Nur wenn stale |
| **Full reindex** | manuell (UI All/Code/Docs) | Große Refactors, Branch, Embedding-Modell |
| **Graph enabled** | bool / Neo4j URL | Infra + Workspace-Flag |
| **retrieve_context sources** | pro Agent/Workspace | z. B. Plan ohne `graph`, Build optional |
| **Stale** | pro Datei | `mtime` oder `content_sha256`, nicht nur `git HEAD > last_index_at` |

**Defaults (90 %):** `index_on_write = debounced`, semantic + graph wenn enabled.  
**Power-User:** `index_on_write = off`, nur manuell Reindex + grep.

### Was wir dafür ändern müssen

#### 1) Datenbank & API

| Bereich | Änderung |
|---------|----------|
| Migration | `project_workspaces`: `index_on_write` (enum/text), optional `graph_index_enabled`; Tabelle `workspace_index_file_state` (`workspace_id`, `path`, `content_sha256`, `indexed_at`) |
| `apps/backend/infrastructure/workspace_columns.py` | SELECT/JSON-Felder erweitern |
| `apps/backend/api/workspaces_api.py` | PATCH akzeptiert neue Felder; Status-Endpoint liefert per-file stale summary |
| `apps/backend/infrastructure/operator_settings.py` | `workspace_index_on_write_default`, ggf. `workspace_graph_enabled_default` |

#### 2) Stale-Logik

| Datei | Änderung |
|-------|----------|
| `apps/backend/infrastructure/workspace_retrieval_bootstrap.py` | `is_index_stale`: OR file-hash mismatch; `index_stale_reason`: `files_changed_since_index` |
| Incremental worker | Nach erfolgreichem Upsert: `workspace_index_file_state` updaten |
| Bootstrap snippet | Hinweis „N files out of date“ statt nur git HEAD |

#### 3) Frontend

| Datei | Änderung |
|-------|----------|
| `WorkspaceRetrievalBar.tsx` / Workspace-Settings | Dropdown Index on write; Graph toggle |
| `AdminInterfacesPlatformSection.tsx` | Operator-Default für index-on-write |
| `apps/frontend/src/lib/api.ts` | Types für neue Workspace-Felder |

#### 4) Retrieval / Agent

| Datei | Änderung |
|-------|----------|
| `retrieve_context.py` | Workspace-/Agent-Default für `sources` (Config oder DB) |
| `retrieval_fusion.py` | Optional: `graph` in RRF (wenn Product will) |
| `plugins/agents/coding.py` / `coding_plan.py` | Default sources dokumentieren |

#### 5) Incremental worker (Stufe B Ergänzung)

- Respektiert `workspace.index_on_write` (override Operator default).
- `immediate` = kein debounce; `off` = enqueue noop.

#### 6) Tests & Doku

- Migration-Test, API PATCH tests, stale per-file tests.
- `docs/features/workspaces.md`, `retrieval-layer.md` Roadmap-Tabelle aktualisieren.

---

## Stufe C — Enterprise / Power (optional)

### Zielverhalten

- Webhook/Cron: **full reindex** nightly oder nach `git pull`
- Sourcegraph-ähnlich: zentraler Graph + Search, async nach Push
- Nur sinnvoll bei Multi-Repo, viele User, Compliance

### Was wir dafür ändern müssen

| Bereich | Änderung |
|---------|----------|
| Scheduler | `apps/backend/infrastructure/coding_schedule_execution.py` oder neuer Job-Typ `workspace_full_reindex` |
| Git hooks | Nach `git_sync` pull: optional `start_semantic_index_async` (Operator flag) |
| HTTP webhook | `POST /v1/admin/workspaces/{id}/reindex` + HMAC secret |
| Multi-tenant ops | Queue (Redis/DB job table), Rate limits, Prioritäten |
| Observability | Metriken: index lag, files stale count, Neo4j/Qdrant health |

**Self-Host Default:** Stufe C **nicht** aktivieren.

---

## Was langfristig **nicht** der beste Weg ist

- [ ] Alles nach jedem Edit **full** reindexen
- [ ] **Diff** im Neo4j speichern (Git + `read_file` reichen)
- [ ] **Graph** in jedem `retrieve_context` Default (teuer, oft irrelevant)
- [ ] Stale **nur** über `git HEAD > last_index_at` (schlecht für No-Git + uncommitted edits)

---

## Umsetzungsreihenfolge (empfohlen)

| # | Item | Stufe | Aufwand (grob) |
|---|------|-------|----------------|
| 1 | `scan_paths` + incremental worker + debounce | A | M |
| 2 | Hooks in write/edit/replace/patch tools | A | S |
| 3 | Env flags `AGENT_WORKSPACE_INDEX_ON_WRITE` | A | S |
| 4 | Tests + retrieval-layer.md | A | S |
| 5 | DB `index_on_write` + Operator/Workspace UI | B | M |
| 6 | `workspace_index_file_state` + per-file stale | B | M |
| 7 | Agent default `sources` + optional graph in RRF | B | S–M |
| 8 | Reindex after `git pull` / cron | C | L |

**Kleinster Schritt mit größtem UX-Gewinn:** Zeilen 1–3 (Stufe A Kern).

---

## Ist-Zustand (Referenz, Stand heute)

| Komponente | Verhalten |
|------------|-----------|
| `retrieve_context` | Default: grep + semantic + docs; **graph** nur explizit |
| `fused_ranking` | grep, semantic, docs, memory — **ohne** graph |
| `index` / UI Reindex | Full workspace → Qdrant + Neo4j |
| `upsert_file_graph` | Pro Datei replace (Symbols DELETE + neu) |
| Stale hint | `git_head_commit_time` vs `last_index_at` |
| Index on attach | `AGENT_WORKSPACE_INDEX_ON_ATTACH` (env, default off) |

---

## Checkliste Stufe A (copy für Issues)

- [x] `coding_index_lib`: `scan_paths`, `list_indexable_rel_paths`
- [x] `workspace_index_incremental.py`: queue + debounce + worker
- [x] `workspace_retrieval.run_incremental_index`
- [x] Post-tool hook: write, edit, replace, apply_patch
- [x] `config.py`: `AGENT_WORKSPACE_INDEX_ON_WRITE`, debounce sec
- [ ] UI: optional incremental job in status bar (phase `incremental` in index_job already)
- [x] Tests: `tests/test_workspace_index_incremental.py`
- [x] Docs: retrieval-layer + coding agent prompt + `.env.example`
