"""Long-running coding benchmarks via project_runs queue + poll."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from tests.benchmarks.agent.harness import (
    ModelProfile,
    ScenarioResult,
    _fetch_run_trace,
)
from tests.benchmarks.agent.metrics import RunMetrics, build_run_metrics
from tests.benchmarks.agent.cases import AgentScenario
from tests.benchmarks.agent.fixtures import FixtureContext
from tests.benchmarks.agent.rubrics import RubricOutcome, evaluate_rubric
from tests.e2e.support.helpers import E2EClient


def _poll_interval_s() -> float:
    return max(5.0, float(os.environ.get("AGENT_BENCH_PROJECT_POLL_S") or "15"))


def _terminal_status(status: str) -> bool:
    return status in ("succeeded", "failed", "cancelled")


def poll_project_run(
    client: E2EClient,
    run_id: str,
    *,
    timeout_s: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    poll_s = _poll_interval_s()
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        payload = client.get_json(f"/v1/project-runs/{run_id}")
        row = payload.get("run") if isinstance(payload, dict) else None
        if not isinstance(row, dict):
            raise RuntimeError(f"project run poll invalid response: {payload!r}")
        last = row
        if _terminal_status(str(row.get("status") or "")):
            return row
        time.sleep(poll_s)
    raise TimeoutError(f"project run {run_id} did not finish within {timeout_s}s (last={last.get('status')})")


def _tools_to_invocations(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        out.append(
            {
                "tool_name": t.get("name"),
                "ok": t.get("ok"),
                "args_json": t.get("args"),
                "result_excerpt": t.get("error") or "",
            }
        )
    return out


def run_project_run_scenario(
    client: E2EClient,
    *,
    profile: ModelProfile,
    scenario: AgentScenario,
    run_id: str,
    fixture_ctx: FixtureContext,
    defaults: dict[str, Any],
) -> ScenarioResult:
    fixture_list = list(scenario.requires)
    if not fixture_ctx.workspace_id:
        return ScenarioResult(
            run_id=run_id,
            scenario_id=scenario.id,
            profile_label=profile.label,
            model=profile.model,
            catalog_owned_by=profile.catalog_owned_by,
            agent_id=scenario.agent_id,
            passed=False,
            score=0.0,
            failure_reason="project_run requires workspace_git fixture (workspace_id)",
            latency_ms=0.0,
            prompt_tokens=None,
            completion_tokens=None,
            tool_call_count=0,
            tool_names=[],
            agent_run_id=None,
            assistant_excerpt="",
            fixtures=fixture_list,
            error="missing workspace_id",
        )

    if not profile.model:
        return ScenarioResult(
            run_id=run_id,
            scenario_id=scenario.id,
            profile_label=profile.label,
            model=profile.model,
            catalog_owned_by=profile.catalog_owned_by,
            agent_id=scenario.agent_id,
            passed=False,
            score=0.0,
            failure_reason="profile.model is empty",
            latency_ms=0.0,
            prompt_tokens=None,
            completion_tokens=None,
            tool_call_count=0,
            tool_names=[],
            agent_run_id=None,
            assistant_excerpt="",
            fixtures=fixture_list,
            error="missing model",
        )

    timeout_s = float(scenario.timeout_s or defaults.get("timeout_s") or 7200.0)
    coding_workflow = {
        "workspace_id": fixture_ctx.workspace_id,
        "agent_id": scenario.agent_id or "coding",
        "model": profile.model,
        "model_catalog_owned_by": profile.catalog_owned_by,
    }
    if scenario.security_scan:
        coding_workflow["security_scan"] = True
    body = {
        "instructions": scenario.prompt,
        "coding_workflow": coding_workflow,
        "project_title": f"bench-{run_id}-{scenario.id}",
    }

    t0 = time.perf_counter()
    error: str | None = None
    project_row: dict[str, Any] = {}
    try:
        created = client.post_json("/v1/project-runs", body)
        project_row = created.get("run") if isinstance(created, dict) else {}
        pr_id = str(project_row.get("id") or "")
        if not pr_id:
            raise RuntimeError(f"project run create failed: {created!r}")
        project_row = poll_project_run(client, pr_id, timeout_s=timeout_s)
    except httpx.HTTPStatusError as exc:
        error = f"HTTP {exc.response.status_code}: {exc.response.text[:500]}"
    except TimeoutError as exc:
        error = str(exc)
    except httpx.HTTPError as exc:
        error = str(exc)
    except RuntimeError as exc:
        error = str(exc)

    latency_ms = (time.perf_counter() - t0) * 1000.0
    result_json = project_row.get("result_json") if isinstance(project_row.get("result_json"), dict) else {}
    status = str(project_row.get("status") or "")
    row_error = str(project_row.get("error") or "").strip() or None
    if row_error and not error:
        error = row_error

    content = str(result_json.get("final_reply_excerpt") or "")
    agent_run_id = str(result_json.get("agent_run_id") or "") or None
    schedule_tools = result_json.get("tools") if isinstance(result_json.get("tools"), list) else []
    invocations = _tools_to_invocations(schedule_tools)
    tool_names = [str(i.get("tool_name") or "") for i in invocations if i.get("tool_name")]

    _, trace_invocations, agent_run = _fetch_run_trace(client, agent_run_id)
    if trace_invocations:
        invocations = trace_invocations
        tool_names = [str(i.get("tool_name") or "") for i in invocations if i.get("tool_name")]

    pseudo_completion = {
        "agentlayer_context": result_json.get("context_snapshot") or {},
        "usage": {},
    }
    if isinstance(agent_run, dict) and isinstance(agent_run.get("token_usage"), dict):
        pseudo_completion["usage"] = agent_run["token_usage"]

    run_metrics_obj: RunMetrics = build_run_metrics(
        completion=pseudo_completion,
        ws_events=None,
        tool_invocations=invocations,
        agent_run=agent_run,
        capture_mode="project_run",
    )
    run_metrics_dict = run_metrics_obj.to_dict()
    run_metrics_dict["project_run_id"] = project_row.get("id")
    run_metrics_dict["project_run_status"] = status
    run_metrics_dict["project_run_outcome"] = result_json.get("outcome")
    run_metrics_dict["duration_ms_reported"] = result_json.get("duration_ms")
    run_metrics_dict["git"] = result_json.get("git")
    run_metrics_dict["files_changed"] = result_json.get("files_changed")
    run_metrics_dict["poll_interval_s"] = _poll_interval_s()

    rubric: RubricOutcome = evaluate_rubric(
        scenario.rubric,
        content=content,
        tool_names=tool_names,
        tool_invocations=invocations,
        error=error,
        latency_ms=latency_ms,
        project_summary=result_json,
        project_status=status,
    )

    return ScenarioResult(
        run_id=run_id,
        scenario_id=scenario.id,
        profile_label=profile.label,
        model=profile.model,
        catalog_owned_by=profile.catalog_owned_by,
        agent_id=scenario.agent_id,
        passed=rubric.passed and status == "succeeded",
        score=rubric.score,
        failure_reason=rubric.failure_reason,
        latency_ms=latency_ms,
        prompt_tokens=run_metrics_obj.prompt_tokens,
        completion_tokens=run_metrics_obj.completion_tokens,
        tool_call_count=len(tool_names),
        tool_names=tool_names,
        agent_run_id=agent_run_id,
        assistant_excerpt=content[:400],
        fixtures=fixture_list,
        error=error,
        http_status=None,
        run_metrics=run_metrics_dict,
    )
