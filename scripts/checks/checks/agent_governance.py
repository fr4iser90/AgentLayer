from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .common import CheckResult, print_header, print_pass, repo_root


@dataclass(frozen=True)
class AgentGovernanceViolation:
    code: str
    file: Path
    reason: str


@dataclass(frozen=True)
class AgentGovernanceWarning:
    code: str
    file: Path
    reason: str


def _configured_path(root: Path, raw: Any) -> Path:
    return root / str(raw)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text.strip() else 0


def _top_level_duplicate_keys(path: Path) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith((" ", "\t", "#", "-")):
            continue
        if ":" not in line:
            continue
        key = line.split(":", 1)[0].strip()
        if not key:
            continue
        if key in seen and key not in duplicates:
            duplicates.append(key)
        seen.add(key)
    return duplicates


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("agent.yaml must contain a mapping")
    return raw


def _prompt_path(agent_dir: Path, data: dict[str, Any]) -> Path:
    raw = data.get("system_prompt_file")
    prompt_file = str(raw or "system_prompt.md").strip() or "system_prompt.md"
    return agent_dir / prompt_file


def _validate_agent(
    *,
    root: Path,
    agent_yaml: Path,
    config: dict[str, Any],
) -> tuple[list[AgentGovernanceViolation], list[AgentGovernanceWarning]]:
    violations: list[AgentGovernanceViolation] = []
    warnings: list[AgentGovernanceWarning] = []

    duplicates = _top_level_duplicate_keys(agent_yaml)
    for key in duplicates:
        violations.append(
            AgentGovernanceViolation(
                code="AGENT001",
                file=agent_yaml,
                reason=f"duplicate top-level YAML key: {key}",
            )
        )

    try:
        data = _load_yaml(agent_yaml)
    except Exception as exc:
        return [
            AgentGovernanceViolation(
                code="AGENT002",
                file=agent_yaml,
                reason=f"invalid agent.yaml: {exc}",
            )
        ], warnings

    required_fields = _as_list(config.get("required_fields"))
    for field in required_fields:
        key = str(field)
        if _non_empty_str(data.get(key)) or isinstance(data.get(key), bool):
            continue
        violations.append(
            AgentGovernanceViolation(
                code="AGENT003",
                file=agent_yaml,
                reason=f"missing or empty required field: {key}",
            )
        )

    agent_id = str(data.get("id") or agent_yaml.parent.name).strip()
    if agent_id and agent_id != agent_yaml.parent.name:
        violations.append(
            AgentGovernanceViolation(
                code="AGENT004",
                file=agent_yaml,
                reason=f"agent id {agent_id!r} must match directory name {agent_yaml.parent.name!r}",
            )
        )

    policy_fields = ("tool_allowlist", "tool_domains", "tool_capability_any")
    if not any(_as_list(data.get(field)) for field in policy_fields):
        violations.append(
            AgentGovernanceViolation(
                code="AGENT005",
                file=agent_yaml,
                reason="agent must define tool_allowlist, tool_domains, or tool_capability_any",
            )
        )

    prompt_file = _prompt_path(agent_yaml.parent, data)
    inline_prompt = data.get("system_prompt")
    if _non_empty_str(inline_prompt):
        prompt_text = str(inline_prompt)
        prompt_source = agent_yaml
    elif prompt_file.exists():
        prompt_text = prompt_file.read_text(encoding="utf-8")
        prompt_source = prompt_file
    else:
        violations.append(
            AgentGovernanceViolation(
                code="AGENT006",
                file=prompt_file,
                reason="missing system prompt file",
            )
        )
        prompt_text = ""
        prompt_source = prompt_file

    if not prompt_text.strip():
        violations.append(
            AgentGovernanceViolation(
                code="AGENT007",
                file=prompt_source,
                reason="system prompt is empty",
            )
        )

    hard_chars = int(config.get("prompt_hard_max_chars") or 12000)
    warn_chars = int(config.get("prompt_warn_max_chars") or 8000)
    prompt_len = len(prompt_text)
    prompt_tokens = _approx_tokens(prompt_text)
    if prompt_len > hard_chars:
        violations.append(
            AgentGovernanceViolation(
                code="AGENT008",
                file=prompt_source,
                reason=f"system prompt exceeds hard budget ({prompt_len} > {hard_chars} chars, ~{prompt_tokens} tokens)",
            )
        )
    elif prompt_len > warn_chars:
        warnings.append(
            AgentGovernanceWarning(
                code="AGENTW001",
                file=prompt_source,
                reason=f"system prompt is over soft budget ({prompt_len} > {warn_chars} chars, ~{prompt_tokens} tokens)",
            )
        )

    for raw_phrase in _as_list(config.get("forbidden_prompt_phrases")):
        phrase = str(raw_phrase).strip()
        if phrase and phrase.lower() in prompt_text.lower():
            violations.append(
                AgentGovernanceViolation(
                    code="AGENT009",
                    file=prompt_source,
                    reason=f"system prompt contains forbidden phrase: {phrase}",
                )
            )

    pinned = [str(item).strip() for item in _as_list(data.get("pinned_tools")) if str(item).strip()]
    allowlist = [str(item).strip() for item in _as_list(data.get("tool_allowlist")) if str(item).strip()]
    max_pinned = int(config.get("max_pinned_tools") or 12)
    max_allowlist = int(config.get("max_tool_allowlist") or 80)
    if len(pinned) > max_pinned:
        violations.append(
            AgentGovernanceViolation(
                code="AGENT010",
                file=agent_yaml,
                reason=f"too many pinned tools ({len(pinned)} > {max_pinned})",
            )
        )
    if len(allowlist) > max_allowlist:
        violations.append(
            AgentGovernanceViolation(
                code="AGENT011",
                file=agent_yaml,
                reason=f"tool_allowlist is too large ({len(allowlist)} > {max_allowlist})",
            )
        )

    unknown_pins = sorted(set(pinned) - set(allowlist))
    if pinned and allowlist and unknown_pins:
        violations.append(
            AgentGovernanceViolation(
                code="AGENT012",
                file=agent_yaml,
                reason=f"pinned tools must also be in tool_allowlist: {', '.join(unknown_pins)}",
            )
        )

    emoji_count = sum(1 for char in prompt_text if ord(char) > 0xFFFF)
    max_prompt_emoji = int(config.get("max_prompt_emoji") or 8)
    if emoji_count > max_prompt_emoji:
        warnings.append(
            AgentGovernanceWarning(
                code="AGENTW002",
                file=prompt_source,
                reason=f"system prompt contains many emoji/non-BMP symbols ({emoji_count} > {max_prompt_emoji})",
            )
        )

    _ = root
    return violations, warnings


def _print_violations(root: Path, violations: list[AgentGovernanceViolation]) -> None:
    print(f"[check:agent_governance] FAILED: {len(violations)} violation(s)")
    for violation in violations:
        print()
        print(f"{violation.code} {violation.file.relative_to(root)}")
        print(f"  {violation.reason}")


def _print_warnings(root: Path, warnings: list[AgentGovernanceWarning]) -> None:
    if not warnings:
        return
    print(f"[check:agent_governance] warnings: {len(warnings)}")
    for warning in warnings:
        print()
        print(f"{warning.code} {warning.file.relative_to(root)}")
        print(f"  {warning.reason}")


def run(name: str, config: dict[str, Any]) -> CheckResult:
    root = repo_root()
    print_header(name)

    agents_root = _configured_path(root, config.get("agents_root", "plugins/agents"))
    violations: list[AgentGovernanceViolation] = []
    warnings: list[AgentGovernanceWarning] = []

    for agent_yaml in sorted(agents_root.glob("*/agent.yaml")):
        agent_violations, agent_warnings = _validate_agent(
            root=root,
            agent_yaml=agent_yaml,
            config=config,
        )
        violations.extend(agent_violations)
        warnings.extend(agent_warnings)

    _print_warnings(root, warnings)
    if violations:
        _print_violations(root, violations)
        return CheckResult(name=name, ok=False, message=f"{len(violations)} agent governance violation(s)")

    print_pass(name)
    return CheckResult(name=name, ok=True)
