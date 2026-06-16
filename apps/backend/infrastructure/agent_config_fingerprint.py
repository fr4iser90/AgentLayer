"""Fingerprint and snapshot for benchmark-sensitive agent configuration."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.backend.domain.agent_config_registry import all_knobs, load_knob_registry
from apps.backend.infrastructure import agent_config_effective

_REPO_ROOT = Path(__file__).resolve().parents[3]


def deployment_git_sha() -> str:
    env = (os.environ.get("AGENTLAYER_GIT_SHA") or os.environ.get("GIT_SHA") or "").strip()
    if env:
        return env[:40]
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            text=True,
            timeout=2,
        )
        return out.strip()[:40]
    except Exception:
        return "unknown"


def _file_content_hash(path: str | None) -> str | None:
    if not path:
        return None
    p = _REPO_ROOT / path
    if not p.is_file():
        return None
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def benchmark_sensitive_effective_map(*, tenant_id: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for knob in all_knobs():
        if not knob.get("benchmark_sensitive"):
            continue
        kid = str(knob.get("id") or "")
        if not kid:
            continue
        layer = str(knob.get("layer") or "")
        if layer in ("code", "rubric", "bench"):
            h = _file_content_hash(str(knob.get("path") or ""))
            if h:
                out[kid] = h
            continue
        if layer == "operator":
            val, src = agent_config_effective.effective_value(kid, tenant_id=tenant_id)
            out[kid] = {"value": val, "source": src}
            continue
        val, src = agent_config_effective.effective_value(kid, tenant_id=tenant_id)
        out[kid] = {"value": val, "source": src}
    return out


def compute_fingerprint(*, tenant_id: int) -> str:
    payload = {
        "git_sha": deployment_git_sha(),
        "registry_version": load_knob_registry().get("version"),
        "knobs": benchmark_sensitive_effective_map(tenant_id=tenant_id),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def fingerprint_response(*, tenant_id: int) -> dict[str, Any]:
    sensitive = [k for k in all_knobs() if k.get("benchmark_sensitive")]
    return {
        "fingerprint": compute_fingerprint(tenant_id=tenant_id),
        "git_sha": deployment_git_sha(),
        "benchmark_sensitive_knob_count": len(sensitive),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def snapshot(*, tenant_id: int) -> dict[str, Any]:
    knobs: dict[str, Any] = {}
    non_writable: dict[str, str | None] = {}
    for knob in all_knobs():
        kid = str(knob.get("id") or "")
        if not kid:
            continue
        layer = str(knob.get("layer") or "")
        if layer in ("code", "rubric", "bench") or not knob.get("writable"):
            h = _file_content_hash(str(knob.get("path") or ""))
            if h:
                non_writable[kid] = h
            continue
        val, _src = agent_config_effective.effective_value(kid, tenant_id=tenant_id)
        knobs[kid] = val
    return {
        "fingerprint": compute_fingerprint(tenant_id=tenant_id),
        "git_sha": deployment_git_sha(),
        "knobs": knobs,
        "non_writable_hashes": non_writable,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
