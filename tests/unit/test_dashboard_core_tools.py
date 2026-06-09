"""Generic dashboard agent tools (data paths + layout ops)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from apps.backend.dashboard.data_paths import apply_data_patches, get_path, set_path
import plugins.tools.personal.dashboard.dashboard as mod


def test_set_path_nested() -> None:
    obj: dict = {"albums": [{"photos": []}]}
    out = set_path(obj, "albums.0.photos", [{"url": "x"}])
    assert get_path(out, "albums.0.photos") == [{"url": "x"}]


def test_apply_data_patches_reserved() -> None:
    data = {"notes": "a"}
    _, err = apply_data_patches(data, [{"path": "_secret", "value": 1}])
    assert err and "reserved" in err


def test_apply_layout_add_block() -> None:
    ul = {"version": 1, "blocks": []}
    data: dict = {}
    new_ul, new_data, err = mod._apply_layout_ops(
        ul, data, [{"op": "add_block", "type": "markdown"}], allowed_block_ids=None
    )
    assert err is None
    assert len(new_ul["blocks"]) == 1
    b = new_ul["blocks"][0]
    assert b["type"] == "markdown"
    dp = b["props"]["dataPath"]
    assert dp in new_data
    assert new_data[dp] == ""


def test_dashboard_list_no_identity() -> None:
    with patch.object(mod, "_identity", return_value=None):
        out = json.loads(mod.list({}))
    assert out["ok"] is False


def test_dashboard_read_and_patch_data() -> None:
    wid = uuid.uuid4()
    uid = uuid.uuid4()
    tid = 1
    ws = {
        "id": str(wid),
        "kind": "custom",
        "title": "Test",
        "ui_layout": {"version": 1, "blocks": []},
        "data": {"notes": "hello"},
        "data_source": "domain",
        "access_role": "owner",
        "access_scope": "full",
        "owner_user_id": str(uid),
        "tenant_id": tid,
        "view_bindings": {},
    }

    with (
        patch.object(mod, "_identity", return_value=(tid, uid)),
        patch(
            "plugins.tools.personal.dashboard.dashboard.resolve_dashboard_id",
            return_value=(wid, None),
        ),
        patch(
            "plugins.tools.personal.dashboard.dashboard.dashboard_db.dashboard_get",
            return_value=ws,
        ),
        patch(
            "apps.backend.domain.collections.service.patch_fields",
            return_value={"ok": True, "source": "domain", "applied": [{"path": "notes"}]},
        ) as mock_up,
    ):
        read_out = json.loads(mod.read({"dashboard_id": str(wid)}))
        assert read_out["ok"] is True
        assert read_out["data"]["notes"] == "hello"

        patch_out = json.loads(
            mod.patch_data(
                {
                    "dashboard_id": str(wid),
                    "patches": [{"path": "notes", "value": "updated"}],
                }
            )
        )
    assert patch_out["ok"] is True
    mock_up.assert_called_once()
    kw = mock_up.call_args.kwargs
    assert kw.get("patches") == [{"path": "notes", "value": "updated"}]


def test_dashboard_patch_layout_viewer() -> None:
    wid = uuid.uuid4()
    uid = uuid.uuid4()
    ws = {
        "kind": "custom",
        "title": "T",
        "ui_layout": {"version": 1, "blocks": []},
        "data": {},
        "access_role": "viewer",
    }
    with (
        patch.object(mod, "_identity", return_value=(1, uid)),
        patch(
            "plugins.tools.personal.dashboard.dashboard.resolve_dashboard_id",
            return_value=(wid, None),
        ),
        patch(
            "plugins.tools.personal.dashboard.dashboard.dashboard_db.dashboard_get",
            return_value=ws,
        ),
    ):
        out = json.loads(
            mod.patch_layout({"dashboard_id": str(wid), "ops": [{"op": "add_block", "type": "table"}]})
        )
    assert out["ok"] is False
    assert "read-only" in out["error"]
