"""Benchmark runs must not emit user notifications."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from apps.backend.infrastructure.notifications.notifications_service import emit_notification


def test_emit_notification_skipped_during_benchmark() -> None:
    uid = uuid.uuid4()
    with patch(
        "apps.backend.domain.shared.identity.get_benchmark_run_id",
        return_value=uuid.uuid4(),
    ):
        with patch(
            "apps.backend.infrastructure.notifications.notifications_store.insert_notification",
        ) as ins:
            emit_notification(
                tenant_id=1,
                user_id=uid,
                kind="dashboard_agent_update",
                title="Dashboard updated: bench-test",
            )
            ins.assert_not_called()
