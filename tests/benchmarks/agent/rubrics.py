"""Automated pass/fail rubrics for agent benchmark scenarios."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

_READ_FILE_TOOL_NAMES = frozenset(
    {"read_file", "repository.read_file", "workspace.read_file"}
)
_WORKSPACE_CREATE_TOOL_NAMES = frozenset(
    {"create", "workspace.create", "workspaces.create", "workspace.create"}
)
_SEARCH_TOOL_NAMES = frozenset(
    {
        "retrieve_context",
        "grep",
        "search",
        "code_grep",
        "workspace.search",
        "repository.search",
    }
)
_SECURITY_TOOL_HINTS = (
    "security_scan",
    "ssc_",
    "resolve",
    "finding_policy",
    "simplesec",
)
_GMAIL_TOOL_HINTS = ("gmail", "mail", "inbox", "email")
_DASHBOARD_TOOL_HINTS = (
    "dashboard",
    "create_dashboard",
    "patch_layout",
    "patch_data",
)
_WRITE_TOOL_NAMES = frozenset(
    {
        "write_file",
        "edit",
        "apply_patch",
        "replace",
        "repository.write_file",
    }
)
_DELEGATE_TOOL_NAMES = frozenset({"delegate"})


@dataclass
class RubricOutcome:
    passed: bool
    score: float
    failure_reason: str | None = None


def _norm_tool_name(name: str) -> str:
    return (name or "").strip().lower()


def _tool_names_lower(tool_names: list[str]) -> set[str]:
    return {_norm_tool_name(n) for n in tool_names if n}


def _used_delegate(tool_names: list[str]) -> bool:
    return bool(_tool_names_lower(tool_names) & _DELEGATE_TOOL_NAMES)


def _coding_edit_action(tool_names: list[str]) -> bool:
    """Direct write tools on the run, or General → coding via delegate."""
    names = _tool_names_lower(tool_names)
    return bool(names & _WRITE_TOOL_NAMES) or bool(names & _DELEGATE_TOOL_NAMES)


def _content_mentions_any(content: str, needles: tuple[str, ...]) -> bool:
    low = (content or "").lower()
    return any(n in low for n in needles)


_S1_DISCOVERY_TOOLS = frozenset({"catalog"})


def _used_s1_discovery_tool(tool_names: list[str]) -> bool:
    names = _tool_names_lower(tool_names)
    return bool(names & _S1_DISCOVERY_TOOLS)


def _mentions_agent_ids(content: str, *, minimum: int = 3) -> bool:
    """True when the reply names at least ``minimum`` specialist agent_id values."""
    low = (content or "").lower()
    known = (
        "coding",
        "coding_plan",
        "security_auditor",
        "dashboard",
        "creative",
        "math",
        "research",
        "communications",
        "media",
        "integrations",
        "outdoor",
        "lifestyle",
        "operator",
    )
    return sum(1 for aid in known if aid in low) >= minimum


def rubric_s1_tool_catalog(
    *,
    content: str,
    tool_names: list[str],
    error: str | None,
    **_: Any,
) -> RubricOutcome:
    if error:
        return RubricOutcome(False, 0.0, error)
    called_catalog = _used_s1_discovery_tool(tool_names)
    named_agents = _mentions_agent_ids(content)
    if called_catalog and named_agents:
        return RubricOutcome(True, 1.0, None)
    parts: list[str] = []
    if not called_catalog:
        parts.append("no catalog tool call detected (invoke catalog via native tool calling)")
    if not named_agents:
        parts.append("reply must name at least three specialist agent_id values from catalog")
    score = 0.5 if called_catalog or named_agents else 0.0
    return RubricOutcome(False, score, "; ".join(parts) or "rubric failed")


def rubric_s2_simple_chat(
    *,
    content: str,
    error: str | None,
    latency_ms: float,
    tool_names: list[str] | None = None,
    **_: Any,
) -> RubricOutcome:
    """Smoke: general answers directly — no tools, no delegate (plain_completion)."""
    if error:
        return RubricOutcome(False, 0.0, error)
    if latency_ms > 60_000:
        return RubricOutcome(False, 0.0, f"latency {latency_ms:.0f}ms exceeds 60s")
    if tool_names:
        return RubricOutcome(
            False,
            0.0,
            f"simple chat must not invoke tools (got: {', '.join(tool_names)})",
        )
    text = (content or "").strip()
    first_line = text.splitlines()[0].strip().lower() if text else ""
    if first_line.rstrip(".") == "paris":
        return RubricOutcome(True, 1.0, None)
    if len(text) > 12:
        return RubricOutcome(
            False,
            0.0,
            f"expected one word 'Paris', got long reply: {text[:80]!r}",
        )
    return RubricOutcome(False, 0.0, f"expected 'Paris', got: {text[:120]!r}")


def rubric_s4_delegate_math(
    *,
    content: str,
    tool_names: list[str],
    error: str | None,
    latency_ms: float,
    **_: Any,
) -> RubricOutcome:
    """Tier 2: general delegates arithmetic to math; reply contains 42."""
    if error:
        return RubricOutcome(False, 0.0, error)
    if latency_ms > 420_000:
        return RubricOutcome(False, 0.0, f"latency {latency_ms:.0f}ms exceeds 420s")
    if not _used_delegate(tool_names):
        return RubricOutcome(False, 0.0, "expected delegate to math agent")
    text = (content or "").strip()
    first_line = text.splitlines()[0].strip() if text else ""
    if first_line == "42" or re.fullmatch(r"42\.?", first_line):
        return RubricOutcome(True, 1.0, None)
    if re.search(r"\b42\b", text) and len(text) <= 12:
        return RubricOutcome(True, 0.85, None)
    return RubricOutcome(
        False,
        0.25 if _used_delegate(tool_names) else 0.0,
        f"delegate ok but expected '42' in reply, got: {text[:120]!r}",
    )


def _s3_readme_first_line_in_reply(content: str) -> bool:
    text = (content or "").strip()
    if len(text) < 3:
        return False
    low = text.lower()
    if "# agent layer" in low:
        return True
    first = text.splitlines()[0].strip().lower()
    return first == "# agent layer" or "agent layer" in first


def rubric_s3_read_file(
    *,
    content: str,
    tool_names: list[str],
    tool_invocations: list[dict[str, Any]] | None,
    error: str | None,
    **_: Any,
) -> RubricOutcome:
    if error:
        return RubricOutcome(False, 0.0, error)
    names = _tool_names_lower(tool_names)
    used_read = bool(names & _READ_FILE_TOOL_NAMES)
    delegated = _used_delegate(tool_names)
    path_ok = False
    for inv in tool_invocations or []:
        tname = _norm_tool_name(str(inv.get("tool_name") or ""))
        if tname not in _READ_FILE_TOOL_NAMES:
            continue
        args = inv.get("args_json") or inv.get("arguments") or {}
        if isinstance(args, str):
            blob = args.lower()
        else:
            blob = str(args).lower()
        excerpt = str(inv.get("result_excerpt") or "").lower()
        if "readme" in blob or "readme" in excerpt:
            path_ok = True
            break
    readme_line = _s3_readme_first_line_in_reply(content)
    non_empty = len((content or "").strip()) >= 3
    if used_read and (path_ok or readme_line or non_empty):
        score = 1.0 if path_ok and readme_line else 0.75
        return RubricOutcome(True, score, None)
    if delegated and readme_line:
        return RubricOutcome(True, 1.0, None)
    if delegated and non_empty:
        return RubricOutcome(True, 0.75, None)
    parts: list[str] = []
    if not used_read and not delegated:
        parts.append("expected delegate to coding_plan or read_file on trace")
    if not path_ok and not readme_line and not non_empty:
        parts.append("no README first line in reply")
    return RubricOutcome(False, 0.25 if (used_read or delegated) else 0.0, "; ".join(parts))


def _used_workspace_create(tool_names: list[str]) -> bool:
    names = _tool_names_lower(tool_names)
    return bool(names & _WORKSPACE_CREATE_TOOL_NAMES) or any(
        "workspace" in n and "create" in n for n in names
    )


def rubric_w1_git_readme(
    *,
    content: str,
    tool_names: list[str],
    tool_invocations: list[dict[str, Any]] | None,
    error: str | None,
    workspace_row: dict[str, Any] | None = None,
    **_: Any,
) -> RubricOutcome:
    if error:
        return RubricOutcome(False, 0.0, error)
    names = _tool_names_lower(tool_names)
    used_read = bool(names & _READ_FILE_TOOL_NAMES)
    delegated = _used_delegate(tool_names)
    used_create = _used_workspace_create(tool_names)
    ws_ok = bool(workspace_row and str(workspace_row.get("id") or "").strip())
    non_empty = len((content or "").strip()) >= 3
    readme_line = _content_mentions_any(content, ("# hello-world", "hello-world", "hello world"))
    if used_create and (used_read or delegated) and non_empty and ws_ok:
        score = 1.0 if (used_read or readme_line) else 0.85
        return RubricOutcome(True, score, None)
    if used_create and (used_read or delegated) and non_empty:
        return RubricOutcome(True, 0.85, None)
    parts: list[str] = []
    if not used_create:
        parts.append("workspace.create not invoked")
    if not used_read and not delegated:
        parts.append("read_file or delegate not used")
    if not ws_ok:
        parts.append("expected bench workspace not found via API")
    if not non_empty:
        parts.append("reply empty")
    return RubricOutcome(
        False,
        0.5 if (used_create or used_read or delegated) else 0.0,
        "; ".join(parts) or "w1 rubric failed",
    )


def _octocat_found(content: str, tool_invocations: list[dict[str, Any]] | None) -> bool:
    blob = (content or "").lower()
    if "octocat" in blob or "hello world" in blob or "hello-world" in blob:
        return True
    for inv in tool_invocations or []:
        excerpt = str(inv.get("result_excerpt") or "").lower()
        if "octocat" in excerpt or "hello world" in excerpt:
            return True
    return False


def rubric_w2_find_octocat(
    *,
    content: str,
    tool_names: list[str],
    tool_invocations: list[dict[str, Any]] | None,
    error: str | None,
    workspace_row: dict[str, Any] | None = None,
    **_: Any,
) -> RubricOutcome:
    if error:
        return RubricOutcome(False, 0.0, error)
    if not _used_workspace_create(tool_names):
        return RubricOutcome(False, 0.0, "workspace.create not invoked")
    if workspace_row is None or not str(workspace_row.get("id") or "").strip():
        return RubricOutcome(False, 0.0, "expected bench workspace not found via API")
    if not tool_names:
        return RubricOutcome(False, 0.0, "no tool calls after workspace create")
    if not _octocat_found(content, tool_invocations):
        return RubricOutcome(False, 0.25, "Octocat / Hello World not found in reply or tool results")
    return RubricOutcome(True, 1.0, None)


def rubric_w2_find_octocat_indexed(
    *,
    content: str,
    tool_names: list[str],
    tool_invocations: list[dict[str, Any]] | None,
    error: str | None,
    **kwargs: Any,
) -> RubricOutcome:
    base = rubric_w2_find_octocat(
        content=content,
        tool_names=tool_names,
        tool_invocations=tool_invocations,
        error=error,
        **kwargs,
    )
    if not base.passed:
        return base
    names = _tool_names_lower(tool_names)
    used_search = bool(names & _SEARCH_TOOL_NAMES) or any(
        "retrieve" in n or "semantic" in n or "grep" in n for n in names
    )
    score = 1.0 if used_search else 0.85
    return RubricOutcome(True, score, None if used_search else "found via tools but no search/retrieval tool")


def rubric_soc1_share_data(
    *,
    content: str,
    tool_names: list[str] | None = None,
    error: str | None,
    dashboard_state: dict[str, Any] | None = None,
    **_: Any,
) -> RubricOutcome:
    if error:
        return RubricOutcome(False, 0.0, error)
    tools = tool_names or []
    has_create = _has_dashboard_tool(tools, "create_dashboard", "dashboard.create")
    has_share = _has_dashboard_tool(tools, "block_share", "share")
    dash = dashboard_state if isinstance(dashboard_state, dict) else {}
    has_dash = bool(str(dash.get("id") or "").strip())
    if "bench-visible" in (content or ""):
        score = 1.0 if has_create and has_dash else 0.9
        return RubricOutcome(True, score, None)
    parts: list[str] = [f"expected bench-visible in reply, got: {(content or '')[:120]!r}"]
    if not has_create:
        parts.append("dashboard create tool not detected")
    if not has_share:
        parts.append("block share tool not detected")
    if not has_dash:
        parts.append("share dashboard not found via API")
    return RubricOutcome(False, 0.0, "; ".join(parts))


def _has_dashboard_tool(tool_names: list[str], *needles: str) -> bool:
    names = _tool_names_lower(tool_names)
    hints = needles or _DASHBOARD_TOOL_HINTS
    return any(any(h in n for h in hints) for n in names)


def _markdown_notes_block(ui_layout: dict[str, Any]) -> bool:
    blocks = ui_layout.get("blocks") if isinstance(ui_layout.get("blocks"), list) else []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if str(block.get("type") or "").strip().lower() != "markdown":
            continue
        props = block.get("props") if isinstance(block.get("props"), dict) else {}
        if str(props.get("dataPath") or "").strip() == "notes":
            return True
    return False


def rubric_d1_dashboard_create(
    *,
    content: str,
    tool_names: list[str],
    error: str | None,
    dashboard_state: dict[str, Any] | None = None,
    expected_title: str | None = None,
    **_: Any,
) -> RubricOutcome:
    if error:
        return RubricOutcome(False, 0.0, error)
    dash = dashboard_state if isinstance(dashboard_state, dict) else {}
    title = str(dash.get("title") or "").strip()
    dash_id = str(dash.get("id") or "").strip()
    has_create = _has_dashboard_tool(tool_names, "create_dashboard", "dashboard.create")
    if dash_id and expected_title and title == expected_title:
        return RubricOutcome(True, 1.0, None)
    if dash_id and title:
        return RubricOutcome(True, 0.9, None)
    if has_create and dash_id:
        return RubricOutcome(True, 0.85, None)
    if has_create:
        return RubricOutcome(True, 0.7, None)
    return RubricOutcome(
        False,
        0.0,
        f"expected dashboard titled {expected_title!r} or create_dashboard tool; got title={title!r}",
    )


def rubric_d2_layout_patch(
    *,
    content: str,
    tool_names: list[str],
    error: str | None,
    dashboard_state: dict[str, Any] | None = None,
    **_: Any,
) -> RubricOutcome:
    if error:
        return RubricOutcome(False, 0.0, error)
    dash = dashboard_state if isinstance(dashboard_state, dict) else {}
    ui_layout = dash.get("ui_layout") if isinstance(dash.get("ui_layout"), dict) else {}
    data = dash.get("data") if isinstance(dash.get("data"), dict) else {}
    notes = str(data.get("notes") or "").strip()
    has_notes_block = _markdown_notes_block(ui_layout)
    has_layout_tool = _has_dashboard_tool(tool_names, "patch_layout", "patch_data")
    if has_notes_block and notes == "bench-notes-ok":
        return RubricOutcome(True, 1.0, None)
    if has_notes_block and notes:
        return RubricOutcome(True, 0.85, None)
    if has_layout_tool and "block_added" in (content or "").lower():
        return RubricOutcome(True, 0.75, None)
    parts: list[str] = []
    if not has_notes_block:
        parts.append("no markdown block with dataPath notes")
    if notes != "bench-notes-ok":
        parts.append(f"notes={notes!r}")
    return RubricOutcome(False, 0.0, "; ".join(parts) or "d2 rubric failed")


def _has_security_tool(tool_names: list[str]) -> bool:
    names = _tool_names_lower(tool_names)
    return any(
        any(h in n for h in _SECURITY_TOOL_HINTS) for n in names
    ) or any(n.startswith("security_scan") for n in names)


def _security_scan_action(tool_names: list[str]) -> bool:
    """SSC tools on the run, or General → security_auditor via delegate."""
    return _has_security_tool(tool_names) or _used_delegate(tool_names)


def rubric_sec1_scan_agentlayer(
    *,
    content: str,
    tool_names: list[str],
    tool_invocations: list[dict[str, Any]],
    error: str | None,
    workspace_row: dict[str, Any] | None = None,
    **_: Any,
) -> RubricOutcome:
    if error:
        return RubricOutcome(False, 0.0, error)
    if not _used_workspace_create(tool_names):
        return RubricOutcome(False, 0.0, "workspace.create not invoked")
    if workspace_row is None or not str(workspace_row.get("id") or "").strip():
        return RubricOutcome(False, 0.0, "expected agentlayer workspace not found via API")
    has_tool = _security_scan_action(tool_names)
    low = (content or "").lower()
    has_scan_ref = "scan_id" in low or "scan id" in low or "scan-" in low
    has_status = "status" in low or "queued" in low or "completed" in low or "started" in low
    if has_tool and (has_scan_ref or has_status):
        return RubricOutcome(True, 1.0, None)
    if has_tool:
        return RubricOutcome(True, 0.75, None)
    return RubricOutcome(
        False,
        0.0,
        "expected delegate or security_scan tool call and scan_id/status in reply",
    )


def rubric_sec2_remediate_agentlayer(
    *,
    content: str,
    tool_names: list[str],
    error: str | None,
    project_summary: dict[str, Any] | None = None,
    project_status: str | None = None,
    git_changes: dict[str, Any] | None = None,
    workspace_row: dict[str, Any] | None = None,
    **_: Any,
) -> RubricOutcome:
    if error:
        return RubricOutcome(False, 0.0, error)
    if not _used_workspace_create(tool_names):
        return RubricOutcome(False, 0.0, "workspace.create not invoked")
    if workspace_row is None or not str(workspace_row.get("id") or "").strip():
        return RubricOutcome(False, 0.0, "expected agentlayer workspace not found via API")
    summary = git_changes if isinstance(git_changes, dict) else {}
    git_changed = bool(summary.get("has_changes"))
    file_diff = summary.get("file_diff") if isinstance(summary.get("file_diff"), dict) else {}
    diff_text = str(file_diff.get("diff") or summary.get("diff") or "")
    has_report_diff = "SECURITY_REPORT" in diff_text
    has_sec = _security_scan_action(tool_names)
    edit_action = _coding_edit_action(tool_names)
    if has_sec and (git_changed or has_report_diff) and edit_action:
        return RubricOutcome(True, 1.0, None)
    if has_sec and (git_changed or has_report_diff):
        return RubricOutcome(True, 0.85, None)
    if has_sec:
        return RubricOutcome(True, 0.6, None)
    parts: list[str] = []
    if not has_sec:
        parts.append("no delegate or security_scan tools")
    if not git_changed and not has_report_diff:
        parts.append("no SECURITY_REPORT or git changes")
    return RubricOutcome(False, 0.0, "; ".join(parts) or "sec2 rubric failed")


def rubric_int1_gmail_connected(
    *,
    content: str,
    tool_names: list[str],
    error: str | None,
    **_: Any,
) -> RubricOutcome:
    if error:
        return RubricOutcome(False, 0.0, error)
    low = (content or "").lower()
    if "gmail-ready" in low:
        return RubricOutcome(True, 1.0, None)
    names = _tool_names_lower(tool_names)
    if any(any(h in n for h in _GMAIL_TOOL_HINTS) for n in names):
        return RubricOutcome(True, 0.9, None)
    if any(h in low for h in _GMAIL_TOOL_HINTS) and "missing" not in low and "not configured" not in low:
        return RubricOutcome(True, 0.75, None)
    return RubricOutcome(False, 0.0, "gmail not confirmed in reply or tools")


def rubric_c1_bench_marker(
    *,
    content: str,
    tool_names: list[str],
    tool_invocations: list[dict[str, Any]],
    error: str | None,
    project_summary: dict[str, Any] | None = None,
    project_status: str | None = None,
    git_changes: dict[str, Any] | None = None,
    workspace_row: dict[str, Any] | None = None,
    **_: Any,
) -> RubricOutcome:
    if error:
        return RubricOutcome(False, 0.0, error)
    if not _used_workspace_create(tool_names):
        return RubricOutcome(False, 0.0, "workspace.create not invoked")
    summary = git_changes if isinstance(git_changes, dict) else {}
    has_changes = bool(summary.get("has_changes"))
    file_diff = summary.get("file_diff") if isinstance(summary.get("file_diff"), dict) else {}
    diff_text = str(file_diff.get("diff") or summary.get("diff") or "")
    stat_text = str(summary.get("stat") or "")
    marker_present = (
        "bench-marker.txt" in diff_text
        or "bench-marker.txt" in stat_text
        or "bench-ok" in diff_text
    )
    edit_action = _coding_edit_action(tool_names)
    reply_ok = "bench-ok" in (content or "")
    ws_ok = bool(workspace_row and str(workspace_row.get("id") or "").strip())
    if edit_action and reply_ok and (has_changes or marker_present) and ws_ok:
        return RubricOutcome(True, 1.0, None)
    if edit_action and reply_ok and ws_ok:
        return RubricOutcome(True, 0.85, None)
    parts: list[str] = []
    if not edit_action:
        parts.append("no delegate or write tool detected")
    if not reply_ok:
        parts.append("reply missing bench-ok")
    if not has_changes and not marker_present:
        parts.append("no git change for bench-marker.txt")
    if not ws_ok:
        parts.append("expected coding workspace not found via API")
    return RubricOutcome(False, 0.0, "; ".join(parts) or "c1 rubric failed")


def rubric_c2_small_edit(
    *,
    content: str,
    tool_names: list[str],
    tool_invocations: list[dict[str, Any]],
    error: str | None,
    git_changes: dict[str, Any] | None = None,
    **_: Any,
) -> RubricOutcome:
    if error:
        return RubricOutcome(False, 0.0, error)
    summary = git_changes if isinstance(git_changes, dict) else {}
    has_changes = bool(summary.get("has_changes"))
    file_diff = summary.get("file_diff") if isinstance(summary.get("file_diff"), dict) else {}
    diff_text = str(file_diff.get("diff") or summary.get("diff") or "")
    stat_text = str(summary.get("stat") or "")
    marker_present = "bench-c2-ok" in diff_text or "bench-c2-ok" in stat_text
    edit_action = _coding_edit_action(tool_names)
    reply_ok = "bench-c2-ok" in (content or "")
    if has_changes and marker_present and edit_action and reply_ok:
        return RubricOutcome(True, 1.0, None)
    if has_changes and edit_action and reply_ok:
        return RubricOutcome(True, 0.9, None)
    if has_changes and edit_action:
        return RubricOutcome(True, 0.75, None)
    parts: list[str] = []
    if not has_changes:
        parts.append("no git changes")
    if not edit_action:
        parts.append("no delegate or write tool detected")
    if not reply_ok:
        parts.append("reply missing bench-c2-ok")
    if has_changes and not marker_present:
        parts.append("diff missing bench-c2-ok marker")
    return RubricOutcome(False, 0.0, "; ".join(parts) or "c2 rubric failed")


RUBRICS: dict[str, Callable[..., RubricOutcome]] = {
    "s1_tool_catalog": rubric_s1_tool_catalog,
    "s2_simple_chat": rubric_s2_simple_chat,
    "s4_delegate_math": rubric_s4_delegate_math,
    "s3_read_file": rubric_s3_read_file,
    "w1_git_readme": rubric_w1_git_readme,
    "w2_find_octocat": rubric_w2_find_octocat,
    "w2_find_octocat_indexed": rubric_w2_find_octocat_indexed,
    "soc1_share_data": rubric_soc1_share_data,
    "d1_dashboard_create": rubric_d1_dashboard_create,
    "d2_layout_patch": rubric_d2_layout_patch,
    "int1_gmail_connected": rubric_int1_gmail_connected,
    "c1_bench_marker": rubric_c1_bench_marker,
    "c2_small_edit": rubric_c2_small_edit,
    "sec1_scan_agentlayer": rubric_sec1_scan_agentlayer,
    "sec2_remediate_agentlayer": rubric_sec2_remediate_agentlayer,
}


def evaluate_rubric(rubric_key: str, **kwargs: Any) -> RubricOutcome:
    fn = RUBRICS.get(rubric_key)
    if fn is None:
        return RubricOutcome(False, 0.0, f"unknown rubric: {rubric_key}")
    return fn(**kwargs)
