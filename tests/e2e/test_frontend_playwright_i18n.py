"""Optional Playwright i18n E2E (Docker + running agent-layer on :8088)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "scripts" / "run-e2e-playwright-i18n.sh"


@pytest.mark.e2e
def test_playwright_i18n_routes_de_en() -> None:
    if not shutil.which("docker"):
        pytest.skip("docker not available")
    if not RUNNER.is_file():
        pytest.skip(f"missing {RUNNER}")
    proc = subprocess.run(
        ["bash", str(RUNNER)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"playwright i18n e2e failed (exit {proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
