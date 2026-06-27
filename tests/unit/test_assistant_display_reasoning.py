"""Client completion prep: reasoning extraction and thought-block split."""

from apps.backend.domain.agent_runtime.assistant_display import prepare_completion_assistant_for_client


def test_prepare_completion_extracts_thought_blocks_and_reasoning_fields():
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Answer here.\n\n[Thought]\nI should check the file first.\n\nMore answer.",
                    "thinking": "provider thinking",
                }
            }
        ]
    }
    out = prepare_completion_assistant_for_client(data)
    msg = out["choices"][0]["message"]
    assert "[Thought]" not in msg["content"]
    assert "Answer here." in msg["content"]
    assert "More answer." in msg["content"]
    assert "provider thinking" in msg["reasoning_content"]
    assert "I should check the file first." in msg["reasoning_content"]
    assert "thinking" not in msg
