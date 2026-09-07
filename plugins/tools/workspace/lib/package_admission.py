"""Package install admission controller for coding_bash pip/npm installs."""

from __future__ import annotations

import json
import logging
import re
import shlex
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from plugins.tools.workspace.lib.package_admission_osv import OsvFinding, query_vulnerabilities
from plugins.tools.workspace.lib.package_admission_policy import (
    AdmissionDecision,
    PackageAdmissionPolicy,
    resolve_policy,
)

logger = logging.getLogger(__name__)

Ecosystem = Literal["pypi", "npm"]

_PIP_MANAGERS = frozenset({"pip", "pip3", "uv"})
_NPM_MANAGERS = frozenset({"npm", "pnpm", "yarn", "bun"})
_INSTALL_ACTIONS = frozenset({"install", "add", "i"})
_SKIP_PACKAGE_FLAGS = frozenset(
    {
        "-e",
        "--editable",
        "-c",
        "--constraint",
        "--no-deps",
        "--only-binary",
        "--prefer-binary",
        "--pre",
        "--no-cache-dir",
        "--upgrade",
        "-U",
        "--upgrade-strategy",
    }
)
_BULK_FLAGS = frozenset({"-r", "--requirement", "--requirements"})
_GLOBAL_FLAGS = frozenset({"-g", "--global"})
_CUSTOM_INDEX_FLAGS = frozenset({"-i", "--index-url", "--extra-index-url", "--registry"})
_DEV_FLAGS = frozenset({"-D", "-d", "--save-dev", "--dev"})
_IGNORE_SCRIPTS_FLAGS = frozenset({"--ignore-scripts"})

_SCOPED_NPM_RE = re.compile(r"^(@[^/]+/[^@]+)(?:@(.+))?$")
_PLAIN_NPM_RE = re.compile(r"^([^@]+)(?:@(.+))?$")
_PYPI_NAME_VER_RE = re.compile(r"^([^=<>!\s]+)(?:==|>=|<=|!=|~=|===)(.+)$")


@dataclass(frozen=True)
class PackageRef:
    name: str
    version_spec: str | None = None
    is_dev: bool = False


@dataclass(frozen=True)
class PackageInstallIntent:
    ecosystem: Ecosystem
    manager: str
    packages: tuple[PackageRef, ...]
    flags: frozenset[str]
    raw_command: str
    bulk_requirements: bool = False
    global_install: bool = False
    custom_index: bool = False


@dataclass
class CheckResult:
    check: str
    passed: bool
    detail: str
    severity: str | None = None


@dataclass
class AdmissionVerdict:
    decision: AdmissionDecision
    reasons: list[str] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    mutated_command: str | None = None


def _parse_npm_package(token: str, *, is_dev: bool) -> PackageRef | None:
    token = token.strip()
    if not token or token.startswith("-"):
        return None
    m = _SCOPED_NPM_RE.match(token)
    if m:
        return PackageRef(name=m.group(1), version_spec=m.group(2), is_dev=is_dev)
    m = _PLAIN_NPM_RE.match(token)
    if not m:
        return None
    name = m.group(1)
    if name.startswith("-"):
        return None
    return PackageRef(name=name, version_spec=m.group(2), is_dev=is_dev)


def _parse_pypi_package(token: str, *, is_dev: bool) -> PackageRef | None:
    token = token.strip()
    if not token or token.startswith("-"):
        return None
    if token in (".", ".."):
        return None
    m = _PYPI_NAME_VER_RE.match(token)
    if m:
        return PackageRef(name=m.group(1), version_spec=m.group(2).strip(), is_dev=is_dev)
    return PackageRef(name=token, version_spec=None, is_dev=is_dev)


def _manager_and_action(tokens: list[str]) -> tuple[str | None, str | None, int]:
    if not tokens:
        return None, None, 0
    if tokens[0].lower() in ("python", "python3") and len(tokens) >= 4 and tokens[1] == "-m":
        manager = tokens[2].lower()
        if manager in ("pip", "pip3"):
            return manager, tokens[3].lower(), 4
        return None, None, 0
    manager = tokens[0].lower()
    if manager == "uv" and len(tokens) >= 3 and tokens[1].lower() == "pip":
        return "uv", tokens[2].lower(), 3
    if manager in _PIP_MANAGERS | _NPM_MANAGERS:
        return manager, tokens[1].lower() if len(tokens) > 1 else None, 2
    return None, None, 0


def parse_package_install(command: str) -> PackageInstallIntent | None:
    """Return install intent when ``command`` is a supported package manager install."""
    cmd = (command or "").strip()
    if not cmd:
        return None
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return None
    manager, action, idx = _manager_and_action(tokens)
    if manager is None or action is None:
        return None
    if manager in _PIP_MANAGERS and action != "install":
        return None
    if manager in _NPM_MANAGERS and action not in _INSTALL_ACTIONS:
        return None

    ecosystem: Ecosystem = "pypi" if manager in _PIP_MANAGERS else "npm"
    flags: set[str] = set()
    packages: list[PackageRef] = []
    bulk_requirements = False
    global_install = False
    custom_index = False
    dev_next = False

    while idx < len(tokens):
        tok = tokens[idx]
        low = tok.lower()
        if low in _BULK_FLAGS:
            bulk_requirements = True
            idx += 2 if idx + 1 < len(tokens) else 1
            continue
        if low in _GLOBAL_FLAGS:
            global_install = True
            flags.add(low)
            idx += 1
            continue
        if low in _CUSTOM_INDEX_FLAGS:
            custom_index = True
            idx += 2 if idx + 1 < len(tokens) else 1
            continue
        if low in _DEV_FLAGS:
            dev_next = True
            flags.add(low)
            idx += 1
            continue
        if low in _SKIP_PACKAGE_FLAGS or low.startswith("-"):
            flags.add(low)
            if low in ("--upgrade-strategy",) and idx + 1 < len(tokens):
                idx += 2
                continue
            idx += 1
            continue
        if ecosystem == "pypi":
            ref = _parse_pypi_package(tok, is_dev=dev_next)
        else:
            ref = _parse_npm_package(tok, is_dev=dev_next)
        dev_next = False
        if ref is not None:
            packages.append(ref)
        idx += 1

    if not packages and not bulk_requirements:
        if manager in _NPM_MANAGERS and action in _INSTALL_ACTIONS:
            return PackageInstallIntent(
                ecosystem=ecosystem,
                manager=manager,
                packages=(),
                flags=frozenset(flags),
                raw_command=cmd,
                bulk_requirements=False,
                global_install=global_install,
                custom_index=custom_index,
            )
        return None

    return PackageInstallIntent(
        ecosystem=ecosystem,
        manager=manager,
        packages=tuple(packages),
        flags=frozenset(flags),
        raw_command=cmd,
        bulk_requirements=bulk_requirements,
        global_install=global_install,
        custom_index=custom_index,
    )


def _parse_iso8601(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _resolve_pypi_version(name: str, version_spec: str | None) -> tuple[str | None, str | None]:
    if version_spec and re.match(r"^\d", version_spec.strip()):
        return version_spec.strip(), None
    url = f"https://pypi.org/pypi/{name}/json"
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(url)
    except httpx.HTTPError as exc:
        return None, f"pypi metadata lookup failed: {exc}"
    if resp.status_code >= 400:
        return None, f"pypi http {resp.status_code}"
    try:
        data = resp.json()
    except ValueError:
        return None, "pypi invalid json"
    info = data.get("info") if isinstance(data, dict) else None
    if isinstance(info, dict) and isinstance(info.get("version"), str):
        return info["version"].strip(), None
    return None, "pypi version missing"


def _resolve_npm_version(name: str, version_spec: str | None) -> tuple[str | None, str | None]:
    if version_spec and re.match(r"^\d", version_spec.lstrip("^~v")):
        return version_spec.lstrip("^~v").strip(), None
    enc = name.replace("/", "%2f")
    url = f"https://registry.npmjs.org/{enc}/latest"
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(url)
    except httpx.HTTPError as exc:
        return None, f"npm metadata lookup failed: {exc}"
    if resp.status_code >= 400:
        return None, f"npm http {resp.status_code}"
    try:
        data = resp.json()
    except ValueError:
        return None, "npm invalid json"
    if isinstance(data, dict) and isinstance(data.get("version"), str):
        return data["version"].strip(), None
    return None, "npm version missing"


def _package_release_age_days(
    *,
    ecosystem: Ecosystem,
    name: str,
    version: str,
) -> tuple[int | None, str | None]:
    if ecosystem == "pypi":
        url = f"https://pypi.org/pypi/{name}/{version}/json"
        field_name = "upload_time"
    else:
        enc = name.replace("/", "%2f")
        url = f"https://registry.npmjs.org/{enc}/{version}"
        field_name = "time"
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(url)
    except httpx.HTTPError as exc:
        return None, f"{ecosystem} release lookup failed: {exc}"
    if resp.status_code >= 400:
        return None, f"{ecosystem} http {resp.status_code}"
    try:
        data = resp.json()
    except ValueError:
        return None, f"{ecosystem} invalid json"

    uploaded: datetime | None = None
    if ecosystem == "pypi":
        urls = data.get("urls") if isinstance(data, dict) else None
        if isinstance(urls, list) and urls:
            first = urls[0]
            if isinstance(first, dict):
                uploaded = _parse_iso8601(str(first.get("upload_time") or ""))
        if uploaded is None and isinstance(data, dict):
            uploaded = _parse_iso8601(str((data.get("info") or {}).get("upload_time") or ""))
    else:
        times = data.get("time") if isinstance(data, dict) else None
        if isinstance(times, dict):
            uploaded = _parse_iso8601(str(times.get(version) or times.get("modified") or ""))
    if uploaded is None:
        return None, f"{ecosystem} upload time missing"
    age = datetime.now(timezone.utc) - uploaded
    return max(0, age.days), None


def _resolve_version(
    ref: PackageRef,
    *,
    ecosystem: Ecosystem,
) -> tuple[str | None, str | None]:
    if ecosystem == "pypi":
        return _resolve_pypi_version(ref.name, ref.version_spec)
    return _resolve_npm_version(ref.name, ref.version_spec)


def _worst_severity(findings: list[OsvFinding]) -> str | None:
    order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
    best: str | None = None
    best_score = -1
    for f in findings:
        score = order.get(f.severity.upper(), 0)
        if score > best_score:
            best_score = score
            best = f.severity.upper()
    return best


def _decision_for_severity(
  severity: str,
  *,
  policy: PackageAdmissionPolicy,
  unattended: bool,
) -> AdmissionDecision:
    sev = severity.upper()
    if sev in policy.block_severity:
        return "block"
    if sev in policy.ask_severity:
        return "block" if unattended else "ask"
    return "allow"


def mutate_install_command(intent: PackageInstallIntent, *, policy: PackageAdmissionPolicy) -> str | None:
    if intent.manager not in _NPM_MANAGERS or not policy.npm_ignore_scripts:
        return None
    if "--ignore-scripts" in intent.raw_command:
        return None
    try:
        tokens = shlex.split(intent.raw_command)
    except ValueError:
        return None
    manager, action, idx = _manager_and_action(tokens)
    if manager is None or action is None:
        return None
    insert_at = idx
    tokens.insert(insert_at, "--ignore-scripts")
    return " ".join(shlex.quote(t) for t in tokens)


def evaluate_install(
    intent: PackageInstallIntent,
    *,
    policy: PackageAdmissionPolicy,
    context: dict[str, Any] | None = None,
    osv_timeout_sec: float = 8.0,
) -> AdmissionVerdict:
    ctx = context or {}
    unattended = bool(ctx.get("agent_unattended"))
    checks: list[CheckResult] = []
    reasons: list[str] = []
    decision: AdmissionDecision = "allow"

    def bump(next_decision: AdmissionDecision, reason: str) -> None:
        nonlocal decision
        reasons.append(reason)
        rank = {"allow": 0, "warn_allow": 1, "ask": 2, "block": 3}
        if rank[next_decision] > rank[decision]:
            decision = next_decision

    if intent.bulk_requirements:
        checks.append(
            CheckResult(
                check="bulk_requirements",
                passed=not policy.block_bulk_requirements,
                detail="install from requirements file",
            )
        )
        if policy.block_bulk_requirements:
            bump("block", "bulk requirements install blocked by package admission policy")
            return AdmissionVerdict(decision=decision, reasons=reasons, checks=checks)

    if intent.global_install and policy.block_global_install:
        checks.append(CheckResult(check="global_install", passed=False, detail="global pip install"))
        bump("block", "global package install is not allowed in workspace")
        return AdmissionVerdict(decision=decision, reasons=reasons, checks=checks)

    if intent.custom_index and policy.block_custom_index:
        checks.append(CheckResult(check="custom_index", passed=False, detail="custom package index"))
        bump("block", "custom package index/registry is not allowed")
        return AdmissionVerdict(decision=decision, reasons=reasons, checks=checks)

    if policy.package_allowlist is not None:
        for ref in intent.packages:
            allowed = ref.name.lower() in policy.package_allowlist
            checks.append(
                CheckResult(
                    check="allowlist",
                    passed=allowed,
                    detail=ref.name,
                )
            )
            if not allowed:
                bump("block", f"package {ref.name!r} is not on the allowlist")

    for ref in intent.packages:
        if ref.name.lower() in policy.package_blocklist:
            checks.append(
                CheckResult(check="blocklist", passed=False, detail=ref.name),
            )
            bump("block", f"package {ref.name!r} is blocklisted")

    lookup_failed = False
    for ref in intent.packages:
        version, ver_err = _resolve_version(ref, ecosystem=intent.ecosystem)
        if ver_err:
            lookup_failed = True
            checks.append(
                CheckResult(check="version_resolve", passed=False, detail=f"{ref.name}: {ver_err}"),
            )
            continue
        if not version:
            checks.append(
                CheckResult(check="version_resolve", passed=False, detail=f"{ref.name}: unresolved"),
            )
            lookup_failed = True
            continue

        if policy.min_version_age_days > 0:
            age_days, age_err = _package_release_age_days(
                ecosystem=intent.ecosystem,
                name=ref.name,
                version=version,
            )
            if age_err:
                lookup_failed = True
                checks.append(
                    CheckResult(
                        check="version_age",
                        passed=False,
                        detail=f"{ref.name}@{version}: {age_err}",
                    )
                )
            elif age_days is not None and age_days < policy.min_version_age_days:
                checks.append(
                    CheckResult(
                        check="version_age",
                        passed=False,
                        detail=f"{ref.name}@{version} released {age_days}d ago",
                    )
                )
                bump(
                    "block",
                    (
                        f"{ref.name}@{version} is only {age_days} day(s) old "
                        f"(minimum {policy.min_version_age_days})"
                    ),
                )

        findings, osv_err = query_vulnerabilities(
            ecosystem=intent.ecosystem,
            name=ref.name,
            version=version,
            timeout_sec=osv_timeout_sec,
        )
        if osv_err:
            lookup_failed = True
            checks.append(
                CheckResult(check="osv", passed=False, detail=f"{ref.name}@{version}: {osv_err}"),
            )
            continue
        worst = _worst_severity(findings)
        if worst:
            relevant = [f for f in findings if f.severity.upper() in policy.block_severity | policy.ask_severity]
            if relevant:
                ids = ", ".join(f.id for f in relevant[:3])
                checks.append(
                    CheckResult(
                        check="osv",
                        passed=False,
                        detail=f"{ref.name}@{version}: {worst} ({ids})",
                        severity=worst,
                    )
                )
                bump(
                    _decision_for_severity(worst, policy=policy, unattended=unattended),
                    f"{ref.name}@{version} has known vulnerabilities ({worst})",
                )
            else:
                checks.append(
                    CheckResult(
                        check="osv",
                        passed=True,
                        detail=f"{ref.name}@{version}: no policy-level CVEs",
                    )
                )
        else:
            checks.append(
                CheckResult(
                    check="osv",
                    passed=True,
                    detail=f"{ref.name}@{version}: clean",
                )
            )

    if lookup_failed:
        failure_action = policy.on_lookup_failure
        checks.append(
            CheckResult(
                check="lookup_failure",
                passed=failure_action != "block",
                detail=failure_action,
            )
        )
        if failure_action == "block":
            bump("block", "package metadata/vulnerability lookup failed")
        elif failure_action == "warn_allow":
            bump("warn_allow", "package metadata/vulnerability lookup failed (monitor)")

    mutated = mutate_install_command(intent, policy=policy)
    if policy.mode == "monitor" and decision in ("allow", "warn_allow"):
        final = "warn_allow" if reasons else "allow"
        return AdmissionVerdict(
            decision=final,
            reasons=reasons,
            checks=checks,
            mutated_command=mutated,
        )
    if policy.mode == "monitor" and decision in ("ask", "block"):
        return AdmissionVerdict(
            decision="warn_allow",
            reasons=reasons + [f"would {decision} in enforce mode"],
            checks=checks,
            mutated_command=mutated,
        )
    return AdmissionVerdict(
        decision=decision,
        reasons=reasons,
        checks=checks,
        mutated_command=mutated,
    )


def _verdict_error_json(verdict: AdmissionVerdict, *, intent: PackageInstallIntent) -> str:
    return json.dumps(
        {
            "ok": False,
            "error": "package admission denied",
            "admission": {
                "decision": verdict.decision,
                "manager": intent.manager,
                "ecosystem": intent.ecosystem,
                "packages": [
                    {"name": p.name, "version_spec": p.version_spec, "dev": p.is_dev}
                    for p in intent.packages
                ],
                "reasons": verdict.reasons,
                "checks": [
                    {
                        "check": c.check,
                        "passed": c.passed,
                        "detail": c.detail,
                        **({"severity": c.severity} if c.severity else {}),
                    }
                    for c in verdict.checks
                ],
            },
        },
        ensure_ascii=False,
    )


def package_admission_gate(
    command: str,
    *,
    context: dict[str, Any] | None,
    workspace_root: str | None = None,
) -> tuple[str | None, str]:
    """
    Returns ``(error_json, effective_command)``.
    When ``error_json`` is set, the caller should return it immediately.
    """
    _ = workspace_root
    policy = resolve_policy(context)
    if not policy.enabled or policy.mode == "off":
        return None, command

    intent = parse_package_install(command)
    if intent is None:
        return None, command

    from apps.backend.infrastructure.platform.config import config

    timeout = float(getattr(config, "PACKAGE_OSV_TIMEOUT_SEC", 8))
    verdict = evaluate_install(intent, policy=policy, context=context, osv_timeout_sec=timeout)

    if verdict.decision == "warn_allow":
        if verdict.reasons:
            logger.warning(
                "package_admission monitor: %s — %s",
                command[:200],
                "; ".join(verdict.reasons),
            )
        effective = verdict.mutated_command or command
        return None, effective

    if verdict.decision in ("block", "ask"):
        return _verdict_error_json(verdict, intent=intent), command

    return None, verdict.mutated_command or command
