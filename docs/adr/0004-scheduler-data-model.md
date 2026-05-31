# ADR 0004: Scheduler — Konfiguration, Jobs, Chat-Tools & Rechte

## Kontext

Der Hintergrund-**Scheduler** führt periodisch Agent-Läufe (`chat_completion`) mit festgelegtem User-Kontext aus und kann bei Bedarf per Telegram benachrichtigen (Tageslimit in `scheduler_outbound_daily`). Die frühere Bezeichnung „Heartbeat“ wurde zu **Scheduler** (Migration `schema_029`: `scheduler_*`, `scheduler_outbound_daily`).

Zusätzlich ist ein **Produktziel** beschrieben: Im Chat soll man z. B. Aufträge für den **IDE-Agent** oder dashboard-gebundene Checks **anlegen** („füge zu Schedules hinzu: …“); diese landen **persistiert**, laufen **später** gegen den richtigen Ziel-Agenten und sind **im Dashboard sichtbar**. Das erfordert eine **Job-Tabelle**, **serverseitige Rechte** (kein Umgehen über Prompts) und optional **LLM-Tools** — aber nur als **validierte API**, nicht als Freitext-SQL.

## Phasen (überlappend, nicht alles auf einmal bauen)

### Phase A — Operator-Singleton (aktuell)

**Eine Zeile** in `operator_settings` mit `scheduler_*`: ein periodischer Hintergrund-Check, konfigurierbar über Admin → Interfaces. Minimale Join-/UI-Last; ausreichend für **einen** globalen Operator-Tick.

### Phase B — Tabelle `scheduler_jobs`

**Umgesetzt (Schema `schema_030`+):** Tabelle `scheduler_jobs` inkl. `last_run_at` und **`coding_workflow` (JSONB)**. **Server:** Daemon-Thread `scheduler_jobs_runner`; **`operator_settings`** (Admin → Interfaces): Worker an/aus, Timeout. Laufzeit: `execution_target` = Registry-`agent_id` (z. B. `general`, `coding`, …). **Dashboard-UI** / Audit optional (Phase D).

Ein Datensatz pro geplantem Job, z. B. mit:

- Identität & Lebenszyklus: `id`, `enabled`, `created_by`, `created_at`, …
- **Ausführung:** `user_id` (Tenant/Kontext wie heute), optional Modell/Tools/Backend-Felder
- **Zeit:** `interval_minutes` und/oder später `cron_expr` + Zeitzone
- **Ziel:** `execution_target` (Registry-`agent_id`) — steuert, **welcher Agent** den Job ausführt
- **Dashboard:** optional `dashboard_id` — Jobs wie „Calendar check in diesem Repo“ sind an einen Dashboard gebunden und können in der **IDE-/Dashboard-UI** gelistet werden
- **Inhalt:** `instructions` (oder strukturierte Payload), wie der ausführende Agent den Task versteht

Die bisherigen `scheduler_*`-Spalten in `operator_settings` können parallel bleiben, als „Default“-Job migriert werden oder später schrittweise deprecated werden.

### Phase C — Chat-gesteuerte Anlage + Tools

**Umgesetzt (erste Iteration):** Agent-Tools `create`, `list`, `set_enabled` im Plugin `plugins/tools/capabilities/platform/scheduler_jobs/scheduler_jobs.py` (Persistenz über `apps.backend/infrastructure/scheduler_jobs_store.py`). **Policy:** `execution_target=ide_agent` nur mit **Admin-Rolle**; Dashboard-Zuordnung nur bei ausreichendem Dashboard-Zugriff; Listen für Nicht-Admins auf Jobs eingeschränkt, die der Nutzer angelegt hat oder die ihn als `execution_user_id` führen.

- **REST (Anlage weiterhin über Tools):** Lese-/Ack-Endpunkte für IDE siehe oben; optionales CRUD-PATCH später.

### Phase D — Sichtbarkeit & Governance

- **UI:** Endpoint(s) „Jobs für Dashboard W“ / „Jobs für Ziel IDE-Agent“; Darstellung im Dashboard, damit Schedules **nicht nur** aus dem Chat existieren.
- **Audit:** Wer hat welchen Job angelegt/geändert (Nachvollziehbarkeit, besonders für IDE-Ziele).
- **Telegram-Limit:** `scheduler_outbound_daily` bleibt user-zentriert; bei Bedarf später um `job_id` erweitert, falls pro Job separat limitiert werden soll.

## Rechte (RBAC) — zwingend serverseitig

Anforderung: **Nur bestimmte Rollen** dürfen z. B. Jobs mit `execution_target = ide_agent` anlegen oder dashboard-fremde Jobs setzen.

- **Jede** Mutation (Tool **und** REST) muss dieselbe Policy prüfen: JWT → Rolle/Capabilities → erlaubte Targets und Dashboards.
- **Kein Workaround** über „anderen Prompt“ oder Client-only-Checks: Policy nur im Backend.
- Konkrete Regeln (z. B. „nur Admin darf IDE-Agent-Schedules“) werden als **konfigurierbare oder hardcodierte Policy** im Handler umgesetzt, nicht in der Tool-Beschreibung allein.

## Entscheidung (überarbeitet)

| Thema | Entscheidung |
|--------|----------------|
| Einfacher Operator-Scheduler | **Phase A** bleibt gültig: `operator_settings.scheduler_*` für den einen globalen Tick. |
| Multi-Job, IDE, Dashboard | **Phase B** ist das Zielmodell: **`scheduler_jobs`** (oder gleichwertiger Name) mit `execution_target`, optional `dashboard_id`. |
| Chat → Schedule | **Phase C:** strukturierte **Tools** + gleiche Server-Regeln wie API. |
| Transparenz & Abuse-Resistenz | **Phase D:** Dashboard-UI + Audit + RBAC im Backend. |

## Status

Akzeptiert (laufend erweitert). `schema_029`–`schema_033`, Tools `schedule_job_*` (inkl. `ide_workflow`), Server-Runner, IDE-API `/v1/scheduler/jobs/*`. Offen: **IDE-Extension**, **Dashboard-UI**-Liste, **Audit-Log**.
