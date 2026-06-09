"""Agent LLM benchmark scenarios (composable via fixture requires)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentScenario:
    id: str
    tier: int
    prompt: str
    rubric: str
    agent_id: str = "general"
    execution: str = "chat"
    security_scan: bool = False
    requires: tuple[str, ...] = ()
    max_tool_rounds: int = 5
    timeout_s: float = 120.0
    skip_without_env: str | None = None


TIER1_SCENARIOS: list[AgentScenario] = [
    AgentScenario(
        id="S1_tool_catalog",
        tier=1,
        prompt=(
            "Use the catalog tool to list tools available to the general agent. "
            "Call the tool, then reply with at least three tool names you found."
        ),
        rubric="s1_tool_catalog",
        max_tool_rounds=4,
        timeout_s=120.0,
    ),
    AgentScenario(
        id="S2_simple_chat",
        tier=1,
        prompt="What is 17 + 25? Reply with the numeric result only.",
        rubric="s2_simple_chat",
        max_tool_rounds=0,
        timeout_s=60.0,
    ),
    AgentScenario(
        id="S3_read_file",
        tier=1,
        prompt=(
            "Use read_file to read README.md in the bound workspace root. "
            "Reply with the first line of the file."
        ),
        rubric="s3_read_file",
        requires=("agentlayer_self",),
        max_tool_rounds=4,
        timeout_s=180.0,
    ),
]

_W2_FIND_OCTOCAT_PROMPT = (
    "In this git workspace, find where 'Octocat' or the Hello World repository is mentioned. "
    "Use workspace search or retrieval tools if available; otherwise read files. "
    "Reply with the file path and a short matching excerpt."
)

TIER2_SCENARIOS: list[AgentScenario] = [
    AgentScenario(
        id="W1_git_readme_no_index",
        tier=2,
        prompt=(
            "Use read_file to read README.md at the repository root of the bound workspace. "
            "Reply with the first non-empty line."
        ),
        rubric="w1_git_readme",
        requires=("workspace_git",),
        max_tool_rounds=4,
        timeout_s=180.0,
    ),
    AgentScenario(
        id="W2_find_octocat_no_index",
        tier=2,
        prompt=_W2_FIND_OCTOCAT_PROMPT,
        rubric="w2_find_octocat",
        requires=("workspace_git",),
        max_tool_rounds=6,
        timeout_s=240.0,
    ),
    AgentScenario(
        id="W2_find_octocat_indexed",
        tier=2,
        prompt=_W2_FIND_OCTOCAT_PROMPT,
        rubric="w2_find_octocat_indexed",
        requires=("workspace_git", "workspace_indexed"),
        max_tool_rounds=6,
        timeout_s=300.0,
    ),
    AgentScenario(
        id="SOC1_block_share_visible",
        tier=2,
        agent_id="dashboard",
        prompt=(
            "A dashboard was prepared with shared_notes='bench-visible'. "
            "Using tools only if needed, confirm the shared_notes value and reply with exactly: bench-visible"
        ),
        rubric="soc1_share_data",
        requires=("dashboard_block_share",),
        max_tool_rounds=3,
        timeout_s=120.0,
    ),
    AgentScenario(
        id="D1_dashboard_create",
        tier=2,
        agent_id="general",
        prompt=(
            "Create a new custom dashboard with title exactly \"{prefix}create\" "
            "(use create_dashboard with kind custom or an empty custom template). "
            "Reply with dashboard_id: … and title: … when done."
        ),
        rubric="d1_dashboard_create",
        max_tool_rounds=6,
        timeout_s=300.0,
    ),
    AgentScenario(
        id="D2_layout_patch",
        tier=2,
        agent_id="dashboard",
        prompt=(
            "On dashboard {dashboard_id} (title \"{prefix}layout\"), use patch_layout to add one markdown "
            "block with props.dataPath set to \"notes\". Use patch_data to set notes to exactly "
            "\"bench-notes-ok\". Reply with block_added: yes"
        ),
        rubric="d2_layout_patch",
        requires=("dashboard_empty",),
        max_tool_rounds=8,
        timeout_s=300.0,
    ),
]

TIER3_SCENARIOS: list[AgentScenario] = [
    AgentScenario(
        id="C1_bench_marker_file",
        tier=3,
        execution="project_run",
        agent_id="coding",
        prompt=(
            "In the bound git workspace, create a new file bench-marker.txt at the repository "
            "root containing exactly one line: bench-ok. Use write_file, edit, or apply_patch. "
            "When the file exists with that content, reply with exactly: bench-ok"
        ),
        rubric="c1_bench_marker",
        requires=("workspace_git",),
        max_tool_rounds=24,
        timeout_s=float(os.environ.get("AGENT_BENCH_C1_TIMEOUT_S") or "7200"),
    ),
    AgentScenario(
        id="C2_small_edit",
        tier=3,
        agent_id="coding",
        prompt=(
            "In the bound git workspace:\n"
            "1. Create and checkout local branch bench-c2-edit (do not git push).\n"
            "2. Open the README at the repository root (README.md or README).\n"
            "3. Add one line containing exactly: bench-c2-ok "
            "(plain line or markdown comment <!-- bench-c2-ok --> is fine).\n"
            "4. Use edit, write_file, or apply_patch.\n"
            "When the line is saved, reply with exactly: bench-c2-ok"
        ),
        rubric="c2_small_edit",
        requires=("workspace_git",),
        max_tool_rounds=12,
        timeout_s=float(os.environ.get("AGENT_BENCH_C2_TIMEOUT_S") or "1800"),
    ),
]

TIER4_SCENARIOS: list[AgentScenario] = [
    AgentScenario(
        id="SEC1_scan_agentlayer",
        tier=4,
        prompt=(
            "This workspace is a clone of https://github.com/fr4iser90/AgentLayer. "
            "Run a SimpleSecCheck security scan on the repository using security_scan_resolve "
            "(or security_scan_start if resolve unavailable). Use the workspace git URL. "
            "Do not poll status repeatedly in one turn — report scan_id and status from the first response. "
            "Reply with lines: scan_id: … and status: …"
        ),
        rubric="sec1_scan_agentlayer",
        agent_id="coding",
        requires=("workspace_agentlayer_git", "ssc_secret"),
        max_tool_rounds=8,
        timeout_s=600.0,
    ),
    AgentScenario(
        id="SEC2_remediate_agentlayer",
        tier=4,
        execution="project_run",
        security_scan=True,
        agent_id="coding",
        prompt=(
            "Security remediation on this AgentLayer workspace (https://github.com/fr4iser90/AgentLayer).\n\n"
            "1. coding_git_read; coding_git_sync pull (ff-only).\n"
            "2. Create branch agent/sec-bench-{today's YYYYMMDD}.\n"
            "3. security_scan_finding_policy_schema once; then security_scan_resolve/start on the repo.\n"
            "4. Write findings summary to docs/SECURITY_REPORT.md.\n"
            "5. Fix at most ONE finding (prefer LOW severity) with a minimal patch.\n"
            "6. No git push. Reply with scan_id, branch, and files changed."
        ),
        rubric="sec2_remediate_agentlayer",
        requires=("workspace_agentlayer_git", "ssc_secret"),
        max_tool_rounds=24,
        timeout_s=float(os.environ.get("AGENT_BENCH_SEC2_TIMEOUT_S") or "7200"),
    ),
]

INTEGRATION_SCENARIOS: list[AgentScenario] = [
    AgentScenario(
        id="INT1_gmail_connected",
        tier=2,
        prompt=(
            "Check whether Gmail is configured for this user (list mail tools or verify connection). "
            "Reply with 'gmail-ready' if credentials are stored, otherwise explain what is missing."
        ),
        rubric="int1_gmail_connected",
        requires=("gmail_secret",),
        max_tool_rounds=4,
        timeout_s=180.0,
    ),
]

_ALL = (
    TIER1_SCENARIOS
    + TIER2_SCENARIOS
    + TIER3_SCENARIOS
    + TIER4_SCENARIOS
    + INTEGRATION_SCENARIOS
)
SCENARIO_BY_ID = {s.id: s for s in _ALL}


def scenarios_for_tier(max_tier: int) -> list[AgentScenario]:
    tier = max(1, int(max_tier))
    return [s for s in _ALL if s.tier <= tier]
