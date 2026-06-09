"""Unit tests for layout-driven dashboard stat compute."""

from __future__ import annotations

import unittest

from apps.backend.dashboard.data_compute import (
    collect_compute_bindings,
    evaluate_compute,
    patches_touch_compute_sources,
    sync_computed_stats_in_data,
)


class TestDataCompute(unittest.TestCase):
    def test_count_and_count_where(self) -> None:
        data = {
            "events": [
                {"title": "A", "status": "open"},
                {"title": "B", "status": "done"},
                {"title": "C", "status": "open"},
            ]
        }
        self.assertEqual(evaluate_compute(data, {"op": "count", "from": "events"}), 3)
        self.assertEqual(
            evaluate_compute(
                data,
                {
                    "op": "count_where",
                    "from": "events",
                    "where": [{"field": "status", "eq": "open"}],
                },
            ),
            2,
        )

    def test_sync_from_layout_bindings(self) -> None:
        layout = {
            "version": 2,
            "blocks": [
                {
                    "id": "kpi-total",
                    "type": "stat",
                    "props": {
                        "dataPath": "stat_total",
                        "title": "Total",
                        "compute": {"op": "count", "from": "events"},
                    },
                },
                {
                    "id": "kpi-open",
                    "type": "stat",
                    "props": {
                        "dataPath": "stat_open",
                        "title": "Open",
                        "compute": {
                            "op": "count_where",
                            "from": "events",
                            "where": [{"field": "status", "neq": "done"}],
                        },
                    },
                },
            ],
        }
        data = {
            "events": [{"status": "open"}, {"status": "done"}],
            "stat_total": {"value": "0", "label": ""},
        }
        out = sync_computed_stats_in_data(data, layout)
        self.assertEqual(out["stat_total"]["value"], "2")
        self.assertEqual(out["stat_open"]["value"], "1")
        bindings = collect_compute_bindings(layout)
        self.assertEqual(len(bindings), 2)

    def test_patches_touch_compute_sources(self) -> None:
        layout = {
            "version": 2,
            "blocks": [
                {
                    "id": "kpi",
                    "type": "stat",
                    "props": {
                        "dataPath": "stat_x",
                        "compute": {"op": "count", "from": "events"},
                    },
                }
            ],
        }
        sources = {"events"}
        self.assertTrue(
            patches_touch_compute_sources([{"path": "events.0.title", "value": "x"}], sources)
        )
        self.assertFalse(
            patches_touch_compute_sources([{"path": "notes", "value": ""}], sources)
        )
        self.assertEqual(len(collect_compute_bindings({"version": 2, "blocks": []})), 0)


if __name__ == "__main__":
    unittest.main()
