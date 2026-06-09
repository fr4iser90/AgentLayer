from apps.backend.infrastructure.operator_settings import (
    external_chat_completions_url,
    external_models_list_url,
    normalize_external_llm_base_url,
)


def test_normalize_strips_trailing_v1_prefix() -> None:
    assert normalize_external_llm_base_url("https://llm.example.com/v1") == "https://llm.example.com"


def test_models_url_no_double_v1() -> None:
    bu = "https://llm.example.com/v1"
    assert external_models_list_url(bu) == "https://llm.example.com/v1/models"


def test_chat_url_no_double_v1() -> None:
    bu = "https://llm.example.com/v1"
    assert external_chat_completions_url(bu) == "https://llm.example.com/v1/chat/completions"
