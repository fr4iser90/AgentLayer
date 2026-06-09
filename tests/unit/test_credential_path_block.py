"""Block agent writes to .env for API keys — use save_user_secret instead."""

from __future__ import annotations

import unittest

from apps.backend.domain.coding.common import is_blocked_credential_path


class TestCredentialPathBlock(unittest.TestCase):
    def test_blocks_env_and_docker_env(self) -> None:
        self.assertTrue(is_blocked_credential_path(".env"))
        self.assertTrue(is_blocked_credential_path("docker/.env"))
        self.assertTrue(is_blocked_credential_path(".env.local"))

    def test_allows_normal_paths(self) -> None:
        self.assertFalse(is_blocked_credential_path("src/main.py"))
        self.assertFalse(is_blocked_credential_path("docs/README.md"))


if __name__ == "__main__":
    unittest.main()
