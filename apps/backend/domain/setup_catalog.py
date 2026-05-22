"""Setup wizard: provider reachability, chat vs embedding models, default profile picks."""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.infrastructure.embedding_client import (
    clear_embedding_health_cache,
    embedding_catalog_health,
    probe_embedding_output_dim,
)
from apps.backend.domain.catalog_chat_llm import pick_reachable_catalog_provider
from apps.backend.infrastructure.model_catalog_providers import (
    fetch_full_model_catalog,
    fetch_models_for_provider,
    get_provider_spec,
    list_provider_specs,
)
from apps.backend.infrastructure.operator_settings import (
    OperatorSettingsPatch,
    apply_operator_settings_patch,
    invalidate_operator_settings_cache,
)
from apps.backend.infrastructure.model_catalog_routing import invalidate_model_catalog_cache
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.rag_embedding_sync import rank_embedding_model_ids

logger = logging.getLogger(__name__)

ModelKind = Literal["chat", "embedding", "unknown"]

_CHAT_HINTS = ("gpt-", "gpt4", "claude", "llama", "mistral", "qwen", "nemotron", "deepseek", "gemma")
_EMBED_HINTS = ("embed", "nomic-embed", "bge", "e5", "minilm", "gte", "sentence")


def classify_model_id(model_id: str) -> ModelKind:
    low = (model_id or "").strip().lower()
    if not low:
        return "unknown"
    if "embed" in low or any(h in low for h in _EMBED_HINTS):
        return "embedding"
    if any(h in low for h in _CHAT_HINTS):
        return "chat"
    return "chat"


def rank_chat_model_ids(model_ids: list[str]) -> list[str]:
    """Prefer obvious chat models over embedding-like ids."""

    def score(mid: str) -> tuple[int, str]:
        low = mid.lower()
        s = 0
        if any(h in low for h in _EMBED_HINTS) or "embed" in low:
            s += 20
        if any(h in low for h in _CHAT_HINTS):
            s -= 10
        if "instruct" in low or "chat" in low:
            s -= 3
        return (s, mid)

    return sorted({m.strip() for m in model_ids if m.strip()}, key=score)


def _models_for_provider(
    merged: list[dict[str, Any]], provider_id: str
) -> tuple[list[str], list[str], list[str]]:
    chat: list[str] = []
    embed: list[str] = []
    other: list[str] = []
    for row in merged:
        if str(row.get("owned_by") or "").strip() != provider_id:
            continue
        mid = str(row.get("id") or "").strip()
        if not mid:
            continue
        kind = classify_model_id(mid)
        if kind == "embedding":
            embed.append(mid)
        elif kind == "chat":
            chat.append(mid)
        else:
            other.append(mid)
    return rank_chat_model_ids(chat), rank_embedding_model_ids(embed), other


def ollama_embedding_base_url() -> str | None:
    """OpenAI-compat host prefix for Ollama embeddings (same host as chat, path /v1/embeddings)."""
    spec = get_provider_spec("ollama")
    raw = (spec.base_url if spec else "") or ""
    if not raw.strip():
        from apps.backend.core.config import config as app_config

        raw = (getattr(app_config, "OLLAMA_BASE_URL", None) or "").strip()
    if not raw:
        return None
    from apps.backend.infrastructure.operator_settings import normalize_external_llm_base_url

    return normalize_external_llm_base_url(raw) or None


def enrich_setup_embedding_meta(
    embedding: dict[str, Any], providers: list[dict[str, Any]]
) -> dict[str, Any]:
    out = dict(embedding)
    out["optional"] = True
    configured = bool(embedding.get("configured"))
    reachable = bool(embedding.get("reachable"))
    out["rag_active"] = configured and reachable and bool(embedding.get("model"))
    if not configured:
        out.setdefault(
            "status_line",
            "Nicht konfiguriert — RAG/Memory-Vektoren inaktiv. Chat und Coding sind davon unabhängig.",
        )
        ollama = next(
            (p for p in providers if p.get("provider_id") == "ollama" and p.get("reachable")),
            None,
        )
        base = ollama_embedding_base_url() if ollama else None
        embed_models = list(ollama.get("embedding_models") or []) if ollama else []
        ranked = rank_embedding_model_ids(embed_models)
        out["ollama_opt_in"] = {
            "available": bool(ollama and base),
            "suggested_base_url": base,
            "suggested_model": ranked[0] if ranked else "nomic-embed-text",
            "suggested_models": ranked,
        }
    return out


def build_setup_catalog() -> dict[str, Any]:
    merged, agentlayer = fetch_full_model_catalog()
    providers_out: list[dict[str, Any]] = []
    any_chat = False

    for spec in list_provider_specs():
        meta = agentlayer.get(spec.provider_id)
        if not isinstance(meta, dict):
            meta = {}
        reachable = bool(meta.get("reachable"))
        chat_models, embed_models, _ = _models_for_provider(merged, spec.provider_id)
        if reachable and chat_models:
            any_chat = True
        providers_out.append(
            {
                "provider_id": spec.provider_id,
                "label": spec.label or spec.provider_id,
                "source": spec.source,
                "reachable": reachable,
                "detail": meta.get("detail"),
                "chat_models": chat_models,
                "embedding_models": embed_models,
                "model_count": len(chat_models) + len(embed_models),
            }
        )

    embedding = agentlayer.get("embedding")
    if not isinstance(embedding, dict):
        embedding = embedding_catalog_health()
    embedding = enrich_setup_embedding_meta(embedding, providers_out)

    suggestions = _suggest_defaults(providers_out, embedding)
    return {
        "providers": providers_out,
        "embedding": embedding,
        "suggestions": suggestions,
        "any_chat_reachable": any_chat,
    }


def _suggest_defaults(
    providers: list[dict[str, Any]], embedding: dict[str, Any]
) -> dict[str, Any]:
    primary = pick_reachable_catalog_provider()
    chat_pool: list[str] = []
    for p in providers:
        if p.get("reachable") and p.get("provider_id") == primary:
            chat_pool = list(p.get("chat_models") or [])
            break
    if not chat_pool:
        for p in providers:
            if p.get("reachable"):
                chat_pool = list(p.get("chat_models") or [])
                primary = str(p.get("provider_id") or primary)
                break

    ranked_chat = rank_chat_model_ids(chat_pool)
    agent = ranked_chat[0] if ranked_chat else None
    coding = ranked_chat[1] if len(ranked_chat) > 1 else agent
    default = agent

    embed_model = None
    if embedding.get("reachable") and embedding.get("model"):
        embed_model = str(embedding["model"])
    elif embedding.get("available_models"):
        ranked = rank_embedding_model_ids([str(x) for x in embedding["available_models"]])
        embed_model = ranked[0] if ranked else None
    for p in providers:
        if p.get("reachable") and p.get("embedding_models"):
            if not embed_model:
                embed_model = (p.get("embedding_models") or [None])[0]
            break

    return {
        "primary_provider_id": primary,
        "model_agent": agent,
        "model_coding": coding,
        "model_default": default,
        "rag_embedding_model": embed_model,
    }


class SetupPreferencesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_provider_id: str = Field(..., min_length=1, max_length=64)
    model_agent: str | None = Field(default=None, max_length=256)
    model_coding: str | None = Field(default=None, max_length=256)
    model_default: str | None = Field(default=None, max_length=256)
    model_vlm: str | None = Field(default=None, max_length=256)
    rag_embedding_model: str | None = Field(default=None, max_length=256)


def apply_setup_preferences(body: SetupPreferencesBody) -> dict[str, Any]:
    pid = (body.primary_provider_id or "").strip()
    spec = get_provider_spec(pid)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"Unbekannter Provider {pid!r}.")

    rows, meta = fetch_models_for_provider(spec)
    if not meta.get("reachable"):
        raise HTTPException(
            status_code=400,
            detail=f"Provider {pid!r} ist nicht erreichbar. Prüfen Sie URL und Netzwerk.",
        )

    chat_ids = {
        str(m.get("id") or "").strip()
        for m in rows
        if str(m.get("id") or "").strip()
        and classify_model_id(str(m.get("id") or "")) != "embedding"
    }

    def pick(field: str | None, fallback: str | None) -> str | None:
        v = (field or "").strip() or None
        if v and chat_ids and v not in chat_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Modell {v!r} ist kein Chat-Modell auf Provider {pid!r}.",
            )
        return v or fallback

    ranked = rank_chat_model_ids([str(r.get("id") or "") for r in rows if r.get("id")])
    first = ranked[0] if ranked else None
    md = pick(body.model_default, first)
    ma = pick(body.model_agent, md or first)
    mc = pick(body.model_coding, ma or md or first)
    mv = pick(body.model_vlm, None)

    key = spec.api_key if spec.api_key else "-"
    db.external_llm_endpoints_sync(
        [
            {
                "sort_order": 0,
                "enabled": True,
                "label": spec.label or pid,
                "base_url": spec.base_url,
                "api_key": key,
                "model_default": md,
                "model_vlm": mv,
                "model_agent": ma,
                "model_coding": mc,
            }
        ]
    )
    invalidate_operator_settings_cache()
    invalidate_model_catalog_cache()

    rag_result: dict[str, Any] = {"updated": False}
    rag_model = (body.rag_embedding_model or "").strip() or None
    if rag_model:
        emb = embedding_catalog_health(force_refresh=True)
        available = [str(x) for x in (emb.get("available_models") or [])]
        if emb.get("model"):
            available.append(str(emb["model"]))
        if available and rag_model not in available:
            ranked_e = rank_embedding_model_ids(available)
            if rag_model not in ranked_e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Embedding-Modell {rag_model!r} ist auf dem Embedding-Endpunkt nicht gelistet.",
                )
        patch = OperatorSettingsPatch(rag_embedding_model=rag_model)
        try:
            dim = probe_embedding_output_dim(model_id=rag_model)
            patch.rag_embedding_dim = dim
            rag_result["embedding_dim"] = dim
        except Exception as exc:
            logger.warning("setup: embedding dim probe failed: %s", exc)
            rag_result["dim_probe_error"] = str(exc)[:200]
        apply_operator_settings_patch(patch)
        rag_result["updated"] = True
    elif not rag_model:
        from apps.backend.infrastructure.embedding_client import _normalized_embedding_base

        if not _normalized_embedding_base():
            apply_operator_settings_patch(OperatorSettingsPatch(rag_enabled=False))
            rag_result["rag_disabled"] = True

    return {
        "ok": True,
        "primary_provider_id": pid,
        "model_agent": ma,
        "model_coding": mc,
        "model_default": md,
        "rag_embedding_model": rag_model,
        "rag": rag_result,
    }


def apply_enable_ollama_embedding() -> dict[str, Any]:
    """Opt-in: use reachable Ollama host for embeddings (stored in operator_settings)."""
    base = ollama_embedding_base_url()
    if not base:
        raise HTTPException(
            status_code=400,
            detail="Ollama ist nicht konfiguriert (OLLAMA_BASE_URL fehlt).",
        )
    spec = get_provider_spec("ollama")
    if spec is not None:
        _, ometa = fetch_models_for_provider(spec)
        if not ometa.get("reachable"):
            raise HTTPException(
                status_code=400,
                detail="Ollama ist nicht erreichbar. Starten Sie Ollama und laden Sie ein Embedding-Modell.",
            )
    merged, _ = fetch_full_model_catalog()
    _, embed_models, _ = _models_for_provider(merged, "ollama")
    ranked = rank_embedding_model_ids(embed_models)
    model = ranked[0] if ranked else "nomic-embed-text"

    apply_operator_settings_patch(
        OperatorSettingsPatch(
            embedding_api_base_url=base,
            rag_enabled=True,
            rag_embedding_model=model,
        )
    )
    invalidate_operator_settings_cache()
    clear_embedding_health_cache()
    invalidate_model_catalog_cache()

    dim_result: dict[str, Any] = {}
    try:
        dim = probe_embedding_output_dim(model_id=model)
        apply_operator_settings_patch(OperatorSettingsPatch(rag_embedding_dim=dim))
        dim_result["embedding_dim"] = dim
    except Exception as exc:
        logger.warning("setup: ollama embedding probe failed: %s", exc)
        dim_result["dim_probe_error"] = str(exc)[:200]

    emb = enrich_setup_embedding_meta(
        embedding_catalog_health(force_refresh=True),
        [],
    )
    return {
        "ok": True,
        "embedding_api_base_url": base,
        "rag_embedding_model": model,
        "embedding": emb,
        **dim_result,
    }


def apply_setup_skip_suggestions() -> dict[str, Any]:
    """Apply catalog suggestions when the user skips step 2 (best-effort)."""
    cat = build_setup_catalog()
    s = cat.get("suggestions") or {}
    pid = str(s.get("primary_provider_id") or "").strip()
    if not pid or not cat.get("any_chat_reachable"):
        return {"ok": True, "saved": False, "skipped": True}
    return {
        **apply_setup_preferences(
            SetupPreferencesBody(
                primary_provider_id=pid,
                model_agent=s.get("model_agent"),
                model_coding=s.get("model_coding"),
                model_default=s.get("model_default"),
                rag_embedding_model=s.get("rag_embedding_model"),
            )
        ),
        "skipped": True,
    }


async def test_embedding_model(model_id: str) -> dict[str, Any]:
    mid = (model_id or "").strip()
    if not mid:
        raise HTTPException(status_code=400, detail="Embedding-Modell-ID fehlt.")
    emb = embedding_catalog_health(force_refresh=True)
    if not emb.get("configured"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Embedding-API nicht konfiguriert. "
                "EMBEDDING_BASE_URL in .env oder „Ollama für Embeddings“ im Setup."
            ),
        )
    try:
        dim = probe_embedding_output_dim(model_id=mid)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:500]) from exc
    return {"ok": True, "model": mid, "embedding_dim": dim, "reachable": True}
