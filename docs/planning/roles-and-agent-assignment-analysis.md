---
doc_id: roles-and-agent-assignment-analysis
domain: agentlayer_docs
tags: [planning, rbac, tenant, identity, site-admin, agent-access, people-ui]
status: done-with-gaps-see-section-9
---

# Rollen, Tenants und Agent-Freigaben — Analyse & zerlegte Arbeitspakete

**Stand:** Analyse 12.09.2026 · Umsetzung P1–P8 ab 16.09.2026 (`5284f0e` … `5ef7efc`) ·
**Nachmessung 04.10.2026 (Abschnitt 9): „komplett erledigt" war zu weit.** Sechs von acht Paketen sind
vollständig, **P3** und **P5** sind teilweise, und der **KI-Vorfilter aus P7 existiert nicht**. Abschnitt 9
steht jedes Paket mit dem **Kommando**, das seinen Stand misst — nicht mit einem Wert, der vergilzt.

**Maßgeblich heute ist nicht dieses Dokument**, sondern
[`ADR 0011`](../adr/0011-roles-and-agent-access-without-tenancy.md) (die Entscheidung und ihre
Restrisiken) und
[`features/agent-registry-and-allowlists.md`](../features/agent-registry-and-allowlists.md)
(die aktuellen Ankerpunkte in Code). Die Pfad- und Feldnamen im Text unten sind der Stand vom
12.09. und teils überholt — **B10** (Doku-Irrtum `agent_registry.py` / Legacy-Feldnamen) ist mit
`5ef7efc` behoben. Der Analyse-Text selbst bleibt ungeändert: er hält fest, wie das Problem am
12.09. gesehen wurde, nicht wie der Code heute aussieht.

**Bezug:** [`knowledge-companion/00-roles-and-scopes.md`](./knowledge-companion/00-roles-and-scopes.md) (kanonisches 3-Ebenen-Rollenmodell),
[`knowledge-companion/03b-identity-roles-and-surfaces.md`](./knowledge-companion/03b-identity-roles-and-surfaces.md),
[`knowledge-companion/05-profession-rbac.md`](./knowledge-companion/05-profession-rbac.md),
[`knowledge-companion/07-tenant-templates.md`](./knowledge-companion/07-tenant-templates.md).
**Ziel:** Klären, wie Agent-Auswahl pro Tenant/User gesteuert wird, was am Rollenmodell schon trägt,
und in welcher Reihenfolge die Lücken geschlossen werden.

---

## 1. Anwendungsfall (warum das hier steht)

Die Instanz läuft privat für mehrere Freundesgruppen (~10 Personen) mit unterschiedlichen Rechten:
eine Person soll programmieren dürfen (Coding-Agent + Workspace), andere nur plaudern/wissen,
wieder andere sollen Dashboards oder Workspaces gar nicht dürfen. Gewünscht ist Verwaltung **pro
Person**, nicht über Organisationsstrukturen, trotzdem mit dem Wunsch nach eigenen Rollen mit Rechten
und langfristig nach Agent-Einreichungen mit Validierung.

## 2. Entschlossene Zielrichtung

| # | Entscheidung | Konsequenz |
|---|--------------|------------|
| D1 | **Tenant-System aus** (`operator_settings.deployment_mode = agent_system`) | Alle Nutzer in Tenant 1; `/v1/org/*`, `require_tenant_admin`, `require_tenant_member` und die Profession-Policy in `/auth/me` sind deaktiviert (404). Freundesgruppen bleiben virtuell. |
| D2 | Rechte **pro User** statt pro Tenant | `agent_access_policies` (scope `user`) + Entitlement-Spalten auf `users` sind der richtige Ort. |
| D3 | Eigene **benutzerdefinierte Rollen mit Rechten** gewünscht | Widerspricht D1 und muss aufgelöst werden → §5 (Weg A vs. Weg B). |
| D4 | **Agent-Einreichung** mit **KI-Vorprüfung + manuellem Global-Admin-Review** | Menschliches Gate bleibt Pflicht; KI ist Vorfilter. Blocker: Agenten sind Dateimaterial → §6. |
| D5 | Agenten im Chat **auswählbar**, gefiltert nach eigenen Rechten | Benötigt eine authoritative, gefilterte Agent-Sicht (heute hartcodiert). |

## 3. Was bereits existiert (und nur verdrahtet werden muss)

| Fähigkeit | Status | Beleg |
|-----------|--------|-------|
| Globaler Admin („site admin") | vorhanden | `users.site_role ∈ {site_admin, site_user}` (`schema_111`), `require_site_admin()` in `apps/backend/infrastructure/identity/auth.py`; `require_admin` ist ein Alias davon |
| Tenant-Rollen | vorhanden | `tenant_memberships.membership_role ∈ {tenant_owner, tenant_admin, tenant_member}` (`schema_111`), `db.user_membership_role()` in `apps/backend/infrastructure/db/identity_tenants.py` |
| Tenant-System aus | vorhanden | `operator_settings.deployment_mode` (`schema_111`), gelesen via `operator_settings_readers.deployment_mode()`; `agent_system` = „single team, no /org UI" |
| **Agent-Freigabe pro User** | **vorhanden, ohne UI** | Tabelle `agent_access_policies` (`schema_109`): `scope ∈ {global, tenant, user}`, `direct_state`/`delegate_state ∈ {inherit, allow, deny}`; Store `apps/backend/infrastructure/agent_runtime/agent_access_policy_store.py`; `PUT`/`DELETE /v1/admin/agents/{agent_id}/access-policy` (`apps/backend/api/agents/controllers/agents_admin_api.py`) |
| Agent-Freigabe pro Tenant | vorhanden, ohne UI | Knob `chat.allowed_agent_ids` (+ `delegate.allowed_agent_ids`) in `agent_config_overrides`; gesetzt nur durch Tenant-Templates (`apps/backend/application/tenant_provisioning/use_cases/tenant_capability_policy.py`) |
| Workspace pro User erlauben | vorhanden | `users.workspace_self_allowed`, `users.workspace_quota`; globaler Default `operator_settings.workspace_allow_self_editing`; editierbar via `PATCH /v1/admin/users/{id}` |
| Weitere per-User-Entitlements | vorhanden | `schedules_allowed`, `media_enabled`, `media_upload_enabled`, `media_sharing_enabled`, `media_storage_quota_mb`, `llm_queue_priority` |
| Freundes- + Sharing-System | vorhanden | `friends`, `friend_requests` (`schema_037`), API `/v1/friends*` (`apps/backend/api/sharing/controllers/friends_api.py`), UI `apps/frontend/src/pages/settings/FriendsSettings.tsx`; Generisches Teilen: `share_permissions` (`schema_039`, `schema_074`), `dashboard_members`, `media_share_grants`, `user_kb_note_shares`, Public-Link-Tokens |
| RBAC-Keim für eigene Rollen | ansatzweise | `tenant_departments`, `tenant_profession_roles`, `user_profession_assignments`, `user_qualifications` (`schema_113`); Capabilities hardcodiert in `apps/backend/domain/tenant_profession/policy.py` |
| Agent-Import | nur Vorschau | `POST /v1/admin/agents/import/analyze` (`agents_import_admin_api.py`) — heuristisch, **ohne Persistierung**, ohne Review |

### 3.1 Die vier Gating-Schichten für `agent_id`

Durchgesetzt wird an **einer** Stelle: `apps/backend/domain/agent_runtime/access.py` →
`user_may_invoke_agent()`, aufgerufen im Chat-Turn (`apps/backend/application/agent_runtime/use_cases/chat_run_bootstrap.py`)
und im Bridge-Pfad (`apps/backend/infrastructure/integrations/bridge_agent_session.py`).

1. `agent.yaml → min_role: admin` — **harte** Denial; keine Policy kann sie übersteuern (`domain/agent_runtime/governance.py`, `direct_hard_denied`). Betroffen: `operator`, `reviewer`, `security_auditor`.
2. Basis-Regel für Nicht-Admins: nur `general` und `knowledge_companion` (`ENDUSER_ALLOWED_AGENT_IDS`).
3. Tenant-Allowlist `chat.allowed_agent_ids` — gilt **nur für Nicht-Admins** („not enabled for your organization").
4. `agent_access_policies` global → tenant → user, letzte Zeile gewinnt.

## 4. Kritische Befunde

- **B1 — `users.role == 'admin'` ist überladen.** `db.user_site_role()` mappt Legacy-`role='admin'` auf
  `site_admin` (Instanz-Admin), und `is_elevated_role()` gibt damit **alle** Agents frei und hebelt
  die Tenant-Allowlist aus. **Bis P1 erledigt ist, darf kein Freund `admin` bekommen.**
- **B2 — `GET /v1/agents` ist ungefiltert.** `apps/backend/api/agents/controllers/agents_api.py` liefert
  jedem eingeloggten Nutzer alle Agents **inklusive `system_prompt`** und Tool-Konfiguration.
  `fetchAgents()` (`apps/frontend/src/lib/api.ts`) ist toter Code.
- **B3 — Der Chat-Picker ist hartcodiert.** `apps/frontend/src/features/chat/chatAgentSelection.ts`
  (`DEEP_LINK_AGENT_IDS = {knowledge_companion, coding_qwen}`), übriges fällt auf `general` zurück.
- **B4 — `require_permission(action, resource_type)` prüft nichts.** Die Dekoration in
  `apps/backend/infrastructure/identity/auth.py` lässt Site-Admins durch und setzt nur die
  Tenant-Identität; `action`/`resource_type` werden gegen nichts validiert. Neue Rechte brauchen
  explizite Checks im Handler (Konvention: `await require_admin(request)` am Anfang).
- **B5 — Scheduling ignoriert Tenant-/User-Policies.** `apps/backend/domain/scheduling/targets.py`
  prüft nur `schedulable` und `min_role`. Ein Nutzer mit Schedules-Recht kann Agents über Jobs
  erreichen, die im Chat gesperrt sind.
- **B6 — Maximal eine Rolle pro User.** `user_profession_assignments` hat PK `(user_id, tenant_id)`.
  „Coder *und* Dashboard-Editor" ist heute nicht darstellbar.
- **B7 — Kein `roles`-/`user_roles`-Table, kein `is_superadmin`, keine `ADMIN_EMAILS`, kein Self-Signup,
  keine Invites.** Accounts legt ausschließlich der Admin an (`POST /v1/admin/users`). Erster Admin:
  `AGENT_INITIAL_ADMIN_EMAIL`/`AGENT_INITIAL_ADMIN_PASSWORD` oder Setup-Wizard.
- **B8 — `deployment_mode` ist nach dem Bootstrap nur über den Operator-Settings-Patch änderbar**
  (`operator_settings_patch_writer.py`); der Setup-Endpoint wirft 409, sobald ein Admin existiert
  (`apps/backend/domain/setup/instance.py`). Vor dem Wechsel auf `agent_system` prüfen, ob Org-/
  Knowledge-Funktionen in Gebrauch sind.
- **B9 — Jeder neue User bekommt automatisch ein Dashboard** (`ensure_default_dashboard_for_new_user`,
  `apps/backend/infrastructure/identity/auth.py`). Wer „Freunde ohne Dashboards" will, muss genau dort ansetzen.
- **B10 — Doku-Irrtum.** `docs/features/agent-registry-and-allowlists.md` verweist auf
  `apps/backend/domain/agent_registry.py` (existiert nicht; real: `domain/agent_runtime/registry.py`)
  und nutzt die Legacy-Feldnamen `AGENT_TOOL_DOMAINS`/`AGENT_TOOL_CAPABILITY_ANY` für YAML.
  Das Access-Policy-System ist dort gar nicht beschrieben. `chat.allowed_agent_ids` fehlt in
  `docs/benchmarks/knob-registry.yaml`.

## 5. Offene Designentscheidung: Rollen ohne Tenants (D3 vs. D1)

| Weg | Beschreibung | Aufwand | Empfehlung |
|-----|--------------|---------|------------|
| **A** | Scope-Rechte als Booleans auf `users` (`can_manage_users`, `can_assign_agents`, `can_manage_dashboards`), Guard-Funktionen nach Vorbild `schedules_allowed`; „Tenant-Admin" wird zu „Konsole-Admin mit eingeschränktem Scope" auf Site-Ebene | klein | **für ~10 Freunde empfohlen** |
| **B** | `tenant_profession_roles` zu echtem RBAC ausbauen: `capabilities JSONB` statt `role_kind`-CHECK, Guards vom `deployment_mode` entkoppeln, Capabilities auf Agent-/Workspace-/Dashboard-Actions erweitern, mehrere Rollen kumulativ (PK ändern) | groß | erst, wenn wirklich Mandantenfähigkeit gebraucht wird |

**Blaupause für „standardmäßig nichts, dann gezielt":** `model_access_policies` +
`model_default_policies` (`schema_105`) haben dieselbe `scope`/`access_state`-Form **mit**
Default-Policy-Konzept. Falls Agents auf Default-Deny umgestellt werden, dieses Muster nehmen —
nicht den Hardcode-Default aus `access.py`.

## 6. Agents einreichen und validieren (D4)

Blocker: Agenten sind **Dateimaterial** (`plugins/agents/<id>/agent.yaml` + `system_prompt.md`),
kein DB-Pfad, `import/analyze` speichert nichts. Zwei realistische Modelle:

1. **DB-Staging + Review-Queue** — Tabelle `agent_submissions` (`pending → approved | rejected`),
   Loader mergeet freigegebene Definitionen zusätzlich zum Dateiscan (der Extra-Scanpfad
   `AGENT_PLUGINS_DIR` zeigt, wie Erweiterungen bisher hereinkommen).
2. **Git-Flow** — Einreichung erzeugt Branch/PR, Review über Diff. Passt zum Postulat
   „reviewable & attributable" aus `docs/adr/0010-external-agent-runtime-port.md`.

KI-Vorprüfung ist buildbar (Wiederverwender im Registry-Bestand: `security_auditor`, `reviewer`)
und prüft Prompt-Injection, Tool-Missbrauch, Secret-Leaks, `min_role`-Vorschlag. Sie ersetzt **kein**
Gate. Reihenfolge: Staging + Queue zuerst, KI als Vorfilter danach.

---

## 7. Zerlegte Arbeitspakete (einzeln startbar)

Reihenfolge P1 → P2 → P3 → P5 → P4 → P6 → P7 → P8. P1 blockiert alles, was Freunden Rechte gibt.

### P1 — Rollen entflechten (Sicherheit zuerst)

> Entkopple `users.role` von `users.site_role`: `is_elevated_role()` darf Agent-Privilegien nicht mehr
> aus dem Legacy-Feld `users.role` ableiten, wenn `users.site_role = 'site_user'`. Prüfe alle Aufrufer
> (`apps/backend/domain/agent_runtime/access.py`, `governance.py`, `apps/backend/domain/scheduling/targets.py`,
> `apps/backend/infrastructure/integrations/bridge_agent_session.py`, `auto_workspace.py`) und passe die
> Tests an. Migration nur, wenn wirklich nötig.

**Done when:** Ein Nutzer mit `role='admin'`, `site_role='site_user'` sieht und benutzt keine Admin-Agents
und bekommt keinen `/v1/admin/*`-Zugriff. Ein `site_admin` behaves unverändert.
**Verify:** `pytest tests/unit/test_agent_access.py`, dann `pytest tests/unit` (Referenzbestand: 1238 passed / 2 skipped).

### P2 — Autoritative Agent-Sicht + dynamischer Picker

> `GET /v1/agents` (`apps/backend/api/agents/controllers/agents_api.py`) mit `get_current_user` absichern
> und über `user_may_invoke_agent()` filtern; Feld `invokable_by_caller` ergänzen; `system_prompt` und
> Tool-Konfiguration aus der Response entfernen. Frontend: `DEEP_LINK_AGENT_IDS` in
> `apps/frontend/src/features/chat/chatAgentSelection.ts` durch die Serverliste ersetzen, `fetchAgents()`
> in `apps/frontend/src/lib/api.ts` reaktivieren.

**Done when:** Der Picker genau die Agents zeigt, die beim Senden durchgehen — für Admin und Nicht-Admin.
**Verify:** Manuell mit einem Nicht-Admin-Account: entzogener Agent fehlt im Picker **und** wird beim
Senden in `chat_run_bootstrap.py` abgewiesen. `pytest tests/unit`.

### P3 — People-Maske „Person → Agents"

> Backend: Batch-Endpoint, der `agent_access_policy_store.upsert_agent_policy()` mit `scope='user'`
> für eine Menge Agent-IDs setzt (allow/deny/inherit). Frontend: Block pro Person in
> `apps/frontend/src/pages/admin/AdminUsers.tsx`, plus Bulk-Aktion „auf mehrere Personen anwenden".

**Done when:** Einem Freund `coding_qwen` (+ `coding`) freizugeben ist ein Vorgang in einem Dialog.
**Verify:** `pytest tests/unit`; UI-Test gegen einen Nicht-Admin-Account.

### P4 — Dashboards so regelbar wie Workspaces

> `operator_settings.dashboards_allowed` (globaler Default, nach Vorbild `workspace_allow_self_editing`)
> und `users.dashboards_allowed` / `users.dashboard_quota`; Durchsetzung im Create-Pfad von
> `apps/backend/api/dashboards/controllers/dashboard_core_api.py` analog der Workspace-Quota-Prüfung;
> `ensure_default_dashboard_for_new_user` an den Default koppeln; Editierfelder in People.

**Done when:** Ein Nutzer ohne Dashboard-Recht kann weder anlegen noch ein Auto-Dashboard behalten;
Quota begrenzt die Anzahl sichtbar.
**Verify:** `pytest tests/unit`; UI-Gegencheck.

### P5 — Tenant-Sichtbarkeit je `deployment_mode`

> Bei `agent_system`: Tenant-Auswahl, Tenant-Spalte und „Tenant anlegen" in
> `apps/frontend/src/pages/admin/AdminUsers.tsx` ausblenden. Bei `multi_tenant`: eigener Tab „Tenants"
> im Admin-Bereich. Ableiten aus `user.deployment_mode` (bereits in `AuthContext` vorhanden).

**Done when:** Im Modus `agent_system` ist nirgends mehr ein Tenant-Begriff sichtbar; `/org` bleibt gesperrt.
**Verify:** UI gegen beide Modi.

### P6 — RBAC ohne Tenants (entscheidet §5 zuerst)

> Weg A: Scope-Booleans auf `users` + Guard-Funktionen, die `/v1/admin/*`-Unterflächen und
> Agent-Zuweisung freigeben. Weg B: `tenant_profession_roles` → `capabilities JSONB`, Guards vom
> `deployment_mode` entkoppeln, mehrere Rollen kumulativ.

**Done when:** Ein beauftragter Nutzer kann anderen Agents zuweisen, ohne Site-Admin zu sein.
**Verify:** `pytest tests/unit`; Testfall „beauftragter Nutzer versucht `/v1/admin/users` PATCH auf
`site_admin`" muss scheitern.

### P7 — Agent-Einreichung + Review-Queue (+ KI-Vorfilter)

> Staging-Ablage nach §6 (Modell 1 oder 2), Status `pending → approved | rejected`, Loader lädt nur
> Freigegebene; Review-UI im Admin-Bereich; optional LLM-Vorprüfung als Hinweis vor dem menschlichen Gate.

**Done when:** Einreichung ist ohne Admin-Review nirgends aktiv; Ablehnung bleibt auditierbar.
**Verify:** `pytest tests/unit`; Registry-Scan zeigt nur freigegebene Agents.

### P8 — Doku & ADR

> `docs/features/agent-registry-and-allowlists.md` korrigieren (Dateipfad, YAML-Feldnamen),
> `chat.allowed_agent_ids` in `docs/benchmarks/knob-registry.yaml` registrieren, ADR für das
> Rollen-/Freigabemodell und für B1 (Rollentrennung) verfassen.

---

## 8. Verifikation (für alle Pakete)

- Tests: `pytest tests/unit` (Ausgangspunkt 1238 passed / 2 skipped), gezielt
  `tests/unit/test_agent_access.py`.
- Ad hoc: ein zweiter Account ohne Admin-Rechte ist das schnellste Prüfmittel für P1/P2/P3 — Picker,
  Chat-Senden und `/v1/admin/*` gemeinsam durchgehen.
- Beide `deployment_mode`-Stellungen testen, sobald P5 landet.

---

## 9. Nachmessung P1–P8 (04.10.2026)

**Warum dieser Abschnitt:** die Zeile oben behauptete „P1–P8 komplett erledigt". Das war zu weit. Nachgemessen
sind sechs Pakete fertig, **P3** und **P5** haben jeweils eine echte Lücke, und der **KI-Vorfilter aus P7
existiert nicht**. Jede Aussage hat das **Kommando**, das sie prüft (Arbeitsbaum
`feat/chat-persist-queue-goal-strip`, Werte vom Lauf 04.10. 21:2x); die Kommandos stehen unter der Tabelle.

| Paket | Stand | Was trägt (Anker, 04.10.) | Was fehlt |
|-------|-------|---------------------------|-----------|
| **P1** Rollen entflechten | **Kern ✓** | Eine Regel an einer Stelle: `domain/identity/roles.py:31` (`ELEVATED_SQL`), `:45` `normalize_site_role`, `:59` `effective_role`; eine gelesene Paar-Zeile `infrastructure/db/identity_tenants.py` (`_role_columns`); jedes `User(...)` normalisiert in `infrastructure/identity/auth.py`; AST-Gate `scripts/checks/checks/legacy_role_reads.py` | Die App kann `site_role` **nicht ändern** — kein `UPDATE` erreicht die Spalte (Kommando 2), geschrieben wird sie nur im `INSERT` beim Anlegen (`identity/auth.py:539,542`) und im Backfill `schema_111_…:43-44`. Herabstufen bleibt ein SQL-Vorgang des Operators |
| **P2** Autoritative Agent-Sicht | **✓ im Code** | Beide Routen hinter `get_current_user` (`api/agents/controllers/agents_api.py:23,30`); Nutzdaten aus `application/agent_runtime/use_cases/agent_catalog.py` — `invokable_by_caller` `:55`, Filter `:69,:83` = `user_may_invoke_agent`, dazu `domain/agent_runtime/catalog.py:56`; `system_prompt` kommt in der Nutzdaten-Datei nicht mehr vor (Kommando 4); FE: `lib/api.ts:70` → `pages/ChatPage.tsx:422`, `DEEP_LINK_AGENT_IDS` nur Fallback (`features/chat/chatAgentSelection.ts:49`) | Der „Done when"-Satz ist ein **UI**-Satz und sein Nachweis (Abschnitt 8: zweiter Account, Picker + Senden gemeinsam) ist nirgends dokumentiert |
| **P3** People → Agents | **teilweise** | Batch-Endpoint `api/agents/controllers/agents_admin_api.py:360-369` (`batch_upsert_user_agent_policies`, `scope='user'`); People-Seite lädt Freigaben (`pages/admin/AdminUsers.tsx:418`), Checkboxen `:789,796,804,841`, Aufruf `:455` | **Bulk über mehrere Personen** fehlt (Kommando 5: kein *selected/bulk* in der Datei). Der Aufruf setzt pro Klick **einen** Agent für **eine** Person — „ein Vorgang in einem Dialog" (§7) ist damit nicht erreicht |
| **P4** Dashboards regelbar | **✓** | Operator-Default `infrastructure/settings/operator_settings.py:230,447`, Patch-Writer `operator_settings_patch_persistence.py:277-278`, Formular `operator_settings_forms.py:139`; reine Regel `domain/dashboards/access.py:25`; Auflösung `infrastructure/dashboard/dashboard_access.py:152,173`; per-User `dashboards_allowed`/`dashboard_quota` gelesen in `infrastructure/identity/auth.py:230,288`; **Auto-Dashboard gekoppelt**: `infrastructure/dashboards/dashboard_persistence.py:240-242` kehrt ohne Recht zurück; `schema_129_…py`; `tests/unit/test_dashboard_access.py`, `test_dashboard_rights_use_site_role.py` | — (Restrisiko: kein Nachweis an einer echten DB, Abschnitt F der Status-Doku) |
| **P5** Tenant-Sichtbarkeit | **eine von zwei Hälften** | `pages/admin/AdminUsers.tsx:97` `showTenantUi = hasOrgSurface(user)` (Helfer `src/auth/deploymentMode.ts:35`), Spaltanzahl `:108` — im Modus `agent_system` ist nichts Tenant-bezogenes sichtbar | Der `multi_tenant`-Zweig: **kein „Tenants"-Tab** im Admin-Bereich (Kommando 6). §7 verlangt beide Modi |
| **P6** RBAC ohne Tenants | **✓ (Weg B)** | `domain/access/capabilities.py:27` `CAP_AGENT_ASSIGN = "agent.assign"`, Konsumenten `api/agents/controllers/agents_admin_api.py` + `agent_config_admin_api.py`; `users.capabilities` (`schema_130`) gelesen in `infrastructure/db/identity_tenants.py`; FE-Sicht `AdminUsers.tsx:100-105` | — ; der §7-Verify-Fall ist als Test vorhanden: `tests/unit/test_p6_capabilities_rbac.py:177` `test_patch_delegated_cannot_touch_site_admin` |
| **P7** Einreichung + Review | **Kern ✓, KI ✗** | `schema_131_agent_submissions.py:37-38` (`pending/approved/rejected`) + partieller Unique auf `pending` (`:10`); Store `infrastructure/agent_runtime/agent_submission_store.py`; `review_submission` materialisiert **nur bei `approve`** (`application/agent_runtime/use_cases/agent_submission_services.py:145-147`) → `agent_submission_materialize.py:35` schreibt `plugins/agents/<slug>/agent.yaml` + `system_prompt.md` und lädt die Registry neu; Endpunkt `api/agents/controllers/agent_submissions_api.py` (`api/main.py:33`), UI `pages/admin/AdminAgentSubmissions.tsx` (+ `test_agent_submission.py`) | **Der KI-Vorfilter aus §6 existiert nicht** (Kommando 8). Nächstes ist `_tool_warnings` (`agent_submission_services.py:54`) — **regelbasiert** (unbekannte Tool-Namen), advisory, kein LLM. ADR 0011 §5 (menschliches Gate) ist davon unabhängig erfüllt |
| **P8** Doku & ADR | **✓** | `docs/features/agent-registry-and-allowlists.md:14` nennt `domain/agent_runtime/registry.py` (B10 ist raus); `docs/benchmarks/knob-registry.yaml:663` `- id: chat.allowed_agent_ids`; `docs/adr/0011-…md` + `0012-admin-tenant-scope.md` | — |

**Kommandos** (jeweils aus dem Repo-Root; Auswertung als `wc -l` oder `head`, wie dabeisteht):

```bash
# 1 — P1: die Legacy-Lesstelle ist weg (04.10.: 2 Treffer, beide Prosa, 0 Aufrufe)
grep -rn 'db\.user_role(' apps plugins --include='*.py'
# 2 — P1: kein UPDATE erreicht site_role (Treffer = nur schema_111_identity_roles_deployment_mode.py:43,44)
grep -rn "UPDATE users SET" --include='*.py' apps/backend plugins | grep -i site_role
# 3 — P1: geschrieben wird die Spalte im INSERT beim Anlegen
grep -rn "INSERT INTO users" --include='*.py' apps/backend plugins
# 4 — P2: system_prompt verlässt die Katalog-Schicht nicht (erwartet: 0)
grep -c '"system_prompt"' apps/backend/application/agent_runtime/use_cases/agent_catalog.py
# 5 — P3: Bulk über mehrere Personen (erwartet: 0 Treffer = Lücke)
grep -in "bulk\|multiple\|selected" apps/frontend/src/pages/admin/AdminUsers.tsx
# 6 — P5: Tenants-Tab (leere Ausgabe = Lücke)
ls apps/frontend/src/pages/admin/ | grep -i tenant
# 7 — P2: die Serverliste sagt, wer invoken darf
grep -n "invokable_by_caller" apps/backend/domain/agent_runtime/catalog.py \
  apps/backend/application/agent_runtime/use_cases/agent_catalog.py
# 8 — P7: KI-Vorfilter im Endpunkt (erwartet: 0 = Lücke)
grep -c "llm\|auditor\|model" apps/backend/api/agents/controllers/agent_submissions_api.py
# 9 — P7: Materialisierung hängt ausschließlich an der Freigabe
grep -rn "materialize_submission" --include='*.py' apps/backend
# 10 — Nebenbefund: die zweite, ungegate Fassung des Auto-Dashboards ist tot
grep -rn "ensure_default_dashboard" --include='*.py' apps/backend | grep dashboard_db
# 11 — Tests: Referenzbestand heute (04.10.: 2328 passed / 2 skipped — §7/§8 nennen 1238 vom 12.09.)
python3 -m pytest tests/unit -q
```

**Offen, nach Nutzen sortiert:**

1. **P1 — `site_role` ändern können.** Solange die App die Spalte nicht schreiben kann, ist jede
   Herabstufung ein SQL-Griff des Operators; die Sicherheitsentscheidung, die dieses Werk trifft, wird
   dadurch nicht unsicher, aber sie bleibt handarbeitig. (`PATCH /v1/admin/users/{id}` kennt kein
   `site_role`-Feld — `api/platform/controllers/admin_users_api.py`, Feldkette endet bei
   `llm_queue_priority`.)
2. **P3 — Bulk.** Mehrere Personen gleichzeitig freigeben ist der Fall, den ~10 Personen mit
   wechselnden Gruppen wirklich haben.
3. **P7 — KI-Vorfilter.** §6 sagt ihn als *danach* an; gebaut ist er nicht. Ein `security_auditor`-Lauf
   über `agent_yaml` + `system_prompt`, dessen Ergebnis **neben** das menschliche Gate tritt (ADR 0011 §5).
4. **P5 — Tenants-Tab** für `multi_tenant`. Solange die Instanz `agent_system` läuft, ist das die
   billigste der Lücken — und die einzige, die nur sichtbar wird, wenn jemand den Modus wechselt.
5. **Der Manuell-/E2E-Nachweis** für P2/P3/P4 an einem zweiten Account. Er fehlt seit der Analyse und ist
   durch Unit-Tests nicht ersetzbar (kein Stack, `legacy-role-migration-status.md` Abschnitt F).

**Nebenbefund beim Nachmessen (P4, nicht Gegenstand dieses Schwungs):** `infrastructure/dashboards/
dashboard_db.py:173` ist eine zweite, **ungegate** Fassung von `ensure_default_dashboard_for_new_user`.
Keiner der drei Importe (`admin_setup.py:11`, `auth.py:30`, `instance_setup_service.py:7`) nutzt sie —
Kommando 10 liefert nur Definition und Logzeile. Tot, aber die Stelle, an der ein künftiger P4-Fix leicht
übersehen wird.
