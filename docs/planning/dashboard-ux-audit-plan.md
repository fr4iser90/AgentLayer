# Dashboard Block UX Audit — Findings & Improve Plan

**Stand:** 2026-09-07 (Seed-Felder + Schedules-Crash nachgezogen)  
**Methode:** Demo-Board mit allen Block-Typen + Demo-Daten → Playwright Chromium → Einzel-Screenshots → visuelle Bewertung.  
**Artefakte:** `example/dashboard-ux-audit/`  
**Wiederholen:** `bash scripts/run-e2e-playwright-dashboard-ux-audit.sh`

**Seed-Fixes (2. Pass):** Timeline `date`/`note`, KPI `trend: up`, Media `source_kind: embed`, Friend-User für Share, 2 Scheduler-Jobs.  
**Bugfix:** Schedules-Block crashte das ganze Board (`pill is not defined` in `DashboardBlocks.tsx`).

**Board:** [UX Audit — All Blocks](http://127.0.0.1:8088/app/dashboard) (ID in `dashboard.json`)

---

## Kritischer Fund (vor Optik) — BEHOBEN

`PATCH /v1/dashboards/{id}` **ignorierte `data`** — Domain Collections sind Source of Truth (`dashboard_db.dashboard_update`).
Die UI speicherte weiterhin `{ data }` beim Save → **Inhalt speichern wirkte tot**, außer Create-Pfad / Collections-Tools.

**Fix (2026-09-07):** `dashboard_data_write.write_dashboard_data` übersetzt das `data`-Payload in
`patch_fields`-Aufrufe pro gebundenem `dataPath` (Listen → Replace, Skalare/Markdown → Collection-Metadata).
Nicht mitgesendete Pfade bleiben unangetastet, damit Teil-Saves keine Listen leeren.
Dashboard-Config ohne Block-Binding (`_agentlayer`) bleibt in `user_dashboards.data` und wird beim Projizieren
wieder eingemischt. PATCH antwortet jetzt mit dem projizierten Board, damit die UI ihren State nicht mit der
rohen Spalte überschreibt. Der granulare Block-Share-Pfad schreibt dieselben Collections, gefiltert auf die
geteilten Blöcke.

**Verifikation:** `python3 scripts/verify_dashboard_data_save.py` (Edit, Row-Delete, Teil-Save, `_agentlayer`)
plus `tests/unit/test_dashboard_data_write.py`.

---

## Bewertungs-Skala

| Note | Bedeutung |
|------|-----------|
| A | Lesbar, klar, wenig Chrome-Noise |
| B | Brauchbar, klare Polish-Punkte |
| C | Nutzbar, aber unruhig / edit-lastig |
| D | Leer, broken, oder schwer lesbar |

---

## Einzelbewertung (mit Demo-Daten)

| # | Block | Shot | Note | Beobachtungen |
|---|-------|------|------|----------------|
| 00 | Full board | `00-full-board.png` | C | Sehr lang; überall doppelte Titel/Rahmen; Scroll-Ermüdung |
| 01 | `table` | `01-table-…` | B | Daten ok; **doppelter Titel** (shell + „TABLE (ITEMS)“); Spalte `done` lowercase; Edit-Inputs wirken wie Formular, nicht wie Liste |
| 02 | `markdown` | `02-markdown-…` | C | Zeigt **Raw Markdown** in Textarea, kein Render; doppeltes Label NOTES; Resize-Griff unnötig laut |
| 03 | `rich_markdown` | `03-rich_markdown-…` | B | Preview gut; Editor+Preview immer Side-by-Side = viel Höhe; doppelter Titel |
| 04 | `gallery` | `04-gallery-…` | C | Bilder ok; **Edit-Chrome** (Drag handle, Upload, URL-Feld) dominiert; View-Modus fehlt |
| 05 | `hero` | `05-hero-…` | B | Bild+Headline ok; Caption fehlt in Overlay; Upload-Button immer sichtbar |
| 06 | `timeline` | `06-timeline-…` | C | Dates/Notes gefüllt (`date`/`note`); edit-first mit großen Note-Feldern; doppelter Titel |
| 07 | `stat` | `07-stat-…` | C | „42 / Open items“ + Trend ↑; darunter immer Edit-Felder; Preview+Editor gemischt |
| 08 | `chart` | `08-chart-…` | C | Chart sichtbar; **Legend vs Farben** verwirrend; Categories-Editor abgeschnitten; Config frisst Platz |
| 09 | `sparkline` | `09-sparkline-…` | B | Linie ok; doppeltes Label; CSV-Editor immer sichtbar; viel Leerraum |
| 10 | `kanban` | `10-kanban-…` | C | Spalten/Karten da; Move via Mini-Select `→ Todo`; kein DnD; Delete überall rot; edit-first |
| 11 | `embed` | `11-embed-…` | B | YouTube preview ok; Config-Felder oben immer; Hint nur Google Calendar obwohl YouTube |
| 12 | `media_player` | `12-media_player-…` | C | YouTube-Embed + Queue ok; Add-embed Placeholder = Calendar-URL-Noise; doppelter Titel |
| 13 | `section` | `13-section-…` | D | **Lehrbuch Double-Chrome**: Section → Nested shell → Markdown shell; Nested zeigt Raw MD |
| 14 | `card_grid` | `14-card_grid-…` | B | Karten lesbar; Tags low-contrast; viel Leerraum unter Grid; doppelter Titel |
| 15 | `share_widget` | `15-share_widget-…` | C | Friend-ID gesetzt; ohne echte Google-Events nur „No upcoming events.“ (kein Fake-Kalender) |
| 16 | `formula_calc` | `16-formula_calc-…` | C | Inputs ok; nach Calculate keine klaren **Ergebnis-Zahlen** sichtbar (nur Formel-String); viel Padding |
| 17 | `dashboard_ref` | `17-dashboard_ref-…` | C | Pin funktioniert; innere Markdown wieder Raw+Resize; Shell-Labels `PINNED REF` / `SRC_NOTES` technisch |
| 18 | `schedules` | `18-schedules-…` | C | 2 Demo-Jobs; doppeltes „SCHEDULES“; Enable/Disable-Button abgeschnitten („Dis“); Target-Text redundant |

---

## Querschnitt-Probleme (alle Elemente)

1. **Doppel-Chrome** — Grid-Shell-Titel + innere Card-Titel + oft dataPath-Label  
2. **Edit-Mode = View-Mode** — User sieht immer Inputs/Buttons, nie eine ruhige Read-Ansicht  
3. **Typografie** — viele `10px`/uppercase Labels; schwer zu scannen  
4. **Akzent-Chaos** — Chat grün, Primary mal blau mal lila (Gallery/Hero)  
5. **Leerraum** — feste Grid-Höhen + wenig Inhalt → große schwarze Flächen  
6. ~~**Save/Data-Pipeline** — PATCH `data` ignored~~ → behoben (siehe oben)

---

## Improve-Plan (erst nach Audit — Priorität)

### P0 — Muss zuerst

1. ~~**Data-Write reparieren**~~ — erledigt 2026-09-07
   - PATCH akzeptiert `data` wieder und spiegelt es über `patch_fields` in die Collections
   - Frontend Save braucht keine Änderung: PATCH liefert jetzt das projizierte Board zurück

2. **Eine Chrome-Schicht im Grid**  
   - In `DashboardGridInner`: innere Block-Wrapper ohne zweiten Border/Titel (Prop `embeddedInGrid`)  
   - Titel nur in Shell **oder** nur im Block, nicht beides  

3. **Use vs Edit trennen**  
   - Use-Mode: renderierte Ansicht (Markdown rendered, Gallery tiles only, Stat nur KPI, Chart nur Chart)  
   - Edit/Layout-Mode: Inputs, Upload, Row+, Delete  

### P1 — Lesbarkeit & Interaktion

4. **Markdown**: Use-Mode = `react-markdown`; Edit-Mode = textarea  
5. **Timeline**: Feld-Mapping `at` → Date-Input fixen; kompaktere Event-Rows; Note einklappbar  
6. **Kanban**: DnD oder klarer Move; Karten als Cards nicht als Input+Select-Haufen  
7. **Table**: View-ähnliche Rows (Checkbox + Text), nicht jedes Feld wie Form-Input; Header-Labels konsistent  
8. **Chart/Stat/Spark**: Config hinter Settings/Expand; Default = Visual only  
9. **Gallery/Hero**: Use-Mode ohne Drag/URL-Felder; Edit hinter Settings  
10. **Media Player**: Player-Fläche oder klare Empty; kein irrelevantes Embed-Feld als Default  
11. **Section**: Nested Blocks ohne eigene Shell-Titel; Section-Chrome reicht  
12. **Typo-Scale**: Shell-Titel ≥12–13px; weniger ALL CAPS  

### P2 — Produkt / Demo / Randfälle

13. **Live `agent_tasks`-Block** (separates Epic, `PLAN_TASKS_PHASE_2_3`) — nicht JSON-Table-Fake  
14. **Schedules**: Demo-Seed oder Empty-State mit CTA „Create schedule“  
15. **Share widget**: besserer Empty-State + Link zu Friends; Demo nur mit User-B möglich  
16. **Formula**: Ergebnisse prominent (Sum=17, Product=60)  
17. **Embed-Hint**: kontextabhängig (YouTube vs Calendar)  
18. **Docs**: Save/Collections-Verhalten dokumentieren; PLAN-Pfade aktualisieren  

---

## Empfohlene Umsetzungsreihenfolge

```
1. P0 Data-Save (erledigt)
2. P0 Single chrome + Use/Edit split (größter Lesbarkeits-Gewinn)
3. P1 Markdown / Timeline / Kanban / Table
4. P1 Chart/Stat/Gallery/Media trim
5. P2 Tasks-live + Randblöcke
```

---

## Nicht in diesem Plan

- Session Goal / Plan-Mode / Chat-Activity → bleiben **Chat**, keine Dashboard-Blöcke  
- Neues Element-Zoo erweitern, bevor Chrome/Save steht  

---

## Referenzen

| Was | Pfad |
|-----|------|
| Screenshots | `example/dashboard-ux-audit/screenshots/` |
| Meta | `example/dashboard-ux-audit/dashboard.json` |
| Seed | `scripts/seed_dashboard_ux_audit.py` |
| Playwright | `apps/frontend/scripts/e2e-playwright-dashboard-ux-audit.mjs` |
| Runner | `scripts/run-e2e-playwright-dashboard-ux-audit.sh` |
| Data ignore | `apps/backend/infrastructure/dashboards/dashboard_db.py` (`dashboard_update`) |
| Tasks Phase 2 | `plugins/dashboards/PLAN_TASKS_PHASE_2_3.md` |
