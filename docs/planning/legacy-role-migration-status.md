---
doc_id: legacy-role-migration-status
domain: agentlayer_docs
tags: [planning, rbac, site-role, legacy-column, security, handoff]
status: in-progress
---

# Legacy-Rollen-Migration — vollständige Aufgabe, Stand, Restarbeit

**Record, kein lebendes Dokument.** Snapshot **02.10.2026, 22:15**, fortgeschrieben **02.10., 23:14**
(Commit des Blocks + Tooling-Commit, Abschnitt A). Quelle: Session
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

### B. Legacy-Rolle: die 7 Stellen aus der Messung — 4 zu, 3 offen

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
- [ ] **5 — Dashboards.** `infrastructure/dashboard/dashboard_access.py:158,165-169` liest
      `db.user_role(uid)` und gibt `user_role=db_role or role` weiter →
      `domain/dashboards/access.py:32-35` prüft `role == "admin"` **vor** `site_role == "site_admin"`.
      Gewährt die Dashboard-Rechte. (Heute verifiziert: beide Stellen unverändert.)
- [ ] **6 — Task-Freigabe.** `plugins/tools/platform/tasks/agent_tasks.py:88` →
      `role = db.user_role(user_id)` → `domain/agent_runtime/task_approval.py:21-25,34-35`. Wer ein
      Task direkt an `queued` (also an der Freigabe vorbei) setzen darf, entscheidet die Legacy-Spalte.
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

**Messgröße für den Rest:** nach Block 1 stehen noch **23** `db.user_role(`-Vorkommen in 17 Dateien.
Davon sind 3 rein dokumentarisch (`domain/workspace/workspace_common.py:118`,
`domain/scheduling/targets.py:122`, `application/identity/use_cases/request_auth.py:73`) und die in
`plugins/tools/platform/scheduler/jobs.py:93,188,219` sind bewusste **Fallbacks**
(`agent_effective_role(uid, db.user_role(uid))` — Legacy nur, wenn die `site_role`-Lese nicht
verfügbar ist). Der decisive Rest sind die Familien 5–7.

### C. Doku

- [x] Gap-Zeile in `docs/features/operator-agent.md:235` neu geschrieben: drei offene Familien
      (Runner/Bridges, zwei Domain-Regeln, `auto_workspace`) und explizit aufgelistet, was am 02.10.
      geschlossen wurde, inkl. Name des neuen Tests.
- [x] **staged und committet** — sitzt in `8312afaf` (Zeile 235, Text unverändert gegenüber dem Snapshot).
- [ ] **dieses Dokument: committen oder löschen?** Steht bewusst noch als `??` im Worktree — es ist ein
      Record über Restarbeit, kein lebender Text. Passt es als Handoff nach `docs/planning/`, gehört die
      Frage in denselben Rutsch wie die beiden Commits; wenn nicht, löscht ihn, bevor er vergilbt.

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
- [ ] **Frontend-Tests und Produktions-Build sind in CI nicht gecastet.** Das `ci`-Profil enthält die
      `frontend_*`-Guard-Skripte und `frontend_i18n`, aber **weder** `npm run test:unit` (Vitest) **noch**
      `npm run build`. Beides ist lokal grün gemessen (01.10. in der Session), nur eben nirgends Pflicht.
- [ ] `python_cve`/`node_cve_full` hängen am Registry-Endpunkt — ein `400 Invalid package tree` ist ein
      Registry-Fehler (Retry), kein Lockfile-Problem. (`node_cve_full` ist nach `--audit-level=high`,
      moderate Funde blockieren nicht.)
- [ ] *Nicht nachgemessen:* „Config-Check hat 224 Dateien nie gescort" — Zahl stammt aus der Session
      vom 02.10. und wurde hier nicht überprüft.

### E. Merge-Lage

- [ ] **PR → main steht aus.** `HEAD = 4ba62ca8`, **2 Commits vor** `origin/feat/chat-persist-queue-goal-strip`
      (die beiden von 02.10. 23:14 — **noch nicht gepusht**, braucht sein Go), der Branch läuft
      **177 Commits** vor `main` her; `main` zuletzt `9aa96e19`.
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

**Nicht ausgeführt:** das `ci`-Profil, Vitest und `npm run build` (laufen beide nirgends Pflicht — D).
„21 passed" sind die drei Dateien, die den Block abdecken; die **ganze** Backend-Suite lief dagegen im
Hook: 2 376 passed.

---

## 5. Reihenfolge-Empfehlung

1. ~~**Block fertig committen** (A)~~ **erledigt 02.10. 23:14**: Profil → `8312afaf` → `git
   ls-tree`-Gegenprobe → `4ba62ca8` für `shell.nix`. Die halbe Lücke (1–4) ist im Baum, die Doku ehrlich.
2. **Familie 6 dann 5** (Task-Freigabe, Dashboards) — klein, klar abgrenzbar, je ein Mutationstest
   („Legacy-Zweig entfernen → Test muss fallen"), wie in Block 1.
3. **Familie 7 zuletzt und als eigener Schwung** — größte Fläche, keine Abdeckung. Zuerst die
   Testabdeckung auf `_override_allowed` bauen (heute null), dann die Aufrufer umstellen.
4. **Gate-Form für Bandit entscheiden, bevor der PR eröffnet wird** (D + E), sonst ist der erste CI-Lauf
   des Branches aus einem Grund rot, der nichts mit dem Change zu tun hat. Seit der Messung von 23:11
   steht die Entscheidung zwischen `-lll` (grün, weil kein Severity-HIGH) und 83 B608.
5. **Push + PR** sind derselbe sichtbare Schritt und liegen bei ihm (E).
