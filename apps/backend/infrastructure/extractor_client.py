"""Schema-driven LLM extraction for K1-lite."""

from __future__ import annotations

import json
import re
from typing import Any

from apps.backend.infrastructure.extractor_catalog_providers import (
    ExtractorProviderSpec,
    get_extractor_provider_spec,
)
from apps.backend.infrastructure.openai_compat_http import http_post_chat_completions
from apps.backend.infrastructure.operator_settings import normalize_external_llm_base_url

_HDR_NAME_TOKEN = re.compile(r"^[!#$%&'*+.0-9A-Z^_`a-z|~-]{1,128}\Z")


def _auth_headers_for_spec(spec: ExtractorProviderSpec) -> dict[str, str]:
    out: dict[str, str] = {"Content-Type": "application/json"}
    secret = (spec.api_key or "").strip()
    hn = (spec.api_header_name or "X-API-KEY").strip() or "X-API-KEY"
    if not secret:
        return out
    if hn.lower() == "authorization":
        out["Authorization"] = secret if secret.lower().startswith("bearer ") else f"Bearer {secret}"
        return out
    if _HDR_NAME_TOKEN.match(hn):
        out[hn] = secret
        return out
    raise ValueError(f"extractor API header name {hn!r} is not a valid HTTP header token")


def _chat_url(spec: ExtractorProviderSpec) -> str:
    base = (normalize_external_llm_base_url(spec.base_url) or spec.base_url).rstrip("/")
    low = base.lower()
    if low.endswith("/chat/completions"):
        return base
    return f"{base}/v1/chat/completions"


def _extract_answer_json(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        return {}
    m = re.search(r"<answer>\s*(.*?)\s*</answer>", text, flags=re.S | re.I)
    if m:
        text = m.group(1).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


def extractor_available(provider_id: str | None = None) -> bool:
    spec = get_extractor_provider_spec(provider_id)
    return spec is not None and bool((spec.model_default or "").strip())


def extract_units_with_llm(
    *,
    text: str,
    file_path: str,
    provider_id: str | None = None,
    model_id: str | None = None,
    timeout_sec: float | None = None,
) -> list[dict[str, Any]]:
    spec = get_extractor_provider_spec(provider_id)
    if spec is None:
        raise ValueError("No extractor provider configured (EXTRACTOR_PROVIDER_1_BASE_URL).")
    model = (model_id or spec.model_default or "").strip()
    if not model:
        raise ValueError("No extractor model configured (knowledge.extractor_model or EXTRACTOR_PROVIDER_N_MODEL).")

    system = (
        "You are a schema-driven information extraction model. Extract project knowledge as strict JSON only. "
        "Do not invent facts. Every item must be grounded in the input text."
    )
    user = (
        "Extract K1-lite project knowledge units from this file.\n"
        "Return JSON with shape: {\"units\": [{\"kind\": \"entity|claim|evidence\", "
        "\"label\": string, \"text\": string, \"line\": integer, \"section\": string, \"source\": \"llm_extractor\"}]}.\n"
        "Use entity for named components/APIs/classes/docs sections, claim for requirements/invariants/design statements, "
        "and evidence for source-backed facts/examples.\n\n"
        f"File path: {file_path}\n\n"
        f"Input text:\n{text[:12000]}"
    )
    data, _ = http_post_chat_completions(
        _chat_url(spec),
        {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": 1800,
        },
        headers=_auth_headers_for_spec(spec),
        timeout=timeout_sec or spec.timeout_sec,
        concurrency_provider_id=f"extractor:{spec.provider_id}",
    )
    choices = data.get("choices")
    content = ""
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict):
            content = str(msg.get("content") or "")
    parsed = _extract_answer_json(content)
    units = parsed.get("units")
    if not isinstance(units, list):
        return []
    out: list[dict[str, Any]] = []
    for unit in units[:120]:
        if not isinstance(unit, dict):
            continue
        kind = str(unit.get("kind") or "").strip().lower()
        text_u = str(unit.get("text") or "").strip()
        if kind not in ("entity", "claim", "evidence") or not text_u:
            continue
        out.append(
            {
                "kind": kind,
                "label": str(unit.get("label") or text_u[:120]).strip()[:200],
                "text": text_u[:4000],
                "line": int(unit.get("line") or 1),
                "section": str(unit.get("section") or "").strip()[:240],
                "source": "llm_extractor",
            }
        )
    return out

