Du hast recht, kurzfristige Entkopplungen ohne Zielbild wären nur technische Schulden. Hier der **langfristige Plan** — als Architektur, die ihr einmal richtig baut und dann erweitert, statt ständig umzubauen.

---

# Langfristiger Plan: Ein generisches Dashboard-System

## 1. Leitprinzipien (Invarianten)

Diese Regeln gelten **dauerhaft**. Alles, was dagegen verstößt, ist technische Schuld.

| # | Invariante |
|---|------------|
| **I1** | Ein Dashboard ist **nur** `{ id, title, ui_layout, data, meta }`. Kein Verhalten hängt am Feld `kind`. |
| **I2** | **Layout** definiert Struktur und Bindings (`dataPath`, `props.compute`, Spalten, …). |
| **I3** | **Daten** sind freies JSON unter beliebigen Pfaden — keine feste Schema-Tabelle pro „Dashboard-Typ“. |
| **I4** | **Templates/Katalog** sind **Startpakete** (Snapshot beim Erstellen), keine Runtime-Klassen. |
| **I5** | **Externe Systeme** (GitHub, SimpleSec, Kalender, …) sind **Connectors** — Plugins, kein Core. |
| **I6** | **Ein Agent-Surface** für alle Boards: lesen, patchen, layouten; Connectors optional. |
| **I7** | **KPIs** nur über deklarative `props.compute` im Layout — nie hardcodierte `stat_*`-Namen im Backend. |

Wenn das steht, kann ein User **ein einziges Board für alles** haben — Repos, Events, Notizen, Security — ohne je `kind: projects` zu brauchen.

---

## 2. Ziel-Architektur (Schichten)

```
┌─────────────────────────────────────────────────────────────────┐
│  UI (React)                                                      │
│  Block-Registry · Grid/Section · Block-Settings · Connectors-UI │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST / WS
┌────────────────────────────▼────────────────────────────────────┐
│  Dashboard Core (kind-agnostisch)                                │
│  · CRUD dashboard                                                │
│  · patch_data / patch_layout                                     │
│  · layout_tree (nested, depth 2)                                 │
│  · data_paths (get/set)                                          │
│  · data_compute (stat bindings)                                  │
│  · list_ops (append/update/delete rows in any list path)         │
│  · sharing / members / proposals                                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌───────────────┐   ┌─────────────────┐   ┌──────────────────┐
│ Template      │   │ Connector       │   │ Agent            │
│ Gallery       │   │ Registry        │   │ (dashboard)      │
│ (read-only    │   │ (plugins)       │   │ + connector      │
│  snapshots)   │   │ github, ssc, …  │   │   tools          │
└───────────────┘   └─────────────────┘   └──────────────────┘
```

**Kein** Layer „ProjectsDashboard“ / „PetsDashboard“ im Core.

---

## 3. Was wird aus `kind`?

### Heute (Problem)
`kind` ist drei Dinge gleichzeitig:
- Template-Key beim Anlegen  
- Filter im Hub („zeige alle Projects-Boards“)  
- **Gate** für Features (`import` nur bei `projects`, Tools nur für `kind`)

Das ist der Kernfehler.

### Langfristig (Ziel)

| Feld | Rolle |
|------|--------|
| `template_id` (neu, optional) | „Herkunft: `projects-v1`“ — nur Anzeige, Filter, Docs |
| `kind` (deprecated → alias) | Übergang: gleicher Wert wie `template_id`, später nur Lesen |
| Verhalten | **Nie** aus `template_id` ableiten |

**Anlegen:**
```
POST /dashboards/from-template { template_id: "projects-v1" }
  → kopiert ui_layout + initial_data
  → speichert template_id als Metadatum
  → danach völlig unabhängig (wie fork)
```

**Custom / leer:**
```
POST /dashboards { title, ui_layout?, data? }
  → template_id = null
```

Katalog unter `plugins/dashboards/*/` bleibt — aber heißt **Template Gallery**, nicht „Dashboard-Arten“.

---

## 4. Core-API (langfristig stabil)

Alles, was jedes Board braucht — **einmal** definieren, nie pro Domain duplizieren:

### Daten
- `GET/PATCH dashboard` — `data` + `ui_layout`
- `patch_data` — `{ path, value }` Patches
- **`list.append_rows`** — `{ list_path, rows[] }`
- **`list.update_row`** — `{ list_path, row_id, patch }`
- **`list.delete_row`** — `{ list_path, row_id }`

Zeilen brauchen stabile `id` (generiert vom Core) — nicht domain-spezifisch.

### Layout
- `patch_layout` — ops: `add_block`, `remove_block`, `set_grid`, `set_props`
- Nested sections (depth 2) — bleibt

### Berechnung
- `finalize_dashboard_data(layout, data)` nach jeder Datenänderung  
- Stat-Blöcke mit `props.compute` (count, count_where, sum, …)  
- Später: `compute` erweitern (avg, min, max, group_by) — **ein** Engine

### Kontext
- Agent/UI senden immer **`dashboard_id`** (embedded chat, URL, Pin)  
- Auflösung „welches Board?“: Kontext → einziges Board des Users → Fehler mit Liste  
- **`resolve_dashboard_id_for_kind` entfällt**

---

## 5. Connectors (statt Domain-Tools)

Alles Domain-spezifische wandert in **registrierte Connectors**:

```yaml
connector: github.repos
  requires: [user_secret: github_pat]
  inputs:
    dashboard_id: uuid
    list_path: string      # wohin schreiben
    repos: [...]
  row_shape:               # Dokumentation + Validierung
    required: [title, remote_url]
    optional: [workspace_id, tags, ...]
  side_effects:
    - optional: create_workspace
```

```yaml
connector: simplesec.portfolio
  requires: [user_secret: ssc_api_key]
  inputs:
    dashboard_id, list_path
    match_field: remote_url   # wie Zeilen gematcht werden
  writes:
    - security_snapshot      # Objekt pro Zeile
  does_not:                 # wichtig
    - start_scans            # separates Tool / anderer Connector
    - hardcode KPIs
```

**Regeln für Connectors:**
- Brauchen **immer** `dashboard_id` + `list_path` (oder leiten `list_path` aus Layout ab)
- **Kein** `kind`-Check
- Schreiben nur in **Listen-Zeilen** oder explizit erlaubte Pfade
- KPIs danach: User/Layout definiert `stat` + `compute`

Langfristig **deprecated** (nicht erweitern):
- `projects.*`, `pets.*`, `ideas.*`, `shopping_list.*` als separate Tool-Domains  
- Stattdessen: `connector.*` + generische `dashboard.list_*`

---

## 6. Block-Modell (das echte „Schema“)

Es gibt **kein** globales Projects-Schema. Das Schema ist **pro Block** in `props`:

```json
{
  "type": "card_grid",
  "props": {
    "dataPath": "repos",
    "columns": [
      { "field": "title", "kind": "text" },
      { "field": "remote_url", "kind": "text" },
      { "field": "security", "kind": "text" }
    ],
    "compute": null
  }
}
```

Ein anderes Board:
```json
{ "dataPath": "veranstaltungen", "columns": [{ "field": "datum" }, { "field": "ort" }] }
```

**Block-Registry** (Frontend) + **block types** (Backend-Validierung) = erweiterbare Typenliste — keine „Builder Factory“ als Monolith, sondern:

- Registry für Block-Typen  
- Layout-Ops für Komposition  
- `data_compute` für abgeleitete Stats  
- Connectors für externe Enrichment  

Das reicht für „Grid in Grid“ und beliebige Dashboards.

---

## 7. Agent-Modell

### Ein Dashboard-Agent
Tools (final):
- `dashboard.read`, `patch_data`, `patch_layout`, `propose_layouts`
- `dashboard.list_append` / `list_update` (generisch)
- `connector.run` oder explizite `connector.github.import_repos`, …
- `dashboard.from_template` (Galerie)

**Kein** Routing „für Repos → projects-Agent“. Ein Agent, Kontext = aktuelles `dashboard_id` + optional `block_id`.

### System-Prompt
- Recipe: „Lies Layout → erkenne dataPaths → patche Daten → setze compute auf stat-Blöcke“  
- Template-`setup.json` → **Onboarding-Hinweise** beim `from-template`, nicht permanente Regeln

### Tasks / Scheduler
- `agent_tasks` = Orchestrierung („scan alle Repos in list_path X“)  
- Connectors = deterministische Ausführung  
- LLM = Layout/UX, nicht ETL

---

## 8. UI-Modell

| Heute | Ziel |
|-------|------|
| „Import GitHub“ nur bei `kind === projects` | „Connectors“ am Board oder am Listen-Block (wenn Spalten passen / User wählt `list_path`) |
| Hub filtert nach `kind` | Hub filtert nach `template_id` / Tags / Suche — kosmetisch |
| Block-Settings pro Typ | + Tab „Data source“ / „Connector“ am Block (optional) |

**Ein Board für alles:** User legt Sections an, jede Section = eigene `dataPath`. Connectors fragen: „In welche Liste?“ (Default: `primary_list_data_path` des Blocks).

---

## 9. Was mit dem bestehenden Katalog passiert

`plugins/dashboards/projects/`, `pets/`, … **bleiben** als:

- `projects.template.json` — Beispiel-Layout + `initial_data` + `compute`-Beispiele  
- `projects.setup.json` — Onboarding-Text für Agent nach `from-template`  
- **Kein** Runtime-Code, der `kind === projects` erzwingt

`dashboard.kind.json` wird zu **`template.manifest.json`**:
```json
{
  "template_id": "projects-v1",
  "label": "Portfolio (Beispiel)",
  "description": "...",
  "template": "projects.template.json",
  "setup": "projects.setup.json"
}
```

`validate_create_kind` → `validate_template_id` — nur beim **Kopieren**, nicht bei jedem PATCH.

---

## 10. Migrationsstrategie (Strangler — kein Big Bang)

Nicht alles auf einmal. Jede Phase hat **Exit-Kriterien**; erst dann die nächste.

### Phase A — Core vervollständigen (Fundament)
**Ziel:** Alles, was heute schon generisch sein soll, ist es auch wirklich.

- `data_compute` ✓ (habt ihr)  
- `finalize_dashboard_data` bei allen Schreibpfaden ✓  
- Generische **`dashboard.list_*`** Tools implementieren  
- `resolve_dashboard_id` überall (ohne kind)  
- Tests: ein `custom`-Board mit zwei Listen + compute-KPIs — **ohne** `projects`-Code

**Exit:** Kein neuer Feature-Code in `projects_kpi`-artigen Modulen; KPIs nur via `compute`.

---

### Phase B — Connectors einführen
**Ziel:** Externe Aktionen als Plugins, nicht als Dashboard-Typ.

- Connector-Registry (Manifest in `plugins/connectors/*/`)  
- Erster Connector: `github.import_repos` (ersetzt `projects_import` **funktional**, nicht nur kind-Gate entfernen)  
- Zweiter Connector: `simplesec.enrich_rows` (nur Zeilen, keine KPIs)  
- API: `POST /dashboards/{id}/connectors/{connector_id}/run`

**Exit:** `projects_import.py` gelöscht; `kind`-Check nirgends in Import-Pfaden.

---

### Phase C — Template-Galerie statt kind-Gates
**Ziel:** `kind` wird Metadatum.

- DB: `template_id` Spalte (Migration); `kind` spiegeln für Kompatibilität  
- Create-Flow: `from-template` primär; `create_dashboard(kind=…)` deprecated  
- Hub/Frontend: Labels aus Template-Manifest, nicht aus hardcoded `kindLabelFor`  
- Agent: `create_dashboard` nur noch `from_template` + `custom`

**Exit:** Kein Backend-Code liest `kind` für Verhalten; nur noch Anzeige/Legacy-API.

---

### Phase D — Domain-Tools abschalten
**Ziel:** Eine Tool-Oberfläche.

- `pets.*`, `ideas.*`, `shopping_list.*` → generische `list_*` + ggf. kleine Connectors  
- Agent `tool_domains` vereinfachen: `dashboard` + `connector`  
- Docs + Tests auf einem generischen „mega board“ E2E

**Exit:** Keine `resolve_dashboard_id_for_kind` Aufrufe mehr im Repo.

---

### Phase E — UX & optional DB-Normalisierung
**Ziel:** Polish, nur wenn nötig.

- Block-Settings: Compute-Editor, Connector-Picker  
- Optional: große Listen aus `data` JSON in eigene Tabelle — **nur** bei Performance-Bedarf, mit gleicher `list_path`-API (Implementation detail)

**Exit:** Produkt-Doku beschreibt ein Modell, nicht neun Dashboard-Arten.

---

## 11. Was du bewusst NICHT tun solltest

| Kurzfristige „Kacke“ | Warum schlecht |
|----------------------|----------------|
| Nur `kind`-Check bei Import entfernen, Rest lassen | Zwei Wege: `projects.*` + generisch — Doppelpflege |
| Security-KPIs hardcoden (`stat_security_*`) | Widerspricht `compute`; nächstes Feature wieder hardcoded |
| `projects_kpi` umbenennen ohne Logik zu ändern | Täuscht Generik vor |
| Neuer `kind: mega` für All-in-one-Boards | Wieder ein Dashboard-Typ |
| LLM soll Scan-Daten in 20× `patch_data` schreiben | Kein Connector, nicht skalierbar |
| Monolith „DashboardBuilderFactory“ | Over-engineering; Registry + Layout-Ops reichen |

---

## 12. Dein „ein Dashboard für alles“-Szenario (Endzustand)

1. User erstellt Board: **leer** oder aus Template `personal-v2`  
2. Agent/User baut Sections: `repos`, `events`, `inbox`  
3. KPIs: stat-Blöcke mit `compute` auf jeweilige Listen  
4. GitHub: Connector `github.import_repos` → `list_path: repos`  
5. Security: Connector `simplesec.enrich_rows` → matched `remote_url`  
6. KPI „critical total“: `sum` über `repos.security_snapshot.critical`  
7. **Kein** `kind`, kein Projects-Tool, kein Template-Zwang  

Das Board ist strukturell identisch zu einem „Projects-only“-Board — nur der Inhalt und die Layout-Wahl unterscheiden sich.

---

## 13. Reihenfolge für dich (Entscheidung)

Wenn du **keine Zwischen-Refactors** willst, ist die einzige sinnvolle Reihenfolge:

```
A (list_* + compute überall)  →  B (Connectors)  →  C (template_id)  →  D (domain tools weg)
```

**Nicht** Phase 1 „Import entgate“ allein — das wäre die kurzfristige Kacke, die du ablehnst. Stattdessen: **Connector `github.import_repos`** als erstes richtiges Stück von Phase B, gebaut auf Phase-A-`list_append`.

---

Wenn du als Nächstes willst, kann ich Phase A + B als **konkretes Tech-Design** (Dateien, APIs, Connector-Manifest-Schema, Deprecation-Tabelle) ausarbeiten — immer noch ohne Code, oder erst mit Code wenn du jeden Phase-Exit abnickst.