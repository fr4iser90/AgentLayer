"""Tool step label (plugin ``tool_step_detail`` hooks)."""

from apps.backend.domain.tool_step_label import format_tool_step_label_from_args


def test_coding_bash_step_detail_from_registry() -> None:
    from apps.backend.domain.plugin_system.registry import get_registry

    reg = get_registry()
    detail = reg.tool_step_detail_for(
        "bash",
        {"command": "git diff plugins/foo.py"},
    )
    assert "git diff" in detail
    label = format_tool_step_label_from_args(
        "bash",
        {"command": "git diff plugins/foo.py"},
        tool_label="Coding: Bash",
    )
    assert label == "Coding: Bash git diff plugins/foo.py"
