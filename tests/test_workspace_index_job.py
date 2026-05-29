"""In-memory workspace index job helpers."""

from __future__ import annotations

import unittest

from apps.backend.infrastructure import workspace_retrieval as wr


class TestWorkspaceIndexJob(unittest.TestCase):
    def setUp(self) -> None:
        wr._index_job_clear("ws-test-1")

    def tearDown(self) -> None:
        wr._index_job_clear("ws-test-1")

    def test_job_snapshot_running(self) -> None:
        wr._index_job_set(
            "ws-test-1",
            status="running",
            phase="scan",
            files_done=10,
            files_total=100,
            started_at="2026-01-01T00:00:00+00:00",
        )
        snap = wr.index_job_for_status("ws-test-1")
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(snap["status"], "running")
        self.assertEqual(snap["phase"], "scan")
        self.assertEqual(snap["files_done"], 10)
        self.assertEqual(snap["files_total"], 100)

    def test_status_payload_includes_job(self) -> None:
        wr._index_job_set("ws-test-1", status="running", phase="qdrant", files_done=1, files_total=5)
        row = (
            "ws-test-1",
            "u",
            "proj",
            "/tmp/p",
            "manual",
            None,
            "main",
            "owner",
            None,
            None,
            None,
            False,
            None,
            True,
            True,
            None,
            None,
            None,
            True,
            None,
            None,
            None,
            None,
            True,
            None,
        )
        payload = wr.index_status_payload(row)
        self.assertTrue(payload.get("ok"))
        job = payload.get("index_job")
        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual(job["phase"], "qdrant")


if __name__ == "__main__":
    unittest.main()
