"""Chat completion routing through model catalog providers."""
from __future__ import annotations

import logging
from typing import Literal

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.agent_runtime.llm_chat_attempt import make_llm_attempt
from apps.backend.infrastructure.agent_runtime.llm_env_providers import parse_llm_env_providers

logger = logging.getLogger(__name__)
LlmStack = Literal["provider_env", "provider_db"]
PROVIDER_FAILOVER_ID = "provider_failover"


def _strip_opt(s: object) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    return t or None

def route_chat_by_catalog_provider(
    catalog_owned_by: str,
    model_from_resolution: str,
    profile_key: str,
    is_override: bool,
) -> tuple[list[tuple[str, dict[str, str], str, str]], LlmStack]:
    from apps.backend.infrastructure.providers.model_catalog_providers import (
        _chat_completions_url,
        get_provider_spec,
        normalize_catalog_provider_id,
        provider_request_headers,
        resolve_model_for_provider,
    )

    pid = normalize_catalog_provider_id(catalog_owned_by)
    if not pid:
        raise ValueError("Invalid catalog provider id.")

    if pid == PROVIDER_FAILOVER_ID:
        from apps.backend.infrastructure.settings.operator_settings_llm_transport import _admin_llm_chat_attempts

        attempts = _admin_llm_chat_attempts(profile_key, is_override, model_from_resolution)
        if not attempts:
            raise ValueError(
                "provider_failover has no admin LLM endpoints — add endpoints under Admin → Interfaces "
                "or pick a specific provider id (provider_db_1, …)."
            )
        return attempts, "provider_db"

    spec = get_provider_spec(pid)
    if spec is None:
        raise ValueError(
            f"Unknown catalog provider {catalog_owned_by!r}. "
            "Add LLM_PROVIDER_N_* in .env or endpoints under Admin → Interfaces → LLM-Endpoints."
        )

    if not spec.base_url.strip():
        raise ValueError(f"Provider {pid!r} has no base URL configured.")

    chat_url = _chat_completions_url(spec)
    headers = provider_request_headers(spec)
    model = resolve_model_for_provider(spec, profile_key, is_override, model_from_resolution)
    if not model:
        raise ValueError(f"Provider {pid!r} has no model id for this request.")

    try:
        from apps.backend.domain.shared.identity import get_identity
        from apps.backend.infrastructure.providers.model_access_policy import is_model_allowed

        tenant_id, user_id = get_identity()
        if user_id is not None and not is_model_allowed(
            pid,
            model,
            tenant_id=tenant_id,
            user_id=user_id,
        ):
            raise ValueError(f"Model {model!r} is not available for provider {pid!r}.")
    except RuntimeError:
        pass

    logger.info(
        "catalog_route: provider=%s (%s) url=%s model=%r",
        pid,
        spec.source,
        chat_url,
        model,
    )
    stack: LlmStack = "provider_db" if spec.source == "db" else "provider_env"
    return [make_llm_attempt(chat_url, headers, model, pid)], stack


def first_env_provider_id() -> str | None:
    rows = parse_llm_env_providers()
    return rows[0].provider_id if rows else None


def first_admin_provider_id() -> str | None:
    from apps.backend.infrastructure.providers.model_catalog_providers import db_catalog_provider_id

    rows = db.operator_provider_endpoints_list_all("chat")
    if not rows:
        rows = db.external_llm_endpoints_list_all()
    for row in rows:
        if _strip_opt(row.get("base_url")):
            return db_catalog_provider_id(int(row["id"]))
    return None

