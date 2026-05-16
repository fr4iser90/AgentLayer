"""Align ``rag_embedding_dim`` in operator_settings with the live embedding API."""

from __future__ import annotations

import logging

from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.embedding_client import (
    _normalized_embedding_base,
    probe_embedding_output_dim,
)

logger = logging.getLogger(__name__)


def ensure_rag_embedding_dim_aligned(*, log_prefix: str = "rag_embedding_sync") -> bool:
    """
    If ``EMBEDDING_BASE_URL`` is configured and the probed vector width differs from
    ``operator_settings.rag_embedding_dim``, patch settings to match the API.

    Returns True when settings were updated.
    """
    if not _normalized_embedding_base():
        return False
    rs = operator_settings.rag_settings()
    if not rs.get("enabled"):
        return False
    model = (rs.get("embedding_model") or "").strip()
    if not model:
        return False
    want = int(rs.get("embedding_dim") or 0)
    try:
        actual = probe_embedding_output_dim(model_id=model)
    except Exception as e:
        logger.warning("%s: probe failed for model %r: %s", log_prefix, model, e)
        return False
    if actual == want:
        return False
    from apps.backend.infrastructure.operator_settings import OperatorSettingsPatch

    operator_settings.apply_operator_settings_patch(
        OperatorSettingsPatch(rag_embedding_dim=actual)
    )
    logger.warning(
        "%s: rag_embedding_dim %s -> %s (model %r); re-run ingest-docs if RAG was empty",
        log_prefix,
        want,
        actual,
        model,
    )
    return True
