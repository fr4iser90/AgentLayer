"""Tests for GitHub REST tools (one module per tool under integrations/github/)."""

from __future__ import annotations

import json
from unittest.mock import patch

from plugins.tools.integrations.github.create_pull_request import create_pull_request
from plugins.tools.integrations.github.get_pull_request import get_pull_request


def test_create_pull_request_requires_head() -> None:
    out = json.loads(
        create_pull_request(
            {"owner": "acme", "repo": "app", "title": "Fix"},
        ),
    )
    assert out["ok"] is False
    assert "head" in out["error"]


def test_create_pull_request_success() -> None:
    fake = {
        "number": 7,
        "title": "Security fixes",
        "state": "open",
        "draft": False,
        "html_url": "https://github.com/acme/app/pull/7",
        "user": {"login": "dev"},
        "head": {"ref": "security-fixes"},
        "base": {"ref": "main"},
        "merged": False,
    }
    with patch(
        "plugins.tools.integrations.github.create_pull_request.github_request",
        return_value=(201, fake),
    ) as req:
        out = json.loads(
            create_pull_request(
                {
                    "owner": "acme",
                    "repo": "app",
                    "title": "Security fixes",
                    "head": "security-fixes",
                    "base": "main",
                    "body": "## Summary\n- SQLi",
                },
            ),
        )
    req.assert_called_once()
    assert req.call_args[0][0] == "POST"
    assert req.call_args[0][1] == "/repos/acme/app/pulls"
    body = req.call_args[1]["json_body"]
    assert body["head"] == "security-fixes"
    assert body["base"] == "main"
    assert out["ok"] is True
    assert out["number"] == 7
    assert out["html_url"] == fake["html_url"]
    assert out["head_ref"] == "security-fixes"


def test_create_pull_request_422_hint() -> None:
    with patch(
        "plugins.tools.integrations.github.create_pull_request.github_request",
        return_value=(422, {"ok": False, "status": 422, "error": "Validation Failed"}),
    ):
        out = json.loads(
            create_pull_request(
                {
                    "owner": "acme",
                    "repo": "app",
                    "title": "T",
                    "head": "missing-branch",
                },
            ),
        )
    assert out["ok"] is False
    assert "hint" in out
    assert "git_push" in out["hint"]


def test_get_pull_request_success() -> None:
    fake = {
        "number": 3,
        "title": "Feat",
        "state": "open",
        "html_url": "https://github.com/o/r/pull/3",
        "user": {"login": "u"},
        "head": {"ref": "feat"},
        "base": {"ref": "main"},
        "body": "details",
    }
    with patch(
        "plugins.tools.integrations.github.get_pull_request.github_request",
        return_value=(200, fake),
    ):
        out = json.loads(
            get_pull_request({"owner": "o", "repo": "r", "pull_number": 3}),
        )
    assert out["ok"] is True
    assert out["body"] == "details"
    assert out["head_ref"] == "feat"
