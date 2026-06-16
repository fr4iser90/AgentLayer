"""Apply agent-config patches with validation and changelog."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from apps.backend.domain.agent_config_registry import all_knobs, knob_by_id
from apps.backend.infrastructure import agent_config_effective, agent_config_fingerprint, agent_config_store
from apps.backend.infrastructure.operator_settings import OperatorSettingsPatch, apply_operator_settings_patch

ActorType = Literal["user", "operator_agent", "reviewer_job"]


def _validate_value(knob: dict[str, Any], value: Any) -> str | None:
    ktype = str(knob.get("type") or "")
    if ktype == "integer":
        try:
            n = int(value)
        except (TypeError, ValueError):
            return "expected integer"
        if n < 1:
            return "integer must be >= 1"
        return None
    if ktype == "boolean":
        if not isinstance(value, bool):
            return "expected boolean"
        return None
    if ktype == "string_list":
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            return "expected list of strings"
        return None
    if ktype == "string":
        if not isinstance(value, str):
            return "expected string"
        return None
    if ktype in ("json", "array"):
        if value is None:
            return "expected json value"
        return None
    return None


def validate_patches(patches: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    for p in patches:
        kid = str(p.get("knob_id") or "").strip()
        if not kid:
            errors.append({"knob_id": "", "error": "knob_id required"})
            continue
        knob = knob_by_id(kid)
        if not knob:
            errors.append({"knob_id": kid, "error": "unknown knob"})
            continue
        if not knob.get("writable"):
            errors.append({"knob_id": kid, "error": "not_writable"})
            continue
        layer = str(knob.get("layer") or "")
        if layer in ("bench", "code", "rubric"):
            errors.append({"knob_id": kid, "error": "not_harness_knob"})
            continue
        if "value" not in p:
            errors.append({"knob_id": kid, "error": "value required"})
            continue
        err = _validate_value(knob, p.get("value"))
        if err:
            errors.append({"knob_id": kid, "error": err})
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def _apply_operator_knob(knob: dict[str, Any], value: Any) -> None:
    key = str(knob.get("operator_settings_key") or "").strip()
    if not key:
        raise ValueError(f"operator knob missing operator_settings_key: {knob.get('id')}")
    if key not in OperatorSettingsPatch.model_fields:
        raise ValueError(f"operator_settings field not supported yet: {key}")
    patch = OperatorSettingsPatch.model_validate({key: value})
    apply_operator_settings_patch(patch)


def apply_patches(
    *,
    tenant_id: int,
    patches: list[dict[str, Any]],
    actor_type: ActorType,
    actor_user_id: uuid.UUID | None,
    actor_agent_id: str | None = None,
    session_id: uuid.UUID | None = None,
    experiment_id: uuid.UUID | None = None,
    hypothesis: str | None = None,
) -> dict[str, Any]:
    validation = validate_patches(patches)
    if not validation["valid"]:
        return {"ok": False, "validation": validation}

    fp_before = agent_config_fingerprint.compute_fingerprint(tenant_id=tenant_id)
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for p in patches:
        kid = str(p.get("knob_id") or "").strip()
        knob = knob_by_id(kid) or {}
        layer = str(knob.get("layer") or "")
        new_val = p.get("value")
        old_val, _src = agent_config_effective.effective_value(kid, tenant_id=tenant_id)

        if layer == "operator":
            try:
                _apply_operator_knob(knob, new_val)
            except ValueError as exc:
                skipped.append({"knob_id": kid, "reason": str(exc)})
                continue
        elif layer in ("runtime_config", "agent_yaml", "router_yaml"):
            agent_config_store.set_override(tenant_id, kid, new_val, user_id=actor_user_id)
        else:
            skipped.append({"knob_id": kid, "reason": "not_writable"})
            continue

        applied.append({"knob_id": kid, "old": old_val, "new": new_val})

    agent_config_effective.invalidate_agent_config_cache(tenant_id)

    from apps.backend.infrastructure.agent_config_router_overlay import (
        apply_router_overlay_to_registry,
        invalidate_router_overlay_cache,
    )

    invalidate_router_overlay_cache(tenant_id)
    if any(str((knob_by_id(str(p.get("knob_id") or "")) or {}).get("layer") or "") == "router_yaml" for p in patches):
        apply_router_overlay_to_registry(tenant_id=tenant_id)

    fp_after = agent_config_fingerprint.compute_fingerprint(tenant_id=tenant_id)
    event_id = agent_config_store.append_changelog(
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        actor_agent_id=actor_agent_id,
        session_id=session_id,
        experiment_id=experiment_id,
        hypothesis=hypothesis,
        patches=applied,
        fingerprint_before=fp_before,
        fingerprint_after=fp_after,
    )

    return {
        "ok": True,
        "applied": applied,
        "skipped": skipped,
        "fingerprint": fp_after,
        "fingerprint_before": fp_before,
        "changelog_event_id": str(event_id),
    }


def draft_patches(*, tenant_id: int, patches: list[dict[str, Any]], hypothesis: str | None = None) -> dict[str, Any]:
    validation = validate_patches(patches)
    fp = agent_config_fingerprint.compute_fingerprint(tenant_id=tenant_id)
    return {
        "ok": validation["valid"],
        "draft_id": str(uuid.uuid4()),
        "validation": {**validation, "fingerprint_preview": fp},
        "hypothesis": hypothesis,
    }


def initialize_defaults_to_db(
    *,
    tenant_id: int,
    actor_user_id: uuid.UUID | None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Persist registry/file/operator defaults into DB so WebUI owns all writable knobs."""
    existing = agent_config_store.list_overrides(tenant_id)
    patches: list[dict[str, Any]] = []
    for knob in all_knobs():
        if not knob.get("writable"):
            continue
        layer = str(knob.get("layer") or "")
        if layer in ("bench", "code", "rubric"):
            continue
        kid = str(knob.get("id") or "")
        if not kid:
            continue
        if not overwrite and kid in existing:
            continue
        val, _src = agent_config_effective.default_value(kid)
        if val is None and layer != "operator":
            continue
        patches.append({"knob_id": kid, "value": val})

    if not patches:
        return {"ok": True, "applied": [], "skipped": [], "message": "nothing_to_initialize"}

    return apply_patches(
        tenant_id=tenant_id,
        patches=patches,
        actor_type="user",
        actor_user_id=actor_user_id,
        hypothesis="initialize defaults to DB (WebUI-owned config)",
    )
