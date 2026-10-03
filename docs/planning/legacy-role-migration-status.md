---
doc_id: legacy-role-migration-status
domain: agentlayer_docs
tags: [planning, rbac, site-role, legacy-column, security, handoff]
status: in-progress
---

# Legacy-Rollen-Migration — vollständige Aufgabe, Stand, Restarbeit

**Record, kein lebendes Dokument.** Snapshot **02.10.2026, 22:15**, fortgeschrieben **02.10., 23:14**
(Commit des Blocks + Tooling-Commit, Abschnitt A), **02.10. ab 23:40 / 03.10. bis 00:04** (Familie 6 =
Task-Freigabe geschlossen, committet 03.10. 00:01), **03.10. bis 13:55** (Familie 5 = Dashboards
geschlossen) und **03.10. 15:2x–15:3x** (Familie 5: alle fünf Mutationen mit Testnamen nachgemessen,
Rest-Metrik neu gezählt, Precommit gelaufen — **rot durch `node_cve_full`, Commit deshalb ausstehend**,
Abschnitt D), **03.10. ab 16:0x** (auf Entscheidung des Owners: `tailwindcss` 3→4 als eigener Schwung —
das Gate ist damit wieder grün, Abschnitt D) **und 03.10. 16:5x–17:0x** (Familie 5 committet,
Tailwind-Schwung committet). Quelle: Session
`9910e7a2-88ab-4521-9d46-d96dd404d97d` (28.09. 19:52 → 02.10. 20:12, 5 843 Records, beim Commit
abgebrochen) **plus** Live-Messung im Working Tree am 02.10. Jeder Hacken unten ist entweder durch
Code/Command belegt oder als *nicht nachgemessen* gekennzeichnet.

Maßgeblich für den Auftrag bleibt [`ADR 0011`](../adr/0011-roles-and-agent-access-without-tenancy.md)
§1 und [`docs/security/rbac.md`](../security/rbac.md); für den Konsolen-Teil
[`features/operator-agent.md`](../features/operator-agent.md). Dieses Dokument ergänzt nur: **was noch
nicht getan ist**.

---

## 1. Die eigentliche Aufgabe

`users.site_role` ist die **einzige** Quelle für Elevation. `users.role` ist eine
Kompatibilitätsspaltte, die noch da ist, damit alte Auslieferungen nicht brechen — sie darf **keine
Berechtigung mehr entscheiden**.

Die Aufgabe: **jede Stelle, die aus `users.role` (bzw. `db.user_role()`) eine Berechtigung ableitet,
auf die kanonische Quelle umstellen** — und zwar so, dass ein Rückfall nicht versehentlich
wiederkommt (Test, der eine Legacy-Lesstelle in den betroffenen Dateien per Source-Scan ablehnt).

Warum das eine Sicherheitsaufgabe ist und kein Aufräumen: die Spalte wird beim Herabstufen **nicht**
mitgezogen. Ein Account mit `site_role='site_user'` kann in `users.role` weiter `admin` stehen haben
und behält dann genau die Rechte, die ihm der Site-Admin gerade aberkannt hat. Der Fehler läuft auch
in die andere Richtung (Verfügbarkeit): ein `site_admin`, der aus der Zeit vor der Spalte nur
`role='user'` hat, wird abgelehnt.

**Vorgeschichte auf demselben Branch** (abgeschlossen, nicht Teil der Restarbeit): Rollen-/Tenant-Modell
12.09.–21.09. (Option A = `AdminScope`, ADR 0012), Deployment-Modi inkl. `single_user`,
Entity-Access-Resolver Phasen 0–5, `tenant_entity_grants`, Tenant-Workspace-Pfade, LLM-Publish-Gate
(schema_133), und die Commit-Reihe `efbe3931 … e920fbf3` (Operator-, Tuning-, Reviewer-Konsole +
Tool-Tür: jeweils „die Gates fragen, die die eigene Route auch fragt"). Der offene Rest dieses Strangs
ist **ausschließlich** die Legacy-Spalte.

---

## 2. Wo die Session abgebrochen ist

Letzte Anweisung: **„precommit-Profil laufen lassen und committen"** (02.10., 20:02). Letzter
Assistant-Block 20:12, Transkript endet dort.

Belegt:

- **Der Commit ist nicht entstanden.** `HEAD = e920fbf3` („ask the tool door the question its routes
  ask", 02.10. **17:22**) — 3 Stunden vor der Anweisung.
- Der Block liegt **stagebereit**: 15 Dateien, `501 insertions(+), 80 deletions(-)`; die neue Testdatei
  steht als `A` im Index (echter Add, kein `git add -N`).
- `docs/features/operator-agent.md` ist **modifiziert, aber nicht staged** — der Text selbst fertig.
- Der `shell.nix`-Edit (Bandit bereitstellen) ist **zweimal nicht gelandet** und fehlt:
  `grep bandit shell.nix` → kein Treffer; `python3 -c "import bandit"` → `ModuleNotFoundError`.

---

## 3. Restarbeit

### A. Hängt sofort in der Luft (der fertig geschriebene, nicht committete Block) — **02.10. 23:14 erledigt**

- [x] **precommit-Profil laufen lassen** — einmal manuell vor dem Commit, dann bei allen drei Commits im
      Hook: alle 27 Checks grün (`ddd_layers … python_cve`), Backend-Suite
      **2 376 passed, 3 skipped, 2 deselected**. Kein
      `SKIP_CHECKS`, kein `--no-verify`. **Was der Gate dabei fand:** `tenant_scope` lehnte die
      `schedules_allowed`-Lese in `infrastructure/scheduling/schedules_access.py:70` ab (Marker fehlte);
      gesetzt auf `# tenant-scope: guarded by user_id pk` — nachgeprüft an **allen** Aufrufern
      (`scheduler_jobs_user_api.py:61,106,165,191,215`, `scheduler_job_presets_user_api.py:27` je
      `user_id=user.id`, `auth_api.py:334` `user=user`): keine Stelle, an der ein Admin einen anderen
      Account damit prüft. Dieselbe Form wie der Zwilling `workspace_service.py:128`.
- [x] **Commit des Blocks** (16 Dateien, `503 insertions(+) / 82 deletions(-)`) **inkl. der lebenden
      Doku** → **`8312afaf`** „take the retired role column out of the schedule and workspace doors".
      Die Gap-Zeile in `docs/features/operator-agent.md` steckt im selben Commit.
- [x] **Nach dem Commit geprüft, dass die neue Datei wirklich drin ist** (in diesem Repo schon einmal
      verloren gegangen, weil `git add -N` nicht in einen normalen Commit gehört):
      `git ls-tree -r HEAD --name-only` → `tests/unit/test_schedule_and_workspace_rights_use_site_role.py`
      vorhanden; `git status --short` zeigt nur dieses Planungsdokument (`??`).
- [x] **Bandit bereitstellen** (separater Commit, ist Tooling, nicht Security-Fix) → **`4ba62ca8`**:
      `shell.nix` += `python3Packages.bandit` (nachgemessen: auflösbar, **1.9.4**, `python3 -m bandit
      --version` läuft in dem Shell). Bewusst **nicht** als `nix_shell_command` in
      `scripts/checks/config.json` verdrahtet — siehe D, das ist eine Gate-Entscheidung.

### B. Legacy-Rolle: die 7 Stellen aus der Messung — 6 zu, 1 offen

Die Tabelle ist die Messung vom 02.10. (16:44), jede Zeile war einzeln nachgelesen. Der Stand unten
ist am 02.10. erneut gegen den Code geprüft.

- [x] **1 — Scheduler-HTTP.** `api/scheduling/controllers/scheduler_jobs_user_api.py:92,177,203,228`,
      `scheduler_job_runs_api.py:49,76`. War `is_admin=(user.role == "admin")` → **fremde Schedules
      listen, aktivieren, archivieren, hart löschen**. Jetzt `db.user_effective_role(user.id) == "admin"`.
- [x] **2 — `client_surface_policy.py:114-130`.** Legacy-Lese **vor** `site_role`/`user_is_tenant_admin`
      → Binding von Workspaces auf **Server-Pfade** (= Host-Dateisystem). Jetzt kanonisch.
- [x] **3 — Selbstbearbeitung des eigenen Quellbaums.** `domain/workspace/workspace_common.py` stempelte
      einen UserLike mit `db.user_role(uid)` für
      `infrastructure/workspace/workspace_service.self_editing_allowed` → `agentlayer-self`-Workspace =
      AgentLayers eigener Quellbaum. Der Carrier übergibt jetzt eine **id statt eines Rollenwerts**.
- [x] **4 — `infrastructure/scheduling/schedules_access.py:44-60`.** `if role == "admin": return True`
      **vor** jeder kanonischen Lese (Feature-Gate + Verstärker für den Runner). Parameter entfernt,
      nicht nur umgestellt — `domain/scheduling/access.py` hat jetzt gar keinen
      `user_role`-Parameter mehr, damit die Legacy-Spalte nicht wieder reingereicht werden kann.
      Auch `api/platform/controllers/auth_api.py` (`may_use_schedules`) läuft jetzt darüber;
      hintere einer fehlgeschlagenen Lese steht bewusst `False`.
      **Getestet:** `tests/unit/test_schedule_and_workspace_rights_use_site_role.py` (neu, 376 Zeilen)
      lehnt eine wiedereingeführte Legacy-Lesstelle in den sechs betroffenen Dateien per Source-Scan ab.
- [x] **5 — Dashboards.** `infrastructure/dashboard/dashboard_access.py:165,168-169` (Zeilen **vor** dem Fix)
      las `db.user_role(uid)` und gab `user_role=db_role or role` weiter →
      `domain/dashboards/access.py:32-36` prüfte `role == "admin"` **vor** `site_role == "site_admin"` und
      gab dann bedingungslos `True`. Gewährt die Dashboard-Rechte.
      (02.10. gegen 23:50 erneut nachgemessen: beide Stellen unverändert.)
      **03.10. 13:55 geschlossen, Form wie Block 1 und 6:** die Regel heißt
      `evaluate_dashboards_access(*, site_role, dashboards_allowed)` und vergleicht nur noch gegen
      `site_admin`; der einzige Aufrufer (`user_may_use_dashboards`) löst über `db.user_site_role(uid)`.
      Der Parameter ist **entfernt**, nicht ignoriert. Mit ihm sind die Rückfallebenen weg, die der alte
      Code an drei Stellen benutzte (`role = str(getattr(user, "role", …))` aus dem Request-Objekt):
      ohne uid und nach einer fehlgeschlagenen Lese steht jetzt bewusst `False`.
      **Nebenbei toter Code:** `dashboard_permission_error_from_flags` hatte **null** Aufrufer
      (`grep -rn dashboard_permission_error_from_flags` über `apps`/`plugins`/`tests` → nur Doku und sein
      eigener Lock-Test) und nahm doch `user_role` — gelöscht statt umgebaut, sonst bleibt eine zweite Tür,
      durch die der Wert wiederkönnte.
      **Getestet:** `tests/unit/test_dashboard_rights_use_site_role.py` (neu, 12 Tests) — Regel pro Akteur
      (herabgestufter Legacy-Admin / Site-Admin / Mitglied), sechs unbekannte `site_role`-Werte erhöhen
      nichts, Resolver pro Akteur mit absichtlich lesebalem Legacy-Wert, „kein Antrag ohne uid",
      Source-Scan über beide Dateien, Signatur-Scan der Regel, AST-Trace `site_role=` → `db.user_site_role`,
      Lock auf die gelöschte zweite Tür. `tests/unit/test_dashboard_access.py`: der Test, der `is True`
      behauptete (herabgestufter Account durfte), ist in seine Gegenbehauptung gedreht; neu: fehlgeschlagene
      Lese verweigert. Zusammen **32 passed**.
      **Mutationen (03.10. gegen 15:25 live wiederholt, je `cp` zurück und per `md5sum -c` geprüft, danach
      wieder 32 passed; Protokolle `.qwen/tmp/fam5/m*.txt`, `.qwen/tmp/fam5/p5.txt`):**
      1 — Resolver `site_role = db.user_role(uid)` → **5 failed, 27 passed** (`test_site_admin_bypass_via_db`,
      `test_the_site_admin_keeps_it_against_a_revoked_grant`, `test_failed_site_role_lookup_denies`,
      Source-Scan, AST-Trace).
      2 — Resolver `site_role = str(getattr(user, "role", "") or "")` → **4 failed, 28 passed**; der
      File-Scan bleibt hier **blind** (kein `db.user_role`-Aufruf — nachgezählt: der Source-Scan steht in
      keiner Fehlerzeile), was trifft, ist der AST-Trace — der Grund, warum er der Zuordnung folgt und
      nicht den Literaltext vergleicht.
      3 — Regel nimmt `user_role` zurück (Parameter + `role == "admin"`-Zweig, ohne jeden Aufrufer) →
      **1 failed, 31 passed** (`test_no_dashboard_rule_accepts_a_role_string`): die Signatur allein ist der
      Rückfall, Verhalten zeigt nichts.
      4 — `dashboard_permission_error_from_flags` wieder eingesetzt → **2 failed, 30 passed**
      (`test_the_second_door_stays_shut`, Signatur-Scan).
      5 — fehlgeschlagene Lese fällt offen statt zu verweigern (`except`-Zweig auf `True`) →
      **1 failed, 31 passed** (`test_failed_site_role_lookup_denies`).
      **Reichweite:** anders als Familie 6 öffnet das hier die **Funktion selbst** — beide Create-Türen
      (`api/dashboards/controllers/dashboard_core_api.py:131,181`) und die Lesetür
      (`infrastructure/dashboards/dashboard_persistence.py:241`, `ensure_default_dashboard_for_new_user`).
      **Ehrlich zum Rand:** `_load_user_dashboards_allowed` gibt bei DB-Fehler weiterhin `True` (wie
      `global_dashboards_enabled`) — das ist die Spalten-Voreinstellung für Auto-Create, keine Elevation,
      und bewusst nicht angefasst. Der AST-Trace verlangt genau **eine** Zuweisung an `site_role`; eine
      zweite würde ihn wieder scharf machen.
- [x] **6 — Task-Freigabe.** `plugins/tools/platform/tasks/agent_tasks.py:88` →
      `role = db.user_role(user_id)` → `domain/agent_runtime/task_approval.py:21-25,34-35`. Wer ein
      Task direkt an `queued` (also an der Freigabe vorbei) setzen darf, entschied die Legacy-Spalte.
      **02.10. gegen 23:50 geschlossen, committet 03.10. 00:01:** Die Domain-Regel heißt jetzt
      `normalize_new_task_status(requested=…,
      site_role=…)` und vergleicht gegen `site_admin`; der Aufrufer löst über `db.user_site_role(user_id)`
      auf. Wie in Block 1 wurde der Parameter **entfernt**, nicht ignoriert — es gibt in der Regel keinen
      Platz mehr für einen Legacy-Rollenwert. **Nebenbei toter Code:** `may_transition_to_queued(*,
      user_role)` hatte null Aufrufer und gab in beiden Zweigen `True` — gelöscht.
      **Getestet:** `tests/unit/test_task_approval_uses_site_role.py` (neu, 8 Tests) — Regel pro Akteur
      (herabgestufter Legacy-Admin / Site-Admin / normales Mitglied), unbekannte `site_role` verweigert,
      `task_create` mit echtem Pfad (Legacy-Leser antwortet fällig `admin`), Source-Scan über beide
      Dateien, Signatur-Scan der Regel, AST-Scan „`site_role=` enthält `user_site_role`".
      **Mutation (02.10. live wiederholt):** `site_role=db.user_role(user_id)` → **3 fallen**, Signatur
      `may_transition_to_queued(*, user_role)` zurückgeholt → **1 fällt**; jeweils per `cp` zurückgesetzt
      und mit `md5sum -c` geprüft, danach wieder 11 passed (beide Dateien zusammen).
      `tests/unit/test_task_approval.py` auf `site_role=` umgestellt (3 Tests).
      **Ehrlich zur Reichweite:** Was die Regel öffnet, ist die **Erstzeile** (`draft` vs. `queued`) —
      nicht die Freigabe selbst. `task_update` setzt jedes Task, das der Aufrufer sehen darf, für **jeden**
      auf `queued`; eine approbation-pflichtige Kette ist das nicht (Gap-Zeile in
      `docs/features/operator-agent.md` sagt das).
- [ ] **7 — `bearer_user_role`-Familie (größte Fläche, null Testabdeckung).** ~10 Aufrufer
      (`chat_completions_api.py:31`, `chat_websocket.py:331`, `voice_realtime_websocket.py:85`,
      `domain/voice/realtime_turn.py:110-112`, `telegram_bridge.py:254`, `discord_bridge.py:377`,
      `bridge_agent_session.py` (4 Lesstellen), `bridge_agent_turn.py:99`, `scheduler.py:149`,
      `scheduler_jobs_runner.py:59`, `coding_schedule_execution.py:443`, `agent_tasks_runner.py:138`) →
      `domain/model_routing/resolution.py:104-112` (`_override_allowed`). Was sie entscheiden: **welches
      Modell ein Turn benutzen darf** — ein Override, ohne dass die kanonischen Regeln (Profil, Freigabe,
      Limit) greifen. In beide Richtungen kaputt.
      Zugehörig: `application/agent_runtime/use_cases/auto_workspace.py:82-88,127` verastelt sich selbst
      auf `db.user_role(user_id) == "admin"` **und** stempelt `u.role` auf das übergebene Objekt.

Zwei Dinge, die den Befund schärfer machen als „nur ein falsches Feld":

- `infrastructure/scheduling/scheduler_jobs_store.py:293-299` dokumentiert ausdrücklich *„actor_is_admin
  is the caller's already-resolved right, never a role read"* — der Aufrufer hielt sich nicht daran.
  (Mit Block 1 behoben; der Vertrag steht jetzt auch auf den Call-Sites.)
- `application/agent_runtime/runtime/io.py` baute ein `_UserRef` mit `role = None`; damit war die
  Legacy-Lese in der DB der **einzige** Entscheider. Der Zweig ist mit `8312afaf` entfernt (1 Zeile).

**Messgröße für den Rest:** nach Block 1 standen 23 `db.user_role(`-Vorkommen in 17 Dateien, nach
Familie 6 **22 in 16 Dateien** (02.10. 23:52), nach Familie 5 **21 in 15 Dateien** (03.10. 13:52; jeweils
`grep -rn 'db\.user_role(' apps plugins --include='*.py'`). Die 21 teilen sich genau: **15 decisive
Lesstellen in 11 Dateien** — Runner und Bridges: `bridge_agent_session.py` 4, `auto_workspace.py` 2, je eine
in `scheduler.py`, `scheduler_jobs_runner.py`, `coding_schedule_execution.py`, `agent_tasks_runner.py`,
`bridge_agent_turn.py`, `telegram_bridge.py`, `discord_bridge.py`, `voice_realtime_turn_service.py`,
`chat_run_bootstrap.py` —, dazu **3 bewusste Fallbacks** in `plugins/tools/platform/scheduler/jobs.py:93,188,219`
(`agent_effective_role(uid, db.user_role(uid))` — Legacy nur, wenn die `site_role`-Lese nicht
verfügbar ist) und **3 rein dokumentarische Zeilen** (`domain/workspace/workspace_common.py:118`,
`domain/scheduling/targets.py:122`, `application/identity/use_cases/request_auth.py:73`).

Die 15 habe ich am 03.10. bis zum Verbraucher verfolgt, wobei **vier ohne Verbraucher-Beweis** bleiben
(`coding_schedule_execution.py:443`, `scheduler.py:149`, `scheduler_jobs_runner.py:59`,
`voice_realtime_turn_service.py:16` — die Zeile liest, wohin der Wert geht, habe ich nicht verfolgt).
Entschieden wird ohne jeden Site-Check an **einer** Stelle: `bridge_agent_session.py:311`
(`min_r == "admin" and ur != "admin"`) — Agent-Freigabe in der Bridge. Die beiden in `auto_workspace.py`
sind **Fallback-Stufe**, auch wenn die Zahl sie oben zählt: `:88` sitzt *in* `is_elevated_admin` **nach**
`db.user_site_admin` (`:76`) und greift nur, wenn die Lese `None` liefert; `:127` stempelt `u.role`, das
`:130` dasselbe `is_elevated_admin` füttert. Bridges und Runner (`bridge_agent_turn.py:99`,
`telegram_bridge.py:254`, `discord_bridge.py:377`, `agent_tasks_runner.py:138`) geben den Wert als
`bearer_user_role` an `chat_completion` weiter, wo `chat_run_bootstrap.py:155-161` ihn über
`db.user_site_admin` wieder kanonisiert. Der Rest ist also **eine Familie**: **7 (`bearer_user_role`)**
samt ihrem Anhängsel `auto_workspace` — und die Lüge steckt in dem Träger, nicht in jeder Einzelzeile.

### C. Doku

- [x] Gap-Zeile in `docs/features/operator-agent.md:235` neu geschrieben: drei offene Familien
      (Runner/Bridges, zwei Domain-Regeln, `auto_workspace`) und explizit aufgelistet, was am 02.10.
      geschlossen wurde, inkl. Name des neuen Tests.
- [x] **staged und committet** — sitzt in `8312afaf` (Zeile 235, Text unverändert gegenüber dem Snapshot).
- [x] **dieses Dokument: committen.** Entscheidung 02.10. 23:20 (er): behalten als Handoff unter
      `docs/planning/`, committet in `ff89496a`. Die Fortschreibung für Familie 6 (Abschnitt B/6,
      Messgröße, Tabellenzeilen unten) sitzt im selben Commit wie die Änderung selbst — ein Record, der
      seine eigene Hash nicht kennen kann.
- [x] Gap-Zeile in `docs/features/operator-agent.md:235` **zweitens** fortgeschrieben: die offene
      Domain-Regel-Zeile nennt jetzt nur noch Dashboards, dafür steht die Task-Regel in der Liste des
      am 02.10. Geschlossenen — plus der honeste Hinweis, dass `task_update` weiterhin jedem das
      Queueing erlaubt. Sitzt im Commit zu Familie 6.
- [x] Gap-Zeile **drittens** fortgeschrieben (03.10.): offene Familien **zwei** — Runner/Bridges und
      `auto_workspace` (die Nummerierung der Zeile folgt jetzt), Dashboards umgezogen in die Liste des
      Geschlossenen: Parameter weg, `db.user_site_role`, die zwei Request-Fallbacks weg, gelöschte zweite
      Tür, Name des neuen Tests, und der Unterschied zur Task-Regel — hier öffnet die Regel die **ganze
      Funktion**, nicht nur den Status einer Zeile.

### D. CI- und Gate-Lücken (am 02.10. gemessen)

- [ ] **Bandit macht CI rot, sobald ein PR läuft.** Kette, nachgelesen: `requirements-dev.txt:4`
      installiert `bandit>=1.7.0`; `.github/workflows/ci.yml` setzt `CHECK_STRICT_TOOLS: "1"` (Zeile 24)
      und läuft `python scripts/checks/run.py --profile ci`; das `ci`-Profil enthält `bandit`;
      `[tool.bandit]` in `pyproject.toml` hat **keine** Schwelle (nur `exclude_dirs = ["tests"]`) →
      jeder Fund = Exit 1. **02.10. 23:11 neu gemessen** (`nix-shell ./shell.nix --run "python3 -m bandit
      -r apps/backend -c pyproject.toml"`, Exit **1**): **185 Funde — 83 MEDIUM, alle B608**
      (SQL aus Strings), **102 LOW** (davon 59 B110 try/except/pass, 8 B404, 8 B603, 6 B607, 4 B105
      „hardcoded password" auf `'bearer'`/`'key-round'`), **kein Fund mit Severity HIGH** — wohl aber 87
      mit *Confidence* HIGH, die beiden Achsen sind zu verwechseln. Dichteste Dateien:
      `server_lifecycle.py` 8, `tenant_content_persistence.py` 7, `operator_settings.py` 7. Das ist eine
      **Gate-Policy-Entscheidung**, keine Fleißaufgabe — zwei Kandidaten: (a) Schwelle auf `-lll`
      (meldet nur high → heute grün, weil kein HIGH), (b) die 83 B608 bereinigen bzw. begründet
      `#nosec`-en. Seit `4ba62ca8` ist der Lauf lokal möglich, ohne das Gate anzuschalten.
- [ ] **Das Precommit-Gate ist rot, ohne dass jemand am Frontend etwas geändert hat (03.10. 15:3x).**
      `python3 scripts/checks/run.py --profile precommit` → **26 Checks grün, `node_cve_full` exit 1**;
      die Backend-Suite im selben Lauf **2 397 passed, 3 skipped, 2 deselected**. Der Check ist per
      `scripts/checks/config.json:641-648` ein `npm audit --audit-level=high` in `apps/frontend`, liest
      also nur `package-lock.json` — das seit `0811a5fd` (26.09.) unverändert ist, und kein Pfad dieses
      Changes berührt JS/TS. Gemessen (`.qwen/tmp/fam5/audit.json`): **7 Funde — 5 high, 2 moderate, alle
      in Dev-Dependencies**; im ausgelieferten Code liegt nichts davon. Die fünf high sind **eine** Kette:
      `braces` (Stack-Exhaustion-DoS über tief verschachtelte Patterns, GHSA-vfj7-8cjw-p6xm; im Lock 3.0.3,
      also bereits die damals gepatchte Fassung) → `micromatch` → `fast-glob` → `chokidar` → `tailwindcss`.
      Entscheidend dabei: das Advisory trifft `braces` mit Range **`*`** — **es existiert keine gepatchte
      Fassung dieses Pakets**, und `npm audit --json` bietet deshalb für die ganze Kette nur den einen Ausweg
      `tailwindcss@4.3.3` mit `isSemVerMajor: true` (eingetragen als `tailwindcss ^3.4.19` in
      `apps/frontend/package.json`). Auch die zwei moderate (`react-router` 6.0.0–7.17.0: Open-Redirect-Bypass
      GHSA-wrjc-x8rr-h8h6, constructor injection in `deserializeErrors()`) wären nur über ein Major zu haben
      (`react-router-dom@7.18.4`) und blockieren bei `--audit-level=high` nicht.
      **Folge:** `.git/hooks/pre-commit` → `scripts/pre-commit-check.sh` läuft genau dieses Profil, der
      Fund blockiert also **jeden Commit auf diesem Branch**, auch einen aus Python und Doku — nachgesehen
      03.10. 15:4x: der Hook hat den Commit zu Familie 5 mit `[check:node_cve_full] FAILED - exit code 1`
      abgelehnt (`.qwen/tmp/fam5/commit_attempt.txt`). Der Record hält einen grünen Lauf 02.10. 23:52;
      zwischen dem und heute änderte nichts am Lockfile — der Advisory-Feed ist der Bewegende (einzige
      tragfähige Erklärung, keine Messung). Drei Kandidaten standen: (a) `tailwindcss` 3→4 ziehen, ein
      eigener Schwung, der mitten in der UI-Umgestaltung das Design-System anfasst; (b) Provider wechseln
      (`CVE_PROVIDER=osv|snyk`, config.json:650-660); (c) warten — nach der Messung oben aber auf etwas,
      das es für `braces` nicht gibt. **Kein Skip ist benutzt worden** — die Änderung zu Familie 5 lag
      darum **gestaged, aber nicht committet**.
- [x] **Entschieden und gezogen: `tailwindcss` 3 → 4 (Variante (a)), eigener Schwung 03.10.** Der Owner
      wollte die echte Reparatur, nicht die Gate-Quelle — weder (b) noch (c). Was sich änderte:
      `tailwindcss ^4.3.3`, neu `@tailwindcss/postcss ^4.3.3`, `postcss ^8.5.25`, **`autoprefixer`
      deinstalliert** (lightningcss übernimmt es im v4-Compiler), `postcss.config.js` nennt nur noch
      `@tailwindcss/postcss`. Damit ist die gesamte v3-Kette aus dem Lock: `braces 3.0.3`, `chokidar 3.6.0`,
      `fast-glob`, `micromatch`, `anymatch`, `commander 4.1.1`, `dlv`, `didyoumean`, `cssesc`,
      `glob-parent`, `arg`. Ergebnis: `npm audit --audit-level=high` → **Exit 0**, noch **2 moderate**
      (`react-router`), die nach `--audit-level=high` nicht blockieren. Das Gate ist grün, **ohne** dass
      `scripts/checks/` oder eine Config angefasst wurde.
    - **Warum `@config` und kein `@theme`:** vier Guard-Skripte importieren die JS-Config zur Laufzeit —
      `check-z-index.mjs:34`, `check-fill-token.mjs:34-35`, `check-border-token.mjs:35`, `width-scan.mjs:23`
      — und `src/ui/fill-token-guard.test.ts` liest zusätzlich `tailwindcss/colors.js`. Ein `@theme` hätte
      eine zweite Quelle der Wahrheit für ~1 200 Token-Aufrufe erzeugt; die Guards und der Compiler würden
      bei der nächsten Config-Änderung auseinanderlaufen. `tailwind.config.js` ist **unverändert**.
    - **Die Falle, die beinahe durchgerutscht wäre.** v4s automatische Source-Erkennung **ignoriert** das
      negated glob (`!src/**/*.{test,...}`) in der JS-Config. Der erste Build compilierte die Guard-Fixtures
      darum mit: **107** Rohtoken-Klassen standen im ausgelieferten Stylesheet, einzeln gemessen
      `bg-red-500`, `bg-indigo-500`, `border-rose-500`, `text-rose-400`, `z-[999]`, `max-w-6xl`. Das ist der
      Moment, in dem die Token-Skala aufhört erzwingbar zu sein — der Guard meldet grün, weil *er* die
      Fixtures ausschließt, während das Bundle sie enthält. Fix: `@import "tailwindcss" source(none)` +
      drei `@source`-Zeilen, davon eine `@source not "../src/**/*.test.{js,ts,jsx,tsx}"`; im finalen Build
      sind alle sechs Klassen **0×**.
    - **Zwei Preflight-Regeln, die v4 nicht mehr hat**, sind in `@layer base` zurückgeholt
      (`apps/frontend/src/index.css`) statt als stille Umgestaltung hingenommen: `cursor: pointer` auf
      Buttons (v4s Fallback ist `default`; `src/ui` enthält **59** nackte `<button>`, alle Primitive wären
      vom Zeiger zum Pfeil geworden, ohne dass eine Call-Site sich geändert hätte) und
      `-webkit-appearance: textfield` + `outline-offset: -2px` auf `[type=search]` — das hielt Chrome davon
      ab, sein eigenes Einfallfeld über `bg-field` zu malen; v4 neutralisiert nur
      `::-webkit-search-decoration`, das ist die andere Hälfte. Die Margen von
      `blockquote/dl/dd/figure/fieldset`, die v3 dort noch einzeln setzte, deckt v4s universeller Reset
      breiter ab — nicht zurückgeholt.
    - **Umbenannt, weil dieselbe Klasse in v4 etwas anderes meint** (jeweils aus den zwei Builds gelesen,
      nicht aus dem Changelog): `shadow-sm`→`shadow-xs` (**14**), `outline-none`→`outline-hidden` (**44**) —
      zusammen **58 Vorkommen auf 57 Zeilen in 36 Dateien**. v4s `shadow-sm` *ist* v3s `shadow`, und
      `outline-hidden` ist die einzige Fokus-Kontrolle, die ein Forced-Colors-Theme übrig lässt, wenn es
      alle `shadow-focus`-Ringe streicht. Bewusst **nicht** geändert, weil identisch gemessen: `shadow`
      (`0 1px 3px 0 …`), `rounded` (`.25rem`), `backdrop-blur` (`blur(8px)`). `ring` (3px→1px) und `blur`
      kommen in `src/` nirgends blank vor.
    - **Größe, erklärt statt hingenommen:** roh **70 380 → 100 430 B**, gzip **13 544 → 16 927 B**
      (+3 383 B, **+25 %**). Mechanismen gezählt: **70 `@property`-Blöcke** (4 403 B = 4,4 %), **275
      `color-mix()`-Fallback-Paare**, `calc(var(--spacing) * N)` statt ausgeschriebener Werte, `:where()`
      bei space-*/divide-*. Vendor-Präfixe überleben autoprefixer: `-webkit-backdrop-filter` 6/6,
      `-webkit-user-select` 3/3, `-webkit-line-clamp` 1/1, `-webkit-font-smoothing` 1/1.
    - **Festgenagelt** wird das in `apps/frontend/src/ui/preflight-compat.test.ts` (neu, 10 Vitest-Fälle):
      die vier wegbenannten Utilities dürfen in keiner `.ts/.tsx` unter `src/` stehen (Tests ausgenommen —
      die *pflanzen* Violations absichtlich), der Matcher darf dabei weder Prosa („the focus ring") noch ein
      Datenwort (`extras: ["ring"]` in `mascotArt.ts`) noch die identischen Utilities erwischen, und die
      drei Atomsowie die beiden Preflight-Regeln müssen in `index.css` stehen. **Sechs Mutationen** machten
      ihn jeweils rot, jede einzeln zurückgeholt und per `md5sum -c` belegt.
- [ ] **Zwei root-owned Ordner in `apps/frontend/node_modules` blockieren jede künftige `npm install`
      (03.10., beim Major-Lauf gefunden).** Nach dem Container vom 21.09. liegen dort `playwright` und
      `playwright-core`, beide **1.49.1**, `root:root` — in `package.json` **und** im Lock **nicht erklärt**,
      von **12** Skripten unter `scripts/probe/` und `scripts/e2e/` aber importiert. `npm install` wollte sie
      entfernen und fiel mit `ENOTEMPTY: directory not empty, rename '.../node_modules/playwright'` ab;
      `rm -r` scheitert mit `EACCES`, weil ein `rename()` über Elternordner hinweg Schreibrecht auf dem
      `..`-Eintrag des **Zielverzeichnisses** braucht und dessen Einträge root gehören, während der
      Vaterordner dem Nutzer gehört. Für den Migrationslauf habe ich beide **umbenannt**
      (`.stray-playwright{,-core,-staging,-core-staging}`) und nach dem Lauf **unter ihre ursprünglichen
      Namen zurückgesetzt** — live geprüft: beide `1.49.1`, Stand 03.10. Die zwei `-staging`-Reste von npm
      mussten liegen bleiben, ihr Vater ist root. **Dauerhafte Beseitigung braucht erhöhte Rechte**
      (`sudo rm -rf apps/frontend/node_modules/playwright apps/frontend/node_modules/playwright-core`) —
      bewusst **nicht** ausgeführt, Entscheidung beim Owner. Solange sie da sind, meldet
      `npm install --dry-run` „removed 2 packages" und der nächste echte Install läuft wieder auf
      `ENOTEMPTY`. Aufgehängt werden kann das dauerhaft nur, indem die beiden entweder sauber deinstalliert
      oder als echte (dev-)Abhängigkeit erklärt werden — letzeres wäre eine eigene Entscheidung, weil die
      1.49.1 nicht die Version ist, die die Skripte erwarten würden.
- [ ] **Frontend-Tests und Produktions-Build sind in CI nicht gecastet.** Das `ci`-Profil enthält die
      `frontend_*`-Guard-Skripte und `frontend_i18n`, aber **weder** `npm run test:unit` (Vitest) **noch**
      `npm run build`. Beides ist lokal grün gemessen (01.10. in der Session), nur eben nirgends Pflicht.
- [ ] `python_cve`/`node_cve_full` hängen am Registry-Endpunkt — ein `400 Invalid package tree` ist ein
      Registry-Fehler (Retry), kein Lockfile-Problem. (`node_cve_full` ist nach `--audit-level=high`,
      moderate Funde blockieren nicht.)
- [ ] *Nicht nachgemessen:* „Config-Check hat 224 Dateien nie gescort" — Zahl stammt aus der Session
      vom 02.10. und wurde hier nicht überprüft.

### E. Merge-Lage

- [ ] **PR → main steht aus.** Alle Commits vom 02.10. (ab `8312afaf` inklusive dieses Dokuments) sind
      **noch nicht gepusht** — Maßzahl statt Zahl: `git rev-list --count origin/feat/chat-persist-queue-goal-strip..HEAD`
      → **5** (gemessen 03.10. nach dem Commit zu Familie 5, `7384e917`; `git rev-list --count main..HEAD`
      dazu **182**). Nach dem Tailwind-Schwung gemessen: **6** bzw. **183** — der Branch läuft damit
      **183 Commits** vor `main` her (Snapshot 177); `main` zuletzt `9aa96e19`. (Stand Snapshot: HEAD war
      `4ba62ca8`, 2 vor `origin`.)
    - `.github/workflows/ci.yml` triggert nur `pull_request` und `push: [main]` → **auf diesem Branch ist
      CI nie gelaufen.** Der erste Lauf ist gleichzeitig der erste Test von D (Bandit) — vorher mit ihm
      die Gate-Form klären, sonst ist der PR rot, bevor er gelesen wurde.
- [ ] PR eröffnen ist **extern sichtbar** — braucht sein explizites Go.

### F. Entscheidungen, die nur er treffen kann

- [ ] **ADR 0013 (OS-Level-Isolation für Workspace-Ausführung)** — Status **Proposed**, Entscheidung
      angefragt 19.09., gewählte Richtung war „plan OS isolation", **null Code** dagegen geschrieben.
- [ ] **Bandit-Gate-Form** (siehe D).
- [ ] **Stack hochziehen oder nicht** — für die Frage, ob die Legacy-Rechte **latent** oder **live**
      sind. Messung 02.10.: DSN-Host `postgres` nicht auflösbar, `127.0.0.1:5432` zu, Container
      `agent-kernel-api-1`/`-web-1` seit ~4 Wochen exited. Die Code-Befunde gelten in beiden Fällen —
      der Unterschied ist nur, ob gerade jemand durch die Tür geht.

---

## 4. Verifikation dieses Dokuments (02.10., hier ausgeführt)

| Prüfung | Ergebnis |
|---|---|
| `pytest tests/unit/test_schedule_and_workspace_rights_use_site_role.py tests/unit/test_schedules_access.py tests/unit/test_client_surface_policy.py -q` | **21 passed in 0.83 s** |
| `git diff --cached --stat` (vor dem Commit) | 15 Dateien, 501(+) / 80(−), neue Testdatei als `A` |
| `git status` (Snapshot 22:15) | HEAD `e920fbf3`; Doc unstaged; **keine** untracked Dateien |
| `git rev-list --count main..HEAD` | 177 |
| `grep bandit shell.nix` / `import bandit` (Snapshot 22:15) | kein Treffer / `ModuleNotFoundError` |
| Legacy-Leser 5/6/7 | unverändert vorhanden (Code-Zeilen oben) |
| **precommit-Profil, 23:14** (`scripts/checks/run.py --profile precommit`) | **all checks passed**, EXIT=0; Backend-Suite **2 376 passed, 3 skipped, 2 deselected** |
| **Commit + Gegenprobe** | `8312afaf` 16 Dateien 503(+) / 82(−); `git ls-tree -r HEAD` enthält die neue Testdatei; `git status --short` = nur dieses Dokument |
| **`python3Packages.bandit` im Kanal** | vorhanden, **1.9.4** (`nix-instantiate --eval`), `python3 -m bandit --version` läuft in `nix-shell`; `nix-instantiate --parse shell.nix` OK |
| **Bandit-Lauf 23:11** | Exit **1** — 185 Funde: 83 MEDIUM (alle B608) / 102 LOW / 0 Severity-HIGH |
| **`db.user_role(` nach `8312afaf`** | **23 Vorkommen in 17 Dateien** — unverändert gegenüber dem Snapshot (16 echte Lesstellen in `apps/backend`, 1 in `plugins/.../agent_tasks.py`, 3 Fallbacks in `scheduler/jobs.py`, 3 rein dokumentarische Zeilen) |
| **Familie 6 — Tests** (`tests/unit/test_task_approval_uses_site_role.py` + `test_task_approval.py`, 02.10. vor 23:52) | **11 passed** |
| **Familie 6 — Mutation 1** (`site_role=db.user_role(user_id)` in `agent_tasks.py`) | **3 failed, 8 passed** — `task_create_queues_only_for_the_site_admin`, `neither_file_reads_the_legacy_role_column`, `the_source_passes_the_canonical_read_to_the_rule`. Zurückkopiert, `md5sum -c` OK, danach 11 passed |
| **Familie 6 — Mutation 2** (`def may_transition_to_queued(*, user_role)` zurück in die Domain-Datei) | **1 failed, 10 passed** — `no_approval_rule_accepts_a_role_string`. Zurückkopiert, `md5sum -c` OK, danach 11 passed |
| **Familie 6 — ganze Suite** (`pytest -q`) | 2 384 passed, 5 skipped, **53 errors** — alle Errors sind `tests/e2e/*` mit `Connection refused` auf `127.0.0.1:8088` (braucht laufenden Stack, Abschnitt F), kein Fehler in `tests/unit` |
| **Familie 6 — precommit-Profil** (02.10., kurz vor 23:52) | **all checks passed**, EXIT=0 |
| **Familie 5 — Tests** (`tests/unit/test_dashboard_rights_use_site_role.py` neu 12 + `tests/unit/test_dashboard_access.py` 20, 03.10.) | **32 passed in 0.13 s** |
| **Familie 5 — Mutation 1** (Resolver `site_role = db.user_role(uid)`) | **5 failed, 27 passed** — `test_site_admin_bypass_via_db`, `test_the_site_admin_keeps_it_against_a_revoked_grant`, `test_failed_site_role_lookup_denies`, Source-Scan, AST-Trace. `cp`-Restore, `md5sum -c` OK, danach 32 passed |
| **Familie 5 — Mutation 2** (Resolver nimmt die Rolle vom Request-Objekt) | **4 failed, 28 passed** — beide Site-Admin-Tests, `test_failed_site_role_lookup_denies`, AST-Trace; der **Source-Scan bleibt blind** (kein `db.user_role`-Aufruf im Text) und musste es auch: er steht in keiner Fehlerzeile |
| **Familie 5 — Mutation 3** (Regel bekommt `user_role` + `role == "admin"`-Zweig, ohne Aufrufer) | **1 failed, 31 passed** — `test_no_dashboard_rule_accepts_a_role_string`; am Verhalten wäre diese Mutation unsichtbar |
| **Familie 5 — Mutation 4** (`dashboard_permission_error_from_flags` wieder eingesetzt) | **2 failed, 30 passed** — `test_the_second_door_stays_shut`, Signatur-Scan |
| **Familie 5 — Mutation 5** (`except`-Zweig des Resolvers auf `True`) | **1 failed, 31 passed** — `test_failed_site_role_lookup_denies` |
| **Familie 5 — ganze Suite** (`pytest -q`, 03.10. 14:24) | **2 397 passed, 5 skipped, 53 errors** — Gegenprobe mit `-rfE`: **alle 53** Errors in `tests/e2e/*`, **0** Failures sonst; Grund live nachgelesen: `RuntimeError: Agent Layer not reachable at http://127.0.0.1:8088/health: [Errno 111] Connection refused` (`tests/e2e/support/helpers.py:240` über `tests/e2e/conftest.py:23`). Gegen Familie 6 sind das genau die 13 neuen Tests mehr |
| **`db.user_role(` nach Familie 5** (03.10. 15:2x) | **21 Vorkommen in 15 Dateien** — siehe Messgröße oben (15 getragen / 3 Fallback-Argument / 3 dokumentarisch) |
| **Familie 5 — precommit-Profil** (03.10. 15:3x) | **FAILED**: 26 Checks grün, **`node_cve_full` exit 1** (npm-audit-Kette `braces`→`micromatch`→`fast-glob`→`chokidar`/`tailwindcss`, 5 high — Details in D). Backend-Suite im Lauf: **2 397 passed, 3 skipped, 2 deselected**. Kein Skip benutzt, Commit bleibt aus |
| **Familie 5 — Commit-Versuch** (03.10. 15:4x) | `git commit -F .qwen/tmp/fam5/msg.txt` → `[check:node_cve_full] FAILED - exit code 1`, `[pre-commit] FAILED`, **EXIT=1**: kein Commit. Die sechs Pfade bleiben **gestaged** (neue Testdatei als `A`), die fertige Message liegt als `.qwen/tmp/fam5/msg.txt`; der Gegencheck auf `git ls-tree -r HEAD` steht darum noch aus |
| **Tailwind — Baseline v3** (03.10., vor dem Major) | `npm run build` Exit 0, ausgeliefertes Stylesheet **70 380 B** roh / **13 544 B** gzip (`.qwen/tmp/tw4/v3.css`) |
| **Tailwind — erster v4-Build** (03.10.) | kompiliert, **aber** Guard-Fixtures mit drin: **107** Rohtoken-/Arbitrary-Klassen im ausgelieferten Stylesheet (gezählt über `bg-*-*`, `z-[…]`, `max-w-6xl` u. ä.); Auslöser: negated glob wird ignoriert |
| **Tailwind — finaler Build** (03.10.) | `npm run build` **EXIT=0**, **20/20 Design-Guards** OK, Stylesheet **100 430 B** roh / **16 927 B** gzip; die sechs nachgeprüften Klassen (`bg-red-500`, `bg-indigo-500`, `border-rose-500`, `text-rose-400`, `z-[999]`, `max-w-6xl`) **0×**; `.shadow-xs` vorhanden, `.shadow-sm` **0**, `.outline-hidden` **2 Regeln** (Basis + `@media (forced-colors:active)`), `cursor:pointer` **2**, `appearance:textfield` **1** |
| **Tailwind — Vitest** (03.10.) | **55 Dateien / 625 Tests passed** (Baseline vorher: 54 / 615 — genau die neue Datei und ihre 10 Fälle) |
| **Tailwind — Mutationen an `preflight-compat.test.ts`** (03.10.) | **sechs**: `shadow-sm` in eine Klasse schreiben, `outline-none` wieder einsetzen, `cursor: pointer` aus `index.css` nehmen, die `@source not`-Zeile löschen, `@config` löschen, den `[type=search]`-Block löschen — jeweils **1 failed**, zurück per `cp` + `md5sum -c` OK, danach wieder grün |
| **`node_cve_full` nach dem Major** (03.10.) | `npm audit --audit-level=high` → **EXIT=0**, nur **2 moderate** (`react-router-dom`/`react-router`, `deserializeErrors()`) |
| **Familie 5 — precommit-Profil nach dem Major** (03.10.) | `python3 scripts/checks/run.py --profile precommit` → **all checks passed**, **EXIT=0** (alle 26 des Profils, `node_cve_full` inklusive) |
| **Familie 5 — Commit** (03.10.) | `git commit -F .qwen/tmp/fam5/msg.txt` → Hook **all checks passed**, **`7384e917`**, **6 files changed, 358 insertions(+), 77 deletions(-)**; Gegencheck: `git ls-tree -r HEAD --name-only \| grep -c test_dashboard_rights_use_site_role` → **1**, `git show --stat` führt die neue Testdatei mit `create mode 100644` |

**Nicht ausgeführt:** das `ci`-Profil (läuft nirgends Pflicht — D). Vitest und `npm run build` sind am
03.10. für den Tailwind-Schwung gelaufen und gemessen (oben); sie bleiben trotzdem ungecastet.
„21 passed" sind die drei Dateien, die den Block abdecken; die **ganze** Backend-Suite lief dagegen im
Hook: 2 376 passed.

---

## 5. Reihenfolge-Empfehlung

1. ~~**Block fertig committen** (A)~~ **erledigt 02.10. 23:14**: Profil → `8312afaf` → `git
   ls-tree`-Gegenprobe → `4ba62ca8` für `shell.nix`. Die halbe Lücke (1–4) ist im Baum, die Doku ehrlich.
2. ~~**Familie 6 dann 5**~~ **beide erledigt.** Familie 6: 02.10. ~23:55, committet 03.10. 00:01
   (`f80b44bb`). Familie 5 (Dashboards): 03.10. 13:55 fertig, **committet 03.10. in `7384e917`** — der
   erste Versuch war am Gate gescheitert (`node_cve_full`), nicht an der Änderung: Regel ohne
   `user_role`-Parameter, `dashboard_access.py` nur noch über
   `db.user_site_role`, die drei Request-Fallbacks weg, der aufruferlose Zwilling
   `dashboard_permission_error_from_flags` gelöscht statt umgebaut; 32 passed, fünf Mutationen mit Namen
   und Zahlen in Abschnitt 4. Die Regel hier öffnete die **ganze Funktion**, nicht nur einen Status.
3. **Familie 7 als nächster Schwung** (war „zuletzt", ist jetzt der einzige Rest) — 15 getragene Lesungen
   in 11 Dateien um den Träger `bearer_user_role` herum, Anhänger `auto_workspace`, **null Testabdeckung**
   auf `domain/model_routing/resolution.py::_override_allowed`. Erst die Abdeckung, dann die Aufrufer.
   Eine einzige Stelle entscheidet bis heute ohne jeden Site-Check: `bridge_agent_session.py:311`.
4. **Eine Gate-Form bleibt zu entscheiden, bevor der PR eröffnet wird** (D): **Bandit** (`-lll` gegen 83
   B608). Die zweite — **`node_cve_full`** — ist entschieden und erledigt: der Owner wollte das
   tailwindcss-Major statt des Provider-Wechsels, es ist 03.10. gezogen (D, Maße in Abschnitt 4). Der
   Hook lässt wieder jeden Commit durch.
5. **Push + PR** sind derselbe sichtbare Schritt und liegen bei ihm (E).
