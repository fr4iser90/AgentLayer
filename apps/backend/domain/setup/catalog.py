"""Setup wizard: provider reachability, chat vs embedding models, default profile picks."""

from __future__ import annotations

import logging
from typing import Any, Literal, Protocol

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

ModelKind = Literal["chat", "embedding", "unknown"]

_CHAT_HINTS = ("gpt-", "gpt4", "claude", "llama", "mistral", "qwen", "nemotron", "deepseek", "gemma")
_EMBED_HINTS = ("embed", "nomic-embed", "bge", "e5", "minilm", "gte", "sentence")


class SetupCatalogDependencies(Protocol):
    def clear_embedding_health_cache(self) -> None: ...

    def embedding_catalog_health(self, *, force_refresh: bool = False) -> dict[str, Any]: ...

    def probe_embedding_output_dim(self, *, model_id: str) -> int: ...

    def pick_reachable_catalog_provider(self) -> str | None: ...

    def fetch_full_model_catalog(self) -> tuple[list[dict[str, Any]], dict[str, Any]]: ...

    def fetch_models_for_provider(self, spec: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]: ...

    def get_provider_spec(self, provider_id: str) -> Any | None: ...

    def list_provider_specs(self) -> list[Any]: ...

    def apply_operator_settings_patch(self, patch: dict[str, Any]) -> None: ...

    def invalidate_operator_settings_cache(self) -> None: ...

    def invalidate_model_catalog_cache(self) -> None: ...

    def normalize_external_llm_base_url(self, raw: str | None) -> str: ...

    def operator_provider_endpoints_sync(
        self, kind: str, rows: list[dict[str, Any]], *, delete_missing: bool = True
    ) -> None: ...

    def normalized_embedding_base(self) -> str: ...

    def setup_voice_summary(self) -> dict[str, Any]: ...

    def setup_external_runtime_summary(self) -> dict[str, Any]: ...

    def operator_provider_endpoints_list_all(self, kind: str) -> list[dict[str, Any]]: ...

    def parse_db_catalog_provider_id(self, provider_id: str) -> int | None: ...

    def provider_endpoint_dedupe_key(self, base_url: str | None) -> str: ...

    def collapse_duplicate_operator_provider_endpoints(self, kind: str) -> int: ...

    def upsert_operator_provider_endpoint_by_base_url(
        self,
        kind: str,
        *,
        label: str,
        base_url: str,
        api_key: str,
        api_header_name: str = "Authorization",
        model_default: str | None = None,
        preserve_existing_model: bool = True,
        max_parallel: int | None = None,
        options_json: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]: ...


_deps: SetupCatalogDependencies | None = None


def register_setup_catalog_dependencies(deps: SetupCatalogDependencies) -> None:
    global _deps
    _deps = deps


def _require_deps() -> SetupCatalogDependencies:
    if _deps is None:
        raise RuntimeError("setup catalog dependencies not registered")
    return _deps


def clear_embedding_health_cache() -> None:
    _require_deps().clear_embedding_health_cache()


def embedding_catalog_health(*, force_refresh: bool = False) -> dict[str, Any]:
    return _require_deps().embedding_catalog_health(force_refresh=force_refresh)


def probe_embedding_output_dim(*, model_id: str) -> int:
    return _require_deps().probe_embedding_output_dim(model_id=model_id)


def pick_reachable_catalog_provider() -> str | None:
    return _require_deps().pick_reachable_catalog_provider()


def fetch_full_model_catalog() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return _require_deps().fetch_full_model_catalog()


def fetch_models_for_provider(spec: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return _require_deps().fetch_models_for_provider(spec)


def get_provider_spec(provider_id: str) -> Any | None:
    return _require_deps().get_provider_spec(provider_id)


def list_provider_specs() -> list[Any]:
    return _require_deps().list_provider_specs()


def apply_operator_settings_patch(patch: dict[str, Any]) -> None:
    _require_deps().apply_operator_settings_patch(patch)


def invalidate_operator_settings_cache() -> None:
    _require_deps().invalidate_operator_settings_cache()


def invalidate_model_catalog_cache() -> None:
    _require_deps().invalidate_model_catalog_cache()


def normalize_external_llm_base_url(raw: str | None) -> str:
    return _require_deps().normalize_external_llm_base_url(raw)


def operator_provider_endpoints_sync(
    kind: str, rows: list[dict[str, Any]], *, delete_missing: bool = True
) -> None:
    _require_deps().operator_provider_endpoints_sync(kind, rows, delete_missing=delete_missing)


def normalized_embedding_base() -> str:
    return _require_deps().normalized_embedding_base()


def _setup_voice_summary() -> dict[str, Any]:
    return _require_deps().setup_voice_summary()


def _setup_external_runtime_summary() -> dict[str, Any]:
    return _require_deps().setup_external_runtime_summary()


def rank_embedding_model_ids(model_ids: list[str]) -> list[str]:
    """Sort provider model ids: embedding-like first, obvious chat models last."""

    def score(mid: str) -> tuple[int, str]:
        low = mid.lower()
        s = 0
        if "embed" in low:
            s -= 20
        if any(h in low for h in _EMBED_HINTS):
            s -= 10
        if any(h in low for h in _CHAT_HINTS):
            s += 15
        return (s, mid)

    return sorted({m.strip() for m in model_ids if m.strip()}, key=score)


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


def chat_provider_embedding_base_url() -> str | None:
    """OpenAI-compat host prefix when a chat provider also exposes /v1/embeddings."""
    spec = get_provider_spec("provider_1")
    raw = (spec.base_url if spec else "") or ""
    if not raw.strip():
        return None
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
        local = next(
            (
                p
                for p in providers
                if p.get("reachable") and (p.get("embedding_models") or str(p.get("provider_id", "")).startswith("provider_"))
            ),
            None,
        )
        base = chat_provider_embedding_base_url() if local else None
        embed_models = list(local.get("embedding_models") or []) if local else []
        ranked = rank_embedding_model_ids(embed_models)
        out["chat_embed_opt_in"] = {
            "available": bool(local and base),
            "suggested_base_url": base,
            "suggested_model": ranked[0] if ranked else None,
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
    voice = _setup_voice_summary()
    external_runtimes = _setup_external_runtime_summary()
    return {
        "providers": providers_out,
        "embedding": embedding,
        "suggestions": suggestions,
        "any_chat_reachable": any_chat,
        "voice": voice,
        "external_runtimes": external_runtimes,
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
    """
    Continue / preferences:

    - If chat endpoints already exist: never insert. Collapse URL twins, mark preferred primary.
    - If none exist yet: create exactly one from the reachable catalog provider.
    """
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

    deps = _require_deps()
    deps.collapse_duplicate_operator_provider_endpoints("chat")
    existing = list(deps.operator_provider_endpoints_list_all("chat"))
    target_key = deps.provider_endpoint_dedupe_key(getattr(spec, "base_url", "") or "")
    eid = deps.parse_db_catalog_provider_id(pid)

    def _pick_preferred(rows_in: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not rows_in:
            return None
        if eid is not None:
            hit = next((row for row in rows_in if int(row.get("id") or 0) == int(eid)), None)
            if hit is not None:
                return hit
        if target_key:
            hit = next(
                (
                    row
                    for row in rows_in
                    if deps.provider_endpoint_dedupe_key(row.get("base_url")) == target_key
                ),
                None,
            )
            if hit is not None:
                return hit
        return min(
            rows_in,
            key=lambda row: (int(row.get("sort_order") or 0), int(row.get("id") or 0)),
        )

    preferred = _pick_preferred(existing)
    explicit_model = (str(body.model_default).strip() if body.model_default else "") or None
    ranked = rank_chat_model_ids([str(r.get("id") or "") for r in rows if r.get("id")])
    first = ranked[0] if ranked else None
    md: str | None

    if existing:
        # Already configured — Continue must not add another row (same host or otherwise).
        md = (
            explicit_model
            or (str(preferred.get("model_default") or "").strip() if preferred else "")
            or first
        )
    else:
        # First-time Continue with no DB endpoints yet: create exactly one.
        md = explicit_model or first
        key = spec.api_key if spec.api_key else "-"
        preferred = deps.upsert_operator_provider_endpoint_by_base_url(
            "chat",
            label=str(getattr(spec, "label", None) or pid),
            base_url=str(getattr(spec, "base_url", "") or ""),
            api_key=key,
            api_header_name=str(getattr(spec, "api_header_name", None) or "Authorization"),
            model_default=md,
            preserve_existing_model=False,
        )

    refreshed = list(deps.operator_provider_endpoints_list_all("chat"))
    # Collapse again in case twin rows existed before this request.
    deps.collapse_duplicate_operator_provider_endpoints("chat")
    refreshed = list(deps.operator_provider_endpoints_list_all("chat"))
    preferred = _pick_preferred(refreshed) or preferred
    if preferred is None:
        raise HTTPException(status_code=400, detail="Kein Chat-Endpunkt nach Continue vorhanden.")

    preferred_id = int(preferred.get("id") or 0)
    if preferred_id >= 1 and len(refreshed) >= 1:
        ordered: list[dict[str, Any]] = []
        ordered.append({**dict(preferred), "sort_order": 0})
        n = 1
        for row in refreshed:
            if int(row.get("id") or 0) == preferred_id:
                continue
            ordered.append({**dict(row), "sort_order": n})
            n += 1
        operator_provider_endpoints_sync("chat", ordered, delete_missing=False)

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
        patch: dict[str, Any] = {"rag_embedding_model": rag_model}
        try:
            dim = probe_embedding_output_dim(model_id=rag_model)
            patch["rag_embedding_dim"] = dim
            rag_result["embedding_dim"] = dim
        except Exception as exc:
            logger.warning("setup: embedding dim probe failed: %s", exc)
            rag_result["dim_probe_error"] = str(exc)[:200]
        apply_operator_settings_patch(patch)
        rag_result["updated"] = True
    elif not rag_model:
        if not normalized_embedding_base():
            apply_operator_settings_patch({"rag_enabled": False})
            rag_result["rag_disabled"] = True

    return {
        "ok": True,
        "primary_provider_id": pid,
        "model_default": md,
        "rag_embedding_model": rag_model,
        "rag": rag_result,
    }


def apply_enable_chat_provider_embedding() -> dict[str, Any]:
    """Opt-in: use first chat provider host for embeddings when it exposes embed models."""
    base = chat_provider_embedding_base_url()
    if not base:
        raise HTTPException(
            status_code=400,
            detail="Kein LLM-Provider konfiguriert (LLM_PROVIDER_1_BASE_URL oder Admin-Endpoint).",
        )
    spec = get_provider_spec("provider_1")
    if spec is not None:
        _, ometa = fetch_models_for_provider(spec)
        if not ometa.get("reachable"):
            raise HTTPException(
                status_code=400,
                detail="Chat-Provider provider_1 ist nicht erreichbar.",
            )
    pid = spec.provider_id if spec is not None else "provider_1"
    merged, _ = fetch_full_model_catalog()
    _, embed_models, _ = _models_for_provider(merged, pid)
    ranked = rank_embedding_model_ids(embed_models)
    model = ranked[0] if ranked else ""
    if not model:
        raise HTTPException(
            status_code=400,
            detail="Kein Embedding-Modell auf dem Chat-Provider. Nutze EMBEDDING_PROVIDER_1_* oder Admin → Memory & RAG.",
        )

    apply_operator_settings_patch(
        {
            "embedding_api_base_url": base,
            "rag_enabled": True,
            "rag_embedding_model": model,
        }
    )
    invalidate_operator_settings_cache()
    clear_embedding_health_cache()
    invalidate_model_catalog_cache()

    dim_result: dict[str, Any] = {}
    try:
        dim = probe_embedding_output_dim(model_id=model)
        apply_operator_settings_patch({"rag_embedding_dim": dim})
        dim_result["embedding_dim"] = dim
    except Exception as exc:
        logger.warning("setup: chat provider embedding probe failed: %s", exc)
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
            "EMBEDDING_PROVIDER_N_* in .env or Admin → Memory & RAG."
            ),
        )
    try:
        dim = probe_embedding_output_dim(model_id=mid)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:500]) from exc
    return {"ok": True, "model": mid, "embedding_dim": dim, "reachable": True}
