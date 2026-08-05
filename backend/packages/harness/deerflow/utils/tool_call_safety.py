"""Safe projections for malformed model tool calls."""

from __future__ import annotations

import re
from typing import Any

_SAFE_TOOL_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]{0,127}")
_SAFE_TOOL_CALL_ID = re.compile(r"[A-Za-z0-9_.:-]{1,256}")


def _safe_invalid_tool_call(value: Any) -> dict[str, Any]:
    call = value if isinstance(value, dict) else {}
    raw_name = call.get("name")
    name = raw_name if isinstance(raw_name, str) and _SAFE_TOOL_NAME.fullmatch(raw_name) else "unknown_tool"
    raw_id = call.get("id")
    call_id = raw_id if isinstance(raw_id, str) and _SAFE_TOOL_CALL_ID.fullmatch(raw_id) else None
    return {
        "type": "invalid_tool_call",
        "id": call_id,
        "name": name,
        "classification": "invalid_tool_arguments",
    }


def sanitize_invalid_tool_calls(value: Any) -> Any:
    """Recursively remove malformed arguments and provider parser details.

    Valid structured ``tool_calls`` are intentionally preserved. When an AI
    message has ``invalid_tool_calls``, its raw provider ``additional_kwargs``
    call view is only a duplicate serialization surface and is removed so it
    cannot retain the malformed argument string.
    """
    if isinstance(value, dict):
        sanitized = {key: sanitize_invalid_tool_calls(item) for key, item in value.items()}
        invalid_calls = value.get("invalid_tool_calls")
        if isinstance(invalid_calls, list) and invalid_calls:
            sanitized["invalid_tool_calls"] = [_safe_invalid_tool_call(call) for call in invalid_calls]
            additional_kwargs = sanitized.get("additional_kwargs")
            if isinstance(additional_kwargs, dict):
                additional_kwargs = dict(additional_kwargs)
                additional_kwargs.pop("tool_calls", None)
                additional_kwargs.pop("function_call", None)
                sanitized["additional_kwargs"] = additional_kwargs
        return sanitized
    if isinstance(value, list):
        return [sanitize_invalid_tool_calls(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_invalid_tool_calls(item) for item in value)
    return value
