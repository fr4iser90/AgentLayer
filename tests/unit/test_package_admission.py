"""Tests for package install admission (parser, policy, gate, npm hardening)."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.backend.domain.coding.package_admission import (
    evaluate_install,
    mutate_install_command,
    package_admission_gate,
    parse_package_install,
)
from apps.backend.domain.coding.package_admission_osv import OsvFinding, clear_osv_cache
from apps.backend.domain.coding.package_admission_policy import PackageAdmissionPolicy
from plugins.tools.workspace.shell.bash import bash


class TestParsePackageInstall(unittest.TestCase):
    def test_pip_simple(self) -> None:
        intent = parse_package_install("pip install requests")
        assert intent is not None
        self.assertEqual(intent.manager, "pip")
        self.assertEqual(intent.ecosystem, "pypi")
        self.assertEqual(intent.packages[0].name, "requests")

    def test_pip_pinned(self) -> None:
        intent = parse_package_install("pip install requests==2.32.3")
        assert intent is not None
        self.assertEqual(intent.packages[0].version_spec, "2.32.3")

    def test_python_m_pip(self) -> None:
        intent = parse_package_install("python3 -m pip install flask")
        assert intent is not None
        self.assertEqual(intent.manager, "pip")
        self.assertEqual(intent.packages[0].name, "flask")

    def test_uv_pip_install(self) -> None:
        intent = parse_package_install("uv pip install httpx")
        assert intent is not None
        self.assertEqual(intent.manager, "uv")
        self.assertEqual(intent.packages[0].name, "httpx")

    def test_npm_install(self) -> None:
        intent = parse_package_install("npm install lodash")
        assert intent is not None
        self.assertEqual(intent.ecosystem, "npm")
        self.assertEqual(intent.packages[0].name, "lodash")

    def test_npm_scoped(self) -> None:
        intent = parse_package_install("npm install @types/node@20.0.0")
        assert intent is not None
        self.assertEqual(intent.packages[0].name, "@types/node")
        self.assertEqual(intent.packages[0].version_spec, "20.0.0")

    def test_bulk_requirements_flag(self) -> None:
        intent = parse_package_install("pip install -r requirements.txt")
        assert intent is not None
        self.assertTrue(intent.bulk_requirements)

    def test_ignores_git_status(self) -> None:
        self.assertIsNone(parse_package_install("git status"))


class TestMutateNpmCommand(unittest.TestCase):
    def test_injects_ignore_scripts(self) -> None:
        intent = parse_package_install("npm install express")
        assert intent is not None
        policy = PackageAdmissionPolicy(npm_ignore_scripts=True)
        mutated = mutate_install_command(intent, policy=policy)
        self.assertIsNotNone(mutated)
        assert mutated is not None
        self.assertIn("--ignore-scripts", mutated)

    def test_skips_when_already_present(self) -> None:
        intent = parse_package_install("npm install --ignore-scripts express")
        assert intent is not None
        policy = PackageAdmissionPolicy(npm_ignore_scripts=True)
        self.assertIsNone(mutate_install_command(intent, policy=policy))


class TestEvaluateInstall(unittest.TestCase):
    def setUp(self) -> None:
        clear_osv_cache()

    def test_blocks_blocklisted_package(self) -> None:
        intent = parse_package_install("pip install evil-pkg")
        assert intent is not None
        policy = PackageAdmissionPolicy(
            mode="enforce",
            package_blocklist=frozenset({"evil-pkg"}),
        )
        with patch(
            "apps.backend.domain.coding.package_admission.query_vulnerabilities",
            return_value=([], None),
        ), patch(
            "apps.backend.domain.coding.package_admission._resolve_version",
            return_value=("1.0.0", None),
        ):
            verdict = evaluate_install(intent, policy=policy, context={})
        self.assertEqual(verdict.decision, "block")
        self.assertTrue(any("blocklist" in c.check for c in verdict.checks))

    def test_blocks_critical_cve_in_enforce(self) -> None:
        intent = parse_package_install("pip install vulnerable==1.0.0")
        assert intent is not None
        policy = PackageAdmissionPolicy(mode="enforce")
        with patch(
            "apps.backend.domain.coding.package_admission.query_vulnerabilities",
            return_value=(
                [OsvFinding(id="GHSA-abc", severity="CRITICAL", summary="bad")],
                None,
            ),
        ), patch(
            "apps.backend.domain.coding.package_admission._resolve_version",
            return_value=("1.0.0", None),
        ):
            verdict = evaluate_install(intent, policy=policy, context={})
        self.assertEqual(verdict.decision, "block")

    def test_monitor_warns_on_critical(self) -> None:
        intent = parse_package_install("pip install vulnerable==1.0.0")
        assert intent is not None
        policy = PackageAdmissionPolicy(mode="monitor")
        with patch(
            "apps.backend.domain.coding.package_admission.query_vulnerabilities",
            return_value=(
                [OsvFinding(id="GHSA-abc", severity="CRITICAL", summary="bad")],
                None,
            ),
        ), patch(
            "apps.backend.domain.coding.package_admission._resolve_version",
            return_value=("1.0.0", None),
        ):
            verdict = evaluate_install(intent, policy=policy, context={})
        self.assertEqual(verdict.decision, "warn_allow")
        self.assertTrue(verdict.reasons)

    def test_blocks_bulk_requirements_in_enforce(self) -> None:
        intent = parse_package_install("pip install -r requirements.txt")
        assert intent is not None
        policy = PackageAdmissionPolicy(mode="enforce", block_bulk_requirements=True)
        verdict = evaluate_install(intent, policy=policy, context={})
        self.assertEqual(verdict.decision, "block")


class TestPackageAdmissionGate(unittest.TestCase):
    def test_off_mode_passthrough(self) -> None:
        with patch(
            "apps.backend.domain.coding.package_admission.resolve_policy",
            return_value=PackageAdmissionPolicy(enabled=False, mode="off"),
        ):
            err, cmd = package_admission_gate("pip install requests", context={})
        self.assertIsNone(err)
        self.assertEqual(cmd, "pip install requests")

    def test_enforce_blocks_with_json(self) -> None:
        policy = PackageAdmissionPolicy(
            mode="enforce",
            package_blocklist=frozenset({"evil-pkg"}),
        )
        with patch(
            "apps.backend.domain.coding.package_admission.resolve_policy",
            return_value=policy,
        ), patch(
            "apps.backend.domain.coding.package_admission.evaluate_install",
        ) as mock_eval:
            from apps.backend.domain.coding.package_admission import AdmissionVerdict

            mock_eval.return_value = AdmissionVerdict(
                decision="block",
                reasons=["blocked"],
                checks=[],
            )
            err, _ = package_admission_gate("pip install evil-pkg", context={})
        assert err is not None
        payload = json.loads(err)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["admission"]["decision"], "block")


class TestBashIntegration(unittest.TestCase):
    def test_blocks_package_install_in_enforce(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ctx = {"workspace": {"path": str(root), "id": "ws-1"}}
            policy = PackageAdmissionPolicy(
                mode="enforce",
                package_blocklist=frozenset({"blocked-pkg"}),
            )
            with patch(
                "apps.backend.domain.coding.package_admission.resolve_policy",
                return_value=policy,
            ), patch(
                "apps.backend.domain.coding.package_admission.evaluate_install",
            ) as mock_eval:
                from apps.backend.domain.coding.package_admission import AdmissionVerdict

                mock_eval.return_value = AdmissionVerdict(
                    decision="block",
                    reasons=["blocklisted"],
                    checks=[],
                )
                out = json.loads(
                    bash({"command": "pip install blocked-pkg"}, context=ctx),
                )
        self.assertFalse(out["ok"])
        self.assertIn("admission", out)

    def test_mutates_npm_install_command(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ctx = {"workspace": {"path": str(root), "id": "ws-1"}}
            policy = PackageAdmissionPolicy(mode="monitor", npm_ignore_scripts=True)

            def fake_run(cmd, **kwargs):
                return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

            with patch(
                "apps.backend.domain.coding.package_admission.resolve_policy",
                return_value=policy,
            ), patch(
                "apps.backend.domain.coding.package_admission.evaluate_install",
            ) as mock_eval:
                from apps.backend.domain.coding.package_admission import AdmissionVerdict

                mock_eval.return_value = AdmissionVerdict(
                    decision="allow",
                    mutated_command="npm install --ignore-scripts lodash",
                )
                with patch(
                    "plugins.tools.workspace.shell.bash.subprocess.run",
                    side_effect=fake_run,
                ) as run_mock:
                    out = json.loads(
                        bash({"command": "npm install lodash"}, context=ctx),
                    )
            run_mock.assert_called_once()
            self.assertEqual(run_mock.call_args.args[0][0:3], ["npm", "install", "--ignore-scripts"])
        self.assertTrue(out["ok"])


if __name__ == "__main__":
    unittest.main()
