"""Layout helpers used by projects import (generic list path resolution)."""

from __future__ import annotations

import unittest

from apps.backend.dashboard.layout_tree import primary_list_data_path


class TestPrimaryListDataPath(unittest.TestCase):
    def test_from_nested_card_grid(self) -> None:
        layout = {
            "version": 2,
            "blocks": [
                {
                    "id": "sec",
                    "type": "section",
                    "props": {
                        "nested": {
                            "version": 2,
                            "blocks": [
                                {
                                    "id": "cards",
                                    "type": "card_grid",
                                    "props": {"dataPath": "veranstaltungen"},
                                }
                            ],
                        }
                    },
                }
            ],
        }
        self.assertEqual(primary_list_data_path(layout), "veranstaltungen")

    def test_fallback_when_no_list_block(self) -> None:
        self.assertEqual(primary_list_data_path({"version": 2, "blocks": []}), "items")
        self.assertEqual(
            primary_list_data_path({"version": 2, "blocks": []}, fallback="projects"),
            "projects",
        )


if __name__ == "__main__":
    unittest.main()
