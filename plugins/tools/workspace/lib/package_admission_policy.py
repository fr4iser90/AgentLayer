"""Package install admission policy — env defaults + runtime context overrides."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AdmissionMode = Literal["off", "monitor", "enforce"]
LookupFailureAction = Literal["allow", "warn_allow", "block"]
AdmissionDecision = Literal["allow", "block", "ask", "warn_allow"]


@dataclass(frozen=True)
class PackageAdmissionPolicy:
    enabled: bool = True
    mode: AdmissionMode = "monitor"
    min_version_age_days: int = 0
    block_severity: frozenset[str] = frozenset({"CRITICAL", "HIGH"})
    ask_severity: frozenset[str] = frozenset({"MEDIUM"})
    block_global_install: bool = True
    npm_ignore_scripts: bool = True
    block_custom_index: bool = True
    block_bulk_requirements: bool = True
    package_blocklist: frozenset[str] = frozenset()
    package_allowlist: frozenset[str] | None = None
    on_lookup_failure: LookupFailureAction = "warn_allow"
    unattended_min_version_age_days: int = 7
    unattended_strict: bool = True


def _parse_mode(raw: str) -> AdmissionMode:
    v = (raw or "").strip().lower()
    if v in ("off", "monitor", "enforce"):
        return v
    return "monitor"


def _parse_severity_set(raw: str, *, default: frozenset[str]) -> frozenset[str]:
    parts = [x.strip().upper() for x in (raw or "").split(",") if x.strip()]
    return frozenset(parts) if parts else default


def _parse_lookup_failure(raw: str, *, mode: AdmissionMode) -> LookupFailureAction:
    v = (raw or "").strip().lower()
    if v in ("allow", "warn_allow", "block"):
        return v
    return "block" if mode == "enforce" else "warn_allow"


def default_policy_from_config() -> PackageAdmissionPolicy:
    from apps.backend.infrastructure.platform.config import config

    mode = _parse_mode(getattr(config, "PACKAGE_ADMISSION_MODE", "monitor"))
    enabled = mode != "off"
    return PackageAdmissionPolicy(
        enabled=enabled,
        mode=mode,
        min_version_age_days=max(0, int(getattr(config, "PACKAGE_MIN_VERSION_AGE_DAYS", 0))),
        block_severity=_parse_severity_set(
            getattr(config, "PACKAGE_BLOCK_SEVERITY_RAW", ""),
            default=frozenset({"CRITICAL", "HIGH"}),
        ),
        ask_severity=_parse_severity_set(
            getattr(config, "PACKAGE_ASK_SEVERITY_RAW", ""),
            default=frozenset({"MEDIUM"}),
        ),
        block_global_install=bool(getattr(config, "PACKAGE_BLOCK_GLOBAL_INSTALL", True)),
        npm_ignore_scripts=bool(getattr(config, "PACKAGE_NPM_IGNORE_SCRIPTS", True)),
        block_custom_index=bool(getattr(config, "PACKAGE_BLOCK_CUSTOM_INDEX", True)),
        block_bulk_requirements=bool(getattr(config, "PACKAGE_BLOCK_BULK_REQUIREMENTS", True)),
        package_blocklist=frozenset(
            x.strip().lower()
            for x in (getattr(config, "PACKAGE_BLOCKLIST_RAW", "") or "").split(",")
            if x.strip()
        ),
        package_allowlist=(
            frozenset(
                x.strip().lower()
                for x in (getattr(config, "PACKAGE_ALLOWLIST_RAW", "") or "").split(",")
                if x.strip()
            )
            if (getattr(config, "PACKAGE_ALLOWLIST_RAW", "") or "").strip()
            else None
        ),
        on_lookup_failure=_parse_lookup_failure(
            getattr(config, "PACKAGE_LOOKUP_FAILURE_ACTION_RAW", ""),
            mode=mode,
        ),
        unattended_min_version_age_days=max(
            0, int(getattr(config, "PACKAGE_UNATTENDED_MIN_AGE_DAYS", 7))
        ),
        unattended_strict=bool(getattr(config, "PACKAGE_UNATTENDED_STRICT", True)),
    )


def resolve_policy(context: dict[str, Any] | None) -> PackageAdmissionPolicy:
    """Merge config defaults with agent run context (unattended schedules)."""
    base = default_policy_from_config()
    ctx = context or {}
    unattended = bool(ctx.get("agent_unattended"))
    if not unattended:
        return base

    min_age = base.min_version_age_days
    if base.unattended_strict:
        min_age = max(min_age, base.unattended_min_version_age_days)
    replacements: dict[str, Any] = {"min_version_age_days": min_age}
    if base.unattended_strict and base.mode == "monitor":
        replacements["mode"] = "enforce"
    return PackageAdmissionPolicy(**{**base.__dict__, **replacements})
