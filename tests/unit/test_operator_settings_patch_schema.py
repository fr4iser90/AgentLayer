"""Operator settings_patch schema and minimal errors (no planner hints)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from apps.backend.infrastructure.operator_settings import (
    operator_settings_patch_field_names,
    operator_settings_patch_tool_parameters,
)


def test_patch_field_names_from_pydantic_model() -> None:
    names = operator_settings_patch_field_names()
    assert "rag_enabled" in names
    assert len(names) > 10


def test_patch_tool_parameters_from_pydantic() -> None:
    params = operator_settings_patch_tool_parameters()
    assert params["type"] == "object"
    assert params.get("minProperties") == 1
    props = params.get("properties") or {}
    assert isinstance(props, dict)
    assert "rag_enabled" in props
    assert params.get("additionalProperties") is False
    assert "description" not in params


def test_settings_patch_empty_minimal_error() -> None:
    from plugins.tools.platform.operator import admin as oa

    uid = uuid.uuid4()
    with patch.object(oa, "get_identity", return_value=(1, uid)):
        with patch.object(oa.db, "user_role", return_value="admin"):
            out = json.loads(oa.settings_patch({}))
    assert out == {
        "ok": False,
        "error": "missing arguments: at least one OperatorSettingsPatch field as top-level JSON property",
        "reason": "empty_arguments",
    }


def test_settings_get_no_hint_fields() -> None:
    from plugins.tools.platform.operator import admin as oa

    uid = uuid.uuid4()
    with patch.object(oa, "get_identity", return_value=(1, uid)):
        with patch.object(oa.db, "user_role", return_value="admin"):
            with patch.object(oa, "operator_settings_public_dict", return_value={"rag_enabled": True}):
                with patch.object(oa, "interface_hints_public", return_value={}):
                    out = json.loads(oa.settings_get({}))
    assert out["ok"] is True
    assert "settings" in out
    assert "hint" not in out
    assert "patch_tool" not in out


def test_planner_skips_extra_hints_for_settings_patch() -> None:
    from apps.backend.domain.agent_tools import (
        PLANNER_NO_EXTRA_HINTS_AFTER_TOOL,
        _tool_parameter_recovery_hint,
        _tool_result_followup_hint,
    )

    assert "settings_patch" in PLANNER_NO_EXTRA_HINTS_AFTER_TOOL
    err = json.dumps({"ok": False, "error": "missing arguments", "reason": "empty_arguments"})
    assert _tool_parameter_recovery_hint("settings_patch", err) is None
    assert _tool_result_followup_hint("settings_patch", err) is not None
