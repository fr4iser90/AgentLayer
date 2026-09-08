from apps.backend.infrastructure.settings.operator_settings import (
    external_chat_completions_url,
    external_models_list_url,
    gateway_models_kinds_for_provider_kind,
    normalize_external_llm_base_url,
)


def test_normalize_strips_trailing_v1_prefix() -> None:
    assert normalize_external_llm_base_url("https://llm.example.com/v1") == "https://llm.example.com"


def test_models_url_no_double_v1() -> None:
    bu = "https://llm.example.com/v1"
    assert external_models_list_url(bu) == "https://llm.example.com/v1/models"


def test_models_url_with_kinds_filter() -> None:
    bu = "https://llm.example.com/v1"
    assert external_models_list_url(bu, kinds="chat") == "https://llm.example.com/v1/models?kinds=chat"
    assert external_models_list_url(bu, kinds="embed") == "https://llm.example.com/v1/models?kinds=embed"
    assert external_models_list_url(bu, kinds="  ") == "https://llm.example.com/v1/models"


def test_gateway_models_kinds_for_provider_kind() -> None:
    assert gateway_models_kinds_for_provider_kind("chat") == "chat"
    assert gateway_models_kinds_for_provider_kind("embedding") == "embed"
    assert gateway_models_kinds_for_provider_kind("extractor") == "extractor"
    assert gateway_models_kinds_for_provider_kind("voice_stt") == "stt"
    assert gateway_models_kinds_for_provider_kind("voice_tts") == "tts"
    assert gateway_models_kinds_for_provider_kind("unknown") is None


def test_chat_url_no_double_v1() -> None:
    bu = "https://llm.example.com/v1"
    assert external_chat_completions_url(bu) == "https://llm.example.com/v1/chat/completions"
