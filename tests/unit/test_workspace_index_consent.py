"""ADR 0009 index consent: stored tier, operator cap, upload sanitisation."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.backend.infrastructure.workspace.workspace_client_index import (
    sanitize_symbol_files,
    sanitize_text_documents,
)
from apps.backend.infrastructure.workspace.workspace_index_consent import (
    INDEX_CONSENT_NONE,
    INDEX_CONSENT_SYMBOLS,
    INDEX_CONSENT_TEXT,
    clamp_index_consent,
    consent_covers,
    consent_refusal,
    default_index_consent_for_mode,
    effective_index_consent,
    mode_needs_consent,
    normalize_index_consent,
    refuse_if_above_operator_cap,
    sanitize_upload_rel_path,
)
from plugins.tools.workspace.lib.common import (
    ClientWorkspaceExecutionError,
    workspace_binding_from_context,
    workspace_record_from_context,
    workspace_retrieval_flags,
)


class TestNormalize(unittest.TestCase):
    def test_known_values(self) -> None:
        self.assertEqual(normalize_index_consent("TEXT"), INDEX_CONSENT_TEXT)
        self.assertEqual(normalize_index_consent("symbols"), INDEX_CONSENT_SYMBOLS)
        self.assertIsNone(normalize_index_consent("full"))
        self.assertIsNone(normalize_index_consent(None))

    def test_defaults(self) -> None:
        self.assertEqual(default_index_consent_for_mode("client"), INDEX_CONSENT_NONE)
        self.assertEqual(default_index_consent_for_mode("server"), INDEX_CONSENT_TEXT)

    def test_covers(self) -> None:
        self.assertTrue(consent_covers("text", "symbols"))
        self.assertTrue(consent_covers("symbols", "symbols"))
        self.assertFalse(consent_covers("symbols", "text"))
        self.assertFalse(consent_covers("none", "symbols"))

    def test_crawl_mode(self) -> None:
        self.assertEqual(mode_needs_consent("code"), INDEX_CONSENT_SYMBOLS)
        self.assertEqual(mode_needs_consent("docs"), INDEX_CONSENT_TEXT)
        self.assertEqual(mode_needs_consent("full"), INDEX_CONSENT_TEXT)


class TestOperatorCap(unittest.TestCase):
    @patch(
        "apps.backend.infrastructure.workspace.workspace_index_consent.operator_index_consent_max",
        return_value="symbols",
    )
    def test_effective_is_min_of_workspace_and_cap(self, _cap: object) -> None:
        ws = {"execution_mode": "client", "index_consent": "text"}
        self.assertEqual(effective_index_consent(ws), "symbols")
        self.assertIsNone(consent_refusal(ws, "symbols"))
        self.assertIn("operator cap is symbols", consent_refusal(ws, "text") or "")

    @patch(
        "apps.backend.infrastructure.workspace.workspace_index_consent.operator_index_consent_max",
        return_value="symbols",
    )
    def test_patch_refuses_rather_than_silently_clamping(self, _cap: object) -> None:
        err = refuse_if_above_operator_cap("text")
        self.assertIsNotNone(err)
        self.assertIn("operator cap is symbols", err or "")
        self.assertIsNone(refuse_if_above_operator_cap("symbols"))
        self.assertIsNone(refuse_if_above_operator_cap("none"))

    @patch(
        "apps.backend.infrastructure.workspace.workspace_index_consent.operator_index_consent_max",
        return_value="none",
    )
    def test_create_clamp_cannot_raise_above_cap(self, _cap: object) -> None:
        self.assertEqual(clamp_index_consent("text"), "none")

    @patch(
        "apps.backend.infrastructure.workspace.workspace_index_consent.operator_index_consent_max",
        return_value="symbols",
    )
    def test_application_patch_helper_raises_the_cap(self, _cap: object) -> None:
        from apps.backend.application.workspace.use_cases.workspace_controller_services import (
            normalize_index_consent_patch,
        )

        self.assertEqual(normalize_index_consent_patch("symbols"), "symbols")
        with self.assertRaises(ValueError) as ctx:
            normalize_index_consent_patch("text")
        self.assertIn("operator cap is symbols", str(ctx.exception))


class TestSanitize(unittest.TestCase):
    def test_relative_paths_only(self) -> None:
        self.assertEqual(sanitize_upload_rel_path("src/a.py"), "src/a.py")
        self.assertIsNone(sanitize_upload_rel_path("/etc/passwd"))
        self.assertIsNone(sanitize_upload_rel_path("../secret"))
        self.assertIsNone(sanitize_upload_rel_path("src/../../etc/passwd"))
        self.assertIsNone(sanitize_upload_rel_path("C:\\Windows\\x.py"))
        self.assertIsNone(sanitize_upload_rel_path("~/.ssh/id_rsa"))

    def test_symbol_payload_strips_bodies_and_oversize_signatures(self) -> None:
        files, errors = sanitize_symbol_files(
            [
                {
                    "path": "/abs/nope.py",
                    "sha256": "a" * 64,
                    "language": "python",
                    "symbols": [{"name": "x", "kind": "function"}],
                },
                {
                    "path": "src/a.py",
                    "sha256": "b" * 64,
                    "language": "python",
                    "symbols": [
                        {
                            "kind": "function",
                            "name": "hello",
                            "line": 3,
                            "signature": "s" * 500,
                            "body": "def hello(): return 1",
                        }
                    ],
                },
            ]
        )
        self.assertTrue(any("relative" in e for e in errors))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["path"], "src/a.py")
        self.assertEqual(len(files[0]["symbols"][0]["signature"]), 200)
        self.assertNotIn("body", files[0]["symbols"][0])

    def test_text_payload_refuses_absolute_and_oversize(self) -> None:
        docs, errors = sanitize_text_documents(
            [
                {"path": "../escape.md", "text": "# no"},
                {"path": "README.md", "text": "# hi"},
            ]
        )
        self.assertEqual(docs, [("README.md", "# hi")])
        self.assertTrue(any("relative" in e for e in errors))


class TestBindingSplit(unittest.TestCase):
    def test_record_returns_client_workspace_without_opening_the_path(self) -> None:
        ws = {"id": "1", "name": "laptop", "path": "/home/me/repo", "execution_mode": "client"}
        ctx = {"workspace": ws}
        self.assertEqual(workspace_record_from_context(ctx), ws)
        with self.assertRaises(ClientWorkspaceExecutionError):
            workspace_binding_from_context(ctx)

    def test_retrieval_flags_read_a_client_workspace(self) -> None:
        sem, ret = workspace_retrieval_flags(
            {
                "workspace": {
                    "id": "1",
                    "path": "/home/me/repo",
                    "execution_mode": "client",
                    "semantic_index_enabled": False,
                    "retrieval_enabled": True,
                }
            }
        )
        self.assertFalse(sem)
        self.assertTrue(ret)
