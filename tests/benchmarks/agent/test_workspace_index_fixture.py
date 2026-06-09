"""workspace_indexed fixture runs when selected (no AGENT_BENCH_RUN_INDEX gate)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.benchmarks.agent.fixtures import FixtureContext, _setup_workspace_indexed


def test_workspace_indexed_runs_without_env_when_workspace_ready() -> None:
    client = MagicMock()
    client.patch_json.return_value = {}
    client.post_json.return_value = {"ok": True}
    ctx = FixtureContext(run_id="r", prefix="p-")
    ctx.workspace_id = "ws-1"

    with patch("tests.benchmarks.agent.fixtures.wait_index_idle") as wait:
        _setup_workspace_indexed(client, ctx)

    wait.assert_called_once()
    assert ctx.indexed is True
    assert "workspace_indexed" not in ctx.skipped
