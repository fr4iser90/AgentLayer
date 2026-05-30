"""Generic numbered EMBEDDING_PROVIDER_N_* env parsing."""

from __future__ import annotations

import os
from unittest.mock import patch

from apps.backend.infrastructure.embedding_env_providers import parse_embedding_env_providers


def test_numbered_embedding_providers() -> None:
    env = {
        "EMBEDDING_PROVIDER_1_BASE_URL": "https://embed-a/v1",
        "EMBEDDING_PROVIDER_1_LABEL": "Primary",
        "EMBEDDING_PROVIDER_2_BASE_URL": "https://embed-b/v1",
    }
    with patch.dict(os.environ, env, clear=False):
        rows = parse_embedding_env_providers()
    assert len(rows) == 2
    assert rows[0].provider_id == "embedding_provider_1"
    assert rows[1].provider_id == "embedding_provider_2"


def test_empty_when_no_providers() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert parse_embedding_env_providers() == []
