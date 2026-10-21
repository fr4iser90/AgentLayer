"""Unit tests for per-job schedule notification settings."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.backend.domain.scheduling.job_notify import (
    normalize_notify_channels,
    normalize_notify_on,
    require_notify_on,
    should_notify_for_outcome,
)
from apps.backend.infrastructure.notifications.notifications_delivery import should_deliver_external
from apps.backend.infrastructure.notifications.notifications_service import notify_scheduler_job_finished


class TestJobNotifyNormalize(unittest.TestCase):
    def test_notify_on_defaults(self) -> None:
        self.assertEqual(normalize_notify_on(None), "always")
        self.assertEqual(normalize_notify_on("FAILURE"), "failure")
        self.assertEqual(require_notify_on(None), None)
        with self.assertRaises(ValueError):
            require_notify_on("sometimes")

    def test_channels_dedupe_and_default(self) -> None:
        self.assertEqual(normalize_notify_channels(None), ["in_app"])
        self.assertEqual(
            normalize_notify_channels(["telegram", "telegram", "in_app", "x"]),
            ["telegram", "in_app"],
        )

    def test_outcome_gate(self) -> None:
        self.assertFalse(should_notify_for_outcome(notify_on="never", success=True))
        self.assertFalse(should_notify_for_outcome(notify_on="failure", success=True))
        self.assertTrue(should_notify_for_outcome(notify_on="failure", success=False))
        self.assertTrue(should_notify_for_outcome(notify_on="always", success=True))


class TestJobChannelOverride(unittest.TestCase):
    def test_override_skips_schedules_pref(self) -> None:
        prefs = {
            "telegram_enabled": True,
            "discord_enabled": False,
            "telegram_schedules": False,
            "telegram_dashboard": False,
            "discord_schedules": False,
            "discord_dashboard": False,
            "external_failures_only": True,
        }
        n = {"kind": "scheduler_job_done", "severity": "info"}
        self.assertFalse(
            should_deliver_external(prefs=prefs, channel="telegram", notification=n)
        )
        self.assertTrue(
            should_deliver_external(
                prefs=prefs,
                channel="telegram",
                notification=n,
                job_channel_override=True,
            )
        )


class TestNotifySchedulerJobFinished(unittest.TestCase):
    def test_never_skips_emit(self) -> None:
        with patch(
            "apps.backend.infrastructure.notifications.notifications_service.emit_notification"
        ) as emit:
            notify_scheduler_job_finished(
                tenant_id=1,
                user_id=__import__("uuid").uuid4(),
                row={
                    "id": "j1",
                    "title": "t",
                    "notify_on": "never",
                    "notify_channels": ["in_app", "telegram"],
                },
                success=True,
            )
            emit.assert_not_called()

    def test_failure_only_skips_success(self) -> None:
        with patch(
            "apps.backend.infrastructure.notifications.notifications_service.emit_notification"
        ) as emit:
            notify_scheduler_job_finished(
                tenant_id=1,
                user_id=__import__("uuid").uuid4(),
                row={
                    "id": "j1",
                    "title": "t",
                    "notify_on": "failure",
                    "notify_channels": ["in_app"],
                },
                success=True,
            )
            emit.assert_not_called()

    def test_always_emits_with_external_channels(self) -> None:
        with patch(
            "apps.backend.infrastructure.notifications.notifications_service.emit_notification"
        ) as emit:
            uid = __import__("uuid").uuid4()
            notify_scheduler_job_finished(
                tenant_id=1,
                user_id=uid,
                row={
                    "id": "j1",
                    "title": "LOGA3",
                    "notify_on": "always",
                    "notify_channels": ["telegram"],
                    "notify_include_output": True,
                },
                success=True,
                output_excerpt="fetched pdf ok",
            )
            emit.assert_called_once()
            kwargs = emit.call_args.kwargs
            self.assertTrue(kwargs["skip_in_app"])
            self.assertEqual(kwargs["external_channels"], frozenset({"telegram"}))
            self.assertIn("fetched pdf ok", kwargs["body"])


if __name__ == "__main__":
    unittest.main()
