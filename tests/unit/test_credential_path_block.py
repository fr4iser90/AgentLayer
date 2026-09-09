"""Block agent writes to .env for API keys — use save_user_secret + env_bindings instead."""

from __future__ import annotations

import json
import unittest

from plugins.tools.workspace.lib.common import (
    is_blocked_credential_path,
    json_blocked_credential_path_error,
)


class TestCredentialPathBlock(unittest.TestCase):
    def test_blocks_env_and_docker_env(self) -> None:
        self.assertTrue(is_blocked_credential_path(".env"))
        self.assertTrue(is_blocked_credential_path("docker/.env"))
        self.assertTrue(is_blocked_credential_path(".env.local"))

    def test_allows_normal_paths(self) -> None:
        self.assertFalse(is_blocked_credential_path("src/main.py"))
        self.assertFalse(is_blocked_credential_path("docs/README.md"))

    def test_error_steers_to_secret_bridge(self) -> None:
        payload = json.loads(json_blocked_credential_path_error(".env"))
        self.assertFalse(payload["ok"])
        hint = payload["hint"]
        self.assertIn("save_user_secret", hint)
        self.assertIn("request_user_secret", hint)
        self.assertIn("env_bindings", hint)
        self.assertIn("bash", hint)
        self.assertIn("env_bindings", payload["for_assistant_must_say_en"])


if __name__ == "__main__":
    unittest.main()
