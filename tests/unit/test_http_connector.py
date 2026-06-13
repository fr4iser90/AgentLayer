"""Tests for generic HTTP connector (SSRF, extract, tools)."""

from __future__ import annotations

import json
import unittest
import uuid
from unittest import mock

from plugins.tools.integrations.http.lib.extract import apply_template, extract_path
from plugins.tools.integrations.http.lib.ssrf import validate_outbound_url


class TestSsrfGuards(unittest.TestCase):
    def test_allows_public_https(self) -> None:
        ok, why = validate_outbound_url("https://api.example.com/v1/items")
        self.assertTrue(ok, why)

    def test_blocks_localhost(self) -> None:
        ok, why = validate_outbound_url("http://127.0.0.1:8080/admin")
        self.assertFalse(ok)
        self.assertEqual(why, "blocked_ssrf")

    def test_blocks_private_ip_literal(self) -> None:
        ok, _ = validate_outbound_url("http://192.168.1.1/")
        self.assertFalse(ok)

    def test_blocks_metadata_host(self) -> None:
        ok, _ = validate_outbound_url("http://metadata.google.internal/")
        self.assertFalse(ok)

    def test_blocks_credentials_in_url(self) -> None:
        ok, why = validate_outbound_url("https://user:pass@api.example.com/")
        self.assertFalse(ok)
        self.assertEqual(why, "blocked_credentials_in_url")


class TestExtract(unittest.TestCase):
    def test_dot_path(self) -> None:
        data = {"data": {"items": [{"id": 1}, {"id": 2}]}}
        self.assertEqual(extract_path(data, "data.items.0.id"), 1)

    def test_template(self) -> None:
        body = apply_template(
            {"title": "{{name}}", "nested": {"x": "{{n}}"}},
            {"name": "Kira", "n": "7"},
        )
        self.assertEqual(body["title"], "Kira")
        self.assertEqual(body["nested"]["x"], "7")


class TestHttpCallTool(unittest.TestCase):
    @mock.patch("plugins.tools.integrations.http.http.execute_http")
    @mock.patch("plugins.tools.integrations.http.http.get_identity")
    def test_call_success(self, mock_ident: mock.MagicMock, mock_exec: mock.MagicMock) -> None:
        from plugins.tools.integrations.http.http import call

        mock_ident.return_value = (1, uuid.uuid4())
        mock_exec.return_value = {"ok": True, "status": 200, "response": {"hello": "world"}}

        out = json.loads(
            call(
                {
                    "method": "GET",
                    "url": "https://api.example.com/ping",
                    "auth": {"type": "bearer", "secret_key": "example_api"},
                }
            )
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["response"]["hello"], "world")


class TestConnectorRunTool(unittest.TestCase):
    @mock.patch("plugins.tools.integrations.connector.connector.execute_http")
    @mock.patch("plugins.tools.integrations.connector.connector.connector_profile_get")
    @mock.patch("plugins.tools.integrations.connector.connector.get_identity")
    def test_run_endpoint(
        self,
        mock_ident: mock.MagicMock,
        mock_get: mock.MagicMock,
        mock_exec: mock.MagicMock,
    ) -> None:
        from plugins.tools.integrations.connector.connector import run

        uid = uuid.uuid4()
        mock_ident.return_value = (1, uid)
        mock_get.return_value = {
            "profile_id": "todoist",
            "base_url": "https://api.todoist.com/rest/v2",
            "auth": {"type": "bearer", "secret_key": "todoist_token"},
            "default_headers": {"Accept": "application/json"},
            "endpoints": {
                "list_tasks": {"method": "GET", "path": "/tasks", "extract": "data"},
            },
        }
        mock_exec.return_value = {"ok": True, "status": 200, "response": []}

        out = json.loads(run({"profile_id": "todoist", "endpoint": "list_tasks"}))
        self.assertTrue(out["ok"])
        self.assertEqual(out["profile_id"], "todoist")
        mock_exec.assert_called_once()
        kw = mock_exec.call_args.kwargs
        self.assertEqual(kw["base_url"], "https://api.todoist.com/rest/v2")
        self.assertEqual(kw["path"], "/tasks")


if __name__ == "__main__":
    unittest.main()
