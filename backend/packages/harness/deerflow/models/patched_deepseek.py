"""Patched ChatDeepSeek request handling for multi-turn tool conversations.

This module provides a patched version of ChatDeepSeek that properly handles
reasoning_content when sending messages back to the API. The original implementation
stores reasoning_content in additional_kwargs but doesn't include it when making
subsequent API calls, which causes errors with APIs that require reasoning_content
on all assistant messages when thinking mode is enabled.

It also preserves the semantic text and non-ASCII characters in list-valued tool
results. ``ChatDeepSeek`` converts those lists to strings with ``json.dumps``
because the provider expects tool content to be a string. That adds an unnecessary
JSON envelope around a single MCP text block and escapes every non-ASCII character,
leaving compatible providers to reconstruct names and quotations from literal
``\\uXXXX`` sequences.
"""

import json
from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_deepseek import ChatDeepSeek

from deerflow.models.assistant_payload_replay import restore_assistant_payloads, restore_reasoning_content


def _restore_unicode_tool_contents(
    payload_messages: list[dict[str, Any]],
    original_messages: list[BaseMessage],
) -> None:
    """Serialize list-valued tool content without losing its source text.

    Match list-valued original messages by ``tool_call_id`` rather than position
    because middleware may inject or trim messages before model invocation. Parse
    the parent's current string instead of copying original content so any block
    normalization performed by the OpenAI adapter remains intact.

    A single MCP text block becomes its text directly. Mixed or multi-block
    content retains its structure as Unicode-preserving JSON.
    """

    list_tool_call_ids = {message.tool_call_id for message in original_messages if isinstance(message, ToolMessage) and isinstance(message.content, list) and isinstance(message.tool_call_id, str) and message.tool_call_id}

    for payload_message in payload_messages:
        if payload_message.get("role") != "tool":
            continue
        tool_call_id = payload_message.get("tool_call_id")
        content = payload_message.get("content")
        if not isinstance(tool_call_id, str) or not tool_call_id or not isinstance(content, str):
            continue
        if tool_call_id not in list_tool_call_ids:
            continue
        try:
            blocks = json.loads(content)
        except (TypeError, ValueError):
            continue
        if not isinstance(blocks, list):
            continue
        only_block = blocks[0] if len(blocks) == 1 else None
        if isinstance(only_block, dict) and set(only_block) <= {"type", "text"} and only_block.get("type") == "text" and isinstance(only_block.get("text"), str):
            payload_message["content"] = only_block["text"]
        else:
            payload_message["content"] = json.dumps(blocks, ensure_ascii=False)


class PatchedChatDeepSeek(ChatDeepSeek):
    """ChatDeepSeek with reasoning replay and lossless tool-result text.

    When using thinking/reasoning enabled models, the API expects reasoning_content
    to be present on ALL assistant messages in multi-turn conversations. This patched
    version ensures reasoning_content from additional_kwargs is included in the
    request payload.
    """

    @classmethod
    def is_lc_serializable(cls) -> bool:
        return True

    @property
    def lc_secrets(self) -> dict[str, str]:
        return {"api_key": "DEEPSEEK_API_KEY", "openai_api_key": "DEEPSEEK_API_KEY"}

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        """Get a request payload with provider-specific fields preserved.

        Overrides the parent method to restore reasoning content on assistant
        turns and literal non-ASCII text in list-valued tool results.
        """
        # Get the original messages before conversion
        original_messages = self._convert_input(input_).to_messages()

        # Call parent to get the base payload
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)

        restore_assistant_payloads(
            payload.get("messages", []),
            original_messages,
            restore_reasoning_content,
        )
        _restore_unicode_tool_contents(payload.get("messages", []), original_messages)

        return payload
