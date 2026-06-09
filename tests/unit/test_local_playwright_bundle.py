"""Unit tests for local Playwright bundle tools (plan validation + export)."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    path = ROOT / "plugins/tools/integrations/browser/local_playwright_bundle.py"
    spec = importlib.util.spec_from_file_location("local_playwright_bundle_uut", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("spec")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestLocalPlaywrightBundle(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        cls.lp = _load_module()

    def test_validate_ok_minimal(self) -> None:
        plan = {"version": 1, "title": "x", "steps": [{"action": "goto", "url": "https://example.com/"}]}
        raw = self.lp.validate_browser_automation_plan({"plan": plan})
        j = json.loads(raw)
        self.assertTrue(j.get("ok"))
        self.assertEqual(j.get("errors"), [])

    def test_validate_rejects_http_non_localhost(self) -> None:
        plan = {"version": 1, "steps": [{"action": "goto", "url": "http://evil.test/"}]}
        raw = self.lp.validate_browser_automation_plan({"plan": plan})
        j = json.loads(raw)
        self.assertFalse(j.get("ok"))

    def test_validate_plan_json_only(self) -> None:
        plan = {"version": 1, "steps": [{"action": "goto", "url": "https://example.com/"}]}
        raw = self.lp.validate_browser_automation_plan({"plan_json": json.dumps(plan)})
        j = json.loads(raw)
        self.assertTrue(j.get("ok"))

    def test_export_creates_zip(self) -> None:
        lp = self.lp
        tmp = ROOT / "plugins/tools/integrations/browser/output/_pytest_local_pw"
        tmp.mkdir(parents=True, exist_ok=True)
        out_root = tmp / "bundles"
        out_root.mkdir(exist_ok=True)

        def fake_output_root():
            out_root.mkdir(parents=True, exist_ok=True)
            return out_root

        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))

        plan = {
            "version": 1,
            "title": "pytest",
            "steps": [
                {"action": "goto", "url": "https://example.com/"},
                {"action": "wait", "selector": "body", "timeout_ms": 5000},
            ],
        }
        orig_out = lp._output_root
        orig_repo = lp._REPO_ROOT
        try:
            lp._output_root = fake_output_root  # type: ignore[method-assign]
            lp._REPO_ROOT = tmp  # type: ignore[method-assign]
            raw = lp.export_local_playwright_bundle({"plan": plan})
        finally:
            lp._output_root = orig_out  # type: ignore[method-assign]
            lp._REPO_ROOT = orig_repo  # type: ignore[method-assign]

        j = json.loads(raw)
        self.assertTrue(j.get("ok"), msg=raw)
        zp = Path(j["zip_path"])
        self.assertTrue(zp.is_file())
        with zipfile.ZipFile(zp) as zf:
            names = set(zf.namelist())
        self.assertIn("task.mjs", names)
        self.assertIn("package.json", names)
        self.assertIn("manifest.json", names)
        self.assertTrue(j.get("zip_sha256"))
