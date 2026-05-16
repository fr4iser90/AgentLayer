"""Deterministic tool transcript recap merged into final completion."""

import json

from apps.backend.domain.agent import (
    _build_client_tool_context_markdown,
    _build_tool_transcript_recap,
    _merge_deterministic_tool_recap_into_final_completion,
    _summarize_tool_json_body,
)


def test_build_tool_transcript_recap_maps_names_and_summarizes_json():
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "coding_bash", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": json.dumps(
                {"ok": True, "output": "hello world", "operation": "run"}
            ),
        },
    ]
    recap = _build_tool_transcript_recap(messages)
    assert "coding_bash" in recap
    assert "hello world" in recap
    assert "ok=True" in recap or "ok=true" in recap.lower()


def test_merge_on_terminal_exit_prefixes_content():
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "x",
                    "type": "function",
                    "function": {"name": "coding_glob", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "x",
            "content": json.dumps({"ok": False, "error": "missing pattern"}),
        },
    ]
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Done.",
                }
            }
        ]
    }
    ok_early = _merge_deterministic_tool_recap_into_final_completion(
        data, messages, plain_completion=False
    )
    assert ok_early
    merged_early = data["choices"][0]["message"]["content"]
    assert "Tool transcript" in merged_early
    assert "coding_glob" in merged_early

    data["choices"][0]["message"]["content"] = "Done."
    ok = _merge_deterministic_tool_recap_into_final_completion(
        data, messages, plain_completion=False
    )
    assert ok
    merged = data["choices"][0]["message"]["content"]
    assert "Tool transcript" in merged
    assert "coding_glob" in merged
    assert "missing pattern" in merged
    assert "### Model reply" in merged
    assert merged.endswith("Done.")


def test_recap_includes_glob_files_list_dir_entries_and_tool_args():
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "g1",
                    "type": "function",
                    "function": {
                        "name": "coding_glob",
                        "arguments": json.dumps(
                            {"pattern": "**/*.py", "path": "src"}
                        ),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "g1",
            "content": json.dumps(
                {
                    "ok": True,
                    "pattern": "**/*.py",
                    "path": "src",
                    "files": ["a.py", "b.py"],
                    "count": 2,
                }
            ),
        },
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "l1",
                    "type": "function",
                    "function": {
                        "name": "coding_list_dir",
                        "arguments": json.dumps({"path": "src"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "l1",
            "content": json.dumps(
                {
                    "ok": True,
                    "path": "src",
                    "entries": [
                        {"name": "a.py", "path": "src/a.py", "is_dir": False},
                        {"name": "lib", "path": "src/lib", "is_dir": True},
                    ],
                    "truncated": False,
                }
            ),
        },
    ]
    recap = _build_tool_transcript_recap(messages)
    assert "**Tool args:**" in recap
    assert "pattern=**/*.py" in recap
    assert "files (2):" in recap
    assert "a.py" in recap and "b.py" in recap
    assert "listing:" in recap
    assert "src/lib/" in recap or "lib/" in recap


def test_client_tool_context_includes_llm_rounds_digest_before_transcript():
    messages = [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "a",
                    "type": "function",
                    "function": {"name": "coding_glob", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "a", "content": '{"ok": false, "error": "need pattern"}'},
    ]
    ctx = _build_client_tool_context_markdown(messages)
    assert "## LLM tool rounds" in ctx
    assert "### Round 1" in ctx
    assert "`coding_glob`" in ctx
    assert "## Tool transcript" in ctx
    assert "### 1." in ctx


def test_summarize_includes_dedupe_server_message():
    raw = json.dumps(
        {
            "ok": True,
            "deduplicated": True,
            "message": (
                "Identical tool+arguments were already run earlier in this reply. "
                "Use the previous tool message in the transcript and continue (no repeat calls)."
            ),
        },
        ensure_ascii=False,
    )
    s = _summarize_tool_json_body(raw, max_body=4000)
    assert "deduplicated=true" in s
    assert "server_note:" in s
    assert "skipped" in s.lower()
    assert "no repeat calls" not in s


def test_recap_tool_args_empty_glob_shows_pattern_missing_and_list_dir_default_path():
    messages = [
        {"role": "user", "content": "Filter sidebar by workspace."},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "g0",
                    "type": "function",
                    "function": {"name": "coding_glob", "arguments": "{}"},
                },
                {
                    "id": "l0",
                    "type": "function",
                    "function": {"name": "coding_list_dir", "arguments": "{}"},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "g0", "content": '{"ok": false, "error": "pattern is required"}'},
        {"role": "tool", "tool_call_id": "l0", "content": '{"ok": true, "path": ".", "entries": []}'},
    ]
    recap = _build_tool_transcript_recap(messages)
    assert "pattern=" in recap
    assert "path=." in recap
