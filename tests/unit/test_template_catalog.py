"""Tests for template_id gallery catalog (Phase C)."""

from __future__ import annotations

import unittest

from apps.backend.infrastructure.dashboards.dashboard_bundle import (
    bundles_by_template_id,
    template_catalog,
    template_path_for_template_id,
)
from apps.backend.infrastructure.dashboards.dashboard_create_helpers import (
    resolve_create_target,
    validate_template_id,
)


class TestTemplateCatalog(unittest.TestCase):
    def test_every_bundle_has_template_id(self) -> None:
        by_tid = bundles_by_template_id()
        self.assertGreater(len(by_tid), 0)
        for tid, bundle in by_tid.items():
            self.assertTrue(tid.endswith("-v1") or tid == "custom")
            self.assertEqual(bundle.template_id, tid)

    def test_projects_template_resolves(self) -> None:
        path = template_path_for_template_id("projects-v1")
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())  # type: ignore[union-attr]

    def test_validate_template_id(self) -> None:
        self.assertIsNone(validate_template_id("projects-v1"))
        self.assertIsNone(validate_template_id("custom"))
        self.assertIsNotNone(validate_template_id("nope-v9"))

    def test_resolve_create_target_prefers_template_id(self) -> None:
        kind, tid, err = resolve_create_target(template_id="projects-v1", kind="pets")
        self.assertIsNone(err)
        self.assertEqual(tid, "projects-v1")
        self.assertEqual(kind, "projects")

    def test_media_station_template_resolves(self) -> None:
        path = template_path_for_template_id("media_station-v1")
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())  # type: ignore[union-attr]
        kind, tid, err = resolve_create_target(template_id="media_station-v1", kind="custom")
        self.assertIsNone(err)
        self.assertEqual(tid, "media_station-v1")
        self.assertEqual(kind, "media_station")

        rows = template_catalog()
        projects = next((r for r in rows if r.get("template_id") == "projects-v1"), None)
        self.assertIsNotNone(projects)
        assert projects is not None
        self.assertEqual(projects.get("kind"), "projects")
        self.assertTrue(projects.get("has_template"))


if __name__ == "__main__":
    unittest.main()
