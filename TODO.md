**Kurz:** Der Agent kann dich heute **nur sehr begrenzt** proaktiv erreichen — nicht als generisches „Task fertig“-System über alle Kanäle. Discord/Telegram sind primär **Eingang + Antwort im gleichen Thread**; echtes Outbound gibt es fast nur beim **Operator-Scheduler → Telegram**.

---

## Was schon existiert

| Mechanismus | Proaktiv? | Kanal |
|-------------|-----------|--------|
| **Discord/Telegram Bridge** | Nein (Antwort auf deine Nachricht) | Gleicher Chat |
| **Operator-Scheduler** (`scheduler.py`) | Ja, wenn LLM nicht `SCHEDULER_OK` sagt | **Nur Telegram** (wenn `telegram_user_id` verlinkt) |
| **`scheduler_jobs`** (Hintergrund-Jobs) | Nein | Nur Log + `last_run_at` / `scheduler_job_runs` |
| **Chat WebSocket** (`agent.done`) | Nur während offener Session | Web-UI |
| **Delegate Auto-Respond** | Nein (synthetische Chat-Turns) | Web-Chat |

Der Scheduler-Prompt erwartet explizit JSON wie `{"notify":true,"message":"..."}` — das ist das einzige etablierte Outbound-Muster:

```148:154:apps/backend/infrastructure/scheduler.py
    sys_prompt = (
        "You are in SCHEDULER mode (background check). "
        "If there is nothing that needs the user's attention, reply with exactly one line: SCHEDULER_OK\n"
        "If something needs attention, reply with compact JSON: "
        '{"notify":true,"message":"...","severity":"low|medium|high"} '
        "or plain text.\n"
```

Verlinkung läuft über **Settings → Connections** (Telegram/Discord User-ID). Es gibt **keine** User-Prefs wie „bei Job X immer Discord“ und **kein** Agent-Tool `notify_user`.

Dashboard-Badges für Agent-Updates existieren nicht — nur Status-Badges in `CardGridBlock` (Projekt-Status, nicht „ungelesen vom Agent“).

---

## Wie es sein *sollte* (Empfehlung)

### 1. Ein generisches **Notification-Event**, viele **Delivery-Adapter**

Nicht „Agent schreibt direkt Telegram“, sondern:

```
Agent/Scheduler/Job fertig
  → Event: { user_id, kind, severity, title, body, deep_link, source_ref }
  → NotificationService
       → In-App Inbox (immer)
       → optional: Telegram / Discord DM / E-Mail
```

**Vorteil:** Einmal implementiert für Scheduler-Jobs, Coding-Runs, Dashboard-`patch_data`, Delegate-Eskalation.

### 2. **Defaults: nicht überall**

„Überall standardmäßig an“ ist zu laut und teuer (Rate-Limits, Spam).

Sinnvolle Defaults:

| Kanal | Default | Begründung |
|-------|---------|------------|
| **Web (In-App)** | **An** | Immer verfügbar, kein externes Setup |
| **Telegram** | Aus, bis verlinkt | Bereits angebunden |
| **Discord** | Aus, bis verlinkt | Braucht DM/Thread-Kontext |
| **E-Mail** | Aus | Für seltene/high-severity |

**Wo konfigurieren:**

- **Global:** Settings → **Notifications** (nicht Connections — das bleibt „Account verknüpfen“)
- **Pro Job:** beim Schedule: `notify_on: never | failure | always`, `channels: [web, telegram]`
- **Pro Dashboard:** optional in `data._agentlayer`: „Agent-Updates hier → Badge + Inbox“

Connections = *kann* senden; Notifications = *wann* und *wohin*.

### 3. **Chat und Dashboard sind komplementär, nicht entweder/oder**

| Situation | UX |
|-----------|-----|
| Du warst im Chat aktiv | Ergebnis im Thread + optional kurze Push |
| Hintergrund-Job / Scheduler | **Inbox** + Push (wenn konfiguriert) |
| Agent hat **Dashboard-Daten** geändert | **Badge am Block/Board** + Eintrag in Inbox |
| Du öffnest Dashboard/Block | Badge weg (`last_seen_at`) |

**Dashboard-Badges** sind hier stark:

- Dot/`!` am Block-Titel oder Board in der Sidebar
- Tooltip: „Agent hat KPIs aktualisiert · vor 2 Min“
- Klick → Block fokussieren oder Diff/Activity-Panel

Das passt zu eurem Modell (viele Boards, Pins, `dashboard_ref`) besser als alles in einen Chat zu quetschen.

Technisch minimal:

```json
// dashboard.data._agentlayer oder separater activity_store
{
  "activity": [
    {
      "id": "...",
      "at": "ISO",
      "block_id": "stat_projects",
      "kind": "agent_patch_data",
      "summary": "3 Projekte verlinkt",
      "read": false
    }
  ]
}
```

Frontend: `unreadCount(block_id)` aus `activity` + `user_last_seen`.

### 4. **Wann der Agent *proaktiv* schreiben darf**

Klare Regeln gegen Spam:

1. **Severity:** `info` → nur In-App; `action_required` → Push erlaubt
2. **Daily cap** pro User/Kanal (wie `scheduler_outbound_daily` — Pattern existiert)
3. **Dedup:** gleicher Job/Block nicht alle 5 Min erneut pingen
4. **Quiet hours** (optional, User-Timezone)
5. Agent-Tool **`notify_user`** nur mit `{ severity, message, link }` — Backend entscheidet Kanäle nach Prefs, nicht das LLM

---

## Konkrete Phasen (passend zu eurem Stand)

**P0 — schnell, hoher Nutzen**

- In-App **Notification-Inbox** (Bell in Header)
- Events aus: `scheduler_jobs` finished/failed, Coding-Schedule-Runs
- Dashboard: Sidebar-Dot + Block-Badge bei Agent-`patch_data` / KPI-Sync

**P1**

- User Notification-Prefs (Web default on, Telegram opt-in)
- Scheduler-Jobs: `notify_on` + Kanalwahl
- `notify_user`-Tool für Agent (backend-gated)

**P2**

- Discord DM outbound (schwieriger als Telegram — braucht DM-Channel oder letzten Bridge-Chat)
- Digest-Modus („3 Updates gebündelt“)
- Deep links: Chat-Thread, Dashboard+Block, Job-Run-Detail

---

## Antwort auf deine konkreten Fragen

1. **Kann der Agent schon anschreiben wenn fertig?**  
   Nur beim **Operator-Scheduler → Telegram**, und nur wenn der Check „Aufmerksamkeit nötig“ meldet. Normale Agent-Läufe und `scheduler_jobs` **nicht**.

2. **Default Discord/Telegram/Web überall?**  
   **Nein.** Default: **Web-Inbox + Dashboard-Badges**. Externe Kanäle **opt-in** nach Verlinkung in Connections.

3. **Immer im Chat vs. Dashboard-Badges?**  
   **Beides:** Chat für dialogische Tasks; **Badges + Inbox** für strukturierte/background Updates an Boards und Blocks. Das skaliert besser bei mehreren Dashboards und Inbox-Aggregation.

Wenn du das umsetzen willst, würde ich mit **P0 (In-App + Dashboard-Badges + Job-finished Events)** starten — wenig Risiko, sofort spürbar, und Telegram/Discord später als Adapter draufsetzen. Dafür müsstest du in **Agent mode** wechseln.