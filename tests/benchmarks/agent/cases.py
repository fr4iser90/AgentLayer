"""Agent LLM benchmark scenarios (composable via fixture requires)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from tests.benchmarks.agent.fixtures import agentlayer_bench_git_url
from tests.e2e.support.helpers import git_clone_url


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
    skip_without_env: str | None = None
    bench_workspace_suffix: str | None = None
    bench_dashboard_title_suffix: str | None = None


def _hello_git_url() -> str:
    return (os.environ.get("AGENT_BENCH_GIT_URL") or git_clone_url()).strip()


def _hello_git_branch() -> str:
    return (os.environ.get("AGENT_BENCH_GIT_BRANCH") or "master").strip() or "master"


def _agentlayer_git_branch() -> str:
    return (os.environ.get("AGENT_BENCH_AGENTLAYER_GIT_BRANCH") or "main").strip() or "main"


def _clone_workspace_step(*, prefix: str, suffix: str, git_url: str, git_branch: str) -> str:
    return (
        f'Use workspace.create with source=git, git_url="{git_url}", git_branch="{git_branch}", '
        f'name exactly "{prefix}{suffix}", and bind=true. Do this before delegate or read tools.\n\n'
    )


def _delegate_coding_step(*, sub_prompt: str) -> str:
    """General chat surface: repo edits run via delegate → coding sub-agent."""
    return (
        "Use delegate with run_subagent=true and agent_id=coding. "
        f"In the delegate prompt, instruct the coding sub-agent to: {sub_prompt} "
        "Do not call write_file, edit, or apply_patch on this surface.\n\n"
    )


def _delegate_security_auditor_step(*, sub_prompt: str) -> str:
    return (
        "Use delegate with run_subagent=true and agent_id=security_auditor. "
        f"In the delegate prompt: {sub_prompt} "
        "Do not call security_scan_* tools directly on this surface.\n\n"
    )


TIER1_SCENARIOS: list[AgentScenario] = [
    AgentScenario(
        id="S1_tool_catalog",
        tier=1,
        prompt=(
            "Use the catalog tool to list tools available to the general agent. "
            "Call the tool, then reply with at least three tool names you found."
        ),
        rubric="s1_tool_catalog",
    ),
    AgentScenario(
        id="S2_simple_chat",
        tier=1,
        prompt="What is 17 + 25? Reply with the numeric result only.",
        rubric="s2_simple_chat",
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
    ),
]

_W2_FIND_OCTOCAT_BODY = (
    "In that workspace, find where 'Octocat' or the Hello World repository is mentioned. "
    "Use workspace search or retrieval tools if available; otherwise read files. "
    "Reply with the file path and a short matching excerpt."
)

TIER2_SCENARIOS: list[AgentScenario] = [
    AgentScenario(
        id="W1_git_readme_no_index",
        tier=2,
        prompt=(
            _clone_workspace_step(
                prefix="{prefix}",
                suffix="git",
                git_url=_hello_git_url(),
                git_branch=_hello_git_branch(),
            )
            + "Use read_file to read README.md at the repository root. "
            "Reply with the first non-empty line."
        ),
        rubric="w1_git_readme",
        bench_workspace_suffix="git",
    ),
    AgentScenario(
        id="W2_find_octocat_no_index",
        tier=2,
        prompt=(
            _clone_workspace_step(
                prefix="{prefix}",
                suffix="git",
                git_url=_hello_git_url(),
                git_branch=_hello_git_branch(),
            )
            + _W2_FIND_OCTOCAT_BODY
        ),
        rubric="w2_find_octocat",
        bench_workspace_suffix="git",
    ),
    AgentScenario(
        id="W2_find_octocat_indexed",
        tier=2,
        prompt=(
            _clone_workspace_step(
                prefix="{prefix}",
                suffix="git",
                git_url=_hello_git_url(),
                git_branch=_hello_git_branch(),
            )
            + "Run a code index on the workspace (index tool or workspace index API via tools) "
            "before searching.\n"
            + _W2_FIND_OCTOCAT_BODY
        ),
        rubric="w2_find_octocat_indexed",
        bench_workspace_suffix="git",
    ),
    AgentScenario(
        id="SOC1_block_share_visible",
        tier=2,
        agent_id="dashboard",
        prompt=(
            "Create a custom dashboard titled exactly \"{prefix}share\" with:\n"
            "- data.shared_notes = bench-visible\n"
            "- data.private_notes = bench-hidden\n"
            "- one markdown block id bench-md-shared with props.dataPath shared_notes\n"
            "- one markdown block id bench-md-private with props.dataPath private_notes\n"
            "Then use dashboard.block_share_grant (or equivalent) to grant view on block "
            "bench-md-shared to {friend_email}.\n"
            "Finally read shared_notes and reply with exactly: bench-visible"
        ),
        rubric="soc1_share_data",
        requires=("friend_pair",),
        bench_dashboard_title_suffix="share",
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
        bench_dashboard_title_suffix="create",
    ),
    AgentScenario(
        id="D2_layout_patch",
        tier=2,
        agent_id="dashboard",
        prompt=(
            "Create a new custom dashboard titled exactly \"{prefix}layout\" (kind custom). "
            "Use patch_layout to add one markdown block with props.dataPath set to \"notes\". "
            "Use patch_data to set notes to exactly \"bench-notes-ok\". "
            "Reply with block_added: yes"
        ),
        rubric="d2_layout_patch",
        bench_dashboard_title_suffix="layout",
    ),
]

TIER3_SCENARIOS: list[AgentScenario] = [
    AgentScenario(
        id="C1_bench_marker_file",
        tier=3,
        execution="chat",
        agent_id="general",
        prompt=(
            _clone_workspace_step(
                prefix="{prefix}",
                suffix="coding",
                git_url=_hello_git_url(),
                git_branch=_hello_git_branch(),
            )
            + _delegate_coding_step(
                sub_prompt=(
                    "Create a new file bench-marker.txt at the repository root containing exactly "
                    "one line: bench-ok (use write_file, edit, or apply_patch in the workspace)."
                )
            )
            + "When the file exists with that content, reply with exactly: bench-ok"
        ),
        rubric="c1_bench_marker",
        bench_workspace_suffix="coding",
    ),
    AgentScenario(
        id="C2_small_edit",
        tier=3,
        agent_id="general",
        prompt=(
            _clone_workspace_step(
                prefix="{prefix}",
                suffix="c2",
                git_url=_hello_git_url(),
                git_branch=_hello_git_branch(),
            )
            + _delegate_coding_step(
                sub_prompt=(
                    "In the bound workspace: (1) create and checkout local branch bench-c2-edit "
                    "(do not git push); (2) open README at repo root (README.md or README); "
                    "(3) add one line containing exactly bench-c2-ok (plain line or "
                    "<!-- bench-c2-ok --> is fine) via edit, write_file, or apply_patch."
                )
            )
            + "When the line is saved, reply with exactly: bench-c2-ok"
        ),
        rubric="c2_small_edit",
        bench_workspace_suffix="c2",
    ),
]

TIER4_SCENARIOS: list[AgentScenario] = [
    AgentScenario(
        id="SEC1_scan_agentlayer",
        tier=4,
        prompt=(
            _clone_workspace_step(
                prefix="{prefix}",
                suffix="agentlayer",
                git_url=agentlayer_bench_git_url(),
                git_branch=_agentlayer_git_branch(),
            )
            + _delegate_security_auditor_step(
                sub_prompt=(
                    "Run a SimpleSecCheck security scan on the repository using security_scan_resolve "
                    "(or security_scan_start if resolve unavailable). Use the workspace git URL. "
                    "Do not poll status repeatedly — report scan_id and status from the first response."
                )
            )
            + "Reply with lines: scan_id: … and status: …"
        ),
        rubric="sec1_scan_agentlayer",
        agent_id="general",
        requires=("ssc_secret",),
        bench_workspace_suffix="agentlayer",
    ),
    AgentScenario(
        id="SEC2_remediate_agentlayer",
        tier=4,
        execution="chat",
        security_scan=True,
        agent_id="general",
        prompt=(
            _clone_workspace_step(
                prefix="{prefix}",
                suffix="agentlayer",
                git_url=agentlayer_bench_git_url(),
                git_branch=_agentlayer_git_branch(),
            )
            + _delegate_coding_step(
                sub_prompt=(
                    "Security remediation on this workspace: (1) git_read status; git_sync pull ff-only; "
                    "(2) create branch agent/sec-bench-{today's YYYYMMDD}; "
                    "(3) security_scan finding_policy_schema once, then resolve/start on the repo; "
                    "(4) write findings summary to docs/SECURITY_REPORT.md; "
                    "(5) fix at most ONE finding (prefer LOW) with a minimal patch; (6) no git push."
                )
            )
            + "Reply with scan_id, branch, and files changed."
        ),
        rubric="sec2_remediate_agentlayer",
        requires=("ssc_secret",),
        bench_workspace_suffix="agentlayer",
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


def bench_workspace_name(scenario: AgentScenario, prefix: str) -> str | None:
    suffix = (scenario.bench_workspace_suffix or "").strip()
    if not suffix:
        return None
    return f"{prefix}{suffix}"


def bench_dashboard_title(scenario: AgentScenario, prefix: str) -> str | None:
    suffix = (scenario.bench_dashboard_title_suffix or "").strip()
    if not suffix:
        return None
    return f"{prefix}{suffix}"
