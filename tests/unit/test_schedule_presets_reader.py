"""The two preset readers answer with the same rows, because they are one read.

The template picker behind the user endpoint and the operator's
``scheduler_presets_list`` each walked ``plugins/schedules/presets`` with their own
loop, so a template one offered could be absent from the other. Both now call
:func:`read_schedule_presets`, which is why one patched
``schedule_presets.schedule_presets_dir`` drives all three assertions below: if a
reader grew its own directory walk again, its rows would stop matching.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

import plugins.tools.platform.operator.admin as operator_admin
from apps.backend.api.scheduling.controllers import scheduler_job_presets_user_api as presets_api
from apps.backend.application.scheduling.use_cases import schedule_presets


class _Actor:
    id = uuid.uuid4()
    role = "admin"


async def _current_user(_request: Any) -> _Actor:
    return _Actor()


def _write(root: Path, name: str, payload: Any) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (root / name).write_text(text, encoding="utf-8")


@pytest.fixture
def preset_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "presets"
    root.mkdir()
    _write(root, "01_first.json", {"id": "first", "label": "First"})
    _write(root, "02_nightly.json", {"id": "nightly", "label": " Nightly ", "description": "  every night  ", "job": {"agent_id": "operator"}})
    _write(root, "03_no_label.json", {"id": "no-label"})
    _write(root, "04_no_id.json", {"label": "No id"})
    _write(root, "05_blank_id.json", {"id": "   ", "label": "Blank id"})
    _write(root, "06_not_an_object.json", [{"id": "list", "label": "List"}])
    _write(root, "07_broken.json", "{ not json")
    _write(root, "08_job_not_object.json", {"id": "badjob", "label": "Bad job", "job": "operator"})
    _write(root, "09_notes.md", "not a preset at all")
    monkeypatch.setattr(schedule_presets, "schedule_presets_dir", lambda: root)
    return root


def test_reader_keeps_usable_templates_in_file_order(preset_dir: Path) -> None:
    rows = schedule_presets.read_schedule_presets()

    assert [row["id"] for row in rows] == ["first", "nightly", "badjob"]
    assert rows[0]["description"] == ""
    assert rows[1]["label"] == "Nightly"
    assert rows[1]["description"] == "every night"
    assert rows[1]["job"] == {"agent_id": "operator"}
    assert rows[2]["job"] == {}


def test_missing_directory_answers_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_presets, "schedule_presets_dir", lambda: tmp_path / "absent")

    assert schedule_presets.read_schedule_presets() == []


def test_endpoint_offers_exactly_what_the_reader_found(
    preset_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(presets_api, "get_current_user", _current_user)
    monkeypatch.setattr(presets_api, "schedule_feature_permission_error", lambda **_kw: None)

    result = asyncio.run(presets_api.list_scheduler_job_presets(object()))

    assert result == {"ok": True, "presets": schedule_presets.read_schedule_presets()}


def test_endpoint_still_refuses_without_the_schedule_feature(
    preset_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(presets_api, "get_current_user", _current_user)
    monkeypatch.setattr(
        presets_api, "schedule_feature_permission_error", lambda **_kw: "schedules are not enabled"
    )

    with pytest.raises(HTTPException) as raised:
        asyncio.run(presets_api.list_scheduler_job_presets(object()))

    assert raised.value.status_code == 403


def test_operator_tool_offers_exactly_what_the_reader_found(
    preset_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(operator_admin, "_require_admin", lambda: (1, uuid.uuid4()))

    payload = json.loads(operator_admin.scheduler_presets_list({}))

    assert payload["ok"] is True
    assert payload["presets"] == schedule_presets.read_schedule_presets()


def test_operator_tool_still_refuses_without_an_admin(
    preset_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(operator_admin, "_require_admin", lambda: operator_admin._err("admin role required"))

    payload = json.loads(operator_admin.scheduler_presets_list({}))

    assert payload["ok"] is False
    assert "presets" not in payload