---
doc_id: planning-dsh-agentlayer-chat-ui-comparison
domain: agentlayer_docs
tags: [chat-ui, agent-ui, tui, dsh, gap-analysis]
---

# AgentLayer ↔ DeepSeek Harness — Chat UI Gegenüberstellung (Stand Sep 2026)

**Zweck:** Faktencheck einer extern erstellten Chat-UI-Dokumentation („DeepSeek Harness Chat UI … Vergleich mit AgentLayer") gegen den echten Code, plus korrigierte Ist-Beschreibung der AgentLayer-Chat-Flächen (Web + TUI).
**Companion:** [`dsh-agentlayer-capability-comparison.md`](./dsh-agentlayer-capability-comparison.md) (Token-Meter, Compaction, Plan/Todo/Goal, MCP, Sandbox), [`agent-runtime-ux-goal-todos-plan.md`](./agent-runtime-ux-goal-todos-plan.md) (Goal/Todos/Activity-Workplan), [`dsh-integration-plan.md`](./dsh-integration-plan.md) (historische Phasen).
**Scope dieses Docs:** ausschließlich Chat-UI — Nachrichtenmodell, Tool-Aktivitäts-Darstellung, Expandierbarkeit, Streaming, Rendering. Kein Feature-Doc, kein Auftrag.

---

## Verifikationsstatus — bitte zuerst lesen

| Seite | Status |
|-------|--------|
| **AgentLayer (Web + TUI + Backend-Events)** | **Verifiziert.** Jede Aussage steht mit `Datei:Zeile`; alle Zeilen wurden gegen die Quelle geprüft. Negativbehauptungen sind durchsucht und als solches markiert. |
| **DeepSeek Harness** | **Ungeprüft.** Die dsh-Beschreibungen (Search Card, „2 more in spill file", Message-/Tool-Call-Formate) sind unverändert aus der geprüften Vorlage übernommen. Der dsh-Checkout war nicht zugänglich. **Kein Verifikationsanspruch** — die dsh-Spalte taugt nicht als Entscheidungsgrundlage, solange sie nicht gegen `packages/…` abgeglichen wurde. |

Das ist bewusst so ausgelegt: Der Wert dieses Docs liegt in der belastbaren AgentLayer-Seite. Der Geschwister-Doc geht denselben Weg (`dsh-agentlayer-capability-comparison.md` referenziert dsh-Pfade, die dort seperat geprüft wurden).

---

## 1. AgentLayer Chat — Ist-Architektur Web (`apps/frontend`)

React 18 + Vite + TypeScript + Tailwind (`apps/frontend/package.json`, Paketname `agent-ui`). Kein Redux/Zustand/MobX in den Dependencies.

### 1.1 Zwei getrennte Datenspuren — nicht ein Nachrichtentyp

Die geprüfte Vorlage beschreibt **einen** Nachrichtentyp mit `type`-Discriminator. Das existiert nicht. Real gibt es zwei Spuren:

**Nachrichtenspur** — `UiMessage`, `apps/frontend/src/features/chat/chatThreadStorage.ts:8`:

```ts
export type UiMessage = {
  role: "user" | "assistant";
  content: string;
  reasoningContent?: string;   // Thinking, nur bei aktivem show-reasoning
  id?: string;
  createdAt?: number;
};
```

Drahtformat `ApiMessage` (`features/chat/conversationsApi.ts`) = Backend `MessageItem`, `apps/backend/api/conversations/controllers/conversations_api.py:31`: `role: Literal["user","assistant","system"]`, `content: Any` (str oder OpenAI-Multimodal-Liste), `created_at`, `id`, `client_message_id`, `reasoning`, `reasoning_content`.

**Aktivitätsspur** — `AgentTimelineEntry`, `chatThreadStorage.ts:42`. Flache Event-Liste mit `kind: string` (**kein** TS-Union/Enum), `text`, plus Tool-Feldern `toolName` / `toolSummary` / `toolOk` / `toolError` / `resultDisplay` (`:63`) / `resultChars` / `durationMs` / `stepPhase: "start" | "done"` / `toolRound` / `nested`, Subagent- und Index- sowie Kontext-Feldern. Ablage im Thread (`chatThreadStorage.ts:97`):

- `agentLog?: AgentTimelineEntry[]` — der laufende Turn
- `turnLogs?: AgentTurnLog[]` mit `AgentTurnLog = { userMessageId, entries }` — archiviert **pro User-Prompt**

Backend-seitig heißt derselbe Container `agent_log`; Kommentar `conversations_api.py:42`: „Legacy: JSON array of timeline entries. Current UI: v2 object `{v, current, turns}`".

**Repo-weite Negativbefunde** (jeweils `grep`, 0 bzw. angegebene Treffer):

- `final_message`: **0 Treffer** in `apps/frontend/src` und `apps/backend`.
- `tool_call`: im Frontend nur als `tool_call_count` in `features/admin/benchmarks/*` und `pages/admin/AdminBenchmarks.tsx` — **nicht** im Chat.
- `tool_result`: ist ein **Client→Server**-WS-Nachrichtentyp (ADR 0009, `apps/backend/api/chat/controllers/chat_websocket.py:16-18`), kein Nachrichten-Variant. `apps/frontend/src` sendet ihn nicht und behandelt `agent.tool_invoke` nicht.
- `TranscriptItem` mit `{ type: "message" | "run_cards" }` (`features/chat/buildRunCards.ts:349`) ist ein **Layout-Gruppierungstyp**, kein Nachrichtentyp.

### 1.2 Timeline → RunCards, und das „notable tool"-Tor

`buildRunCardsFromTimeline` (`features/chat/buildRunCards.ts:167`) faltet die flache Timeline in `RunCard`s der `RunCardKind = "subagent" | "index" | "tool" | "compaction"` (`buildRunCards.ts:5`).

Entscheidend und in der Vorlage nicht enthalten — ein `tool_start` bekommt **nur für ausgewählte Tools** eine Karte (`buildRunCards.ts:313-318`):

```ts
const notable =
  tool.startsWith("coding_") ||
  tool === "bash" ||
  tool === "retrieve_context" ||
  tool.startsWith("security_scan");
```

`delegate` wird übersprungen (`:311`), alle übrigen Tools erzeugen **nie** eine Karte. Der Nicht-notable-Pfad zeigt nur die Textzeile `name` plus Fehler/chars/Dauer (`features/chat/agentChatWsCore.ts:396-421`). Das ist die eigentliche Einschränkung der Web-Ansicht — nicht „keine Tool-Karte".

### 1.3 Expandierbarkeit: vorhanden, drei Mechaniken

| Was | Mechanik | Beleg |
|-----|----------|-------|
| Reasoning / Thinking | natives `<details>`, `defaultOpen` aus `getAgentShowReasoning()`, `<pre class="max-h-64 overflow-y-auto">` | `features/chat/AssistantTurnBlock.tsx:19-51` (`:31`, `:48`) |
| RunCard-Details | Hybrid: lokal `useState(defaultExpanded = false)` **oder** kontrolliert via lifted `expandedRunCardIds: Set<string>`; Toggle-Button `t("chat:runCardShowDetails")` / `runCardHideDetails` | `features/chat/RunCardBlock.tsx:163`, `:166`, `:391`; `pages/ChatPage.tsx:510`, `:784`, Weitergabe `:3869-3870` und `:3892-3893`; i18n `locales/de/chat.json:249`, `locales/en/chat.json:249` |
| **Command output** (`resultDisplay`) | verschachtelte `<details>` mit i18n-Key `runCardCommandOutput`, `<pre class="max-h-48 overflow-y-auto … font-mono">`, `open={…}` bei Fehlschlag | `RunCardBlock.tsx:367-377`, `:421-428` (`open={row.failed}`), `:445-452` (`open={d.toolOk === false}`) |
| Subagent Thinking-/Output-Auszüge | `<details>` + `<pre class="max-h-32">` / `max-h-40`, letzteres `open={card.status === "running"}` | `RunCardBlock.tsx:299-306`, `:312-319` |
| Context-Injections | eine eingeklappte Gruppe am Turn-Anfang | `features/chat/interleavedTurnSegments.ts:62-81`, `ContextInjectionGroup.tsx` |

Zusammengeklappt zeigt eine Karte die letzten 1 (`COLLAPSED_PREVIEW_DONE`) bzw. 2 (`COLLAPSED_PREVIEW_RUNNING`) Step-Labels — ohne „N more"-Zähler (`RunCardBlock.tsx:35-36`, `collapsedStepPreview:48`).

### 1.4 Streaming: Live-Blase **und** Side-Panel

- `ChatInFlightAssistantTurn.tsx:31-71` — die In-Flight-Assistenten-Blase: dieselbe `AssistantTurnBlock` wie fertig gemeldete Turns, mit `content` aus `useAgentStreamText(store)`, `reasoningContent` aus `useAgentStreamReasoning(store)`, `liveLog`-Timeline, `running`. Sichtbar bei `loading && mode === "agent"`.
- `ChatLiveActivityPanel.tsx:20-53` → `ChatAgentActivityPanel.tsx:20-37` (`memo`, `layout="header"`) → `AgentActivityPanel.tsx` — Ein-Zeilen-Liste im Header, **nicht** im Nachrichtentext. Das `memo` hält Live-Ticks von der Seiten-Re-render heraus.
- Store: `createLiveTurnStore()` (`features/chat/useAgentLiveTurn.ts:32-201`), RAF-batchig, über `useSyncExternalStore` konsumiert. Kein Zustand-Paket.
- `MessageTurnActivity.tsx` (flache Step-Liste) wird **nur** vom Dashboard-Embedded-Chat benutzt (`features/dashboard/DashboardEmbeddedChat.tsx`), nicht von `ChatPage`.

### 1.5 Rendering: Fließtext, kein Markdown

`react-markdown@^9.1.0` ist installiert (`apps/frontend/package.json:26`), aber **kein** File in `features/chat/` importiert es (0 Treffer für `markdown` dort). Es nutzen es `features/legal/LegalMarkdown.tsx` und `features/dashboard/KanbanRichMarkdownBlocks.tsx`.

Assistententext und Nutzertext sind reines `whitespace-pre-wrap`: `features/chat/ProposalMessageBody.tsx:134`, `:140`, `:148`; `features/chat/UserMessageBubble.tsx:15`, `:35`. Kein Code-Block, keine Syntax-Highlighting, kein `dangerouslySetInnerHTML` im Chat. Fenced Code Blocks stehen wörtlich im Absatz. Tool-Output nutzt `<pre … font-mono>`, Reasoning `<pre … font-sans>`.

### 1.6 Caps — meist still, einmal mit Marker

| Cap | Wert | Beleg |
|-----|------|-------|
| Tool-Result-Vorschau (Backend) | `_RESULT_DISPLAY_MAX = 4000` | `apps/backend/domain/delegation/result_preview.py:9`; Ansetzen `chat_tool_events.py:99-103` |
| Derselbe Cap im Client | `.slice(0, 4000)` | `features/chat/agentChatWsCore.ts:393`, `features/chat/subagentActivity.ts:59` |
| Tool-Fehler | 500 Zeichen | `chat_tool_events.py` (`result_error`) |
| Subagent-Auszüge | `SUBAGENT_EXCERPT_MAX = 12_000` | `features/chat/buildRunCards.ts:76` (Anwendung `:99`) |
| `agent.llm_round`-Auszug / Goal-Ziel | `.slice(0, 200)` / `.slice(0, 120)` | `features/chat/agentChatWsCore.ts` |
| Steps in der Aktivitätenliste | `RECENT_STEPS_MAX = 8` | `features/chat/AgentActivityPanel.tsx` |

**Präzisierung** (wichtiger Unterschied zur Vorlage): Es gibt **kein Spill-File** und **keine „mehr laden"**-Einstiegstelle. Aber `_tail_for_display` baut serverseitig einen Marker ein — `…(+N chars)` + der Rest-Schwanz (`result_preview.py:14-20`). Der Nutzer sieht also, **dass** abgeschnitten wurde, kann das Fehlende aber nicht holen. Der TUI-Client meldet Abschneiden als JSON-Flag `"truncated"` (`apps/tui/agentlayer_tui/local_exec.py:236` `_tail`), nicht als Textmarker.

---

## 2. AgentLayer Chat — Ist-Architektur TUI (`apps/tui`)

Eigenständiges Paket `agentlayer-tui`, Textual-basiert (`apps/tui/agentlayer_tui/app.py:12-17`), nur HTTP + WebSocket, importiert kein Backend (siehe `README.md`, [ADR 0008](../adr/0008-tui-client-contract.md)).

### 2.1 Transcript = einzelne Zeilen, keine Widget-Liste

`compose` (`app.py:149-158`): `Static#title`, `VerticalScroll#transcript`, `Static#strip` (Goal-Strip), `Static#suggest`, `Static#hint`, `Input#prompt`, `Footer`. Kein `RichLog`, kein `Collapsible`.

- `_append` (`app.py:190`): mountet pro Zeile ein `Static(f"{indent}{line.text}", classes=f"line {line.kind}", markup=False)`; Einrückung `" │ " * line.depth`.
- `_apply_line` (`app.py:200`): hat die Zeile einen `key` und existiert schon ein Widget dazu, wird **das Widget überschrieben** — deshalb wird die Tool-Zeile bei „done" umgeschrieben statt ergänzt.
- Zeilenmodell `Line` (frozen dataclass `kind; text; depth; key`) in `events.py:24-30`; `events.py` ist bewusst frei von Textual-Imports.

Benutzte `kind`-Werte (CSS-Klassen `app.py:87-103`): `user`, `assistant`, `reasoning`, `tool_start`, `tool_done`, `tool_error`, `sub_start`, `sub_done`, `goal`, `info`, `dim`, `warn`, `error`. **Keine** Textpräfixe wie `[USER]` / `[TOOL_CALL]` / `[TOOL_RESULT]`.

### 2.2 Toolzeile — die Glyphen sind real

`apps/tui/agentlayer_tui/events.py:14-16`:

```python
TOOL_GLYPH = "\u23fa"  # ⏺
OK_MARK = "\u2713"     # ✓
FAIL_MARK = "\u2717"   # ✗
```

- Start (`_tool_start_line`, `events.py:131-141`): `f"{TOOL_GLYPH} {label}"`, bei abweichendem `summary` zusätzlich `" — {summary}"`. Key `tool:{name}:{round}` (`_tool_key`, `events.py:125`). Label-Kette `step_label` → `label` → `name` (`tool_label`, `events.py:106`).
- Done (`_tool_done_line`, `events.py:142-167`): überschreibt dieselbe Key-Zeile; `mark = FAIL_MARK if ok is False else OK_MARK` (`:158`), `tail = f"  {mark} {DOT.join(parts)}"`, `parts` aus `failed: {error}`, `{chars} chars` (`result_chars`), `format_duration(duration_ms)`. Ergebnis: **`⏺ grep ✓ 3 chars 123 ms`** — die Vorlage hat das korrekt.
- Delegiert: `⏺ delegate → {agent_id}` (`events.py:279`), Done `└ {agent_id} {mark}` (`:294`). Abgelehnte Argumente: `! {name} rejected — {detail}` (`events.py:168-180`).

### 2.3 Keine Expandierbarkeit

- Kein `Collapsible`, keine Expand-Aktion, kein Detail-Key, kein Kommando für Argumente oder vollständigen Output.
- Das **einzige** `ModalScreen` ist `PermissionScreen` (`app.py:45`, Bindings `y`/`a`/`n`/`escape` `app.py:48`), nur für `agent.permission_ask` und lokale Tool-Gates.
- App-`BINDINGS` (`app.py:112`): `ctrl+c` (cancel_turn), `ctrl+shift+c` (copy_selection), `ctrl+d`, `ctrl+l`, `tab`. Keine Detail-Taste.
- Voller Tool-Output erscheint im Transcript **überhaupt nicht** — nur `result_chars` und Dauer.
- Reasoning-Widget zeigt nur den Schwanz: `self._state.reasoning[-2000:]` (`app.py:375`).
- Vorschau-Caps: `req.args_preview[:600]` (`app.py:61`), lokale Gate-Vorschau `[:2000]` (`app.py:441`), `tool_invoke`-Wait-Hinweis `[:200]` (`events.py:352`).
- Einziges „more" ist Text in anderen Kontexten: Command-Palette `… +{n} more (tab to cycle)` (`commands.py:167`), Goal-Strip `(+{n})` für >6 Todos (`events.py:216`).
- Datenrettung ist rein textuell: Maus-Selection + Clipboard (`ALLOW_SELECT = True` `app.py:83`, `_copy_selection` `app.py:329`) und `/tools` für die Tool-Namen des letzten Turns (`app.py:514`).
- Kappen im lokalen Runner: `MAX_FILE_BYTES = 2_000_000`, `MAX_SEARCH_MATCHES = 100`, `MAX_BASH_OUTPUT = 50_000` (`local_exec.py:46-53`), `_tail(…, max_lines=200)` (`:236`). **Kein Spill-File.**

---

## 3. WebSocket-Grundlage (beide Clients)

Endpoint `GET /ws/v1/chat?token=…` (`apps/backend/api/chat/controllers/chat_websocket.py:5`). Client→Server: `ping`, `cancel`, `add_tools`, `continue_step`, `permission_reply`, `tool_result`, `client_capabilities`, `secret_saved`, `chat` (`chat_websocket.py:7-30`).

Server→Client, toolrelevant: `agent.tool_start`, `agent.tool_done` (`chat_tool_events.py:37`, `:89`), `agent.tool_invoke` (ADR 0009), `agent.subagent_start` / `_step` / `_done`, dazu `agent.session`, `agent.llm_round_start`, `agent.llm_delta`, `agent.llm_round`, `agent.goal`, `agent.todos`, `agent.secret_prompt`, `agent.permission_ask`, `agent.done`, `agent.cancelled`, `chat.completion` (Docstring `chat_websocket.py:31-38`).

**Doku-Lücke:** das Docstring ist eine *Subset*-Liste und nennt emittierte Events nicht, die beide Clients behandeln: `agent.plan_mode` (`use_cases/conversation_goal_events.py:50`), `agent.goal_round` (`use_cases/goal_round_driver.py:57`, `:88`), `agent.subagent_delta` / `agent.subagent_reasoning` (`domain/agent_runtime/subagent_events.py:33-36`), `agent.llm_slot_wait` (`infrastructure/agent_runtime/llm_concurrency.py:237`), `agent.deferred_wait` (`domain/agent_runtime/async_wait.py:63`), `agent.step_wait` (`use_cases/chat_control.py:126`), `agent.aborted` (`chat_websocket.py:351`).
`index_start` / `index_done` / `compaction_done` / `context_inject` / `llm_queue` sind demgegenüber **Timeline-`kind`-Werte im Frontend**, keine WS-Eventnamen — nicht verwechseln.

---

## 4. Korrekturtabelle der geprüften Vorlage

| Abschnitt der Vorlage | Behauptung | Befund |
|---|---|---|
| §2.1.1–2.1.4 | Web-Nachrichten als `{type: message\|tool_call\|tool_result\|final_message, role, content, timestamp, id, tool_name, arguments, result}` | **Konstruiert.** `UiMessage` = `role`/`content`/`reasoningContent?`/`id?`/`createdAt?` (`chatThreadStorage.ts:8`); `MessageItem` (`conversations_api.py:31`) ohne `type`. `final_message` 0 Treffer. Tool-Daten leben in `AgentTimelineEntry` (`chatThreadStorage.ts:42`). |
| §2.2 | „Web nutzt ähnliche Struktur wie dsh, nur weniger komplexe Expandierung" | **Irreführend in beide Richtungen.** Struktur grundlegend anders (Rolle + parallele Timeline, §1.1). Expandierung ist vorhanden und differenziert (`<details>`, lifted `Set`, Auto-open bei Fehler, §1.3). Die reale Einschränkung ist das notable-Tor (`buildRunCards.ts:313`). |
| §4 Tabelle | „Tool Call Card: Web ❌ Nein" | **Falsch.** `RunCardBlock.tsx` existiert; RunCards mit Titel, Steps, Detail-Zweig. |
| §4 Tabelle | „Tool Result Expandable: Web ✅" | **Nur teilweise.** Nur für notable Tools erreichbar (`buildRunCards.ts:313-318`), und für Top-Level-`tool_done` im First-Party-Chat gar nicht (siehe §5.2). |
| §4 Tabelle | „TUI Tool Call/Result Expandable ✅ (textbasiert)" | **Falsch.** Kein Collapsible, kein Detail-Modal, Output nie im Transcript (§2.3). |
| §3.1.1 | TUI-Zeilen `[USER]` / `[TOOL_CALL]` / `[TOOL_RESULT]` / `[FINAL_MESSAGE]` | **Falsifiziert.** `kind` ist CSS-Klasse (§2.1); User-Zeile nutzt `›` (`app.py:282`). |
| §3.1.2–3.1.3 | `⏺ grep — <desc>`, `⏺ grep ✓ 3 chars 123 ms` | **Korrekt** (`events.py:14-16`, `:131-167`). |
| §1.2.1 | „Search Card" mit Dateibaum, Komprimierung bei 250 Ergebnissen, „2 more in spill file" | **Auf AgentLayer-Seite inexistent.** Kein Spill-File (nur `StatusPill`-Falschtreffer); Kappen siehe §1.6/§2.3. dsh-Seite hier ungeprüft. |
| §6.2 | „State Management: Zustand" | **Nicht vorhanden.** `useSyncExternalStore` auf handgebautem `createLiveTurnStore()` (`useAgentLiveTurn.ts:32`); kein `zustand` in `package.json`. |
| §6.2 | „React (vermutlich)", „Textual" | **Zufällig korrekt** — React 18/Vite/TS/Tailwind, Textual (`app.py:12-17`). |
| §6.3 | „Textbasierte Erweiterung durch Klicks" (TUI) | **Falsch.** Textual-`Static`-Zeilen ohne Klick-Expand; `ALLOW_SELECT` betrifft nur Textauswahl. |
| — | *(in der Vorlage gar nicht erwähnt)* | `agent_log`/Timeline-Architektur, `turnLogs` pro Prompt, notable-Tor,-handler-Divergenz, kein Markdown, Goal/Todos/Plan-Mode-Flächen, Round-Driver. |

---

## 5. Unabhängige Befunde aus dem AgentLayer-Code

### 5.1 Tool-Argumente sind auf dem Draht und werden verworfen

`emit_tool_start_event` schickt neben `summary` (args-Zeile) und `step_label` auch **`wire_arguments`** (Preview) und **`normalized_arguments`** (das vollständige Argument-Dict): `apps/backend/application/agent_runtime/use_cases/chat_tool_events.py:46`, `:48`; Label-Bau über `format_tool_step_label_from_args` (`:35`).

Im Chat-Frontend liest jedoch niemand diese Felder — konsumiert werden `name`, `summary`, `label`, `step_label` (`agentChatWsCore.ts:367-375`, `ChatPage.tsx:2535-2542`, `toolStepLabel.ts:3`). **Beide Felder liegen ungenutzt brach.**

**Wiederverwendungs-Anker vorhanden:** dieselben Felder werden in Admin/Benchmarks bereits dargestellt und exportiert — `pages/admin/AdminBenchmarks.tsx:692-693` (`wire_arguments`), `:705-706` (`result_display`), `features/admin/benchmarks/benchmarksApi.ts:279-281` (Typ), `benchCopyDetails.ts:20-33`, `:201-202`, `benchExport.ts:38-43`, `:154-156`. Format- und Redactionspflege muss also nicht neu erfunden werden.

### 5.2 Zwei parallele WS-Handler — mit echter Divergenz

Es gibt zwei unabhängige Implementierungen der Event-Behandlung:

1. Inline-Kette in `pages/ChatPage.tsx:2127-2700` (First-Party-Chat)
2. `handleAgentWsMessage` in `features/chat/agentChatWsCore.ts:167-465` (via `useAgentChatWs.ts`, genutzt von `features/dashboard/DashboardEmbeddedChat.tsx`)

`ChatPage.tsx` importiert aus `agentChatWsCore` nur `deferredWaitMessage` / `llmSlotWaitMessage`.

**Folge:** `agentChatWsCore.ts:391-393` liest `msg.result_display` und schreibt `resultDisplay`; `ChatPage.tsx` enthält **keine einzige** Referenz auf `result_display`/`resultDisplay`. Der First-Party-Chat zeigt deshalb bei Top-Level-`agent.tool_done` **keinen Command output** — `resultDisplay` kommt dort ausschließlich aus `subagent_step` (`features/chat/subagentActivity.ts:57-59`). Der Embedded-Chat im Dashboard kann es. Das ist ein Verhalten, kein Stilunterschied.

### 5.3 Kein Markdown im Chat

Siehe §1.5. Für Assistanten-Antworten mit Code-Blöcken ist das der sichtbarste Mangel; die Bibliothek ist bereits im Bundle.

### 5.4 `agent.tool_invoke` ohne Frontend-Handler

Client-seitige Workspace-Tools (ADR 0009) sind im **TUI** implementiert (`apps/tui/agentlayer_tui/local_exec.py`, `jail.py`, `events.py:349`), im Web-Frontend gibt es weder Handler noch `tool_result`-Senden. Wer Tool-Details im Web zeigt, erweitert also nur den Server-ausgeführten Pfad.

### 5.5 Doku-Index

`docs/README.md` (Abschnitt *Planning*) listete die drei dsh-/UX-Dossiers nicht — `dsh-agentlayer-capability-comparison.md`, `dsh-integration-plan.md`, `agent-runtime-ux-goal-todos-plan.md` waren Orphan-Seiten. Nach diesem Doc sind sie nachgezogen (`docs/CONVENTIONS.md`: „Prefer fixing broken links over adding new orphan pages"). Für den Chat-Surface existiert insgesamt **kein** `docs/features/chat*.md`.

---

## 6. Was davon übernehmen — priorisiert, Web zuerst

**Bewusst nur Vorschlag, in diesem Doc nicht umgesetzt.**

| P | Was | Warum günstig | Anknüpfungspunkt |
|---|-----|---------------|------------------|
| **P0** | `normalized_arguments` in der RunCard anzeigen (eigenes `<details>` neben „Command output") | Daten sind schon da (§5.1) — kein Backend-, kein DB-Änderung; Redaction folgt dem Result-Pfad | `RunCardBlock.tsx:367-381` (Muster), `:445-452` (Details-Zweig); Admin-Vorbilder `AdminBenchmarks.tsx:692-706`; i18n-Keys in `locales/{en,de}/chat.json` ergänzen |
| **P0** | ChatPage-Inline-`tool_done` auf `result_display` bringen — vorzugsweise durch Konsolidierung auf `agentChatWsCore` statt Nachziehen | behebt §5.2 und die Doppelwartung; ansonsten zwei Orte, die weiter auseinanderlaufen | `ChatPage.tsx:2611` (Handler), `agentChatWsCore.ts:391-421` (Konsolidierungsziel) |
| **P1** | notable-Tor von harter Auswahl auf weiche Präferenz umstellen, damit Everyday-Tools überhaupt eine Karte bekommen | AgentLayer ist Everyday/Knowledge-Produkt; das Tor stammt aus Coding-Zeiten | `buildRunCards.ts:313-318` |
| **P1** | Stille Kappen sichtbar machen: „+N Zeichen" statt verschluckter Rest, mit dem bereits vorhandenen `resultChars` | Nutzer sieht heute nur bei `_tail_for_display` (`…(+N chars)`), sonst nichts | §1.6; `chatThreadStorage.ts:63` (`resultDisplay`), `resultChars` |
| **P2** | Markdown für Assistanten-/Nutzer-Text | eigener Entscheid, nicht von der Vorlage abgeschrieben; `react-markdown` + `remark-gfm` bereits im Bundle | §1.5; `ProposalMessageBody.tsx:134-148`, `UserMessageBubble.tsx:15-35` |
| **P2** | `docs/features/chat-ui.md` als Ist-Referenz anlegen | Chat ist der wichtigste Surface und undokumentiert (§5.5) | Inhalte aus §1–§3 übernehmbar |

## 7. Bewusst nicht übernehmen

- **dsh „Search Card" 1:1.** AgentLayer hat keinen File-Tree-Surface im Chat, und das notable-Tor ist ein anderes Problem als Karten-Layout.
- **Spill-Files.** Erfordert Server-seitiges Ablegen von Tool-Output und einen Abruf-Endpoint — neue Daten- und Retention-Fläche (Secret-Redaction!) für marginale Sicht. Stattdessen §6 P1.
- **`type`-Union mit `final_message`.** Würde `UiMessage` **und** `MessageItem` **und** die Persistenz-Form betreffen (§1.1) und die bestehende Timeline-Spur duplizieren.
- **Detail-Modal im TUI.** Kollidiert mit dem schlanken `Static`-Transcript; `PermissionScreen` ist bewusst das einzige Modal. Wenn überhaupt: `/tool`-Kommando, kein Modal.
- **Markdown im TUI.** `markup=False` (`app.py:190`) ist Absicht — Tool-Output darf nicht als Markup interpretiert werden.
- **dsh-Events/`Surface`-Protokoll.** Passt nicht zu `agent_log` v2 (`{v, current, turns}`); dazu `dsh-agentlayer-capability-comparison.md` Phase 1.

---

## 8. Referenzen

**AgentLayer Web:** `apps/frontend/src/features/chat/` — `chatThreadStorage.ts`, `buildRunCards.ts`, `RunCardBlock.tsx`, `AssistantTurnBlock.tsx`, `ChatInFlightAssistantTurn.tsx`, `ChatLiveActivityPanel.tsx`, `ChatAgentActivityPanel.tsx`, `AgentActivityPanel.tsx`, `MessageTurnActivity.tsx`, `interleavedTurnSegments.ts`, `subagentActivity.ts`, `agentChatWsCore.ts`, `useAgentChatWs.ts`, `useAgentLiveTurn.ts`, `toolStepLabel.ts`, `ProposalMessageBody.tsx`, `UserMessageBubble.tsx`, `conversationsApi.ts`; `apps/frontend/src/pages/ChatPage.tsx`.

**AgentLayer TUI:** `apps/tui/agentlayer_tui/` — `app.py`, `events.py`, `client.py`, `commands.py`, `local_exec.py`, `jail.py`.

**AgentLayer Backend:** `apps/backend/api/chat/controllers/chat_websocket.py`, `apps/backend/api/conversations/controllers/conversations_api.py`, `apps/backend/application/agent_runtime/use_cases/chat_tool_events.py`, `apps/backend/domain/delegation/result_preview.py`, `apps/backend/domain/tools/step_label.py`.

**Vergleich/Planung:** [`dsh-agentlayer-capability-comparison.md`](./dsh-agentlayer-capability-comparison.md) · [`agent-runtime-ux-goal-todos-plan.md`](./agent-runtime-ux-goal-todos-plan.md) · [`dsh-integration-plan.md`](./dsh-integration-plan.md) · [ADR 0008 Client-Contract](../adr/0008-tui-client-contract.md) · [ADR 0009 Client-side Execution](../adr/0009-client-side-execution.md)

**DeepSeek Harness:** *in diesem Doc nicht verifiziert.* Referenzpfad laut `dsh-agentlayer-capability-comparison.md`: `/home/fr4iser/Documents/Git/deepseek-harness-master/` (hier nicht lesbar). Vor dsh-seitigen Schlüssen gegen `packages/…` abgleichen.
