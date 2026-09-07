"""Tests for persisting dashboard ``data`` payloads into domain collections."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

from apps.backend.infrastructure.dashboards.dashboard_data_write import (
    split_reserved_data,
    write_dashboard_data,
)

_LAYOUT = {
    "version": 2,
    "blocks": [
        {
            "id": "tbl",
            "type": "table",
            "grid": {"x": 0, "y": 0, "w": 12, "h": 7},
            "props": {"dataPath": "items", "columns": []},
        },
        {
            "id": "md",
            "type": "markdown",
            "grid": {"x": 0, "y": 7, "w": 12, "h": 5},
            "props": {"dataPath": "notes"},
        },
        {
            "id": "gal",
            "type": "gallery",
            "grid": {"x": 0, "y": 12, "w": 12, "h": 8},
            "props": {"dataPath": "photos"},
        },
    ],
}

_BINDINGS = {"items": "c-items", "notes": "c-notes", "photos": "c-photos"}


def _write(data: dict, **kwargs):
    return write_dashboard_data(
        dashboard_id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        tenant_id=1,
        ui_layout=_LAYOUT,
        view_bindings={},
        template_id=None,
        data=data,
        **kwargs,
    )


def _patched_paths(mock_patch_fields) -> dict:
    kwargs = mock_patch_fields.call_args.kwargs
    return {p["path"]: p["value"] for p in kwargs["patches"]}


class TestSplitReservedData(unittest.TestCase):
    def test_splits_agentlayer_config_from_board_content(self) -> None:
        content, reserved = split_reserved_data(
            {"items": [{"id": "r1"}], "_agentlayer": {"system_prompt_extra": "hi"}}
        )
        self.assertEqual(content, {"items": [{"id": "r1"}]})
        self.assertEqual(reserved, {"_agentlayer": {"system_prompt_extra": "hi"}})

    def test_handles_missing_payload(self) -> None:
        self.assertEqual(split_reserved_data(None), ({}, {}))


class TestWriteDashboardData(unittest.TestCase):
    @patch("apps.backend.infrastructure.dashboards.dashboard_data_write.domain_svc.patch_fields")
    @patch(
        "apps.backend.infrastructure.dashboards.dashboard_data_write.domain_svc.resolve_bindings_for_dashboard"
    )
    def test_writes_every_bound_path_present_in_payload(self, mock_bindings, mock_patch) -> None:
        mock_bindings.return_value = dict(_BINDINGS)
        mock_patch.return_value = {"ok": True, "applied": [], "errors": []}

        rows = [{"id": "r1", "name": "Alpha"}]
        _write({"items": rows, "notes": "# Hi", "photos": []})

        self.assertEqual(
            _patched_paths(mock_patch),
            {"items": rows, "notes": "# Hi", "photos": []},
        )

    @patch("apps.backend.infrastructure.dashboards.dashboard_data_write.domain_svc.patch_fields")
    @patch(
        "apps.backend.infrastructure.dashboards.dashboard_data_write.domain_svc.resolve_bindings_for_dashboard"
    )
    def test_partial_payload_leaves_untouched_paths_alone(self, mock_bindings, mock_patch) -> None:
        mock_bindings.return_value = dict(_BINDINGS)
        mock_patch.return_value = {"ok": True, "applied": [], "errors": []}

        _write({"notes": "only notes"})

        self.assertEqual(_patched_paths(mock_patch), {"notes": "only notes"})

    @patch("apps.backend.infrastructure.dashboards.dashboard_data_write.domain_svc.patch_fields")
    @patch(
        "apps.backend.infrastructure.dashboards.dashboard_data_write.domain_svc.resolve_bindings_for_dashboard"
    )
    def test_granular_scope_drops_paths_outside_shared_blocks(self, mock_bindings, mock_patch) -> None:
        mock_bindings.return_value = dict(_BINDINGS)
        mock_patch.return_value = {"ok": True, "applied": [], "errors": []}

        _write(
            {"items": [{"id": "r1"}], "notes": "nope"},
            allowed_top_keys={"items"},
        )

        self.assertEqual(_patched_paths(mock_patch), {"items": [{"id": "r1"}]})

    @patch("apps.backend.infrastructure.dashboards.dashboard_data_write.domain_svc.patch_fields")
    @patch(
        "apps.backend.infrastructure.dashboards.dashboard_data_write.domain_svc.resolve_bindings_for_dashboard"
    )
    def test_payload_without_bound_paths_skips_collection_write(self, mock_bindings, mock_patch) -> None:
        mock_bindings.return_value = dict(_BINDINGS)

        result = _write({"unbound": "value"})

        self.assertTrue(result.get("ok"))
        mock_patch.assert_not_called()

    @patch("apps.backend.infrastructure.dashboards.dashboard_data_write.domain_svc.patch_fields")
    @patch(
        "apps.backend.infrastructure.dashboards.dashboard_data_write.domain_svc.resolve_bindings_for_dashboard"
    )
    def test_empty_payload_is_a_noop(self, mock_bindings, mock_patch) -> None:
        result = _write({})

        self.assertTrue(result.get("ok"))
        mock_bindings.assert_not_called()
        mock_patch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
