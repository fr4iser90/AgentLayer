# Neue Out-of-Band-Bridges (Slack, Matrix, …)

Gateways außerhalb der Web-UI speichern den Verlauf pro **AgentLayer-User** und **externem Chat-Kontext** in Postgres. Dafür gibt es **keine** zentralen Enum-Listen mehr in `conversations_db` oder in der Sidebar: die Web-UI gruppiert Chats nach dem String `source`, der aus `bridge_agent_sessions.provider` kommt.

## Was du nicht anfassen musst

- `src/infrastructure/conversations_db.py` — leitet `source` automatisch aus der Bridge-Tabelle ab.
- `interfaces/agent-ui` — Sidebar nutzt beliebige `source`-Strings.

## Was du implementierst

### 1. Provider-ID

Wähle einen **stabilen, kleingeschriebenen** Identifikator (z. B. `slack`, `matrix`). Der erscheint in der API als `conversation.source` und in der UI als Abschnittsname.

Definiere eine Konstante **im eigenen Integrationsmodul** (nicht zwingend in `bridge_agent_session.py`):

```python
BRIDGE_SLACK = "slack"
```

### 2. Kontext abbilden

`bridge_agent_sessions` braucht:

| Feld | Bedeutung |
|------|-----------|
| `scope_chat_id` | `int` — z. B. Telegram-`chat.id`, Discord-`channel.id` |
| `scope_thread_id` | `int` oder `0`/`NULL`-Semantik — z. B. Telegram-Forum-Thread; sonst `None` |
| `workspace_id` | (nach Migration `schema_044`) optional — gebundenes **Coding-/Security-Workspace** für diesen Chat |
| `default_agent_id` | optional — Agent-Override (`/agent …`); sonst bei gesetztem Workspace Default **`coding`** |

Der zusammengesetzte Schlüssel `(user_id, provider, scope_chat_id, scope_thread_id)` ist eindeutig. Passe deine Plattform-IDs so an, dass sie in **int** passen (Hash nur, wenn du weißt, was du tust).

### 3. Pro eingehender Nachricht

Referenzimplementierungen (gleiches Muster):

- `apps/backend/infrastructure/integrations/telegram_bridge.py` — `bridge_agent_conversation_ensure` → `bridge_try_slash_command` (optional) → `messages_for_bridge_completion` → `work.update(bridge_chat_completion_extras(...))` → `chat_completion` → `conversation_append_message`
- `apps/backend/infrastructure/integrations/discord_bridge.py` — dasselbe

Ablauf:

1. Externe User-ID → **AgentLayer** `user_id` + `tenant_id` (wie bei Telegram/Discord über Verknüpfung / DB).
2. `conv_id = bridge_agent_conversation_ensure(user_id, tenant_id, provider=BRIDGE_…, scope_chat_id=…, scope_thread_id=…, model=…)`.
3. Wenn `bridge_try_slash_command(...)` Text zurückgibt: an den Nutzer senden und **stop** (kein LLM-Round).
4. `msg_list = messages_for_bridge_completion(user_id, conv_id, new_user_text=text)`.
5. `work = { "model", "messages", "stream": false }` dann `work.update(bridge_chat_completion_extras(user_id, provider=…, scope_chat_id=…, scope_thread_id=…))` — setzt `workspace_id` / `agent_id` aus der Bridge-Session.
6. `set_identity` / `chat_completion` wie in den bestehenden Bridges (Rollen, Tools).
7. Antwort mit `conversation_append_message` für `user` und `assistant` persistieren.
8. **Clear:** `bridge_agent_conversation_ensure` dann `bridge_agent_session_reset` — löscht nur **Nachrichten**, **nicht** Workspace-/Agent-Bindung.

**Slash-Befehle (Telegram/Discord, Text nach Prefix):**

- `/workspace list` — eigene Workspaces (UUID + Name)
- `/workspace bind <uuid>` — Workspace an diesen Chat binden
- `/workspace clear` — Bindung entfernen
- `/agent list` / `/agent <id>` / `/agent clear` — Agent-Override (Admin-only Agents werden serverseitig abgewiesen)

### 4. Prozess / Lifecycle

Bridges laufen typischerweise in einem **Background-Thread** neben Uvicorn. Siehe:

- `telegram_bridge.start_background()` / `stop_background()`
- `discord_bridge.start_background()` / `stop_background()`
- Einbindung in `src/api/main.py` im `lifespan`-Hook (`try`/`except`, optional).

Deine neue Bridge: gleiches Muster — `your_bridge.start_background()` in `lifespan` registrieren.

### 5. Konfiguration & Sicherheit

- Bot-Token / Webhooks über `operator_settings` oder Umgebungsvariablen (wie die bestehenden Interfaces).
- Nur **verknüpfte** externe Accounts dürfen chatten (gleiche Idee wie `user_id_telegram_global` / Discord-Lookup).

---

**Kurz:** Neue Bridge = neues Integrationsmodul + `bridge_agent_conversation_ensure` mit deiner `provider`-Zeichenkette; Persistenz und Web-UI folgen automatisch.
