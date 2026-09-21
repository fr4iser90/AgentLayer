"""Unit tests for the vision audit stage script.

``vision_audit.py`` is the ``--vision`` stage of ``validate_stack.sh``. Its exit
contract is the load-bearing part: a subjective "looks off" must never redden the
suite, but a pass that audited *nothing* must. That asymmetry is easy to break, and
breaking it silently turns the stage into either noise or a false green.
"""

from __future__ import annotations

import importlib.util
import io
import json
import urllib.error
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "vision_audit.py"

# 1x1 transparent PNG — enough to be a real image without bloating the fixture.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("vision_audit", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def shots(tmp_path):
    d = tmp_path / "screenshots"
    d.mkdir()
    return d


@pytest.fixture
def env(monkeypatch):
    def set_env(**overrides):
        base = {
            "VISION_BASE_URL": "http://gw.test/v1",
            "VISION_API_KEY": "k",
            "VISION_MODEL": "coder",
        }
        base.update(overrides)
        for key, val in base.items():
            if val is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, val)

    return set_env


@pytest.fixture
def out(tmp_path):
    return tmp_path / "vision.md"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _completion(content) -> bytes:
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


# ------------------------------------------------------------------ _extract_content
def test_extract_content_plain_string(mod):
    assert mod._extract_content({"choices": [{"message": {"content": "  clipped row  "}}]}) == "clipped row"


def test_extract_content_part_list(mod):
    data = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "line one"},
                        {"type": "text", "text": "line two"},
                    ]
                }
            }
        ]
    }
    assert mod._extract_content(data) == "line one\nline two"


def test_extract_content_ignores_non_text_parts(mod):
    data = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "image", "url": "x"},
                        {"type": "text", "text": "kept"},
                    ]
                }
            }
        ]
    }
    assert mod._extract_content(data) == "kept"


def test_extract_content_empty_shapes(mod):
    assert mod._extract_content({}) == ""
    assert mod._extract_content({"choices": []}) == ""
    assert mod._extract_content({"choices": [{}]}) == ""
    assert mod._extract_content({"choices": [{"message": {}}]}) == ""


# -------------------------------------------------------------------------- main()
def _main(mod, monkeypatch, argv):
    monkeypatch.setattr("sys.argv", ["vision_audit.py", *argv])
    return mod.main()


def test_main_reports_every_missing_env_var(mod, env, monkeypatch, shots, out, capsys):
    env(VISION_BASE_URL=None, VISION_API_KEY=None, VISION_MODEL=None)
    rc = _main(mod, monkeypatch, ["--screenshots", str(shots), "--out", str(out)])
    assert rc == 1
    err = capsys.readouterr().err
    for name in ("VISION_BASE_URL", "VISION_API_KEY", "VISION_MODEL"):
        assert name in err


def test_main_names_only_the_missing_var(mod, env, monkeypatch, shots, out, capsys):
    env(VISION_MODEL=None)
    rc = _main(mod, monkeypatch, ["--screenshots", str(shots), "--out", str(out)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "VISION_MODEL" in err
    assert "VISION_BASE_URL" not in err


def test_main_fails_when_screenshots_not_a_dir(mod, env, monkeypatch, tmp_path, out):
    env()
    rc = _main(mod, monkeypatch, ["--screenshots", str(tmp_path / "nope"), "--out", str(out)])
    assert rc == 1


def test_main_fails_when_no_pngs(mod, env, monkeypatch, shots, out):
    env()
    (shots / "notes.txt").write_text("not an image")
    rc = _main(mod, monkeypatch, ["--screenshots", str(shots), "--out", str(out)])
    assert rc == 1


def test_main_audits_and_exits_zero(mod, env, monkeypatch, shots, out):
    env()
    (shots / "a.png").write_bytes(PNG_BYTES)
    (shots / "b.png").write_bytes(PNG_BYTES)

    seen: list[dict] = []

    def fake_urlopen(req, timeout=None):
        seen.append(json.loads(req.data.decode()))
        return FakeResponse(_completion("- clipped header in the users table"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    rc = _main(mod, monkeypatch, ["--screenshots", str(shots), "--out", str(out)])
    assert rc == 0

    report = out.read_text(encoding="utf-8")
    assert "# Vision audit — 2 screenshot(s)" in report
    assert "## a.png" in report and "## b.png" in report
    assert "clipped header" in report
    assert len(seen) == 2
    assert seen[0]["model"] == "coder"
    assert seen[0]["stream"] is False


def test_main_sends_image_as_base64_data_uri(mod, env, monkeypatch, shots, out):
    env()
    (shots / "a.png").write_bytes(PNG_BYTES)
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        captured["auth"] = req.get_header("Authorization")
        captured["url"] = req.full_url
        return FakeResponse(_completion("NO DEFECTS"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    _main(mod, monkeypatch, ["--screenshots", str(shots), "--out", str(out)])

    assert captured["url"] == "http://gw.test/v1/chat/completions"
    assert captured["auth"] == "Bearer k"
    parts = captured["body"]["messages"][0]["content"]
    img = next(p for p in parts if p["type"] == "image_url")
    assert img["image_url"]["url"].startswith("data:image/png;base64,")
    assert len(img["image_url"]["url"]) > len("data:image/png;base64,")


def test_no_defects_reply_is_not_a_failure(mod, env, monkeypatch, shots, out):
    env()
    (shots / "clean.png").write_bytes(PNG_BYTES)
    monkeypatch.setattr(
        mod.urllib.request, "urlopen", lambda req, timeout=None: FakeResponse(_completion("NO DEFECTS"))
    )
    assert _main(mod, monkeypatch, ["--screenshots", str(shots), "--out", str(out)]) == 0
    assert "NO DEFECTS" in out.read_text(encoding="utf-8")


def test_http_error_is_recorded_but_not_fatal(mod, env, monkeypatch, shots, out):
    """One bad model call must not sink the pass — advisory contract."""
    env()
    (shots / "a.png").write_bytes(PNG_BYTES)
    (shots / "b.png").write_bytes(PNG_BYTES)

    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 503, "down", {}, io.BytesIO(b"engine busy"))
        return FakeResponse(_completion("- fine"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    rc = _main(mod, monkeypatch, ["--screenshots", str(shots), "--out", str(out)])
    assert rc == 0, "one errored image must not fail the whole stage"
    assert calls["n"] == 2
    report = out.read_text(encoding="utf-8")
    assert "ERROR 503" in report
    assert "engine busy" in report


def test_generic_exception_does_not_kill_the_pass(mod, env, monkeypatch, shots, out):
    env()
    (shots / "a.png").write_bytes(PNG_BYTES)
    (shots / "b.png").write_bytes(PNG_BYTES)

    calls = {"n": 0}

    def urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("connection reset")
        return FakeResponse(_completion("- fine"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)
    assert _main(mod, monkeypatch, ["--screenshots", str(shots), "--out", str(out)]) == 0
    assert calls["n"] == 2, "must continue to the next image after an exception"
    assert "connection reset" in out.read_text(encoding="utf-8")


def test_every_image_erroring_fails_the_stage(mod, env, monkeypatch, shots, out):
    """Nothing audited is not advisory — it is a broken stage."""
    env()
    (shots / "a.png").write_bytes(PNG_BYTES)

    def boom(req, timeout=None):
        raise OSError("no route to host")

    monkeypatch.setattr(mod.urllib.request, "urlopen", boom)
    assert _main(mod, monkeypatch, ["--screenshots", str(shots), "--out", str(out)]) == 1


def test_limit_caps_the_number_of_images(mod, env, monkeypatch, shots, out):
    env()
    for name in ("a.png", "b.png", "c.png"):
        (shots / name).write_bytes(PNG_BYTES)
    n = {"c": 0}

    def urlopen(req, timeout=None):
        n["c"] += 1
        return FakeResponse(_completion("NO DEFECTS"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)
    assert _main(mod, monkeypatch, ["--screenshots", str(shots), "--out", str(out), "--limit", "2"]) == 0
    assert n["c"] == 2
    assert "# Vision audit — 2 screenshot(s)" in out.read_text(encoding="utf-8")


def test_empty_model_reply_is_written_as_placeholder(mod, env, monkeypatch, shots, out):
    env()
    (shots / "a.png").write_bytes(PNG_BYTES)
    monkeypatch.setattr(
        mod.urllib.request, "urlopen", lambda req, timeout=None: FakeResponse(_completion(""))
    )
    assert _main(mod, monkeypatch, ["--screenshots", str(shots), "--out", str(out)]) == 0
    assert "(empty response)" in out.read_text(encoding="utf-8")
