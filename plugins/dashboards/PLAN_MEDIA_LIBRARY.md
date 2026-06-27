# Implementierungsplan: Media Library (Audio/Video), Quotas, Admin & Sharing

**Stand:** Entwurf — noch nicht implementiert.

Erweiterung von Track A (`PLAN_UPLOAD_AND_SHARING.md`) um **Audio/Video-Wiedergabe und Agent-Kuration**. Kein YouTube-Download als Plattform-Feature.

**Prinzipien**

- Binärdaten **nicht** in `user_dashboards.data` — nur Referenzen (`media_id`, `embed_url`, Queue-Reihenfolge).
- **Legal by design:** Embed/Link-Quellen vs. User-Upload getrennt; kein zentraler Ripper.
- **Operator → User:** globale Schalter in `operator_settings`, pro User Quota/Flags in `users` (wie `workspace_quota`).
- Sharing nur für **eigene Uploads** mit Lizenz-Metadaten — keine gerippten Streams.

---

## Abhängigkeiten

```
Track A (Uploads)           ── Basis für User-Upload-Pfad
Track B (dashboard_members) ── Lesen gemeinsamer Dashboards
Media Stufe 1               ── unabhängig von C2/C3 Sharing
Media Stufe 3 (Share)       ── braucht ACL + license-Feld
```

Empfohlene Reihenfolge: **M1 → M2 → M3 → (M4 OAuth)**.

---

## Rechtliche Quell-Typen (`source_kind`)

| `source_kind` | Beschreibung | Bytes auf Disk | Teilen erlaubt |
|---------------|--------------|----------------|----------------|
| `embed` | HTTPS-URL auf Allowlist (YouTube, Vimeo, …) | nein | nein (Drittanbieter) |
| `upload` | User-eigene Datei | ja | ja, wenn `license` gesetzt |
| `external_link` | Spotify/Bandcamp/… — nur Metadaten + URL | nein | nein |
| `archive` | CC/Internet-Archive — optional Stufe 4 | optional | ja mit CC-Lizenz |

**Explizit ausgeschlossen:** `youtube_download`, `stream_rip`, beliebige URL → Bytes.

---

## Track M — Schema (PostgreSQL)

### M1 — `operator_settings` (globale Overrides)

Neue Spalten (Migration `schema_NNN_media_operator`):

```sql
ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
  media_library_enabled BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
  media_user_upload_enabled BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
  media_sharing_enabled BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
  media_default_user_quota_mb INTEGER;  -- NULL = Env-Fallback

ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
  media_upload_max_file_mb INTEGER;   -- pro Datei, NULL = Env

ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
  media_upload_allowed_mime TEXT;     -- kommagetrennt, NULL = Env

ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
  media_embed_allowed_hosts TEXT;     -- kommagetrennt, NULL = Code-Default
```

Env-Fallbacks (Vorschlag in `apps/backend/infrastructure/config.py`):

- `AGENT_MEDIA_UPLOAD_DIR` → `{AGENT_DATA_DIR}/media_uploads/`
- `AGENT_MEDIA_DEFAULT_USER_QUOTA_MB` → `500`
- `AGENT_MEDIA_UPLOAD_MAX_FILE_MB` → `50`
- `AGENT_MEDIA_UPLOAD_ALLOWED_MIME` → `audio/mpeg,audio/mp4,audio/flac,audio/ogg,audio/wav,video/mp4`

`effective_*`-Helfer analog `effective_dashboard_upload_max_bytes()` in `operator_settings.py`.

### M2 — `users` (pro Nutzer)

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS
  media_enabled BOOLEAN;  -- NULL = Tenant/Operator-Default erben

ALTER TABLE users ADD COLUMN IF NOT EXISTS
  media_storage_quota_mb INTEGER;  -- NULL = effective default

ALTER TABLE users ADD COLUMN IF NOT EXISTS
  media_upload_enabled BOOLEAN;  -- NULL = erben

ALTER TABLE users ADD COLUMN IF NOT EXISTS
  media_sharing_enabled BOOLEAN;  -- NULL = erben
```

Admin-PATCH wie `workspace_quota` in `apps/backend/api/main.py` + `AdminUsers.tsx`.

**Effektive Quota-Prüfung:**

```python
def effective_media_quota_bytes(user_row, operator_row) -> int:
    mb = user_row.get("media_storage_quota_mb")
    if mb is None:
        mb = operator_row.get("media_default_user_quota_mb")
    if mb is None:
        mb = config.MEDIA_DEFAULT_USER_QUOTA_MB
    return max(1, int(mb)) * 1024 * 1024

def user_media_bytes_used(user_id, tenant_id) -> int:
    # SUM(size_bytes) FROM media_items WHERE owner AND source_kind='upload' AND deleted_at IS NULL
    ...
```

### M3 — `media_items` (Metadaten)

```sql
CREATE TABLE IF NOT EXISTS media_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dashboard_id UUID REFERENCES user_dashboards(id) ON DELETE SET NULL,

  source_kind TEXT NOT NULL CHECK (source_kind IN (
    'embed', 'upload', 'external_link', 'archive'
  )),

  -- upload
  storage_relpath TEXT UNIQUE,
  content_type TEXT,
  size_bytes BIGINT NOT NULL DEFAULT 0,
  original_name TEXT NOT NULL DEFAULT '',

  -- embed / external
  external_url TEXT,
  embed_provider TEXT,  -- youtube | vimeo | spotify | …

  -- gemeinsame Metadaten
  title TEXT NOT NULL DEFAULT '',
  artist TEXT NOT NULL DEFAULT '',
  album TEXT NOT NULL DEFAULT '',
  duration_sec INTEGER,
  cover_url TEXT,

  -- Recht / Sharing
  license TEXT CHECK (license IS NULL OR license IN (
    'owned', 'cc-by', 'cc-by-sa', 'cc0', 'other'
  )),
  license_note TEXT NOT NULL DEFAULT '',

  tags TEXT[] NOT NULL DEFAULT '{}',
  metadata JSONB NOT NULL DEFAULT '{}',

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,

  CONSTRAINT media_upload_has_storage CHECK (
    source_kind <> 'upload' OR (
      storage_relpath IS NOT NULL AND content_type IS NOT NULL AND size_bytes > 0
    )
  ),
  CONSTRAINT media_embed_has_url CHECK (
    source_kind NOT IN ('embed', 'external_link', 'archive')
    OR external_url IS NOT NULL
  )
);

CREATE INDEX idx_media_items_owner ON media_items (owner_user_id, created_at DESC)
  WHERE deleted_at IS NULL;

CREATE INDEX idx_media_items_dashboard ON media_items (dashboard_id)
  WHERE deleted_at IS NULL;

CREATE INDEX idx_media_items_tenant_kind ON media_items (tenant_id, source_kind)
  WHERE deleted_at IS NULL;
```

Soft-delete (`deleted_at`) — Bytes erst nach Grace-Period physisch löschen (Cron/Job).

### M4 — `media_queues` (Wiedergabe-Queue pro Dashboard oder User)

Queue-Daten **können** im Dashboard-JSON leben (`data.media_queue`), aber für Agent-Tools und Quota-Audit ist eine normierte Tabelle hilfreich:

```sql
CREATE TABLE IF NOT EXISTS media_queues (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dashboard_id UUID REFERENCES user_dashboards(id) ON DELETE CASCADE,
  name TEXT NOT NULL DEFAULT 'default',
  shuffle BOOLEAN NOT NULL DEFAULT false,
  repeat_mode TEXT NOT NULL DEFAULT 'off'
    CHECK (repeat_mode IN ('off', 'one', 'all')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (owner_user_id, dashboard_id, name)
);

CREATE TABLE IF NOT EXISTS media_queue_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  queue_id UUID NOT NULL REFERENCES media_queues(id) ON DELETE CASCADE,
  media_item_id UUID NOT NULL REFERENCES media_items(id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (queue_id, position),
  UNIQUE (queue_id, media_item_id)
);

CREATE INDEX idx_media_queue_entries_queue ON media_queue_entries (queue_id, position);
```

**Alternative (Stufe 1 minimal):** Queue nur als JSON-Array in `user_dashboards.data` unter `media_queue.items[]` — Tabelle erst ab Stufe 2.

### M5 — `media_share_grants` (Feingranular, nur Uploads)

Analog `dashboard_block_share_grants` — getrennt, weil Media tenant-übergreifend pro Item sein kann:

```sql
CREATE TABLE IF NOT EXISTS media_share_grants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  media_item_id UUID NOT NULL REFERENCES media_items(id) ON DELETE CASCADE,
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  viewer_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  permission TEXT NOT NULL DEFAULT 'play'
    CHECK (permission IN ('play', 'play_and_download')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ,
  UNIQUE (media_item_id, viewer_user_id)
);

CREATE INDEX idx_media_share_grants_viewer ON media_share_grants (viewer_user_id);
```

**Regeln:**

- Nur `source_kind = 'upload'` und `license IS NOT NULL`.
- Operator: `media_sharing_enabled = false` → INSERT verweigern.
- Owner-User: `media_sharing_enabled = false` → INSERT verweigern.

---

## Track M — HTTP API

Router-Vorschlag: `apps/backend/api/media_api.py` (Prefix `/v1/media`).

| Methode | Pfad | Zweck |
|---------|------|--------|
| GET | `/v1/media/items` | Eigene Library (+ geteilte via JOIN) |
| POST | `/v1/media/items/upload` | multipart — prüft Quota, MIME, Feature-Flags |
| POST | `/v1/media/items/embed` | Body: `{ external_url, title?, … }` — Allowlist |
| GET | `/v1/media/items/{id}` | Metadaten |
| GET | `/v1/media/items/{id}/stream` | Range-Requests für `upload` (Auth + ACL) |
| DELETE | `/v1/media/items/{id}` | Soft-delete; Owner only |
| GET | `/v1/media/quota` | `{ used_bytes, quota_bytes, upload_enabled, … }` |
| GET/POST/PATCH | `/v1/media/queues/…` | Queue CRUD (Stufe 2) |
| POST | `/v1/media/items/{id}/share` | Grant an `viewer_user_id` (Stufe 3) |
| DELETE | `/v1/media/share-grants/{id}` | Owner widerruft |

Upload-Flow (wie `dashboard/router.py`):

1. `effective_media_enabled(user)` → 403 wenn aus
2. `effective_media_upload_enabled(user)` → 403
3. Streaming-Read mit `Accept-Ranges`, `Content-Type`, max. Rate optional
4. Tenant-Isolation auf allen Queries

---

## Track M — Dashboard-UI

### Neuer Block-Typ: `media_player`

In `_BLOCK_TYPES` (`plugins/tools/personal/dashboard/dashboard.py`) ergänzen:

```json
{
  "type": "media_player",
  "props": {
    "title": "Music",
    "showQueue": true,
    "defaultVolume": 0.8
  },
  "dataPath": "media_queue"
}
```

**`data.media_queue` (JSON in Dashboard):**

```json
{
  "now_playing_id": "uuid-or-null",
  "items": [
    {
      "ref": "media:uuid",
      "title": "Track name",
      "artist": "Artist",
      "source_kind": "embed",
      "external_url": "https://www.youtube.com/embed/…",
      "duration_sec": 240
    },
    {
      "ref": "media:uuid",
      "source_kind": "upload",
      "stream_url": "/v1/media/items/{id}/stream"
    }
  ],
  "shuffle": false,
  "repeat": "off"
}
```

Frontend: `MediaPlayerBlock.tsx` — HTML5 `<audio>` für Uploads, `<iframe>` oder provider-spezifisch für Embed (Reuse `embedUrlAllowed`-Logik aus `EmbedBlock.tsx`).

### Optional: Dashboard-Kind `media-station`

`plugins/dashboards/media-station/` — Template mit `media_player` + Liste „Library“.

---

## Track M — Agent-Tools

Neues Plugin: `plugins/tools/personal/media/media.py`

```python
TOOL_ID = "media"
TOOL_BUCKET = "media"
TOOL_DOMAIN = "media"
TOOL_CAPABILITIES = ("media.read", "media.write")
TOOL_MIN_ROLE = "user"
```

| Tool | Capability | Beschreibung |
|------|------------|--------------|
| `media.list` | read | Library des Users (Filter: tag, source_kind) |
| `media.quota` | read | used / limit / flags |
| `media.add_embed` | write | URL → `media_items` (embed), Allowlist |
| `media.enqueue` | write | Item ans Dashboard-Queue (`media_queue` oder DB) |
| `media.dequeue` | write | Position/ID entfernen |
| `media.set_now_playing` | write | `now_playing_id` setzen |
| `media.update_metadata` | write | title, artist, tags (Owner) |
| `media.delete` | write | Soft-delete Upload (Owner) |
| `media.share_grant` | write | Stufe 3 — nur upload + license |

**Nicht implementieren:** `media.download_url`, `media.import_youtube`.

### Dashboard-Agent (`plugins/agents/dashboard/agent.yaml`)

```yaml
tool_domains:
  - media   # optional, nur wenn Operator media_library_enabled
pinned_tools:
  - media.list
  - media.enqueue
```

Guards in `dashboard_agent_guards.py` oder eigenes `media_agent_guards.py`:

- Vor `media.add_embed`: Host gegen `effective_media_embed_allowed_hosts()`
- Vor Upload-Tools: Quota-Check
- Agent darf **keine** Share-Grants ohne explizite User-Anfrage + `license` gesetzt

---

## Admin-UI

Erweiterung `AdminInterfacesPlatformSection.tsx`:

- Media Library an/aus (global)
- User-Upload an/aus
- Sharing an/aus
- Default-Quota (MB), Max-Dateigröße, MIME-Liste
- Embed-Hosts (Textarea, kommagetrennt)

Erweiterung `AdminUsers.tsx` (pro User):

- `media_enabled`, `media_storage_quota_mb`, `media_upload_enabled`, `media_sharing_enabled`
- Anzeige: belegter Speicher / Quota

---

## Implementierungsstufen

### Stufe M1 — MVP (2–3 Wochen)

- [ ] Migration: `operator_settings` + `users` Spalten
- [ ] `media_items` Tabelle + `media_db.py` + `file_storage` unter `media_upload_dir()`
- [ ] API: upload, list, stream, delete, quota
- [ ] `MediaPlayerBlock` + Queue in Dashboard-JSON
- [ ] Tools: `media.list`, `media.quota`, `media.add_embed`, `media.enqueue`, `media.dequeue`
- [ ] Admin: globale Schalter + Default-Quota
- [ ] Tests: 413 over quota, 403 feature off, 415 bad MIME, fremder Tenant → 404

### Stufe M2 — Persistente Queues & „Station“

- [ ] `media_queues` + `media_queue_entries`
- [x] Dashboard-Kind `media-station`
- [ ] Agent: `media.set_now_playing`, Playlist-Reorder
- [ ] Optional: WebSocket „now playing“ für multi-tab sync
- [x] Footer-Mini-Player + persistentes Audio (Uploads) über Routen hinweg
- [x] General-Agent: `media` domain + System-Prompt Workflow
- [x] Chat-Audio-Anhang → Mediathek (`agent_audio` ingest)
- [x] Webradio / HTTPS-Streams (`external_link`, `media_add_stream`)

### Stufe M3 — Sharing (legal)

- [ ] `media_share_grants` + API
- [ ] Tool `media.share_grant` mit Pflichtfeld `license`
- [ ] Stream-Endpoint respektiert Grants (`play` vs `play_and_download`)
- [ ] UI: „Mit Nutzer teilen“ nur bei Uploads

### Stufe M4 — OAuth-Integrationen (optional)

- [ ] Spotify Web Playback / Apple Music — User-OAuth, Tokens in `user_secrets`
- [ ] Tools nur Metadaten + Playback über SDK im Frontend
- [ ] Kein serverseitiges Caching von DRM-Inhalten

---

## Test-Checkliste

- Upload über User-Quota → 413; über Datei-Limit → 413.
- `media_library_enabled=false` → 403 auf alle Media-Endpoints.
- Embed mit nicht-allowlisteter Host → 400.
- Viewer mit Share-Grant `play` → Stream OK; DELETE → 403.
- Embed-Item → Share-API → 400 „not shareable“.
- Dashboard löschen → `dashboard_id` auf Items NULL, Queue-Einträge CASCADE.
- Gallery-Uploads (Bilder) und Media-Uploads getrennte Quotas/Pfade.

---

## Datei-Anker (bei Umsetzung anlegen/erweitern)

| Bereich | Pfade |
|---------|--------|
| Config | `apps/backend/infrastructure/config.py` |
| Operator | `apps/backend/infrastructure/operator_settings.py` |
| DB | `apps/backend/infrastructure/db/migrations/versions/schema_NNN_*.py` |
| Media API | `apps/backend/api/media_api.py`, `media_db.py`, `media_policy.py` |
| Storage | `apps/backend/infrastructure/dashboard_file_storage.py` (reuse) |
| Dashboard blocks | `apps/frontend/src/features/dashboard/MediaPlayerBlock.tsx` |
| Agent tools | `plugins/tools/personal/media/media.py` |
| Admin UI | `AdminInterfacesPlatformSection.tsx`, `AdminUsers.tsx` |
| Agent config | `plugins/agents/dashboard/agent.yaml` |

---

## Offene Entscheidungen (vor M1 klären)

1. **Queue in JSON vs. DB sofort** — Empfehlung: JSON in M1, DB in M2.
2. **Video** — Stufe 1 nur Audio + Embed-Video; Upload-Video optional mit strengerem MIME/Quota.
3. **Transcoding** — nein in M1 (Original-Format streamen); ffmpeg später nur wenn nötig.
4. **Separate Quota von Dashboard-Bildern** — ja (`media_storage_quota_mb` unabhängig von Gallery).

---

*Plan-Version: 1 — bei Start M1 zuerst Operator-Flags + Quota-Modell finalisieren.*
