# Implementierungsplan: Dashboard-Uploads, Admin-Limits, Rechte & Sharing

**Stand:** Track **A1–A3** umgesetzt — lokale Speicherung unter `dashboard_upload_dir()`, Tabelle `dashboard_files`, `POST/GET/DELETE` unter `/v1/dashboards/…`, Admin-Overrides in `operator_settings`, Gallery-UI mit `wsfile:{uuid}`-Referenzen. Weiteres (Sharing, ACL) folgt laut Stufen unten.

Dieses Dokument setzt die zuvor besprochene **Kurzfassung** in eine **reihenfolgetreue** Umsetzung um. Ziel ist pragmatische Stufen — nicht alles auf einmal.

**Prinzipien**

- Binärdaten **nicht** dauerhaft in `user_dashboards.data` (kein Riesen-JSON); dort nur **Referenzen** (IDs, Pfade, signierte URLs).
- **Globale** Upload-Limits zuerst (Operator/Admin); Tenant/User-Quotas optional später.
- Sharing **stufenweise**: Vorlage → Read-only → Mitgliedschaft; kein „komplettes Dashboard-JSON für alle“ als erster Schritt.

---

## Abhängigkeiten zwischen Tracks

```
Track A (Uploads)     ── unabhängig von Sharing
Track B (ACL Basis)   ── Voraussetzung für Track C (Mitgliedschaft)
Track C Stufe 1       ── Vorlagen (kann früh, ohne ACL)
Track C Stufe 2–3     ── brauchen ACL + ggf. Upload-URLs für private Bilder
```

Empfohlene Reihenfolge: **A1 → A2 → A3 → B1 → C1 → (C2) → (C3)**.

---

## Track A — Datei-Uploads (Speicher-Schicht + Gallery)

### A0 — Ist-Zustand festhalten

- Gallery-Block: `interfaces/agent-ui/src/features/dashboard/DashboardBlocks.tsx` — Felder `url`, `caption`; nur manuelle URL.
- Persistenz: `PATCH /v1/dashboards/{id}` → `user_dashboards.data` (`src/dashboard/db.py`).

### A1 — Speicherort & Konfiguration

- **Entscheidung treffen:** lokales Volume (z. B. `AGENT_DATA_DIR/dashboard_uploads/`) vs. S3-kompatibles Backend (später).
- **Env (Vorschlag):** `AGENT_DASHBOARD_UPLOAD_DIR`, `AGENT_DASHBOARD_UPLOAD_MAX_BYTES`, `AGENT_DASHBOARD_UPLOAD_ALLOWED_MIME` (kommagetrennt).
- **Admin-Overrides (global):** neue Spalten in `operator_settings` *oder* dedizierte Tabelle `operator_limits` — konsistent mit bestehendem Muster in `src/infrastructure/operator_settings.py` (PUT/PATCH Admin-API, UI in Admin).
- **Dokumentation:** `.env.example` + kurzer Hinweis in Admin-Interfaces oder eigener Admin-Unterseite „Limits“.

**Deliverable:** Server liest effektive Limits (Env mit Fallback, Admin überschreibt wenn gesetzt).

### A2 — Metadaten in PostgreSQL

Neue Tabelle (Vorschlag) `dashboard_files` (oder `user_dashboard_attachments`):

| Spalte | Zweck |
|--------|--------|
| `id` UUID PK | Referenz für JSON |
| `tenant_id`, `owner_user_id` | Besitz + Isolation |
| `dashboard_id` UUID FK → `user_dashboards` | Optional NULL, wenn Upload vor Zuordnung erlaubt |
| `storage_key` / `path` | interner Pfad oder Bucket-Key |
| `mime`, `size_bytes`, `original_name` | Validierung & UI |
| `created_at` | Audit |

- **Indizes:** `(owner_user_id, created_at)`, `(dashboard_id)`.
- **Migration:** Alembic oder euer bestehendes SQL unter `src/infrastructure/db/migrations/`.

**Deliverable:** CRUD-Hilfen in `src/infrastructure/db/` oder `src/dashboard/files_db.py` (nur Meta, Bytes auf Disk).

### A3 — HTTP API

- `POST /v1/dashboards/{dashboard_id}/files` — `multipart/form-data`, prüft Owner (wie `dashboard_get`), Limits, MIME, Größe; schreibt Datei + Zeile in `dashboard_files`.
- `GET /v1/dashboards/files/{file_id}/content` **oder** signierte URL mit kurzer TTL — **Auth Pflicht**, kein öffentliches Erraten von IDs.
- `DELETE /v1/dashboards/files/{file_id}` — nur Owner (später: ACL „editor“).

**Deliverable:** Endpunkte in `src/dashboard/router.py` (oder Sub-Router), Tests mit kleiner Dummy-Datei.

### A4 — UI (Gallery)

- Neben URL-Feld: **„Hochladen“** → `FormData` → POST; nach Erfolg `url` im Eintrag auf **API-URL** oder **signierte URL** setzen (einheitliche Strategie dokumentieren).
- Fehleranzeige (413, 415), Fortschritt optional.

**Deliverable:** `DashboardBlocks.tsx` Gallery angepasst; kein Breaking Change für reine Remote-URLs (beides erlaubt).

### A5 — Agent / Tools (optional, später)

- Tool `dashboard_attach_image` oder generisch `upload_dashboard_file` mit Policy — erst nach stabiler API.

---

## Track B — Rechte (Feintuning, Vorbereitung Sharing)

### B1 — Modell dokumentieren & minimal erweitern

**Heute:** `list` / `dashboard_get` nur `owner_user_id = current user` + `tenant_id`.

**Erweiterung (Schema-Vorschlag):** Tabelle `dashboard_members`:

| Spalte | Zweck |
|--------|--------|
| `dashboard_id` | FK |
| `user_id` | Mitglied |
| `role` | `viewer` \| `editor` (Enum/Text) |
| `invited_by`, `created_at` | Audit |

- **Unique:** `(dashboard_id, user_id)`.
- **Regel:** Owner bleibt in `user_dashboards.owner_user_id`; Members zusätzlich. Owner hat implizit `editor`.

### B2 — API-Anpassung

- `list`: eigene + die, wo Mitglied.
- `dashboard_get` / `patch` / `delete`: Zugriff wenn Owner **oder** Rolle `editor` (PATCH) / `viewer` (GET only).
- **DELETE Dashboard:** nur Owner (explizit festlegen).

### B3 — UI

- DashboardPage: nur Owner sieht „Löschen“ / gefährliche Aktionen; Viewer read-only (bestehendes `saving`/Edit sperren).

**Deliverable:** Kein externes Sharing nötig — nur mehrere Nutzer **innerhalb desselben Tenants** (wie euer Produkt heute gedacht ist).

---

## Track C — Sharing (stufenweise)

### C1 — Vorlage teilen (kein gemeinsamer Datenstand)

- **Export:** JSON Snippet: `kind` + `ui_layout` + leeres `initial_data` (oder anonymisiert) — kein `user_dashboards.id`.
- **Import:** „Neuen Dashboard aus Vorlage“ — bereits ähnlich zu „Kind aus Catalog“; optional **User-saved templates** in neuer Tabelle oder als `kind=custom` Preset.
- **Kein** ACL nötig für reine Datei-/Clipboard-Vorlagen.

**Deliverable:** Export/Import-Buttons oder API `POST /v1/dashboards/from-template` mit Body (validieren!).

### C2 — Read-only Freigabe

- **Token-basiert:** `dashboard_share_tokens` mit `dashboard_id`, `token_hash`, `expires_at`, `scope=read`.
- URL: `/app/dashboard/shared?t=…` oder API `GET /v1/dashboards/shared/{token}` → nur GET-Daten, kein PATCH.
- Optional: Passwort auf Token-Ebene.

**Deliverable:** Öffentlichkeit bewusst begrenzen; Rate-Limit; kein Listing aller Shares.

### C3 — Mitgliedschaft (gemeinsames Board)

- Nutzt **B** (`dashboard_members`).
- UI: „Einladen“ (User per E-Mail in Tenant auflösen oder User-ID für Admin).
- **Konflikte:** letzte Änderung gewinnt (optimistic locking mit `updated_at` auf `user_dashboards` empfohlen — Spalte existiert).

**Deliverable:** Zwei Editoren am selben Dashboard; Gallery-Uploads unter gemeinsamer ACL (Editor).

---

## Nicht-Ziele (explizit zurückstellen)

- Öffentliches CDN ohne Auth für private Uploads.
- Base64-Bilder im `data` JSON als Dauerlösung.
- „Komplettes Dashboard mit einem Klick weltweit editierbar teilen“ ohne Token/ACL.
- Shopping-Liste als Sonderfall: erst **C3** oder **dediziertes** „shared list“-Objekt planen (siehe auch `PLAN_TASKS_PHASE_2_3.md`).

---

## Test-Checkliste (kurz)

- Upload über Limit → 413; falsches MIME → 415.
- Fremder Tenant / fremder User → 404 (kein Leak).
- Viewer kann nicht PATCH; Editor kann; Owner kann löschen.
- Share-Token abgelaufen → 401/404.
- Gallery: alte reine `https://`-URLs funktionieren weiter.

---

## Datei-Anker im Repo (Stand Plan-Erstellung)

| Bereich | Pfade |
|---------|--------|
| Dashboard API | `src/dashboard/router.py`, `src/dashboard/db.py` |
| UI Dashboard | `interfaces/agent-ui/src/pages/DashboardPage.tsx`, `…/features/dashboard/DashboardBlocks.tsx` |
| Admin-Limits-Muster | `src/infrastructure/operator_settings.py`, `interfaces/.../AdminInterfaces.tsx` |
| Auth | `get_current_user`, `db.user_tenant_id` |

---

*Plan-Version: 1 — bei Architektur-Entscheidungen (nur Disk vs. S3) A1 zuerst finalisieren.*
