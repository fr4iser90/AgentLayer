"""LLM risk assessment of an agent prompt, gating publish.

Publishing a prompt version used to check only that the row existed. The gate
here asks a utility model what the prompt actually instructs the agent to do
and refuses publish on a ``high`` verdict; only a site admin may publish past
that, and the override is recorded on the version row.

Fail-closed by construction: an unreachable provider, an empty reply or
unparseable JSON all raise :class:`PromptRiskUnavailable`, so a missing
verdict never reads as a cleared one. ``risk_level`` defaults to
``'unassessed'`` in the schema for the same reason.

The kill switch is not a convenience. The provider concurrency slot is waited
on with no deadline (``llm_concurrency._ProviderGate`` polls forever, and
``_DEFAULT_MAX_PARALLEL`` is 1 for a provider spec that sets none), so a
saturated provider can hold a publish open indefinitely and the httpx timeout
cannot break that wait. Only disabling the gate can.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

RISK_LEVELS = ("low", "medium", "high")

GATE_ENABLED_ENV = "AGENT_PROMPT_RISK_GATE_ENABLED"
ASSESS_TIMEOUT_SEC = 45.0

_CONTRACT = """\
You review a system prompt before it is published to a production AI agent.

Reply with ONE JSON object only (no markdown fences):
{"level": "low"|"medium"|"high", "reasons": ["short reason", ...]}

high  = the prompt instructs the agent to do something that could damage the
        operator or leak data: send secrets, files or conversation content to
        an outside destination, run destructive or privileged commands,
        bypass an approval or permission check, impersonate a human, or
        override its own safety rules.
medium = it reaches into sensitive territory (credentials, shells, deletion,
        network calls) but only in a bounded, clearly-scoped way.
low   = nothing sensitive is instructed.

Judge what the prompt asks the agent to DO. A prompt that merely mentions a
secret, a shell or a deletion in order to warn against it is not high.
"""


class PromptRiskUnavailable(RuntimeError):
    """No verdict could be produced. Publish must not proceed."""


@dataclass(frozen=True, slots=True)
class PromptRisk:
    level: str
    reasons: tuple[str, ...]

    @property
    def blocking(self) -> bool:
        return self.level == "high"


def gate_enabled() -> bool:
    """Off-switch for the whole gate. Enabled unless explicitly turned off.

    The default is on because publish is meant to require the assessment. Set
    ``AGENT_PROMPT_RISK_GATE_ENABLED=0`` only when the provider is wedged and
    an operator deliberately wants unassessed publishes.
    """
    raw = (os.environ.get(GATE_ENABLED_ENV) or "").strip().lower()
    if not raw:
        return True
    return raw in {"1", "true", "yes", "on"}


def _parse_json_loose(text: str) -> dict[str, Any] | None:
    """Mirror of the delegate-decision parser: fences, then a bare object."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped)
    if fenced:
        stripped = fenced.group(1).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        brace = re.search(r"\{[\s\S]*\}", stripped)
        if not brace:
            return None
        try:
            parsed = json.loads(brace.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _normalise_reasons(raw: Any) -> tuple[str, ...]:
    if isinstance(raw, str):
        cleaned = raw.strip()
        return (cleaned[:300],) if cleaned else ()
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            out.append(text[:300])
    return tuple(out[:8])


def _verdict_from(payload: dict[str, Any]) -> PromptRisk:
    level = str(payload.get("level") or "").strip().lower()
    if level not in RISK_LEVELS:
        raise PromptRiskUnavailable(
            f"risk assessment returned an unusable level: {payload.get('level')!r}"
        )
    return PromptRisk(level=level, reasons=_normalise_reasons(payload.get("reasons")))


def assess_prompt_risk(
    prompt_text: str,
    *,
    agent_id: str = "",
    llm_call: Callable[..., tuple[dict[str, Any], bool]] | None = None,
) -> PromptRisk:
    """Ask the utility model for a verdict. Raises rather than guessing.

    ``llm_call`` is required and has the same signature as
    ``post_catalog_chat_completions``. The domain does not resolve one itself:
    reaching into the infrastructure layer for a client is exactly the edge this
    layer must not cross. Callers in the application layer supply it.
    """
    text = (prompt_text or "").strip()
    if not text:
        raise PromptRiskUnavailable("prompt text is empty, nothing to assess")
    if llm_call is None:
        raise PromptRiskUnavailable("no llm_call supplied for risk assessment")
    call = llm_call

    user_payload = f"Agent id: {agent_id}\n\nSystem prompt under review:\n{text}"

    try:
        response, _tools_omitted = call(
            messages=[
                {"role": "system", "content": _CONTRACT},
                {"role": "user", "content": user_payload},
            ],
            timeout=ASSESS_TIMEOUT_SEC,
            temperature=0.1,
            max_tokens=500,
        )
    except Exception as exc:  # provider down, timeout, no slot, no model configured
        raise PromptRiskUnavailable(
            f"risk assessment provider call failed: {type(exc).__name__}: {exc}"
        ) from exc

    content = ""
    if isinstance(response, dict):
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            message = first.get("message")
            if isinstance(message, dict):
                content = str(message.get("content") or "")
            if not content:
                content = str(first.get("text") or "")

    if not content.strip():
        raise PromptRiskUnavailable("risk assessment model returned empty content")

    parsed = _parse_json_loose(content)
    if parsed is None:
        raise PromptRiskUnavailable("risk assessment model did not return JSON")

    return _verdict_from(parsed)
