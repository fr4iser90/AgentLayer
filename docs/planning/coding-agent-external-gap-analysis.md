---
doc_id: planning-coding-agent-external-gap
domain: planning
tags: [planning, coding-agent, external-comparison, parity, system-prompt, memory, tools, permissions, permission-ask]
---

# AgentLayer Coding-Agent: Gap-Analyse vs. externes Referenzprodukt

Dieses Dokument beschreibt das Produktmodell eines **externen Referenzprodukts** (primär aus dem offiziellen [Agents-Dokument](https://opencode.ai/docs/agents) und dem [GitHub README](https://github.com/anomalyco/opencode)) und **AgentLayers** aktuelles Verhalten (Codepfad `apps/backend/domain/agent.py`, Registry, Plugins, Web-UI). Ziel ist ein **vollständiger Scope** für spätere Umsetzung: gleicher *Ablauf* wie dort beschrieben heißt hier **funktional äquivalente Nutzererfahrung** (Build/Plan, Subagents, Permissions, Schritte, Memory), nicht identische Implementierung.

**Hinweis zur Wartung:** Das externe Referenzprodukt entwickelt sich schnell; Verweise auf externe URLs und Konfigurationsschemas können sich ändern. AgentLayer-interne Pfade beziehen sich auf den Stand des Repos zum Zeitpunkt der Erstellung dieses Dokuments.

---

## 1. Executive Summary

| Thema | Referenz (extern) | AgentLayer (Ist) | Parität / Risiko |
|--------|-----------|------------------|------------------|
| **Primär-Agenten** | `build` (Standard), `plan` (read-only + ask für bash/edit); Tab-Wechsel, festes UX-Muster | `general`, `coding`, `coding_plan`, … über Registry + UI; Coding-Seite sendet jetzt `agent_id: "coding"` | **Teilweise:** Coding ≈ Build, coding_plan ≈ Plan; UX-Wechsel nicht Tab-identisch |
| **Subagents** | `general`, `explore`, `scout` + `@mention`, Child-Sessions, Task-Permissions | `task` + `run_plan_subagent`, eingebetteter `coding_plan`-Lauf | **Lücken:** kein `@explore`/`@scout`-Äquivalent, keine gleiche Session-Hierarchie-Navigation |
| **Permissions** | Granular `allow` / `ask` / `deny` pro Permission-Key (edit, bash, grep, …), inkl. Bash-Globs | Capability-Governance, Tool-Allowlists, `bash`-Blocklists, Workspace-Gates | **Unterschiedlich:** kein UI-native „ask before bash“ wie im Plan-Modus des Referenzprodukts |
| **Schritte / Kosten** | `steps` pro Agent dort, sonst Modell stoppt | `AGENT_MAX_TOOL_ROUNDS` (Default in Config oft 8; Betreiber können höher setzen — z. B. 20) + Rescue-Completion | **Anpassbar,** Semantik ≠ `steps` dort |
| **Memory / Kontext** | Eigene Hidden Agents (`compaction`, `title`, `summary`) | `AGENT_SYSTEM_PROMPT`, User-Persona, Dashboard-Kontext, **User-Memory-Snippet** aus DB, `.agentlayer.json`-Hinweise | **Teilweise:** kein automatisches Compaction-Agent-Äquivalent |
| **LSP** | Explizit im Permission-Modell | `lsp` Tool + Index/Symbole | **Funktional ähnlich**, anderes API-Modell |
| **MCP** | Permission-Globs für `mymcp_*` | Roadmap / Platzhalter | **Lücke** |

**Kernbotschaft:** Derselbe **Nutzer-Prompt** führt **nicht** automatisch zum gleichen Verhalten; erst wenn **Agent-ID**, **Tool-Allowlist**, **Systemprompt-Kette**, **Modell** und **Limits** vergleichbar sind, nähert sich das Ergebnis an. Ein konkreter Produktions-Fehler war: Coding-Web-UI ohne `agent_id` → falsche Tool-Mischung (Introspection-Tools bei `TOOL_DOMAIN`‑Fallback) + fehlender Coding-Systemprompt.

---

## 2. Referenzmodell: externes Terminal-Coding-Produkt

### 2.1 Produktpositionierung (README)

- **Open source** Coding-Agent mit Fokus auf **TUI** und optional **Desktop**; **Client/Server** (TUI nur ein Client).
- **Zwei eingebaute Primary-Agenten:** `build` (voller Zugriff), `plan` (Analyse, standardmäßig ask für file edits & bash).
- **Subagent `general`** (`@general`) für komplexe/mehrstufige Aufgaben.
- **Provider-agnostisch** (Zen empfohlen, aber Claude/OpenAI/Google/lokal).
- **LSP** als eingebautes Feature (README).

### 2.2 Agenten-Architektur (öffentliche Agents-Doku)

**Primary vs Subagent**

- **Primary:** Hauptkonversation; Wechsel per Tab / Keybind; Permissions steuern Toolzugriff.
- **Subagent:** per `@` oder automatisch; **Child-Sessions** mit Navigation (`session_child_first`, Cycle, Parent).

**Eingebaute Agenten (Auszug)**

| Agent | Modus | Rolle |
|--------|--------|--------|
| **build** | primary | Standard-Entwicklung, volle Tools |
| **plan** | primary | Analyse/Plan; file edits & bash default **ask** |
| **general** | subagent | Forschung, mehrstufig, volle Tools (außer todo laut Doku) |
| **explore** | subagent | Schnell, read-only, Codebase-Erkundung |
| **scout** | subagent | Read-only, externe Deps/Docs, managed cache |
| **compaction** | primary (hidden) | Kontext komprimieren, automatisch |
| **title** | primary (hidden) | Session-Titel |
| **summary** | primary (hidden) | Zusammenfassungen |

**Konfiguration**

- JSON (`opencode.json`) oder Markdown unter `~/.config/opencode/agents/` bzw. `.opencode/agents/`.
- Pro Agent: `description`, `mode`, `model`, `temperature`, `steps` (max agentische Iterationen), `permission`, `prompt` (Datei), `top_p`, Provider-Extras.

**Permissions (Referenz-Stack)**

- Werte: `allow`, `ask`, `deny`.
- Keys u. a.: `read`, `edit`, `glob`, `grep`, `list`, `bash`, `task`, `external_directory`, `lsp`, `webfetch`, `websearch`, …
- Bash kann mit **Globmustern** fein justiert werden (`git log*` allow, `*` ask).

**Max steps**

- Feld `steps`: harte Obergrenze für Agent-Schritte; bei Limit spezielles System-Signal + Zusammenfassung / restliche Aufgaben (laut Doku).

---

## 3. Ist-Zustand: AgentLayer (intern)

### 3.1 Einstiegspunkte

| Pfad | Beschreibung |
|------|----------------|
| HTTP | `POST /v1/chat/completions` (`apps/backend/api/main.py`) |
| WebSocket | `/ws/v1/chat` (`apps/backend/api/chat_websocket.py`) |
| Agent-Definitionen | `plugins/agents/*.py` + `apps/backend/domain/agent_registry.py` (`AGENT_TOOL_MAP`, optional `AGENT_TOOL_NAMES`) |
| Tools | `plugins/tools/**` mit `TOOLS` / `HANDLERS`, Registry-Scan |

### 3.2 Reihenfolge der **Message- und Kontext-Injektion** (`chat_completion`)

Relevant für „fühlt sich wie Referenzprodukt an“: **dieselbe Reihenfolge** beeinflusst, was das Modell zuerst „sieht“.

Ablauf (vereinfacht, siehe `agent.py`):

1. `messages` aus Request-Body kopieren.
2. `max_tool_rounds_eff` aus `AGENT_MAX_TOOL_ROUNDS` und optionalem Body `agent_max_tool_rounds` (geclamped).
3. **`_inject_system_prompt`** — hängt `AGENT_SYSTEM_PROMPT` (Env) an erste System-Message.
4. **`_inject_dashboard_context`** — wenn `agent_dashboard_context` mit gültiger Dashboard-ID.
5. **`_inject_agent_system_prompt`** — **nur wenn `agent_id` gesetzt** und Agent in Registry; sonst **kein** Agent-Prompt.
6. Optional **`tool_prefetch`** (Client-Hint).
7. **`apply_user_persona_system`** — Nutzer-Persona / Profil (Settings).
8. **`_inject_user_memory_context`** — Memory-Graph/Facts aus DB, abhängig von letztem User-Text und optional `dashboard_id`.
9. **`_inject_workspace_dot_agentlayer_hints`** — read-only Hinweise aus `{workspace}/.agentlayer.json`.
10. Modellauflösung, LLM-Transport (Ollama / external / llama.cpp je nach Routing).
11. Tool-Merge und Filter: Kategorien → optional **`agent_id`** (Domain + explizite Namensliste) → Capability-Hints → Denylist / Prefetch.
12. Wenn Tools aktiv: **`_append_tool_usage_discipline`** (im Stil gängiger TUI-Agenten Kurzdisziplin im Systemtext).

**Konsequenz:** Fehlt `agent_id`, fehlen Agent-Prompt **und** (bei nur `TOOL_DOMAIN`) kann die Tool-Pipeline **andere** Tools exposieren als bei expliziter Registry-Allowlist.

### 3.3 Tool-Domain und Introspection (`tool_routing.py`)

- `filter_merged_tools_by_domain` sammelt alle Tools mit `domain == <requested>` **oder** `domain == shared`, und **fügt immer** `TOOL_INTROSPECTION` hinzu:
  - `list_available_tools`, `get_tool_help`, `list_tool_categories`, `list_tools_in_category`.
- **Wenn** `agent_id` gesetzt ist und der Agent eine **explizite** `tool_names`-Liste hat (aus Registry), wird **danach** auf genau diese Namen gefiltert — die Introspection-Tools fallen typischerweise **raus**, wenn sie nicht in der Allowlist stehen (Coding-Agent).

### 3.4 Coding vs Coding-Plan (Registry)

- **`coding`:** `AGENT_TOOL_DOMAIN = "coding"`, Workspace Pflicht, Prompt in `plugins/agents/coding.py`; Tool-Liste über `AGENT_TOOL_MAP` (`coding.*` + Factory-Tools + `project_explain` etc.).
- **`coding_plan`:** Read-only-Exploration, eigene Allowlist (`AGENT_TOOL_NAMES` in `coding_plan.py`).

### 3.5 Subagent / Plan bei AgentLayer

- **`task`** kann einen eingebetteten `coding_plan`-Lauf auslösen (`run_plan_subagent`), inkl. Parent/Child-Run-IDs und Cancel-Propagation (siehe Tests und `agent.py`).
- **Unterschied zu Referenzprodukt:** keine TUI-Navigation zwischen Parent/Child-Sessions; kein `@explore` / `@scout` als erste Klasse.

### 3.6 Limits und Abbruch

- **`AGENT_MAX_TOOL_ROUNDS`** (`config.MAX_TOOL_ROUNDS`): harte Obergrenze für Tool-Runden; bei Erreichen Rescue-Completion mit Systemhinweis (`agent.py` Ende der Tool-Schleife).
- **Cancel:** WebSocket `cancel`, `cancel_event` zwischen Tools.

### 3.7 Transportfehler und UX

- `apps/backend/infrastructure/llm_user_errors.py`: mappt `httpx`-Timeouts etc. auf **verständliche** Nutzer- und Log-Meldungen (WebSocket + HTTP Chat).

---

## 4. Dimensionen-Vergleich (Detail)

### 4.1 Primary: Build ↔ Coding

| Aspekt | Referenzprodukt `build` | AgentLayer `coding` |
|--------|------------------|----------------------|
| Ziel | Voller Dev-Flow im Repo | Workspace-gebundenes Editieren + Shell + Index |
| Prompt | Konfigurierbar (`prompt` Datei) | `AGENT_SYSTEM_PROMPT` in `plugins/agents/coding.py` + globales `AGENT_SYSTEM_PROMPT` |
| Tools | Permissions-first (`allow`/`ask`/`deny`) | Allowlist + Domain + Capabilities + Blocklists (bash) |
| UI-Contract | TUI / Desktop | Web Coding Page + ggf. Chat |

**Paritätslücken:** Referenzprodukt **ask**-Workflow pro Bash/Edit; AgentLayer hat **kein** natives Approval-UI pro Toolcall (außerhalb von Produkt-Features wie Step-Wait / externen Policies).

### 4.2 Primary: Plan ↔ coding_plan

| Aspekt | Referenzprodukt `plan` | AgentLayer `coding_plan` |
|--------|-----------------|----------------------------|
| Writes | default ask → effektiv keine silent writes | keine Write-Tools in Allowlist |
| Bash | default ask | kein Shell-Tool in Allowlist |
| UX | Tab zu Plan wechseln | Agent-Auswahl in UI / Subagent |

### 4.3 Subagents

| Referenz (extern) | AgentLayer-Äquivalent / Status |
|----------|-------------------------------|
| `general` | `task` + LLM-orchestrierte Tool-Schleifen; kein `@general` |
| `explore` | `coding_plan` + `search` / `glob` / `git_read`; kein dedizierter „Explore“-Agent |
| `scout` | Teilweise `semantic_search` / externe Tools; kein „managed dependency cache“ wie beschrieben |
| Child sessions | Explizite Session-Baum-Navigation | Konversationen + eingebetteter Plan-Subagent ohne TUI-Navigation |

### 4.4 Hidden system agents (compaction, title, summary)

| Feature | Referenz (extern) | AgentLayer |
|---------|----------|------------|
| Kontext-Kürzung | `compaction` Agent | **Nicht** als eigener Agent; ggf. Modell/Truncation extern |
| Titel | `title` Agent | Conversation-Titel aus erster User-Message / API |
| Summary | `summary` Agent | Kein automatischer Summary-Agent; optional Memory / manuelle Flows |

**Roadmap-Idee:** optionale Hooks: nach N Tokens System-„compact“-Round, Titel-Agent-Call, etc. (aufwändig).

### 4.5 Memory

| Referenz (Doku) | AgentLayer |
|-----------------|------------|
| Session-spezifische Hidden Agents für Summary/Compaction | `_inject_user_memory_context`: Fakten + Graph-Snippet aus DB, getriggert durch letzten User-Text; Dashboard-scoped wenn `dashboard_id` |
| Konfigurierbar pro Projekt | Operator + User Secrets + DB |

**Parität:** unterschiedliche **Semantik** (Referenzprodukt eher Session-Lifecycle; AgentLayer eher persistente User-Memory + Dashboard).

### 4.6 LSP

| Referenz (extern) | AgentLayer |
|----------|------------|
| Permission-Key `lsp` | Tool `lsp` + Index/Symbole |
| Opt-in LSP | vorhanden, aber anderes Konfigurationsmodell |

### 4.7 MCP

| Referenz (extern) | AgentLayer |
|----------|------------|
| Permissions mit `mymcp_*` Globs | MCP in Produkt-Roadmap / IDE-Placeholder; keine volle Parität |

### 4.8 Client/Server und Worktree

| Referenz (extern) | AgentLayer |
|----------|------------|
| Explizite Client/Server-Trennung, lokaler Worktree | Backend + Browser; Workspace-Pfade in DB + Container |

---

## 5. Gap-Analyse nach Priorität

### P0 — Korrektheit / „Agent tut offensichtlich Falsches“

1. **Coding:** Jeder Einstieg, der **Coding im Workspace** meint, muss `agent_id: "coding"` + Workspace mitschicken (**CodingAgentPage:** erledigt). Separat (kein Coding-DoD): generischer Chat / Dashboard-Assistent kann anderen `agent_id` oder Router-Logik nutzen — nicht mit Referenzprodukt-**build** verwechseln.
2. **`TOOL_DOMAIN` allein** für Coding vermeiden, wenn Registry-Agent existiert (Dokumentation + Lint in UI).
3. **Schwache Modelle:** Introspection-Tools nicht anbieten, wenn `agent_id` ohnehin explizit ist (bereits durch Allowlist); zusätzlich **Router-Hints** oder Modell-Profile „small“ mit kürzerer Toolliste erwägen.

### P1 — Ablauf-Parität zu Referenzprodukt (Build/Plan)

1. **Tab- oder Toggle-UX:** schneller Wechsel Coding ↔ coding_plan in **derselben** Session ohne Kontextverlust (heute: Agent-Wechsel im Dropdown).
2. **Plan-Modus:** Bash/Edit explizit „deny“ auf UI-Ebene + klare Copy (wie Referenzprodukt Plan).
3. **`steps`‑Semantik:** Referenzprodukt `steps` dokumentieren und mit `AGENT_MAX_TOOL_ROUNDS` + UI-Slider alignen; bei Limit **einheitliche** Nutzer-Nachricht (nicht nur Rescue).

### P2 — Subagents & Sessions

1. **`@explore` / `@scout`‑Äquivalente** als Registry-Agents oder feste Subagent-Tools mit festem Tool-Budget.
2. **Sichtbare Child-Runs** in UI (Run-ID, Parent, Link zum eingebetteten Plan-Output) — heute teils in Logs / Tool-JSON.
3. **Task-Permission-Matrix** wie Referenzprodukt (`permission.task` Globs) für `task`-Ziele.

### P3 — Permissions „ask“

1. Pro-Tool oder pro-Bash-Pattern **Approval-Queue** im Web (großer UX-/Backend-Aufwand).
2. Bis dahin: **Step-Wait** (`agent_pause_between_rounds`) als Operator-Kompromiss ausbauen.

### P4 — Hidden lifecycle agents

Compaction / Title / Summary als **konfigurierbare** Hintergrund-Jobs (Cron oder post-round).

---

## 6. Zielbild: „Gleicher Ablauf wie Referenzprodukt“ (funktional)

Dieser Abschnitt definiert **Akzeptanzkriterien**, nicht Implementierung.

### 6.1 Session starten

- Nutzer wählt explizit **Build**-Äquivalent (`coding`) mit gebundenem Workspace.
- System injiziert **Coding-Agent-Prompt** + globale Disziplin + Workspace-Hints + optional Memory.
- Toolliste = **nur** Coding-relevante Tools (keine Registry-Browser).

### 6.2 Plan phase

- Ein Klick / Tab auf **Plan**-Äquivalent (`coding_plan`): gleiche Konversation oder verknüpfte Ansicht, **keine** Write-Tools, keine Shell.
- Optional: gleiches Modell wie Build oder kleineres (Referenzprodukt macht das pro Agent).

### 6.3 Ausführung

- Modell wählt direkt `read_file` / `list_dir` / `write_file` / Patch-Tools.
- Bei unsicherem Bash: entweder **deny** (Plan) oder **ask** (wenn P3 umgesetzt) oder dokumentierte Safe-Commands.

### 6.4 Subagent

- Nutzer oder Build-Agent startet **Explore**-Pass (read-only, begrenzte Runden) → strukturiertes Ergebnis zurück in Hauptthread (wie Referenzprodukt Child-Session, minimal: zusammengefasster Tool-Recap + Attachment).

### 6.5 Lange Chats

- Automatische oder manuelle **Compaction** unter konfigurierbarer Token-Schwelle.

### 6.6 Fehler

- Timeouts / Netzwerk: **verständliche** Meldung (bereits `llm_user_errors`).

---

## 6b. Referenzprodukt — Monorepo- und Laufzeit-Analyse (Branch `dev`, Quell-Recherche)

> **Methode:** GitHub [Contents API](https://api.github.com/repos/anomalyco/opencode/contents/packages?ref=dev) + Rohdateien von  
> `https://raw.githubusercontent.com/anomalyco/opencode/dev/...`  
> Kein vollständiger lokaler Clone dieses Repos in der Analyse-Session — für PR-Level-Ports soll ein Entwickler `anomalyco/opencode` lokal klonen und in `packages/opencode` iterieren.

### 6b.1 Paket-Landschaft (`packages/`)

| Paket | Rolle (Kurz) |
|--------|----------------|
| `packages/opencode` | **Kern des Agent-Runtimes:** Session, Agent, Tool, Permission, Processor |
| `packages/core` | Shared Infrastruktur (`aisdk`, `filesystem`, `catalog`, Effect-Helfer, Flags, …) |
| `packages/llm` | Provider-/Modell-Schicht |
| `packages/console`, `app`, `web`, `ui`, `desktop` | Clients (TUI/Web/Desktop) |
| `packages/sdk` | SDK-Generierung (vgl. `AGENTS.md` im Upstream-Repo) |
| `packages/plugin`, `function`, `containers` | Erweiterungen / Deployment |
| `packages/http-recorder`, `identity`, `slack`, `enterprise` | Randprodukte |

**Konsequenz:** Verhalten „wie Referenzprodukt“ ist **nicht** nur Prompting — es hängt an **`packages/opencode/src/session/processor.ts`** und **`packages/opencode/src/tool/*`**. AgentLayer-Äquivalente Schicht bleibt **`chat_completion`** in `agent.py` plus Plugin-Tools.

### 6b.2 Session-Processor (Harness)

**Pfad:** `packages/opencode/src/session/processor.ts`

Aus der Rohdatei (Auszug der Architektur-Signale):

- **`DOOM_LOOP_THRESHOLD = 3`** — explizite Erkennung von „hängenden“ Wiederholungen, unabhängig von einem globalen `maxSteps`.
- **`Result = "compact" | "stop" | "continue"`** — der Steuerfluss kennt **Compaction** als erstklassiges Ergebnis.
- **Effect / `Layer.effect`** — Abhängigkeiten: `Session`, `Config`, `Bus`, `Snapshot`, **`Agent`**, `LLM`, **`Permission`**, `Plugin`, `SessionSummary`, `SessionStatus`, `SyncEvent`, …

**AgentLayer:** Tool-Runden, Trashing, Rescue-Completion und Cancel liegen in **`apps/backend/domain/agent.py`**; ein dedizierter **Compaction**-Pfad wie das dortige `compact`-Ergebnis gibt es **nicht** in gleicher Form.

### 6b.3 Task-Tool und Child-Sessions

**Pfad:** `packages/opencode/src/tool/task.ts`

Wesentliche Mechanik (aus Rohdatei):

- Tool-ID **`task`**; Parameter u. a. `description`, `prompt`, `subagent_type`, optional `task_id` (**Resume** derselben Subagent-Session).
- Vor Ausführung: **`ctx.ask({ permission: "task", patterns: [subagent_type], ... })`**, sofern kein `bypassAgentCheck` — **Ask ist im Tool-Executor** verankert, nicht nur in der Systemnachricht.
- **`sessions.create({ parentID, title, permission: [...] })`** — Child-Session; `permission` wird aus **`deriveSubagentSessionPermission`** + optionalen experimentellen `primary_tools`-Overrides zusammengesetzt.
- Beim Prompt der Kind-Session werden **Tool-Flags** gesetzt (u. a. `task: false`, `todowrite: false`), damit der Subagent **nicht rekursiv** denselben Task-Spawn pflegt.

**AgentLayer:** `task` + `run_plan_subagent` nähert sich dem, fehlt aber: **einheitliches Session-Objekt mit Parent/Child**, **Permission-Ask im Tool-Pfad**, **explizites Resume-Modell** (`task_id`), **automatisches Rekursions-Gating** auf derselben Ebene.

### 6b.4 Tool-Registry (Referenzprodukt)

**Pfad:** `packages/opencode/src/tool/` (Directory)

First-Class-Tools inkl. Prompt-Textdateien (`.txt`): u. a. `read`, `write`, `edit`, `apply_patch`, `glob`, `grep`, `shell`, `lsp`, `webfetch`, `websearch`, **`task`**, **`plan`**, `question`, `repo_clone`, `repo_overview`, `skill`, …

**AgentLayer:** Funktional ähnliche Fähigkeiten über **`coding_*`**, `fs_*`, `github_*`, … — **andere Namen/Schemas**; identische **User-Prompts** führen ohne Mapping-Schicht **nicht** garantiert zu denselben Tool-Calls.

### 6b.5 Tests / Harness (Upstream-Repo-Kultur)

**Pfad:** `AGENTS.md` (Repo-Root)

- Tests **nicht** vom Repo-Root; z. B. aus `packages/opencode` mit `bun typecheck` / paketlokalen Befehlen.
- Starke Nutzung von **Bun**, **Effect**, parallelen Tools wo sinnvoll.

**AgentLayer:** `pytest` + eigene Plugin-Disziplin — Build-Harness ist anders; Parität betrifft **Produktverhalten**, nicht identisches Test-Runner-Setup.

---

## 6c. Definition of Done — wann ist „wie Referenzprodukt“ erreicht?

**Geltungsbereich:** Die Tabelle unten gilt für **Funktions-Parität des Coding-Agents** (`coding` / `coding_plan`, Workspace-gebunden) — vergleichbar mit Referenzprodukt **build / plan / task** im Repo-Kontext. **Nicht** Teil dieses DoD: der generische **Dashboard-Assistent** (`DashboardEmbeddedChat`, Multimodal-Chat mit `agent_dashboard_context` ohne Repo-Workspace); das ist ein anderes UI-Szenario und kein Ersatz für die Coding-Seite.

Alle der folgenden Kriterien müssen **erfüllt** sein (oder im selben Dokument als **„Won’t do“** mit Begründung festgehalten werden):

| # | Kriterium | AgentLayer-Ist (Kurz) |
|---|-----------|------------------------|
| D1 | **Coding-Build** (`coding`): alle **Coding**-Einstiege senden zuverlässig `agent_id: "coding"` **und** gültigen Workspace-Kontext (wie Referenzprodukt build im Worktree) | **CodingAgentPage** (Web): ja (`agent_id: "coding"`). Offen: jeder **weitere** Einstieg, der denselben Agent fahren soll (z. B. mobiles Coding, dedizierte API-Clients) — **nicht** der Dashboard-Allgemein-Chat |
| D2 | **Plan-Session** = Primary read-only + **keine** Write/Bash-Tools + klare Nutzer-Kopie | `coding_plan` existiert; Tab-/Toggle-UX fehlt |
| D3 | **Subagent/Task** mit **Parent/Child**-Nachweis, **Resume-ID**, **Anti-Rekursion** (Task/Task) | `task`/Plan: teilweise; kein Referenzprodukt-`task_id`-Modell |
| D4 | **Permissions `ask`** mindestens für **edit** + **bash** (UI-Approval) | Fehlt (nur Allowlist/Capabilities) |
| D5 | **Doom/Stuck** — Schranke vergleichbar Referenzprodukt `DOOM_LOOP_THRESHOLD` oder nachweislich äquivalent | `AGENT_TOOL_THRASH` existiert; Semantik ≠ 1:1 |
| D6 | **Compaction** — konfigurierbar, bevor Kontext „hart“ bricht | Kein eigenes Compaction-Agent-Äquivalent |
| D7 | **Messbar:** Median Tool-Runden für Referenz-Tasks (README-Edit, „finde Symbol X“) ≤ vereinbartes Budget mit gleichem Modellprofil | Nicht gemessen |

Solange **ein** Kriterium offen ist: Ziel **nicht** erreicht.

---

## 6d. Referenzprodukt — Permission-Service (Quelle: `permission/index.ts`)

**Pfad:** `packages/opencode/src/permission/index.ts` ([Rohdatei auf `dev`](https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/permission/index.ts))

Das ist die **technische** Grundlage hinter der Doku-Zeile „`allow` / `ask` / `deny`“ — nicht nur Konfiguration, sondern ein **laufzeitfähiger** Entscheidungsbaum:

| Baustein | Referenzprodukt (Implementierung) |
|----------|----------------------------|
| Aktionen | `Action = "allow" \| "deny" \| "ask"` |
| Regeln | `Rule { permission, pattern, action }` in einem **Ruleset** (Array); Auswertung über `evaluate(permission, pattern, ...rulesets)` inkl. Wildcards |
| `ask` | Wenn für **kein** Muster ein klares `allow` reicht und **kein** `deny` greift → `needsAsk`; Request bekommt ID, landet in `pending`, **`Bus.publish(permission.asked)`**, Effect wartet auf `Deferred` |
| Nutzer-Antwort | `Reply = "once" \| "always" \| "reject"`; optional `message` (Feedback → `CorrectedError`) |
| `always` | Patterns aus `existing.info.always` werden ins persistente **`approved`**-Ruleset (DB-Zeile `PermissionTable`) als `allow` nachgetragen |
| `reject` | Aktueller Request **und** alle anderen **pending** derselben `sessionID` werden abgelehnt (Kaskade) |
| Edit-Tools | `EDIT_TOOLS = ["edit", "write", "apply_patch"]` → Permission-Key **`edit`** für Tool-Disable-Logik (`disabled()`), nicht nur pro Tool-Name |

**AgentLayer-Gegenüberstellung:** Governance läuft über **Tool-Allowlists**, Domains, Capabilities und Bash-Blocklists — es gibt **keine** vergleichbare **suspend-until-user-replies**-Schicht pro Toolcall mit Bus-Events und persistiertem „always allow this pattern“. Das erklärt, warum **D4** (UI-`ask` für edit/bash) ein eigenes Backend- und Frontend-Feature ist, nicht „nur“ ein JSON-Flag wie bei Referenzprodukt-Agents.

**Konsequenz für Parität:** Ein AgentLayer-„ask“-MVP sollte sich an **diesem** Modell orientieren (Request-ID, pending queue, `once`/`always`/`reject`, optional Session-Kaskade bei Reject), statt nur ein modales „OK“ ohne Regel-Fortschreibung.

---

## 7. Umsetzungs-Roadmap (Vorschlag, mehrere Iterationen)

### Phase A — Korrektheit (kurz)

- [x] Coding Web: `agent_id: "coding"` (bereits umgesetzt).
- [ ] Audit **Coding-Pfade:** alle Einstiege, die Repo-Workspace-Coding auslösen (`CodingAgentPage`, ggf. WS/API/mobile), auf `agent_id: "coding"` + Workspace. (Generischer `ChatPage` / Dashboard-Chat: eigene Produktregeln, **kein** Blocker für dieses Gap-DoD.)
- [ ] Dokumentation für Betreiber: `AGENT_MAX_TOOL_ROUNDS`, Modellwahl, Proxy-Timeouts.
- [ ] Optional: Referenzprodukt lokal klonen (`dev`) und `packages/opencode/src/session/processor.ts` + `tool/task.ts` beim Debuggen offen legen.

### Phase B — UX-Parität Build/Plan

- [ ] Coding-UI: prominenter **Plan**-Toggle (wechselt Agent + erklärt read-only) — funktionales Äquivalent: Tab zwischen `build` / `plan`.
- [ ] Einheitliche Copy für `max_tool_rounds` / Rescue (Nutzer versteht, was passiert ist); optional UI-Anzeige des Limits wie Referenzprodukt `steps`.

### Phase C — Subagents

- [ ] Expliziter **Explore**-Agent (read-only, festes Tool-Budget) + UI-Einstieg — Upstream-Referenz: Subagent `explore`.
- [ ] Scout-ähnlicher Pfad für „externe Doku“ (optional Web/MCP später) — Referenzprodukt: `scout`.
- [ ] `task` um **Resume-Identität** + **Parent-Run-Transparenz** erweitern (Vergleich `task_id` in Referenzprodukt `task.ts`).

### Phase D — Permissions

- [ ] Design-Dokument für „ask“ + UI-Mock; Implementierung in Schichten (nur Bash zuerst) — Upstream-Referenz: `ctx.ask` in `tool/task.ts`, **Permission-Service** in `permission/index.ts` (§6d), Permission-Tabelle in [Agents-Doku](https://opencode.ai/docs/agents).

### Phase E — Lifecycle

- [ ] Optional: Background-Compaction, auto title/summary Jobs — Upstream-Referenz: `session/compaction.ts`, Hidden Agents in Doku.

### Phase F — Stuck-Erkennung / Processor-Parität

- [ ] Abgleich `DOOM_LOOP_THRESHOLD` (Referenzprodukt `processor.ts`) mit `AGENT_TOOL_THRASH_*` — Lücken dokumentieren, ggf. zweite Schranke ergänzen.
- [ ] Architektur-Entscheid: bleibt eine große `chat_completion`-Schleife oder Auslagerung in „SessionProcessor“-Modul (nur interner Name, kein Framework-Zwang).

---

## 8. Anhang

### 8.1 Relevante Dateien (nicht abschließend)

| Bereich | Dateien |
|---------|---------|
| Chat-Kern | `apps/backend/domain/agent.py` |
| Tool-Routing | `apps/backend/domain/plugin_system/tool_routing.py` |
| WS / HTTP | `apps/backend/api/chat_websocket.py`, `apps/backend/api/main.py` |
| LLM-Fehler | `apps/backend/infrastructure/llm_user_errors.py` |
| Coding-Agent | `plugins/agents/coding.py`, `plugins/agents/coding_plan.py` |
| Registry | `apps/backend/domain/agent_registry.py` |
| Config | `apps/backend/core/config.py`, `.env.example` |

### 8.2 Umgebungsvariablen (Auszug)

- `AGENT_MAX_TOOL_ROUNDS` — harte Tool-Runden-Obergrenze (Server).
- `AGENT_SYSTEM_PROMPT` — globaler Zusatz-Systemprompt.
- LLM-URLs / Timeouts — siehe `.env.example` und Runbooks.

### 8.3 Externe Referenzen

- Upstream-Repo (extern): https://github.com/anomalyco/opencode
- Öffentliche Agents-Doku (extern): https://opencode.ai/docs/agents
- Rohcode (Beispiele, extern):
  - `https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/processor.ts`  
  - `https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/tool/task.ts`  
  - `https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/permission/index.ts`  
- AgentLayer Coding-Roadmap (bestehend): `docs/planning/coding-agent-roadmap.md`

---

## 9. Mehrere Sessions / Wartung dieses Dokuments

Dieses Dokument ist bewusst **lang** und als **Single Source of Truth** für die Funktions-Paritäts-Diskussion gedacht. Änderungen am Verhalten von `chat_completion`, neuen Agents oder Permission-UX sollten hier in **Abschnitt 3 / 5 / 6b–6d / 7** nachgezogen werden.

**Changelog (intern):**

- Ergänzung **§6b–6c**: Quell-Recherche Referenzprodukt `dev` (Processor, Task-Tool, Paketliste), **Definition of Done**-Tabelle, Roadmap-Phasen F.
- Ergänzung **§6d**: Referenzprodukt `permission/index.ts` (allow/ask/deny, Bus, once/always/reject, Mapping edit/write/apply_patch → `edit`).
- **§6c / P0 / Phase A:** Geltungsbereich **Coding-Agent** vs. Dashboard/generischer Chat klar getrennt (Dashboard ist kein Coding-Build-Einstieg).

Wenn der Umfang unhandlich wird:

- Option A: Abschnitte 6b+ in `docs/planning/reference-upstream-source-digest.md` auslagern und hier nur Summary + Links.
- Option B: Versionierung im Titel (`… analysis v2`).

---

*Ende Dokument.*
