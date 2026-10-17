---
doc_id: runbook-responsive-probe
title: Responsive layout probe
tags: [runbook, playwright, responsive, frontend]
---

# Responsive layout probe

Metric-first gate: Playwright crawls signed-in routes at **phone / tablet / desktop**
and fails when the page (or sticky chrome) scrolls horizontally — the usual
“bricked column / sideways scroll” bug. Screenshots are optional artifacts.

Static page-shell lint (`npm run lint:page-shell`) only checks *which* `max-w-*`
token a page uses. This probe checks *runtime* layout at real viewports.

Routes are discovered automatically from `src/App.tsx` (nested `<Route path>` tree).
New pages do **not** need a hand-edited path map — only an entry in App.tsx. The
page-shell baseline optionally labels the shell tier (`page` / `pageWide` / …).

## Prerequisites

- Healthy stack (`curl -sf http://127.0.0.1:8088/health`)
- `AGENT_E2E_EMAIL` / `AGENT_E2E_PASSWORD` in `.env` or `.env.e2e`
- Docker (for the wrapper) **or** local Playwright Chromium

## Run

```bash
# Full matrix (Docker), shots on failure
bash scripts/run-e2e-responsive.sh

# Smoke a few routes
bash scripts/run-e2e-responsive.sh --limit 5 --shots fail

# One route, all viewports, all screenshots
bash scripts/run-e2e-responsive.sh --routes /app/admin/interfaces/providers --shots all

# From apps/frontend with local chromium
cd apps/frontend
npm run e2e:responsive
npm run e2e:responsive:shots
```

Via stack validation (opt-in, after the app is up):

```bash
scripts/validate_stack.sh --responsive
# or only that stage once the stack is already healthy:
scripts/validate_stack.sh --stage responsive --responsive
```

## Artifacts

Written under `output/responsive/<stamp>/` (gitignored):

| file | meaning |
|------|---------|
| `report.json` | machine-readable cells + findings |
| `report.md` | human summary |
| `screenshots/*.png` | when `--shots fail` or `all` |

## Interpreting failures

| kind | meaning |
|------|---------|
| `page_x` | `document` / `body` wider than the viewport |
| `chrome_x` | header / sticky bar wider than its box |
| `shell_token` | `max-w-page*` computed width is wrong (e.g. spacing key collision → 40px) |
| `shell_narrow` | PageShell column collapsed far below its density |
| `scroll_trap` | content taller than `main`, but no ancestor is scrollable (`overflow:hidden` clip) |
| `text_h` | nowrap text clipped (soft in v1 — reported, not fail) |

### Who should scroll?

Decided in `AppLayout` → `AppShell` `scroll` (probe: `expectedScrollMode`):

| mode | routes | scrollport |
|------|--------|------------|
| **fill** | `/chat`, `/dashboard`, `/projects`, `/studio` (+ nested) | page-owned inner region; `main` is `overflow-hidden` |
| **page** | settings, admin, org, docs, tasks, schedules, legal, … | `main` (`overflow-y-auto`) |

Probe kinds: `scroll_mode` (DOM ≠ expected), `scroll_trap` (content taller than viewport, nothing scrolls).

Do **not** wrap `Outlet` in `h-full overflow-hidden` under page-scroll surfaces — that clips tall settings pages.

Fix the layout (flex `min-w-0`, wrap, smaller grids, correct `max-w-page*`), then re-run.

## Allowlist

False positives only. Add `route|viewport|kind` to
`apps/frontend/scripts/responsive-overflow-allowlist.json` → `entries`, e.g.:

```json
{
  "entries": [
    "/app/admin/benchmarks|phone|chrome_x"
  ]
}
```

Do not allowlist real sideways page scroll.

## Viewports

| id | size |
|----|------|
| phone | 390×844 |
| tablet | 768×1024 (`md` rail edge) |
| desktop | 1440×900 |

## Related

- `npm run lint:page-shell:explain` — static shell inventory
- `npm run probe:overflow` — older single-viewport text probe
- `docs/runbooks/playwright.md` — Chromium / volume notes
