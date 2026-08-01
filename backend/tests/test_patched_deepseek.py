"""Tests for deerflow.models.patched_deepseek.PatchedChatDeepSeek.

Covers:
- LangChain serialization protocol: is_lc_serializable, lc_secrets, to_json
- reasoning_content restoration in _get_request_payload (single and multi-turn)
- Non-ASCII preservation in list-valued tool results
- Positional fallback when message counts differ
- No-op when no reasoning_content present
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _make_model(**kwargs):
    from deerflow.models.patched_deepseek import PatchedChatDeepSeek

    return PatchedChatDeepSeek(
        model="deepseek-v4-pro",
        api_key="test-key",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Serialization protocol
# ---------------------------------------------------------------------------


def test_is_lc_serializable_returns_true():
    from deerflow.models.patched_deepseek import PatchedChatDeepSeek

    assert PatchedChatDeepSeek.is_lc_serializable() is True


def test_lc_secrets_contains_api_key_mapping():
    model = _make_model()
    secrets = model.lc_secrets
    assert "api_key" in secrets
    assert secrets["api_key"] == "DEEPSEEK_API_KEY"
    assert "openai_api_key" in secrets


def test_to_json_produces_constructor_type():
    model = _make_model()
    result = model.to_json()
    assert result["type"] == "constructor"
    assert "kwargs" in result


def test_to_json_kwargs_contains_model():
    model = _make_model()
    result = model.to_json()
    assert result["kwargs"]["model_name"] == "deepseek-v4-pro"
    assert result["kwargs"]["api_base"] == "https://api.deepseek.com/v1"


def test_to_json_kwargs_contains_custom_api_base():
    model = _make_model(api_base="https://ark.cn-beijing.volces.com/api/v3")
    result = model.to_json()
    assert result["kwargs"]["api_base"] == "https://ark.cn-beijing.volces.com/api/v3"


def test_to_json_api_key_is_masked():
    """api_key must not appear as plain text in the serialized output."""
    model = _make_model()
    result = model.to_json()
    api_key_value = result["kwargs"].get("api_key") or result["kwargs"].get("openai_api_key")
    assert api_key_value is None or isinstance(api_key_value, dict), f"API key must not be plain text, got: {api_key_value!r}"


# ---------------------------------------------------------------------------
# reasoning_content preservation in _get_request_payload
# ---------------------------------------------------------------------------


def _make_payload_message(role: str, content: str | None = None, tool_calls: list | None = None) -> dict:
    msg: dict = {"role": role, "content": content}
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return msg


def test_reasoning_content_injected_into_assistant_message():
    """reasoning_content from additional_kwargs is restored in the payload."""
    model = _make_model()

    human = HumanMessage(content="What is 2+2?")
    ai = AIMessage(
        content="4",
        additional_kwargs={"reasoning_content": "Let me think: 2+2=4"},
    )

    base_payload = {
        "messages": [
            _make_payload_message("user", "What is 2+2?"),
            _make_payload_message("assistant", "4"),
        ]
    }

    with patch.object(type(model).__bases__[0], "_get_request_payload", return_value=base_payload):
        with patch.object(model, "_convert_input") as mock_convert:
            mock_convert.return_value = MagicMock(to_messages=lambda: [human, ai])
            payload = model._get_request_payload([human, ai])

    assistant_msg = next(m for m in payload["messages"] if m["role"] == "assistant")
    assert assistant_msg["reasoning_content"] == "Let me think: 2+2=4"


def test_no_reasoning_content_is_noop():
    """Messages without reasoning_content are left unchanged."""
    model = _make_model()

    human = HumanMessage(content="hello")
    ai = AIMessage(content="hi", additional_kwargs={})

    base_payload = {
        "messages": [
            _make_payload_message("user", "hello"),
            _make_payload_message("assistant", "hi"),
        ]
    }

    with patch.object(type(model).__bases__[0], "_get_request_payload", return_value=base_payload):
        with patch.object(model, "_convert_input") as mock_convert:
            mock_convert.return_value = MagicMock(to_messages=lambda: [human, ai])
            payload = model._get_request_payload([human, ai])

    assistant_msg = next(m for m in payload["messages"] if m["role"] == "assistant")
    assert "reasoning_content" not in assistant_msg


def test_reasoning_content_multi_turn():
    """All assistant turns each get their own reasoning_content."""
    model = _make_model()

    human1 = HumanMessage(content="Step 1?")
    ai1 = AIMessage(content="A1", additional_kwargs={"reasoning_content": "Thought1"})
    human2 = HumanMessage(content="Step 2?")
    ai2 = AIMessage(content="A2", additional_kwargs={"reasoning_content": "Thought2"})

    base_payload = {
        "messages": [
            _make_payload_message("user", "Step 1?"),
            _make_payload_message("assistant", "A1"),
            _make_payload_message("user", "Step 2?"),
            _make_payload_message("assistant", "A2"),
        ]
    }

    with patch.object(type(model).__bases__[0], "_get_request_payload", return_value=base_payload):
        with patch.object(model, "_convert_input") as mock_convert:
            mock_convert.return_value = MagicMock(to_messages=lambda: [human1, ai1, human2, ai2])
            payload = model._get_request_payload([human1, ai1, human2, ai2])

    assistant_msgs = [m for m in payload["messages"] if m["role"] == "assistant"]
    assert assistant_msgs[0]["reasoning_content"] == "Thought1"
    assert assistant_msgs[1]["reasoning_content"] == "Thought2"


def test_positional_fallback_when_count_differs():
    """Falls back to positional matching when payload/original message counts differ."""
    model = _make_model()

    human = HumanMessage(content="hi")
    ai = AIMessage(content="hello", additional_kwargs={"reasoning_content": "My reasoning"})

    # Simulate count mismatch: payload has 3 messages, original has 2
    extra_system = _make_payload_message("system", "You are helpful.")
    base_payload = {
        "messages": [
            extra_system,
            _make_payload_message("user", "hi"),
            _make_payload_message("assistant", "hello"),
        ]
    }

    with patch.object(type(model).__bases__[0], "_get_request_payload", return_value=base_payload):
        with patch.object(model, "_convert_input") as mock_convert:
            mock_convert.return_value = MagicMock(to_messages=lambda: [human, ai])
            payload = model._get_request_payload([human, ai])

    assistant_msg = next(m for m in payload["messages"] if m["role"] == "assistant")
    assert assistant_msg["reasoning_content"] == "My reasoning"


# ---------------------------------------------------------------------------
# Non-ASCII preservation in list-valued tool results
# ---------------------------------------------------------------------------


def test_list_tool_content_preserves_literal_unicode():
    model = _make_model(api_base="https://ark.cn-beijing.volces.com/api/v3")
    human = HumanMessage(content="Inspect the account")
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "collect_account",
                "args": {},
                "id": "call-account",
                "type": "tool_call",
            }
        ],
    )
    content = [
        {
            "type": "text",
            "text": '{"display_name":"云沐荟足道官方号"}',
        }
    ]
    tool = ToolMessage(content=content, tool_call_id="call-account")

    payload = model._get_request_payload([human, ai, tool])
    tool_payload = next(message for message in payload["messages"] if message["role"] == "tool")

    assert tool_payload["content"] == content[0]["text"]
    assert "\\u4e91\\u6c90\\u835f" not in tool_payload["content"].lower()


def test_multi_block_tool_content_preserves_structure_and_literal_unicode():
    model = _make_model()
    content = [
        {"type": "text", "text": "账号：云沐荟"},
        {"type": "image", "url": "/mnt/user-data/contact-sheet.jpg"},
    ]
    tool = ToolMessage(content=content, tool_call_id="call-video")

    payload = model._get_request_payload([tool])

    assert "账号：云沐荟" in payload["messages"][0]["content"]
    assert "\\u4e91\\u6c90\\u835f" not in payload["messages"][0]["content"].lower()
    blocks = json.loads(payload["messages"][0]["content"])
    assert blocks[0] == content[0]
    assert blocks[1]["type"] == "image_url"
    assert blocks[1]["image_url"]["url"] == content[1]["url"]


def test_single_text_block_with_metadata_keeps_its_structure():
    model = _make_model()
    content = [
        {
            "type": "text",
            "text": "账号：云沐荟",
            "annotations": [{"source": "public-profile"}],
        }
    ]
    tool = ToolMessage(content=content, tool_call_id="call-account")
    base_payload = {
        "messages": [
            {
                "role": "tool",
                "content": json.dumps(content),
                "tool_call_id": "call-account",
            }
        ]
    }

    with patch.object(type(model).__bases__[0], "_get_request_payload", return_value=base_payload):
        with patch.object(model, "_convert_input") as mock_convert:
            mock_convert.return_value = MagicMock(to_messages=lambda: [tool])
            payload = model._get_request_payload([tool])

    assert "账号：云沐荟" in payload["messages"][0]["content"]
    assert "\\u4e91\\u6c90\\u835f" not in payload["messages"][0]["content"].lower()
    assert json.loads(payload["messages"][0]["content"]) == content


def test_plain_string_tool_content_is_unchanged():
    model = _make_model()
    tool = ToolMessage(content="云沐荟足道官方号", tool_call_id="call-account")

    payload = model._get_request_payload([tool])

    assert payload["messages"][0]["content"] == "云沐荟足道官方号"


def test_list_tool_content_matches_by_tool_call_id_when_messages_are_injected():
    model = _make_model()
    first = ToolMessage(
        content=[{"type": "text", "text": "第一个工具：云沐荟"}],
        tool_call_id="call-first",
    )
    second = ToolMessage(
        content=[{"type": "text", "text": "第二个工具：黄金礼品"}],
        tool_call_id="call-second",
    )
    base_payload = {
        "messages": [
            _make_payload_message("system", "Injected system message"),
            {
                "role": "tool",
                "content": json.dumps(second.content),
                "tool_call_id": "call-second",
            },
            {
                "role": "tool",
                "content": json.dumps(first.content),
                "tool_call_id": "call-first",
            },
        ]
    }

    with patch.object(type(model).__bases__[0], "_get_request_payload", return_value=base_payload):
        with patch.object(model, "_convert_input") as mock_convert:
            mock_convert.return_value = MagicMock(to_messages=lambda: [first, second])
            payload = model._get_request_payload([first, second])

    tools_by_id = {message["tool_call_id"]: message["content"] for message in payload["messages"] if message["role"] == "tool"}
    assert "第一个工具：云沐荟" in tools_by_id["call-first"]
    assert "第二个工具：黄金礼品" in tools_by_id["call-second"]


def test_duplicate_tool_call_id_uses_matching_parent_content_after_trimming():
    model = _make_model()
    first = ToolMessage(
        content=[{"type": "text", "text": "第一条：云沐荟"}],
        tool_call_id="duplicate-call",
    )
    second = ToolMessage(
        content=[{"type": "text", "text": "第二条：黄金礼品"}],
        tool_call_id="duplicate-call",
    )
    base_payload = {
        "messages": [
            {
                "role": "tool",
                "content": json.dumps(second.content),
                "tool_call_id": "duplicate-call",
            }
        ]
    }

    with patch.object(type(model).__bases__[0], "_get_request_payload", return_value=base_payload):
        with patch.object(model, "_convert_input") as mock_convert:
            mock_convert.return_value = MagicMock(to_messages=lambda: [first, second])
            payload = model._get_request_payload([first, second])

    assert "第二条：黄金礼品" in payload["messages"][0]["content"]
    assert "第一条：云沐荟" not in payload["messages"][0]["content"]


def test_modified_or_unknown_tool_payload_is_not_overwritten():
    model = _make_model()
    original = ToolMessage(
        content=[{"type": "text", "text": "云沐荟"}],
        tool_call_id="call-account",
    )
    base_payload = {
        "messages": [
            {
                "role": "tool",
                "content": "middleware-replaced-content",
                "tool_call_id": "call-account",
            },
            {
                "role": "tool",
                "content": json.dumps(original.content),
                "tool_call_id": "unknown-call",
            },
        ]
    }

    with patch.object(type(model).__bases__[0], "_get_request_payload", return_value=base_payload):
        with patch.object(model, "_convert_input") as mock_convert:
            mock_convert.return_value = MagicMock(to_messages=lambda: [original])
            payload = model._get_request_payload([original])

    assert payload["messages"][0]["content"] == "middleware-replaced-content"
    assert payload["messages"][1]["content"] == json.dumps(original.content)
