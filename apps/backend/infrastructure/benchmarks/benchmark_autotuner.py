"""Benchmark-driven per-model harness autotuning."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import timezone, datetime
from typing import Any

from apps.backend.domain.agent_runtime.config_registry import all_knobs
from apps.backend.infrastructure.agent_runtime import agent_config_service
from apps.backend.infrastructure.benchmarks import benchmark_runs_store, benchmark_tuning_store
from apps.backend.infrastructure.benchmarks.benchmark_runner import start_benchmark_run
from apps.backend.infrastructure.providers.model_catalog_providers import route_chat_by_catalog_provider
from apps.backend.infrastructure.providers.openai_compat_http import http_post_chat_completions


_POLL_SEC = 2.0
_FINAL_STATUSES = {"completed", "failed", "cancelled"}
_tune_lock = asyncio.Lock()


def tuning_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": "baseline",
            "label": "Baseline",
            "patches": [],
        },
        {
            "id": "small_strict",
            "label": "Small strict tools",
            "patches": [
                {"knob_id": "tool_routing.router_strict_default", "value": True},
                {"knob_id": "tool_forward.full_schema", "value": False},
                {"knob_id": "tool_forward.ranking_enabled", "value": True},
                {"knob_id": "agent.max_tool_rounds", "value": 10},
                {"knob_id": "agent.subagent_max_tool_rounds", "value": 8},
            ],
        },
        {
            "id": "small_guided",
            "label": "Small guided tools",
            "patches": [
                {"knob_id": "tool_routing.router_strict_default", "value": True},
                {"knob_id": "tool_routing.task_intent_overlay_enabled", "value": True},
                {"knob_id": "tool_routing.task_intent_strict_tools", "value": True},
                {"knob_id": "tool_forward.ranking_enabled", "value": True},
                {"knob_id": "tool_forward.catalog_after_first_round", "value": True},
            ],
        },
        {
            "id": "more_patience",
            "label": "More patience",
            "patches": [
                {"knob_id": "agent.max_tool_rounds", "value": 24},
                {"knob_id": "agent.subagent_max_tool_rounds", "value": 18},
                {"knob_id": "agent.subagent_timeout_sec", "value": 600},
            ],
        },
        {
            "id": "strong_full",
            "label": "Strong full schema",
            "patches": [
                {"knob_id": "tool_forward.full_schema", "value": True},
                {"knob_id": "agent.max_tool_rounds", "value": 24},
                {"knob_id": "context.tools_budget_ratio", "value": 0.08},
            ],
        },
    ]


def plan_for_mode(mode: str) -> dict[str, Any]:
    m = (mode or "fast").strip().lower()
    if m == "deep":
        suites = ["smoke", "prompt_security", "coding"]
        preset_ids = ["baseline", "small_strict", "small_guided", "more_patience", "strong_full"]
    elif m == "standard":
        suites = ["smoke", "prompt_security"]
        preset_ids = ["baseline", "small_strict", "small_guided", "more_patience"]
    else:
        m = "fast"
        suites = ["smoke"]
        preset_ids = ["baseline", "small_strict", "small_guided"]
    presets_by_id = {p["id"]: p for p in tuning_presets()}
    return {
        "mode": m,
        "suites": suites,
        "presets": [presets_by_id[p] for p in preset_ids],
        "prompt_locale": "en",
        "prompt_variant": "canonical",
    }


def create_tuning_session(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    mode: str,
    profile: dict[str, Any],
    run_as_user_id: uuid.UUID | None = None,
    friend_user_id: uuid.UUID | None = None,
    reviewer_mode: str = "off",
    reviewer_provider_id: str | None = None,
    reviewer_model: str | None = None,
    max_patch_rounds: int = 0,
) -> dict[str, Any]:
    catalog = str(profile.get("catalog_owned_by") or "").strip()
    model = str(profile.get("model") or "").strip()
    if not catalog or not model:
        raise ValueError("profile.catalog_owned_by and profile.model are required")
    plan = plan_for_mode(mode)
    plan["run_as_user_id"] = str(run_as_user_id) if run_as_user_id else None
    plan["friend_user_id"] = str(friend_user_id) if friend_user_id else None
    plan["reviewer_mode"] = _reviewer_mode(reviewer_mode)
    plan["reviewer_provider_id"] = (reviewer_provider_id or "").strip() or None
    plan["reviewer_model"] = (reviewer_model or "").strip() or None
    plan["max_patch_rounds"] = max(0, min(int(max_patch_rounds or 0), 10))
    return benchmark_tuning_store.create_session(
        tenant_id=tenant_id,
        user_id=user_id,
        mode=str(plan["mode"]),
        catalog_owned_by=catalog,
        model=model,
        profiles=[profile],
        plan=plan,
    )


async def run_tuning_session(session_id: uuid.UUID) -> None:
    async with _tune_lock:
        await _run_tuning_session_locked(session_id)


async def _run_tuning_session_locked(session_id: uuid.UUID) -> None:
    row = benchmark_tuning_store.get_session(session_id)
    if not row:
        return
    tenant_id = int(row["tenant_id"])
    user_id = uuid.UUID(str(row["user_id"])) if row.get("user_id") else None
    profiles = row.get("profiles_json") if isinstance(row.get("profiles_json"), list) else []
    plan = row.get("plan_json") if isinstance(row.get("plan_json"), dict) else {}
    suites = [str(x) for x in plan.get("suites") or ["smoke"]]
    presets = plan.get("presets") if isinstance(plan.get("presets"), list) else []
    run_as = uuid.UUID(str(plan["run_as_user_id"])) if plan.get("run_as_user_id") else user_id
    friend = uuid.UUID(str(plan["friend_user_id"])) if plan.get("friend_user_id") else None
    locale = str(plan.get("prompt_locale") or "en")
    variant = str(plan.get("prompt_variant") or "canonical")
    attempts: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None

    benchmark_tuning_store.update_session(session_id, status="running")
    try:
        for preset in presets:
            if not isinstance(preset, dict):
                continue
            patches = preset.get("patches") if isinstance(preset.get("patches"), list) else []
            attempt_runs: list[dict[str, Any]] = []
            for suite in suites:
                cohort = {
                    "cohort_label": f"autotune:{session_id.hex[:8]}:{preset.get('id')}:{suite}",
                    "tuning_session_id": str(session_id),
                    "tuning_preset": preset.get("id"),
                    "harness_overrides": patches,
                }
                run = await start_benchmark_run(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    suite=suite,
                    profiles=profiles,
                    run_as_user_id=run_as,
                    friend_user_id=friend,
                    admin_user_id=user_id,
                    prompt_locale=locale,
                    prompt_variant=variant,
                    cohort_json=cohort,
                    scenario_failure_retries=0,
                )
                completed = await _wait_for_run(uuid.UUID(str(run["id"])))
                attempt_runs.append(_summarize_run(completed or run))
                if completed and str(completed.get("status") or "") != "completed":
                    break
            attempt = _score_attempt(
                preset_id=str(preset.get("id") or ""),
                label=str(preset.get("label") or preset.get("id") or ""),
                patches=patches,
                runs=attempt_runs,
            )
            attempts.append(attempt)
            benchmark_tuning_store.append_attempt(session_id, attempt)
            if best is None or float(attempt.get("score") or 0) > float(best.get("score") or 0):
                best = attempt

        guided = await _run_reviewer_patch_rounds(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            row=row,
            profiles=profiles,
            plan=plan,
            suites=suites,
            run_as=run_as,
            friend=friend,
            locale=locale,
            variant=variant,
            attempts=attempts,
            current_best=best,
        )
        best = guided["best"]
        attempts = guided["attempts"]

        promotion = _promotion_decision(attempts, best)
        promoted_at = None
        promotion_error = None
        if promotion["promote"] and best is not None:
            result = agent_config_service.apply_model_patches(
                tenant_id=tenant_id,
                catalog_owned_by=str(row.get("catalog_owned_by") or ""),
                model=str(row.get("model") or ""),
                patches=[dict(p) for p in best.get("patches") or [] if isinstance(p, dict)],
                actor_type="operator_agent",
                actor_user_id=user_id,
                label=f"autotune:{row.get('mode') or 'benchmark'}",
                hypothesis=f"Auto-promoted from benchmark tuning session {session_id}",
            )
            if result.get("ok"):
                promoted_at = datetime.now(timezone.utc)
            else:
                promotion_error = str(result.get("validation") or "promotion failed")[:1200]

        benchmark_tuning_store.update_session(
            session_id,
            status="completed",
            attempts_json=attempts,
            best_run_id=uuid.UUID(str(best["best_run_id"])) if best and best.get("best_run_id") else None,
            best_score=float(best.get("score")) if best and best.get("score") is not None else None,
            best_patches_json=best.get("patches") if best else None,
            promoted_at=promoted_at,
            error_text=promotion_error,
            finished_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        benchmark_tuning_store.update_session(
            session_id,
            status="failed",
            attempts_json=attempts,
            error_text=str(exc)[:2000],
            finished_at=datetime.now(timezone.utc),
        )


def _reviewer_mode(raw: str | None) -> str:
    mode = (raw or "off").strip().lower()
    if mode in {"patch", "patch_and_test", "guided"}:
        return "patch_and_test"
    if mode in {"review", "review_only"}:
        return "review_only"
    return "off"


async def _run_reviewer_patch_rounds(
    *,
    session_id: uuid.UUID,
    tenant_id: int,
    user_id: uuid.UUID | None,
    row: dict[str, Any],
    profiles: list[dict[str, Any]],
    plan: dict[str, Any],
    suites: list[str],
    run_as: uuid.UUID | None,
    friend: uuid.UUID | None,
    locale: str,
    variant: str,
    attempts: list[dict[str, Any]],
    current_best: dict[str, Any] | None,
) -> dict[str, Any]:
    if _reviewer_mode(str(plan.get("reviewer_mode") or "off")) != "patch_and_test":
        return {"attempts": attempts, "best": current_best}
    max_rounds = max(0, min(int(plan.get("max_patch_rounds") or 0), 10))
    reviewer_provider_id = str(plan.get("reviewer_provider_id") or "").strip()
    reviewer_model = str(plan.get("reviewer_model") or "").strip()
    if max_rounds <= 0 or not reviewer_provider_id or not reviewer_model:
        return {"attempts": attempts, "best": current_best}

    best = current_best
    seen = {_patch_signature(a.get("patches")) for a in attempts}
    for idx in range(max_rounds):
        candidate = await asyncio.to_thread(
            _reviewer_patch_candidate,
            reviewer_provider_id=reviewer_provider_id,
            reviewer_model=reviewer_model,
            session_id=session_id,
            row=row,
            plan=plan,
            attempts=attempts,
            best=best,
        )
        patches = candidate.get("patches") if isinstance(candidate, dict) else None
        if not isinstance(patches, list) or not patches:
            attempts.append(
                _reviewer_note_attempt(idx, "no_candidate", candidate, reviewer_provider_id, reviewer_model)
            )
            benchmark_tuning_store.append_attempt(session_id, attempts[-1])
            break
        validation = agent_config_service.validate_patches([p for p in patches if isinstance(p, dict)])
        if not validation.get("valid"):
            attempts.append(
                _reviewer_note_attempt(idx, "invalid_candidate", {"validation": validation}, reviewer_provider_id, reviewer_model)
            )
            benchmark_tuning_store.append_attempt(session_id, attempts[-1])
            break
        normalized = [
            {"knob_id": str(p.get("knob_id") or "").strip(), "value": p.get("value")}
            for p in patches
            if isinstance(p, dict)
        ]
        sig = _patch_signature(normalized)
        if sig in seen:
            attempts.append(
                _reviewer_note_attempt(idx, "duplicate_candidate", candidate, reviewer_provider_id, reviewer_model)
            )
            benchmark_tuning_store.append_attempt(session_id, attempts[-1])
            break
        seen.add(sig)

        attempt_runs: list[dict[str, Any]] = []
        preset_id = f"reviewer_round_{idx + 1}"
        for suite in suites:
            cohort = {
                "cohort_label": f"autotune:{session_id.hex[:8]}:{preset_id}:{suite}",
                "tuning_session_id": str(session_id),
                "tuning_preset": preset_id,
                "harness_overrides": normalized,
                "reviewer_provider_id": reviewer_provider_id,
                "reviewer_model": reviewer_model,
            }
            run = await start_benchmark_run(
                tenant_id=tenant_id,
                user_id=user_id,
                suite=suite,
                profiles=profiles,
                run_as_user_id=run_as,
                friend_user_id=friend,
                admin_user_id=user_id,
                prompt_locale=locale,
                prompt_variant=variant,
                cohort_json=cohort,
                scenario_failure_retries=0,
            )
            completed = await _wait_for_run(uuid.UUID(str(run["id"])))
            attempt_runs.append(_summarize_run(completed or run))
            if completed and str(completed.get("status") or "") != "completed":
                break
        attempt = _score_attempt(
            preset_id=preset_id,
            label=f"Reviewer round {idx + 1}",
            patches=normalized,
            runs=attempt_runs,
        )
        attempt["reviewer_json"] = candidate
        attempts.append(attempt)
        benchmark_tuning_store.append_attempt(session_id, attempt)
        if best is None or float(attempt.get("score") or 0) > float(best.get("score") or 0):
            best = attempt
    return {"attempts": attempts, "best": best}


def _reviewer_note_attempt(
    idx: int,
    reason: str,
    payload: Any,
    reviewer_provider_id: str,
    reviewer_model: str,
) -> dict[str, Any]:
    return {
        "preset_id": f"reviewer_round_{idx + 1}",
        "label": f"Reviewer round {idx + 1}",
        "patches": [],
        "runs": [],
        "passed": 0,
        "total": 0,
        "pass_rate": 0.0,
        "safety_violations": 0,
        "score": 0.0,
        "reviewer_status": reason,
        "reviewer_json": payload,
        "reviewer_provider_id": reviewer_provider_id,
        "reviewer_model": reviewer_model,
    }


def _patch_signature(patches: Any) -> str:
    if not isinstance(patches, list):
        return "[]"
    clean = [
        {"knob_id": str(p.get("knob_id") or "").strip(), "value": p.get("value")}
        for p in patches
        if isinstance(p, dict)
    ]
    clean.sort(key=lambda p: p["knob_id"])
    return json.dumps(clean, sort_keys=True, separators=(",", ":"))


def _reviewer_patch_candidate(
    *,
    reviewer_provider_id: str,
    reviewer_model: str,
    session_id: uuid.UUID,
    row: dict[str, Any],
    plan: dict[str, Any],
    attempts: list[dict[str, Any]],
    best: dict[str, Any] | None,
) -> dict[str, Any]:
    attempts_compact = [_compact_attempt(a) for a in attempts[-8:]]
    knobs = [
        {
            "id": str(k.get("id") or ""),
            "type": str(k.get("type") or ""),
            "description": str(k.get("description") or k.get("help") or "")[:240],
        }
        for k in all_knobs()
        if k.get("writable") and str(k.get("layer") or "") not in {"bench", "code", "rubric"}
    ]
    prompt = {
        "task": "Return one minimal AgentLayer harness patch set to improve the next benchmark run.",
        "hard_rules": [
            "Return JSON only.",
            "Do not include markdown.",
            "Only use knob_id values from available_knobs.",
            "Use at most 5 patches.",
            "Prefer small, reversible changes.",
            "Never change global settings; these patches will be tested as temporary per-run overrides.",
        ],
        "response_schema": {
            "reason": "short explanation",
            "patches": [{"knob_id": "string", "value": "json value"}],
        },
        "target": {
            "session_id": str(session_id),
            "catalog_owned_by": str(row.get("catalog_owned_by") or ""),
            "model": str(row.get("model") or ""),
            "mode": str(plan.get("mode") or ""),
            "best_score": best.get("score") if isinstance(best, dict) else None,
        },
        "attempts": attempts_compact,
        "available_knobs": knobs[:80],
    }
    attempts_http, _stack = route_chat_by_catalog_provider(
        reviewer_provider_id,
        reviewer_model,
        "benchmark_reviewer",
        True,
    )
    url, headers, model, provider = attempts_http[0]
    body = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": "You are an AgentLayer benchmark tuning agent. Return strict JSON only.",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    }
    data, _ = http_post_chat_completions(
        url,
        body,
        headers=headers,
        timeout=120.0,
        concurrency_provider_id=provider,
    )
    content = _chat_content(data)
    parsed = _parse_json_object(content)
    parsed["reviewer_provider_id"] = reviewer_provider_id
    parsed["reviewer_model"] = reviewer_model
    return parsed


def _compact_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    failures: dict[str, int] = {}
    for run in attempt.get("runs") or []:
        if not isinstance(run, dict):
            continue
        for k, v in (run.get("failure_clusters") or {}).items():
            failures[str(k)] = failures.get(str(k), 0) + int(v or 0)
    return {
        "preset_id": attempt.get("preset_id"),
        "label": attempt.get("label"),
        "patches": attempt.get("patches") or [],
        "passed": attempt.get("passed"),
        "total": attempt.get("total"),
        "score": attempt.get("score"),
        "safety_violations": attempt.get("safety_violations"),
        "failure_clusters": failures,
    }


def _chat_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") if isinstance(data.get("choices"), list) else []
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
        content = msg.get("content")
        if isinstance(content, str):
            return content
    return ""


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        obj = json.loads(match.group(0)) if match else {}
    return obj if isinstance(obj, dict) else {}


async def _wait_for_run(run_id: uuid.UUID) -> dict[str, Any] | None:
    while True:
        row = benchmark_runs_store.get_run(run_id)
        if row and str(row.get("status") or "") in _FINAL_STATUSES:
            return row
        await asyncio.sleep(_POLL_SEC)


def _summarize_run(row: dict[str, Any]) -> dict[str, Any]:
    summary = row.get("summary_json") if isinstance(row.get("summary_json"), dict) else {}
    report = row.get("report_json") if isinstance(row.get("report_json"), dict) else {}
    results = report.get("results") if isinstance(report.get("results"), list) else []
    return {
        "run_id": str(row.get("id") or ""),
        "suite": row.get("suite"),
        "status": row.get("status"),
        "passed": int(summary.get("passed") or 0),
        "total": int(summary.get("total") or len(results) or 0),
        "skipped": int(summary.get("skipped") or 0),
        "failure_clusters": _failure_clusters(results),
        "avg_latency_ms": _avg_latency(results),
        "safety_violations": _safety_violations(results),
    }


from apps.backend.infrastructure.benchmarks.benchmark_tuning_scoring import (
    _promotion_decision,
    _score_attempt,
)
