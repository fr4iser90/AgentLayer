from apps.backend.infrastructure.benchmarks.benchmark_autotuner import (
    _patch_signature,
    _promotion_decision,
    _reviewer_mode,
    _score_attempt,
    plan_for_mode,
)


def test_plan_for_mode_progressive_suites() -> None:
    assert plan_for_mode("fast")["suites"] == ["smoke"]
    assert plan_for_mode("standard")["suites"] == ["smoke", "prompt_security"]
    assert plan_for_mode("deep")["suites"] == ["smoke", "prompt_security", "coding"]


def test_score_attempt_penalizes_safety_failures() -> None:
    good = _score_attempt(
        preset_id="good",
        label="Good",
        patches=[],
        runs=[
            {
                "run_id": "r1",
                "status": "completed",
                "passed": 2,
                "total": 2,
                "failure_clusters": {},
                "safety_violations": 0,
            }
        ],
    )
    unsafe = _score_attempt(
        preset_id="unsafe",
        label="Unsafe",
        patches=[],
        runs=[
            {
                "run_id": "r2",
                "status": "completed",
                "passed": 1,
                "total": 2,
                "failure_clusters": {"safety": 1},
                "safety_violations": 1,
            }
        ],
    )

    assert good["score"] > unsafe["score"]
    assert good["best_run_id"] == "r1"


def test_promotion_decision_requires_improvement_over_baseline() -> None:
    baseline = {"preset_id": "baseline", "score": 30.0, "patches": [], "total": 3}
    same = {
        "preset_id": "small_strict",
        "score": 30.0,
        "patches": [{"knob_id": "agent.max_tool_rounds", "value": 10}],
        "total": 3,
        "safety_violations": 0,
    }
    better = {**same, "score": 42.0}

    assert _promotion_decision([baseline, same], same)["promote"] is False
    assert _promotion_decision([baseline, better], better)["promote"] is True


def test_reviewer_mode_normalizes_patch_and_test() -> None:
    assert _reviewer_mode("guided") == "patch_and_test"
    assert _reviewer_mode("patch") == "patch_and_test"
    assert _reviewer_mode("review") == "review_only"
    assert _reviewer_mode("") == "off"


def test_patch_signature_is_order_stable() -> None:
    a = [
        {"knob_id": "agent.max_tool_rounds", "value": 10},
        {"knob_id": "tool_forward.full_schema", "value": False},
    ]
    b = list(reversed(a))
    assert _patch_signature(a) == _patch_signature(b)
