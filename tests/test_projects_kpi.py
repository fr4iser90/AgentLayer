"""Unit tests for projects KPI auto-sync."""

from __future__ import annotations

import unittest

from apps.backend.dashboard.projects_kpi import (
    compute_projects_kpis,
    patches_touch_projects_list,
    sync_projects_kpis_in_data,
)


class TestProjectsKpi(unittest.TestCase):
    def test_compute_counts(self) -> None:
        projects = [
            {"workspace_id": "ws1", "status": "active"},
            {"workspace_id": "", "status": "archived"},
            {"workspace_id": "", "status": ""},
        ]
        self.assertEqual(compute_projects_kpis(projects), (3, 1, 2))

    def test_sync_updates_stat_blocks(self) -> None:
        data = {
            "projects": [{"title": "a"}, {"title": "b", "workspace_id": "x"}],
            "stat_projects": {"value": "0", "label": "Total repos", "suffix": "", "trend": ""},
        }
        out = sync_projects_kpis_in_data(data)
        self.assertEqual(out["stat_projects"]["value"], "2")
        self.assertEqual(out["stat_linked"]["value"], "1")
        self.assertEqual(out["stat_active"]["value"], "2")
        self.assertEqual(out["stat_projects"]["label"], "Total repos")

    def test_patches_touch_projects(self) -> None:
        self.assertTrue(
            patches_touch_projects_list([{"path": "projects", "value": []}], "projects")
        )
        self.assertTrue(
            patches_touch_projects_list([{"path": "projects.0.title", "value": "x"}], "projects")
        )
        self.assertFalse(
            patches_touch_projects_list([{"path": "notes", "value": ""}], "projects")
        )


if __name__ == "__main__":
    unittest.main()
