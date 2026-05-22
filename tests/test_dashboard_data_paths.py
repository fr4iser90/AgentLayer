"""Dashboard data path helpers."""

from apps.backend.dashboard.data_paths import apply_data_patches, get_path, set_path


def test_get_set_top_level() -> None:
    assert get_path({"a": 1}, "a") == 1
    assert set_path({}, "b", 2)["b"] == 2
