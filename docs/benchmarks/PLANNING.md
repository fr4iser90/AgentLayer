# Agent tuning & benchmark platform — planning index

**Scope:** planning only. **Start here.** Status checklist: [`todo.md`](./todo.md).

**Planning status: v3.2**

---

## Two different meanings of “automatic” (read this first)

| | **Who starts things** | **What gets recorded** |
|---|------------------------|-------------------------|
| **Rule** | **Never the system alone.** Only **you** — via the **Benchmarks page** or **LLM (Operator)** when you ask. | **Always the platform.** Every patch, run, fingerprint, cohort → **automatic tracking** in DB / History / Stats. |
| **Analogy** | You click Start / you tell the LLM “do X” | The logbook writes itself |

**Never:** Benchmark starts on its own after a patch, via cron, webhook, `on_knob_apply`, or background jobs without you.

**Always:** When you (or the LLM on **your instruction**) start a run → `run_id`, fingerprint, cohort, results land in History/Stats — you do not log anything by hand.

---

## Product goal

Find the best **Agent-Layer configuration** measured across a **model matrix**.

**Two ways to start benchmarks (both initiated by you):**

1. **Benchmarks page (WebUI)** — live today: Admin → Benchmarks → Run, pick matrix, Start.  
2. **LLM (Operator chat)** — planned: e.g. *“turn ranking off and start routing-core”* → Operator patches settings, starts bench, can run **multiple iterations** in one session when you ask.

---

## Core policy

### Who may start what?

| Action | Benchmarks page | Operator LLM (when you ask) | System alone |
|--------|-----------------|----------------------------|--------------|
| Change settings | Agent tuning tab (planned) / Interfaces | `agent_config_apply` | ❌ |
| Start benchmark | ✅ Run tab (live) | `benchmark_run_start` (planned) | ❌ |
| Try several variants | You start run 1, 2, 3… | You: *“try A, bench, then B, bench…”* → LLM loop | ❌ |

### What is tracked automatically? (observability — always on)

| Event | Stored automatically (target) |
|-------|----------------------------|
| Every `agent_config_apply` | Changelog + fingerprint (Phase 1+) |
| Every benchmark run | `benchmark_runs` row, `report_json`, History tab |
| Run + config together | `cohort_label`, fingerprint on run (Phase 1+) |
| Results | Stats tab; later Analysis / Patterns |
| LLM as actor | `actor.type: operator_agent` in changelog |

You do **not** track anything manually — the platform links config snapshot ↔ run ↔ outcome.

---

## Workflow A — Benchmarks page (manual, live today)

```text
You: Admin → Benchmarks → Run
    → pick matrix / profiles, suite, Start
    → run appears in History/Stats (tracking automatic)
Optional: change settings first in Interfaces / later Agent tuning tab
```

**No Operator required.** LLM optional only for analysis (Reviewer, later).

---

## Workflow B — LLM (Operator), you steer via chat

You give direction; Operator executes tools. **One** or **multiple** passes.

### Single pass

```text
You: "Turn ranking off, max rounds 12, start routing-core cohort v8"
Operator:
  1. agent_config_apply
  2. benchmark_run_start
  3. benchmark_run_get (poll)
  4. reply: run_id, short summary
Platform: changelog + run + fingerprint linked automatically
```

### Multiple passes (you want to try variants)

```text
You: "Try three variants and after each start routing-core:
      (1) ranking off
      (2) ranking off, max rounds 16
      (3) ranking off, catalog after first round off"

Operator loop (only because YOU asked):
  apply variant 1 → benchmark_run_start → wait → brief report
  apply variant 2 → benchmark_run_start → wait → brief report
  apply variant 3 → benchmark_run_start → wait → brief report
  → compare the three run_ids / cohorts

You: "Which was best?" → optional Reviewer / analysis
```

Operator does **not** start an extra run without your instruction. Multiple runs = **your** request in the message.

### Settings only, no benchmark

```text
You: "Set max rounds to 12"
Operator: agent_config_apply only — no benchmark_run_start
```

---

## Operator tools (when you ask)

| Tool | Purpose |
|------|---------|
| `agent_config_knobs` | current effective values |
| `agent_config_apply` | change settings (before bench) |
| `benchmark_run_start` | queue run (same as Benchmarks page) |
| `benchmark_run_get` | status / results |
| `benchmark_analysis` | compare cohorts (Phase 2+) |

**Reviewer** is separate — verdict only; does not start benchmarks.

---

## Build order (engineering)

| Phase | Deliverable |
|-------|-------------|
| **0.5** | agent-config API + Operator apply + **benchmark_run_start/get** (Workflow B) |
| **1** | Auto-**tracking**: fingerprint, changelog, cohort on runs |
| **2** | Analysis when you ask for results |
| **3** | Agent tuning WebUI (extends Workflow A) |
| **5** | Reviewer agent |
| **6** | CI / nightly — **optional**, not default UX |

Benchmarks page (Workflow A) **stays**; LLM is an **additional** control path, not a replacement.

---

## Live vs planned

| | Today | Planned |
|---|-------|---------|
| Start bench (Benchmarks page) | ✅ | — |
| Runs in History/Stats | ✅ | + fingerprint / cohort link |
| Settings + bench via LLM | ❌ | Operator tools |
| LLM tries multiple variants | ❌ | Operator loop on request |
| Tracking patch ↔ run | partial | Phase 1 |
| System starts bench without you | ❌ | **stays ❌** |

---

## Knobs & schemas

[`knob-registry.yaml`](./knob-registry.yaml), [`tuning-interfaces.md`](./tuning-interfaces.md), [`schemas/interfaces/`](./schemas/interfaces/).

**Runtime config → WebUI/DB, not `.env`.** See registry header.

---

## Related docs

| Doc | Content |
|-----|---------|
| [`implementation-plan.md`](./implementation-plan.md) | Phase checklist |
| [`agent-tuning-platform.md`](./agent-tuning-platform.md) | Architecture |
| [`api-surface.md`](./api-surface.md) | HTTP |
