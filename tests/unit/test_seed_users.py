"""Unit tests for the E2E user-B seed script.

``seed_users.py`` is a thin wrapper, but its contract matters: it must always
close both HTTP clients, and it must turn any failure into exit 1 rather than a
traceback that ``validate_stack.sh`` reads as a different failure class.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "e2e" / "seed_users.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("e2e_seed_users", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeClient:
    def __init__(self, email: str, user_id: str):
        self.email = email
        self.user_id = user_id
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def wired(monkeypatch, mod):
    """Replace every external seam the script touches."""
    calls: dict = {"closed": [], "login_args": None}
    admin = FakeClient("admin@example.com", "u-admin")
    user_b = FakeClient("b@example.com", "u-b")

    monkeypatch.setattr(mod, "load_e2e_env", lambda: calls.__setitem__("env", True))
    monkeypatch.setattr(mod, "require_server", lambda: calls.__setitem__("server", True))
    monkeypatch.setattr(mod, "admin_credentials", lambda: ("admin@example.com", "pw"))

    def login(email, password):
        calls["login_args"] = (email, password)
        return admin

    monkeypatch.setattr(mod.E2EClient, "login", staticmethod(login))
    monkeypatch.setattr(mod, "ensure_user_b", lambda c: user_b)
    return {"admin": admin, "user_b": user_b, "calls": calls}


def test_main_returns_zero_and_reports_identity(wired, mod, capsys):
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "b@example.com" in out
    assert "u-b" in out


def test_main_uses_admin_credentials_for_login(wired, mod):
    mod.main()
    assert wired["calls"]["login_args"] == ("admin@example.com", "pw")


def test_main_closes_both_clients_on_success(wired, mod):
    mod.main()
    assert wired["admin"].closed is True
    assert wired["user_b"].closed is True


def test_main_returns_one_and_reports_failure(wired, mod, monkeypatch, capsys):
    monkeypatch.setattr(mod, "require_server", lambda: (_ for _ in ()).throw(RuntimeError("no server")))
    assert mod.main() == 1
    err = capsys.readouterr().err
    assert "seed failed" in err
    assert "no server" in err


def test_main_closes_admin_even_when_user_b_fails(wired, mod, monkeypatch, capsys):
    """The finally block must still run: a leaked admin client is a real leak."""
    monkeypatch.setattr(
        mod, "ensure_user_b", lambda c: (_ for _ in ()).throw(RuntimeError("quota"))
    )
    assert mod.main() == 1
    assert wired["admin"].closed is True
    assert "quota" in capsys.readouterr().err


def test_main_does_not_close_a_client_that_was_never_created(mod, monkeypatch, capsys):
    """require_server failing before any client exists must not raise in finally."""
    monkeypatch.setattr(mod, "load_e2e_env", lambda: None)
    monkeypatch.setattr(mod, "require_server", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    assert mod.main() == 1
    assert "down" in capsys.readouterr().err
