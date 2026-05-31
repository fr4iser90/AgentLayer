from apps.backend.api.main import merge_model_catalog_rows


def test_merge_keeps_same_id_on_different_providers() -> None:
    provider_1 = [{"id": "Qwen.gguf", "object": "model", "owned_by": "provider_1"}]
    llama = [{"id": "Qwen.gguf", "object": "model", "owned_by": "llama_cpp"}]
    out = merge_model_catalog_rows(provider_1, llama)
    assert len(out) == 2
    by = {(r["owned_by"], r["id"]) for r in out}
    assert by == {("provider_1", "Qwen.gguf"), ("llama_cpp", "Qwen.gguf")}


def test_merge_keeps_distinct_ids_from_both() -> None:
    provider_1 = [{"id": "a", "owned_by": "provider_1"}]
    llama = [{"id": "b", "owned_by": "llama_cpp"}]
    out = merge_model_catalog_rows(provider_1, llama)
    assert len(out) == 2
    by = {r["id"]: r["owned_by"] for r in out}
    assert by == {"a": "provider_1", "b": "llama_cpp"}


def test_merge_dedupes_identical_owned_by_and_id() -> None:
    a = [{"id": "m", "owned_by": "provider_1"}]
    b = [{"id": "m", "owned_by": "provider_1"}]
    out = merge_model_catalog_rows(a, b)
    assert len(out) == 1
