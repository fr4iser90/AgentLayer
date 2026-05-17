"""Doc maintenance schedule modes and canonical instructions (per-workspace, not global unify)."""

from __future__ import annotations

from typing import Any

DOC_MAINTENANCE_MODE_RESPECT = "respect"
DOC_MAINTENANCE_MODE_BOOTSTRAP = "bootstrap"
_VALID_MODES = frozenset({DOC_MAINTENANCE_MODE_RESPECT, DOC_MAINTENANCE_MODE_BOOTSTRAP})

DOC_PROFILE_PATH = "docs/DOC_PROFILE.md"
CONVENTIONS_PATH = "docs/CONVENTIONS.md"
REPORT_PATH = "docs/MAINTENANCE_REPORT.md"


def parse_doc_maintenance_mode(workflow: dict[str, Any] | None) -> str:
    """Return ``respect`` or ``bootstrap`` (default ``respect``)."""
    if not workflow:
        return DOC_MAINTENANCE_MODE_RESPECT
    raw = workflow.get("doc_maintenance_mode")
    if raw is None:
        return DOC_MAINTENANCE_MODE_RESPECT
    m = str(raw).strip().lower()
    if m in _VALID_MODES:
        return m
    return DOC_MAINTENANCE_MODE_RESPECT


def normalize_doc_maintenance_mode_value(raw: Any) -> str | None:
    """Validate mode for ``coding_workflow`` JSON; raises ValueError if invalid."""
    if raw is None:
        return None
    m = str(raw).strip().lower()
    if not m:
        return None
    if m not in _VALID_MODES:
        raise ValueError(
            f"doc_maintenance_mode must be {DOC_MAINTENANCE_MODE_RESPECT!r} or "
            f"{DOC_MAINTENANCE_MODE_BOOTSTRAP!r}"
        )
    return m


def mode_summary_line(mode: str) -> str:
    if mode == DOC_MAINTENANCE_MODE_BOOTSTRAP:
        return (
            "**Mode: bootstrap** — opt-in minimal AgentLayer doc layout where missing; "
            "do not restructure repos that already have a clear doc system."
        )
    return (
        "**Mode: respect** — follow this repository's existing documentation layout and tone; "
        "do not impose a foreign folder scheme."
    )


def build_doc_maintenance_instructions(mode: str) -> str:
    """Canonical scheduled-job instructions (respect vs bootstrap)."""
    m = mode if mode in _VALID_MODES else DOC_MAINTENANCE_MODE_RESPECT
    mode_line = mode_summary_line(m)

    profile_block = f"""## Project memory (every run)
1. If `{DOC_PROFILE_PATH}` exists, read it first (doc roots, conventions, last inventory).
2. After Phase 1 inventory, update `{DOC_PROFILE_PATH}` with: doc roots, index pages, conventions source
   (`{CONVENTIONS_PATH}` present or not), top gaps, and date (append/replace Inventory section only).
3. Always maintain `{REPORT_PATH}` for this run (Inventory + Done/Blocked)."""

    conventions_block = f"""## Conventions file
- If `{CONVENTIONS_PATH}` exists, follow it.
- If missing: note in `{REPORT_PATH}` and `{DOC_PROFILE_PATH}`; do **not** invent strict rules unless mode is bootstrap."""

    phase0 = """## Phase 0 — Git (required first)
1. coding_git_read: inspect git status.
2. If working tree is NOT clean and current branch is NOT named agent/*: append reason to docs/MAINTENANCE_REPORT.md and STOP (no pull, no doc edits).
3. coding_git_sync with operation pull (fast-forward only). On failure: log to docs/MAINTENANCE_REPORT.md and STOP.
4. Create or checkout branch agent/doc-YYYYMMDD (use today's date via coding_bash). Do not commit on main/master."""

    phase1_respect = """## Phase 1 — Inventory (read-only, respect project)
1. Discover how **this** repo organizes docs (README, docs/, wiki/, adr/, plugin READMEs, etc.).
2. Survey existing doc trees; list up to 5 **highest-impact** gaps (broken links, missing index, stale README).
3. Append Inventory section to docs/MAINTENANCE_REPORT.md and update docs/DOC_PROFILE.md."""

    phase1_bootstrap = """## Phase 1 — Inventory + bootstrap gaps (opt-in structure)
1. Discover current doc layout; record in docs/DOC_PROFILE.md.
2. List up to 5 highest-impact gaps in docs/MAINTENANCE_REPORT.md.
3. **Only if missing** and the repo has no equivalent: create minimal files (at most 3 new files this run):
   - docs/README.md — short index with links to existing doc folders
   - docs/CONVENTIONS.md — brief: doc types (how-to, reference, ADR), language, link policy
   - docs/DOC_PROFILE.md — if not yet present (project memory template)
   Do **not** duplicate existing docs/ or rename folders."""

    phase2_respect = """## Phase 2 — Edits (limits, respect project)
- Fix at most **3** gaps from the inventory.
- Touch at most **8** files total.
- Only edit paths that already exist **or** are listed in docs/DOC_PROFILE.md as in-scope (typically docs/ and root README.md).
- No src/tests refactors, no dependency bumps, no git push."""

    phase2_bootstrap = """## Phase 2 — Edits (limits, bootstrap)
- Fix at most **3** gaps from the inventory (prefer broken links, missing index, README clarity).
- Touch at most **8** files total (including at most 3 **new** files from Phase 1).
- Scope: docs/, root README.md only.
- No src/tests refactors, no dependency bumps, no git push."""

    phase3 = """## Phase 3 — Close
1. Run coding_workspace_verify if configured for this workspace.
2. Append Done or Blocked summary to docs/MAINTENANCE_REPORT.md.
3. Reply with a short plain-text summary (mode, branch, files changed, verify result)."""

    phase1 = phase1_bootstrap if m == DOC_MAINTENANCE_MODE_BOOTSTRAP else phase1_respect
    phase2 = phase2_bootstrap if m == DOC_MAINTENANCE_MODE_BOOTSTRAP else phase2_respect

    return "\n\n".join(
        [
            "Scheduled documentation maintenance for **THIS workspace only**.",
            mode_line,
            profile_block,
            conventions_block,
            phase0,
            phase1,
            phase2,
            phase3,
        ]
    )
