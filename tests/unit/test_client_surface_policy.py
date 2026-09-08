"""Client surface policy: WEB_ONLY / WEB_AND_TUI / TUI_ONLY and API-key workspace modes."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.backend.infrastructure.platform.client_surface_policy import (
    apply_surface_preset,
    is_browser_chat_path,
    mode_allowed_for_api_key,
    refuse_api_key_workspace_mode,
    reset_auth_material,
    set_auth_material,
    surface_preset,
)


class ClientSurfacePolicyTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_auth_material()

    def test_presets(self) -> None:
        with patch(
            "apps.backend.infrastructure.platform.client_surface_policy._read_row",
            return_value={
                "web_ui_enabled": True,
                "api_key_clients_enabled": False,
                "api_key_workspace_modes": "both",
            },
        ):
            self.assertEqual(surface_preset(), "WEB_ONLY")
            applied = apply_surface_preset("TUI_ONLY")
            self.assertFalse(applied["web_ui_enabled"])
            self.assertTrue(applied["api_key_clients_enabled"])

    def test_browser_chat_paths(self) -> None:
        self.assertTrue(is_browser_chat_path("/app/chat"))
        self.assertTrue(is_browser_chat_path("/app/dashboard/shared"))
        self.assertTrue(is_browser_chat_path("/app"))
        self.assertFalse(is_browser_chat_path("/app/login"))
        self.assertFalse(is_browser_chat_path("/app/admin"))
        self.assertFalse(is_browser_chat_path("/app/setup"))
        self.assertFalse(is_browser_chat_path("/app/admin/interfaces/platform"))

    def test_api_key_workspace_modes(self) -> None:
        with patch(
            "apps.backend.infrastructure.platform.client_surface_policy.api_key_workspace_modes",
            return_value="server",
        ):
            self.assertTrue(mode_allowed_for_api_key("server"))
            self.assertFalse(mode_allowed_for_api_key("client"))
            reset_auth_material()
            self.assertIsNone(refuse_api_key_workspace_mode("client"))
            set_auth_material("api_key")
            self.assertIsNotNone(refuse_api_key_workspace_mode("client"))
            self.assertIsNone(refuse_api_key_workspace_mode("server"))

        with patch(
            "apps.backend.infrastructure.platform.client_surface_policy.api_key_workspace_modes",
            return_value="client",
        ):
            set_auth_material("api_key")
            self.assertIsNone(refuse_api_key_workspace_mode("client"))
            self.assertIsNotNone(refuse_api_key_workspace_mode("server"))

        with patch(
            "apps.backend.infrastructure.platform.client_surface_policy.api_key_workspace_modes",
            return_value="both",
        ):
            set_auth_material("api_key")
            self.assertIsNone(refuse_api_key_workspace_mode("client"))
            self.assertIsNone(refuse_api_key_workspace_mode("server"))

    def test_server_workspaces_admin_only(self) -> None:
        from apps.backend.infrastructure.platform.client_surface_policy import (
            refuse_server_workspace_for_user,
        )

        class U:
            def __init__(self, role: str) -> None:
                self.role = role
                self.id = None

        with patch(
            "apps.backend.infrastructure.platform.client_surface_policy.server_workspaces_admin_only",
            return_value=True,
        ):
            self.assertIsNone(refuse_server_workspace_for_user(U("admin"), "server"))
            self.assertIsNotNone(refuse_server_workspace_for_user(U("user"), "server"))
            self.assertIsNone(refuse_server_workspace_for_user(U("user"), "client"))

        with patch(
            "apps.backend.infrastructure.platform.client_surface_policy.server_workspaces_admin_only",
            return_value=False,
        ):
            self.assertIsNone(refuse_server_workspace_for_user(U("user"), "server"))


if __name__ == "__main__":
    unittest.main()
