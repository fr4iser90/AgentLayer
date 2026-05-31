"""Scope rules for Plan-agent code search tools (no token blocklists)."""

from __future__ import annotations

from typing import Any

_PLAN_SEARCH_TOOLS = frozenset({"coding_search", "coding_semantic_search"})

# Root / cwd is not a scope — still searches the whole workspace tree.
_INVALID_PATH_PREFIXES = frozenset({".", "./", ""})

# Top-level repo dirs are too broad for targeted verification.
_SHALLOW_PATH_PREFIXES = frozenset({"apps", "plugins", "scripts", "docs", "tests"})

_GIT_FORENSICS_BLOCKED_TOOLS = frozenset(
    {
        "retrieve_context",
        "coding_semantic_search",
        "coding_glob",
        "coding_list_dir",
        "coding_symbols",
        "coding_lsp",
        "project_explain",
    }
)


def _normalize_path_prefix(args: dict[str, Any]) -> str:
    return str(args.get("path_prefix") or "").strip().replace("\\", "/").rstrip("/")


def _has_valid_path_prefix(args: dict[str, Any]) -> bool:
    path_prefix = _normalize_path_prefix(args)
    if not path_prefix or path_prefix in _INVALID_PATH_PREFIXES:
        return False
    if path_prefix in _SHALLOW_PATH_PREFIXES:
        return False
    return True


def _plan_delegate_mode(tool_context: dict[str, Any] | None) -> str:
    ctx = tool_context or {}
    mode = str(
        ctx.get("agent_delegate_mode") or ctx.get("agent_plan_delegate_mode") or ""
    ).strip().lower()
    return mode


def coding_plan_search_blocked(
    tool_name: str,
    args: dict[str, Any],
    *,
    tool_context: dict[str, Any] | None = None,
) -> str | None:
    """Plan agent: repo-wide text search requires an explicit subdirectory scope."""
    if (tool_name or "").strip() not in _PLAN_SEARCH_TOOLS:
        return None
    query = str(args.get("query") or "").strip()
    if not query:
        return None

    mode = _plan_delegate_mode(tool_context)
    if mode == "git_forensics" and tool_name == "coding_search":
        ctx = tool_context or {}
        if not ctx.get("plan_git_diff_seen"):
            return (
                "git_forensics: run coding_git_read diff_stat (and read changed files) before "
                "coding_search. Then set path_prefix to the directory of a changed file "
                "(e.g. plugins/tools/capabilities/coding/), not apps/plugins/scripts alone."
            )

    if _has_valid_path_prefix(args):
        return None

    path_prefix = _normalize_path_prefix(args)
    if path_prefix in _SHALLOW_PATH_PREFIXES:
        return (
            f"Plan agent: path_prefix {path_prefix!r} is too broad. "
            "Use a subdirectory of changed files (e.g. plugins/tools/capabilities/coding/), "
            "not a top-level repo folder."
        )
    return (
        f"Plan agent: {tool_name} must include path_prefix scoped to a subdirectory "
        f"(not '.' or empty). Query {query[:80]!r} without scope matches too much of the repo. "
        "Use coding_git_read for git state, coding_read_file for known paths, "
        "or add path_prefix (e.g. apps/backend/domain)."
    )


def coding_plan_tool_blocked(
    tool_name: str,
    args: dict[str, Any],
    tool_context: dict[str, Any] | None = None,
) -> str | None:
    """All Plan-agent tool guards (search scope, git_forensics allowlist)."""
    name = (tool_name or "").strip()
    mode = _plan_delegate_mode(tool_context)
    if mode == "git_forensics" and name in _GIT_FORENSICS_BLOCKED_TOOLS:
        return (
            f"git_forensics mode: {name} is not allowed. "
            "Use coding_git_read (status, log, branch, diff_stat), coding_read_file on changed paths, "
            "then coding_search with path_prefix scoped to a changed file's directory."
        )
    return coding_plan_search_blocked(name, args, tool_context=tool_context)


# Back-compat alias for existing imports/tests.
def coding_plan_coding_search_blocked(
    args: dict[str, Any],
    *,
    tool_context: dict[str, Any] | None = None,
) -> str | None:
    return coding_plan_search_blocked("coding_search", args, tool_context=tool_context)
