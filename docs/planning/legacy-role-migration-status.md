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
Rest-Metrik neu gezählt, Precommit gelaufen — **rot durch `node_cve_full`, dieser Commit bleibt aus**,
Abschnitt D), `tailwindcss` 3→4 als eigener Schwung (Entscheidung des Owners nach dem abgelehnten Commit;
Abschnitt D), **committet 03.10. 23:35 Familie 5 (`7384e917`) und 23:43 der Major (`fa3dddbe`, per amend
04.10. 00:13 → `d53a0950`)**, **gepusht 04.10. 01:02 (Abschnitt E)** und **04.10. 13:45–21:20
(Familie 7: der `bearer_user_role`-Träger ist closed, die Legacy-Lesstelle `db.user_role` ist gelöscht,
Gate und Akteur-Tests sind neu — B/7, Messgröße in B, Doku in C, Maße in Abschnitt 4)**. **Die Zeiten
dieses Satzes sind gemessen, nicht erinnert** — `mtime` der Artefakte und `git reflog`: grün-Lauf des
Profils 23:27, Baseline-Backups des Majors 21:02, `commit_attempt.txt` 19:28, `precommit.txt` (rot)
15:56; für Familie 7 `auto_workspace.py` 13:45, `domain/identity/roles.py` 17:34, `config.json` 18:19,
`checks/legacy_role_reads.py` 18:22, `test_legacy_role_reads.py` 18:31, `auth.py` 19:38,
`test_remaining_role_carriers_use_site_role.py` 20:54, `identity_tenants.py` 20:58. Die Uhrzeiten, die vor
dieser Korrektur im Kopfstand dastanden (15:4x, 16:0x, 16:5x–17:0x), waren zu früh und sind ersetzt.
Quelle: Session
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

### B. Legacy-Rolle: die 7 Stellen aus der Messung — **alle 7 zu (04.10.)**

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
- [x] **7 — `bearer_user_role`-Familie (größte Fläche, null Testabdeckung).** ~10 Aufrufer
      (`chat_completions_api.py:31`, `chat_websocket.py:331`, `voice_realtime_websocket.py:85`,
      `domain/voice/realtime_turn.py:110-112`, `telegram_bridge.py:254`, `discord_bridge.py:377`,
      `bridge_agent_session.py` (4 Lesstellen), `bridge_agent_turn.py:99`, `scheduler.py:149`,
      `scheduler_jobs_runner.py:59`, `coding_schedule_execution.py:443`, `agent_tasks_runner.py:138`) →
      `domain/model_routing/resolution.py:104-112` (`_override_allowed`). Was sie entscheiden: **welches
      Modell ein Turn benutzen darf** — ein Override, ohne dass die kanonischen Regeln (Profil, Freigabe,
      Limit) greifen. In beide Richtungen kaputt.
      Zugehörig: `application/agent_runtime/use_cases/auto_workspace.py:82-88,127` verastelt sich selbst
      auf `db.user_role(user_id) == "admin"` **und** stempelt `u.role` auf das übergebene Objekt.
      **04.10. geschlossen — die Familie ist zugunsten einer Regel aufgelöst, nicht Aufrufer für
      Aufrufer.** Der Befund von unten hat sich bestätigt: die Lüge steckt im **Träger**, nicht in den
      Einzelzeilen. Also vier Schritte:
      1. **Reine Regel:** `apps/backend/domain/identity/roles.py` (neu) — `SITE_ADMIN`/`SITE_USER`,
         `ADMIN`/`USER`, `normalize_site_role`, `effective_role(site_role, legacy_role)`, `ELEVATED_SQL`.
         Der Legacy-Wert spricht **genau dann**, wenn `site_role` NULL ist — und `schema_111` beschränkt
         `site_role` auf `site_admin`/`site_user`, „NULL" **ist** also der Fall „nie migriert". Keine DB,
         keine Settings, kein Log.
      2. **Ein Resolver:** `infrastructure/db/identity_tenants.py::_role_columns(user_id) ->
         (site_role, legacy_role)` ist die **einzige** Stellenlesung des Paares; `user_site_role`
         (:123), `user_site_admin` (:129) und `user_effective_role` (:142) sitzen alle darauf.
         Fehlende id, fehlende Zeile, fehlgeschlagene Query → `(None, None)` → die Regel antwortet
         unerhöht. **`db.user_role` ist gelöscht**, nicht entmutigt: `grep -rn 'db\.user_role(' apps
         plugins --include='*.py'` → 2 Treffer, beide Prosa (`domain/scheduling/targets.py:124`,
         `domain/workspace/workspace_common.py:118`), 0 Aufrufe.
      3. **Choke Point:** `infrastructure/identity/auth.py` normalisiert **jede** `User(...)`-Konstruktion
         (`:186`, `:275`, `:320`, `:561`), auch `get_user_by_id` (`role=effective_role(row[3], row[2])`).
         Daraus folgt der Satz, der die halbe Familie überflüssig macht: **`.role` auf einem
         authentifizierten Objekt ist bereits die Auflösung** — die bearer-Fütterungen von Bridges,
         Runnern und `chat_completions_api` tragen also nicht die Spalte weiter, sondern das Wort.
      4. **Träger dicht gemacht:** `auto_workspace.py` astet über `db.user_site_admin` und stempelt kein
         `u.role` mehr; das Catalog-Tool nimmt sein Role vom Resolver statt aus einem Context-Key
         (`plugins/tools/platform/agents/catalog.py`); die Bridge-Agent-Tür und das Chat-Run-Objekt
         laufen über dieselbe Auflösung; `agent_effective_role(user_id, fallback_role)` antwortet aus dem
         Fallback **nur noch ohne id** — eine nicht lesbare Zeile verweigert, statt dem Claim zu glauben.
      **Getestet:** `tests/unit/test_remaining_role_carriers_use_site_role.py` (neu, **17 Tests**) —
      jede Fixture ist ein **Zeilenpaar** `(users.site_role, users.role)`, gepatcht an
      `identity_tenants._role_columns`, **nie** das Urteil eines Lesers. Vier Akteure (herabgestufter
      Legacy-Admin / Site-Admin / nie migriert / Zeile nicht lesbar) × Träger: Chat-Run-Objekt
      (`bootstrap_chat_run` wirklich aufgerufen, Run-Store geparkt), Agent-Tür der Application-Schicht,
      Catalog-Tool, Bridge-`/agent list`, Modell-Override-Tür, `User.role` des authentifizierten
      Objekts, Bearer-Carrier des OpenAI-Endpoints. Dazu „ein `x-role: admin`-Header ändert nichts" und
      „ein mitgetragener bearer-Claim macht den Träger nicht erhöht".
      Zwei Tests davon hängen nicht an einem Träger, sondern am Resolver selbst:
      `test_every_role_reader_costs_the_paired_statement_and_nothing_else` pinnt an einem
      aufzeichnenden Fake-Pool die **SQL**, die eine Rollenfrage kosten darf — ein Statement, beide
      Spalten (`SELECT site_role, role FROM users WHERE id = %s`) — und
      `test_the_legacy_reader_is_gone_from_the_facade` hält `user_role` von `identity_tenants` und der
      `db`-Fassade fern. An Sonde M4 (unten) trifft beide Schichten dieselbe Regression, und der
      Unterschied ist den Notiz wert: die drei Träger-Tests fallen dort **als Crash**
      (`RuntimeError: database pool not initialized`) weil die Sonde ihren Patchpunkt
      `_role_columns` umgeht, der Statement-Test fällt **sachlich** — er kennt kein Expected-Wort und
      meldet deshalb jede andere Statement-Folge.
      **Gate (neu):** `scripts/checks/checks/legacy_role_reads.py`, eingetragen in `fast`, `precommit`,
      `security`, `architecture`, `ci` (`python3 scripts/checks/run.py --check legacy_role_reads`);
      `scope: all` über `apps/backend`, `plugins`, `scripts`, Migrationen ausgenommen.
      Drei Regeln: `legacy-alone` (eine Statement, die `users` nennt und die Legacy-Spalte, ohne
      `site_role` dabeizuhaben), `pair-outside-identity` (eine Paar-Lesung außerhalb der drei
      Identitäts-Leser), `claim-read` (`getattr(obj, "role")` — ein Claim, der vom Objekt abgelesen
      wird, ist keine Elevation). Die Spalte wird an die `users`-Relation **ihrer eigenen** Statement
      gebunden, ein `m.role` neben `JOIN users u` bleibt unberührt. Ausnahmen liegen als **drei Pfade
      mit Begründung** in `scripts/checks/config.json` (`identity_pair_readers`: `identity_tenants.py`,
      `auth.py`, `persistence/postgres/identity_repository.py`), nicht als Zeilen-Freigabe. Der
      Repo-eigene Zustand ist selbst gepinnt: `tests/unit/test_legacy_role_reads.py` (neu, **19 Tests**)
      enthält `test_the_repository_is_clean` und `test_every_exemption_is_still_earned` — eine
      Ausnahme darf nicht ihren Anlass überleben.
      **Mutation Proof (04.10., vier Sonden; jede Datei danach per `cp` aus einer Vorab-Kopie zurück,
      Byte-Gleichheit mit `sha256sum` gegen die vorher gespeicherte Summe geprüft):**
      · **M1** — `auth.get_user_by_id` antwortet `role=row[2]`: **3 failures**, ausschließlich in der
      neuen Datei (`test_the_authenticated_user_object_carries_the_resolved_word`,
      `…bearer_carrier_forwards_the_authenticated_word_and_nothing_more`,
      `test_a_header_claiming_a_role_is_not_the_authenticated_word`). Der Index-Read ist dem AST-Gate
      **unsichtbar** — die beiden Schichten ergänzen sich, keine allein reicht.
      · **M2** — Chat-Run stempelt `bearer_user_role or _role_for_agent`: exakt
      `test_a_carried_bearer_claim_still_does_not_make_the_carrier_elevated` fällt.
      · **M3** — neue Datei mit `SELECT id, role FROM users WHERE id = %s`: `--check legacy_role_reads`
      → `FAILED - 1 legacy role-column read(s) in 974 file(s)` mit Regel `legacy-alone` und Fix-Hinweis;
      parallel fällt `test_the_repository_is_clean`. Sonde danach gelöscht.
      · **M4** — `user_site_admin` umgebaut auf eine eigene Single-Column-Query
      (`SELECT role FROM users WHERE id = %s`) am Resolver vorbei: `--check legacy_role_reads` →
      `FAILED` mit `identity_tenants.py:143 [legacy-alone]` — die Ausnahme der Datei gilt **nur** für
      die Paar-Lesung. In `tests/unit/test_remaining_role_carriers_use_site_role.py` fallen vier Tests:
      der Statement-Pin sachlich, `test_the_chat_run_carrier_carries_the_resolved_word`,
      `test_a_carried_bearer_claim_still_does_not_make_the_carrier_elevated` und
      `test_the_agent_door_ignores_a_role_claim_on_the_caller_object` als Crash. Datei per `cp`
      zurück, `sha256sum -c` → `OK`.
      **Was die Sonden trafen:** M1 und M2 saßen in Dateien, die **vor** Familie 7 geändert wurden
      (`auth.py` = Familie 4, `chat_run_bootstrap.py` = der Träger selbst) — die neuen Tests schlagen
      also auf bestehendem Code zurück, nicht nur auf dem neuen. M3 traf den Fall „neue Datei", M4 den
      Fall „Resolver umgebaut".
      **Ehrliche Restlücken:** (a) **der App fehlt der Weg, `site_role` zu *ändern*.** Geschrieben wird
      die Spalte an zwei Stellen: beim **Anlegen** eines Kontos — `auth.py:539` leitet sie aus dem
      Wort ab, das der Admin im Formular wählt, `auth.py:542` schreibt sie ins `INSERT` — und beim
      Backfill `schema_111_identity_roles_deployment_mode.py:43-44`. **Kein** `UPDATE` erreicht sie:
      `grep -rn "UPDATE users SET" --include='*.py' apps/backend plugins | grep -i site_role` → nur die
      zwei Migrations-Zeilen; `PATCH /v1/admin/users/{id}` kennt kein `site_role`-Feld
      (`api/platform/controllers/admin_users_api.py`, die Feldkette endet bei `llm_queue_priority`;
      `:160` **liest** die Spalte nur für die Scope-Frage). Herabstufen bleibt ein SQL-Vorgang des
      Operators — dieses Werk nimmt dem zurückgelassenen `role='admin'` die Entscheidungskraft, nicht
      den Wert. Nebenbei, ehrlich: **beim Anlegen entscheidet das Formularwort `role` immer noch über
      `site_role`** (`role='admin'` → `site_admin`); die Kopplung ist gewollt (sonst legt niemand mehr
      Admins an), aber sie ist die eine Stelle, wo das Legacy-Feld noch nach *vorn* wirkt.
      (b) Der E2E-Stack läuft nicht (Abschnitt F), ein Nachweis an einer echten DB steht aus.
      (c) `tenant_scope` meldete beim Commit **vier** weitere ungestonte Statements (drei davon
      **vorbestehend**, hochgekommen, weil `scope: staged` den dirty Tree liest):
      `chat_run_bootstrap.py:105/:303`, `bridge_agent_session.py:131` — alle drei durch `user_id`
      abgesichert und jetzt mit `# tenant-scope: guarded by user_id …` markiert; der vierte ist meine
      eigene `_role_columns`-Lese, markiert als `site-wide` wie ihr Zwilling `auth.get_user_by_id`.

Zwei Dinge, die den Befund schärfer machen als „nur ein falsches Feld":

- `infrastructure/scheduling/scheduler_jobs_store.py:293-299` dokumentiert ausdrücklich *„actor_is_admin
  is the caller's already-resolved right, never a role read"* — der Aufrufer hielt sich nicht daran.
  (Mit Block 1 behoben; der Vertrag steht jetzt auch auf den Call-Sites.)
- `application/agent_runtime/runtime/io.py` baute ein `_UserRef` mit `role = None`; damit war die
  Legacy-Lese in der DB der **einzige** Entscheider. Der Zweig ist mit `8312afaf` entfernt (1 Zeile).

**Messgröße für den Rest:** nach Block 1 standen 23 `db.user_role(`-Vorkommen in 17 Dateien, nach
Familie 6 **22 in 16 Dateien** (02.10. 23:52), nach Familie 5 **21 in 15 Dateien** (03.10. 13:52; jeweils
`grep -rn 'db\.user_role(' apps plugins --include='*.py'`). Nach Familie 7 (04.10.) steht dasselbe
Kommando mit **2 Treffern in 2 Dateien — beide Prosa, 0 Aufrufe** (`domain/scheduling/targets.py:124`,
`domain/workspace/workspace_common.py:118`); die Funktion selbst ist aus
`infrastructure/db/identity_tenants.py` und der `db`-Fassade entfernt, und
`test_the_legacy_reader_is_gone_from_the_facade` hält sie fern. Die Zahlen unterhalb bleiben als Messung
vom 03.10. stehen. Die 21 teilen sich genau: **15 decisive
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
- [x] Gap-Zeile **viertens** fortgeschrieben (04.10.): sie behauptet keine offene Familie mehr. Beide
      Familien stehen in der Vergangenheit, als „04.10. geschlossen — und mit ihnen die Lesstelle", mit
      der Messung im Text (`grep -rn 'db\.user_role(' apps plugins --include='*.py'` → zwei Prosa-Zeilen,
      0 Aufrufe), dem Choke-Point-Satz („`.role` auf einem authentifizierten Objekt ist die Auflösung"),
      dem, was die Familie entschied (`_override_allowed`, Bridge-`min_role`-Tür, Chat-Run-Objekt), dem
      Versagen beim nicht lesbaren Akteur, dem neuen Test, dem Gate und seinen Mutationen. Der
      Schlusssatz der Sektion ist ersetzt: der `agent_effective_role`-Fallback antwortet **nur ohne id**,
      und die drei Scheduler-Tools lösen seit diesem Schwung selbst (`db.user_effective_role(caller_uid)`
      in `plugins/tools/platform/scheduler/jobs.py:93,188,219`).
- [x] **ADR 0011 §1 berichtigt (04.10.).** Der Halbsatz, die Spalte werde „noch von Legacy-Flächen
      gelesen", war eine **Aussage über heute** und damit falsch, nicht Geschichte — zurückgezogen auf den
      Stand der Entscheidung, ergänzt um die heutige Messung. Der Consequences-Teil ist nachgelesen und
      korrekt; dort ist nichts geändert.
- [x] **P1–P8 nachgemessen (04.10.).** `docs/planning/roles-and-agent-assignment-analysis.md` behauptete
      „komplett erledigt am 16.09." — sein neuer **Abschnitt 9** hält den heutigen Stand pro Paket fest,
      jeweils mit dem **Kommando**, das ihn misst: sechs Pakete fertig, **P3** ohne Bulk über mehrere
      Personen, **P5** ohne Tenants-Tab, **P7** ohne KI-Vorfilter (gebaut ist nur die regelbasierte
      Tool-Warnung `_tool_warnings`), und als Rest dieselbe `site_role`-Schreiblücke wie (a) oben.
      Frontmatter-Status dort: `done-with-gaps-see-section-9`.

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
- [ ] **Das Precommit-Gate ist rot, ohne dass jemand am Frontend etwas geändert hat (03.10. 15:5x).**
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
      03.10. 19:28 (mtime von `.qwen/tmp/fam5/commit_attempt.txt`; die erste Notiz hier sagte 15:4x und war
      falsch): der Hook hat den Commit zu Familie 5 mit `[check:node_cve_full] FAILED - exit code 1`
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

- [ ] **PR → main steht aus; der Push nicht mehr.** **04.10. 01:02 auf ausdrückliche Weisung gepusht**
      (`git reflog` der Remote-Ref: „update by push"), Fast-Forward `e920fbf3..d53a0950` — sechs Commits:
      `8312afaf`, `4ba62ca8`, `ff894966`, `f80b44bb`,
      `7384e917` (Familie 5), `d53a0950` (Tailwind-Major). Nachgemessen nach dem Push:
      `git rev-list --count origin/feat/chat-persist-queue-goal-strip..HEAD` → **0**,
      `git rev-list --count main..HEAD` → **183**; `origin/…` = `d53a0950`, `main` = `9aa96e19`.
      Vorher standen dieselben Messungen **5** bzw. **182** (nach `7384e917`) und **6** bzw. **183**
      (nach `d53a0950`) — die ältere Zeile „noch nicht gepusht, HEAD war `4ba62ca8`, 2 vor `origin`"
      beschreibt den Stand des Snapshots und ist überholt.
    - **Die Zahl oben gilt für `d53a0950`, nicht für diesen Text.** `cf670560` hat diesen Abschnitt
      geschrieben; nach ihm gemessen: **184** auf `main`, **0** ungepusht. Der Commit, in dem
      dieser Nachsatz steht, ist schon der nächste, und jeder danach zählt weiter. Maßgeblich ist darum
      das Kommando, nicht die Zahl: `git rev-list --count main..HEAD` für den Abstand zu `main`,
      `git rev-list --count origin/feat/chat-persist-queue-goal-strip..HEAD` für die Frage, ob der
      letzte Stand draußen ist — nach jedem Push wieder **0**.
    - **Der Push ändert nichts an der CI-Lage:** `.github/workflows/ci.yml` triggert nur `pull_request`
      und `push: [main]`, ein Push auf diesen Branch also **kein Lauf**. (Live nachzusehen war das hier
      nicht — auf diesem Rechner ist kein `gh`-CLI; die Aussage steht auf der Workflow-Konfiguration.)
      **Auf diesem Branch ist damit weiterhin nie CI gelaufen.** Der
      erste Lauf ist gleichzeitig der erste Test von D (Bandit) — vorher mit ihm die Gate-Form klären,
      sonst ist der PR rot, bevor er gelesen wurde.
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
| **Familie 5 — precommit-Profil** (03.10. 15:56 = mtime von `.qwen/tmp/fam5/precommit.txt`) | **FAILED**: 26 Checks grün, **`node_cve_full` exit 1** (npm-audit-Kette `braces`→`micromatch`→`fast-glob`→`chokidar`/`tailwindcss`, 5 high — Details in D). Backend-Suite im Lauf: **2 397 passed, 3 skipped, 2 deselected**. Kein Skip benutzt, der Versuch bringt keinen Commit |
| **Familie 5 — Commit-Versuch** (03.10. 19:28 = mtime von `.qwen/tmp/fam5/commit_attempt.txt`) | `git commit -F .qwen/tmp/fam5/msg.txt` → `[check:node_cve_full] FAILED - exit code 1`, `[pre-commit] FAILED`, **EXIT=1**: kein Commit. Die sechs Pfade bleiben **gestaged** (neue Testdatei als `A`), die fertige Message liegt als `.qwen/tmp/fam5/msg.txt`; der Gegencheck auf `git ls-tree -r HEAD` steht darum noch aus — **erledigt 23:35** nach dem grünen Lauf, zwei Zeilen weiter unten |
| **Tailwind — Baseline v3** (03.10., vor dem Major) | `npm run build` Exit 0, ausgeliefertes Stylesheet **70 380 B** roh / **13 544 B** gzip (`.qwen/tmp/tw4/v3.css`) |
| **Tailwind — erster v4-Build** (03.10.) | kompiliert, **aber** Guard-Fixtures mit drin: **107** Rohtoken-/Arbitrary-Klassen im ausgelieferten Stylesheet (gezählt über `bg-*-*`, `z-[…]`, `max-w-6xl` u. ä.); Auslöser: negated glob wird ignoriert |
| **Tailwind — finaler Build** (03.10.) | `npm run build` **EXIT=0**, **20/20 Design-Guards** OK, Stylesheet **100 430 B** roh / **16 927 B** gzip; die sechs nachgeprüften Klassen (`bg-red-500`, `bg-indigo-500`, `border-rose-500`, `text-rose-400`, `z-[999]`, `max-w-6xl`) **0×**; `.shadow-xs` vorhanden, `.shadow-sm` **0**, `.outline-hidden` **2 Regeln** (Basis + `@media (forced-colors:active)`), `cursor:pointer` **2**, `appearance:textfield` **1** |
| **Tailwind — Vitest** (03.10.) | **55 Dateien / 625 Tests passed** (Baseline vorher: 54 / 615 — genau die neue Datei und ihre 10 Fälle) |
| **Tailwind — Mutationen an `preflight-compat.test.ts`** (03.10.) | **sechs**: `shadow-sm` in eine Klasse schreiben, `outline-none` wieder einsetzen, `cursor: pointer` aus `index.css` nehmen, die `@source not`-Zeile löschen, `@config` löschen, den `[type=search]`-Block löschen — jeweils **1 failed**, zurück per `cp` + `md5sum -c` OK, danach wieder grün |
| **`node_cve_full` nach dem Major** (03.10.) | `npm audit --audit-level=high` → **EXIT=0**, nur **2 moderate** (`react-router-dom`/`react-router`, `deserializeErrors()`) |
| **Familie 5 — precommit-Profil nach dem Major** (03.10.) | `python3 scripts/checks/run.py --profile precommit` → **all checks passed**, **EXIT=0** (alle 26 des Profils, `node_cve_full` inklusive) |
| **Familie 5 — Commit** (03.10. 23:35) | `git commit -F .qwen/tmp/fam5/msg.txt` → Hook **all checks passed**, **`7384e917`**, **6 files changed, 358 insertions(+), 77 deletions(-)**; Gegencheck: `git ls-tree -r HEAD --name-only \| grep -c test_dashboard_rights_use_site_role` → **1**, die Commit-Ausgabe führt die neue Testdatei mit `create mode 100644` |
| **Tailwind-Schwung — Zeiten** (`mtime`, 03.10.) | Baseline-Backups `package.json`/`lock`/`index.css`/`postcss.config.js`/`tailwind.config.js` **21:02**, v3-Build **21:09**, erster v4-Build **21:30**, `@source`-Build **21:44**, Umbau-Build **21:59**, finaler Build **22:22** und bestätigt **22:37**, Mutationen bis **22:29** |
| **Major — Commit + Amend** | `git commit` **03.10. 23:43** → `fa3dddbe`, Ausgabe: **42 files changed, 637 insertions(+), 1057 deletions(-)** und `create mode 100644 apps/frontend/src/ui/preflight-compat.test.ts` (`.qwen/tmp/tw4/commit_tw.txt`); Gegencheck im Baum: `git ls-tree -r HEAD --name-only \| grep -c src/ui/preflight-compat.test.ts` → **1**. Amend nach dieser Doku-Korrektur **04.10. 00:13** → **`d53a0950`** (da ungepusht, darum zulässig). Gegen den alten Hash: `grep -rn "fa3dddbe" docs/` → **kein Treffer** |
| **Vitest auf dem committeten Stand** (03.10. 23:46) | `npm run test` → **55 files / 625 tests passed**, **VITEST_EXIT=0** |
| **Push** (`git reflog` der Remote-Ref) | **04.10. 01:02:10 +0200 — „update by push"**, Fast-Forward `e920fbf3..d53a0950`; danach nachgemessen: `git rev-list --count origin/feat/chat-persist-queue-goal-strip..HEAD` → **0**, `git status -sb` → **keine** ahead/behind-Markierung |
| **Familie 7 — Tests** (`python3 -m pytest tests/unit/test_remaining_role_carriers_use_site_role.py tests/unit/test_legacy_role_reads.py -q`) | **36 passed** — 17 Actor-×-Träger- bzw. Resolver-Tests und 19 Selbstpinnen des Gates |
| **Familie 7 — einzelne Datei** (`python3 -m pytest tests/unit/test_remaining_role_carriers_use_site_role.py -q`) | **17 passed in 0.22 s** |
| **Familie 7 — Gate** (`python3 scripts/checks/run.py --check legacy_role_reads`) | `passed` (974 Dateien im Scope) |
| **Familie 7 — Legacy-Leser** (`grep -rn 'db\.user_role(' apps plugins --include='*.py'`) | **2 Treffer, beide Prosa** (`domain/scheduling/targets.py:124`, `domain/workspace/workspace_common.py:118`) |
| **Familie 7 — wer schreibt `site_role`?** (`grep -rn "UPDATE users SET" --include='*.py' apps/backend plugins \| grep -i site_role` **und** `grep -rn "INSERT INTO users" --include='*.py' apps/backend plugins`) | kein `UPDATE` erreicht die Spalte (die Updates treffen Entitlement-Spalten, `api/platform/controllers/admin_users_api.py:186,192,198,204,222` u. a.); geschrieben wird sie im `INSERT` beim Anlegen (`identity/auth.py:539,542`, abgeleitet aus dem Formularwort `role`) und im Backfill `schema_111_identity_roles_deployment_mode.py:43-44`. **Ändern kann sie die App nicht** — Herabstufen bleibt SQL |
| **Familie 7 — Mutationen** | **M1** `auth.get_user_by_id` → `role=row[2]`: **3 failed** (die drei Auth-Träger). **M2** Chat-Run stempelt `bearer_user_role or …`: **1 failed**. **M3** neue Datei mit `SELECT id, role FROM users`: Gate `FAILED - 1 legacy role-column read(s) in 974 file(s)` + `test_the_repository_is_clean`. **M4** `user_site_admin` mit eigener Single-Column-Query: Gate `identity_tenants.py:143 [legacy-alone]` + **4 failed** (1 sachlich, 3 als Crash). Jede Sonde per `cp` zurück, `sha256sum -c` → **OK** |
| **Familie 7 — ganze Suite** (`python3 -m pytest tests/unit -q`, 04.10.) | **2328 passed, 2 skipped** — zwei Läufe 04.10.: **23.09 s** (vor den Doku-Edits) und **24.76 s** (direkt vor dem Commit, nach dem Resolver-Cleanup und §9 der Analyse-Doku). Vor dem Schwung 2 326; die Differenz sind die zwei Resolver-Pins |
| **Familie 7 — precommit direkt vor dem Commit** (`python3 scripts/checks/run.py --profile precommit`, 04.10.) | **`[checks] all checks passed`**, EXIT=0, **real 0m52.860s** — **kein** Skip-Flag (`SKIP_CHECKS`/`SKIP_PRE_COMMIT`) benutzt oder nötig. Der Hook beim `git commit` läuft danach ein zweites Mal; maßgeblich ist sein Ergebnis |
| **Familie 7 — Umfang der Änderung** (`git diff --staged --shortstat` nach `git add -- apps plugins scripts tests docs`; Pfade mit `git diff --staged --name-status`) | **51 Dateien, 1594(+) / 388(−)** — gemessen 04.10. nach dem Stage; **diese Zeile wird nach dieser Messung geschrieben** und verschiebt den Wert um ihre eigene Länge, maßgeblich für den Schwung ist die Commit-Ausgabe. **Vier** Pfade stehen als `A` (also neu): `domain/identity/roles.py`, `scripts/checks/checks/legacy_role_reads.py`, `tests/unit/test_legacy_role_reads.py`, `tests/unit/test_remaining_role_carriers_use_site_role.py`. Gegenprobe auf Löschungen: `git diff --staged --name-status \| grep -c "^D"` → **0**. Nötig war sie: `application/identity/commands/__init__.py` stand vor dem Stage als **Löschung** im Index, während die Datei auf Platte lag (Zustand nach `git rm --cached`) — ohne das eine `git add` hätte der Commit das Modul gelöscht; nach dem Stage steht es als `M` |

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
3. ~~**Familie 7 als nächster Schwung**~~ **erledigt 04.10.** Die 15 getragenen Lesungen sind nicht
   Aufrufer für Aufrufer umgestellt, sondern **zugunsten einer Regel aufgelöst**: reine Regel in
   `domain/identity/roles.py`, ein Resolver (`identity_tenants._role_columns`), Choke Point in `auth.py`,
   dazu `db.user_role` **gelöscht** (2 Prosa-Treffer, 0 Aufrufe). Die `min_role`-Tür der Bridge
   (`bridge_agent_session.py`) fragt jetzt denselben Resolver; `auto_workspace` astet über
   `db.user_site_admin` und stempelt kein `u.role` mehr. Null Testabdeckung ist sie nicht mehr: 17 Tests
   mit Zeilenpaaren als Fixture, dazu ein AST-Gate (`legacy_role_reads`) mit Selbstpinnen und vier
   Sonden — alles in Abschnitt B/7 und Abschnitt 4.
   **Was von diesem Punkt übrig bleibt:** (a) **der Schreibpfad** — keine Runtime-Codezeile setzt
   `users.site_role`, Herabstufen ist ein SQL-Vorgang des Operators; (b) **der E2E-Nachweis** an einer
   echten Instanz (Abschnitt F); (c) der PR (Punkt 5).
4. **Eine Gate-Form bleibt zu entscheiden, bevor der PR eröffnet wird** (D): **Bandit** (`-lll` gegen 83
   B608). Die zweite — **`node_cve_full`** — ist entschieden und erledigt: der Owner wollte das
   tailwindcss-Major statt des Provider-Wechsels, es ist 03.10. gezogen (D, Maße in Abschnitt 4). Der
   Hook lässt wieder jeden Commit durch.
5. **PR bleibt bei ihm (E).** Der Push ist erledigt: 04.10. 01:02 auf seine Weisung, Fast-Forward
   `e920fbf3..d53a0950`, `origin/feat/chat-persist-queue-goal-strip` = `d53a0950`, ungepushte Commits
   **0**. Der PR ist der Teil, der extern sichtbar ist — und der einzige, der CI auslöst.
