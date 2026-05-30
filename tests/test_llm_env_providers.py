"""Generic numbered LLM_PROVIDER_N_* env parsing."""

from __future__ import annotations

import os
from unittest.mock import patch

from apps.backend.infrastructure.llm_env_providers import parse_llm_env_providers


def test_numbered_providers() -> None:
    env = {
        "LLM_PROVIDER_1_BASE_URL": "http://host-a:8080",
        "LLM_PROVIDER_1_LABEL": "Local",
        "LLM_PROVIDER_2_BASE_URL": "https://api.openai.com/v1",
        "LLM_PROVIDER_2_API_KEY": "sk-test",
    }
    with patch.dict(os.environ, env, clear=False):
        rows = parse_llm_env_providers()
    assert len(rows) == 2
    assert rows[0].provider_id == "provider_1"
    assert rows[0].label == "Local"
    assert rows[1].provider_id == "provider_2"
    assert rows[1].api_key == "sk-test"


def test_empty_when_no_providers() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert parse_llm_env_providers() == []
