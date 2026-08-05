"""Bounded, credential-free preservation of MCP result metadata.

MCP content ``annotations`` and ``_meta`` are transport evidence, not model
instructions.  They are therefore retained in the ToolMessage artifact rather
than copied into provider-facing content blocks.  This module owns the small
loss contract for that conversion boundary.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from langchain_core.tools import ToolException

MCP_RESULT_METADATA_KEY = "mcp_metadata"
MCP_RESULT_METADATA_CONTRACT = "mcp-result-metadata-v1"
MCP_RESULT_METADATA_SANITIZATION = "credential-redacted-bounded-v1"
OPERATOR_PRIVATE_MCP_META_PREFIX = "ip_agent_operator_private_"

_MAX_DEPTH = 6
_MAX_MAPPING_ITEMS = 64
_MAX_SEQUENCE_ITEMS = 64
_MAX_KEY_CHARS = 128
_MAX_TEXT_CHARS = 2_000

_SECRET_FIELD = re.compile(
    r"(?:api[_-]?key|authorization|cookie|credential|password|passwd|profile[_-]?path|refresh[_-]?token|secret|session|signature|token)",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT = re.compile(r"(?i)\b(api[_-]?key|authorization|cookie|credential|password|passwd|refresh[_-]?token|secret|session|signature|token)\b\s*[:=]\s*[^\s,;&]+")
_AUTH_VALUE = re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_URL = re.compile(r"https?://[^\s<>'\"]+")


class McpToolResultError(ToolException):
    """Transport failure carrying only DeerFlow-sanitized MCP artifact data."""

    def __init__(self, message: str, *, artifact: dict[str, Any] | None) -> None:
        super().__init__(message)
        self.artifact = artifact


def is_operator_private_mcp_meta_key(value: object) -> bool:
    """Identify server-only MCP metadata before it reaches model or API state."""

    normalized = str(value or "").replace("\x00", " ").strip()
    return normalized.startswith(OPERATOR_PRIVATE_MCP_META_PREFIX)


def _sanitize_url(match: re.Match[str]) -> str:
    value = match.group(0)
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "[REDACTED_URL]"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _sanitize_text(value: object) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    text = _AUTH_VALUE.sub("[REDACTED]", text)
    text = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _URL.sub(_sanitize_url, text)
    return text[:_MAX_TEXT_CHARS]


def sanitize_mcp_metadata(value: Any, *, depth: int = 0) -> Any:
    """Return a bounded JSON-compatible copy with credential material removed."""
    if depth >= _MAX_DEPTH:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:_MAX_MAPPING_ITEMS]:
            if is_operator_private_mcp_meta_key(raw_key):
                continue
            key = _sanitize_text(raw_key)[:_MAX_KEY_CHARS]
            if not key or _SECRET_FIELD.search(key) or is_operator_private_mcp_meta_key(key):
                continue
            sanitized[key] = sanitize_mcp_metadata(raw_value, depth=depth + 1)
        return sanitized
    if isinstance(value, (list, tuple)):
        return [sanitize_mcp_metadata(item, depth=depth + 1) for item in value[:_MAX_SEQUENCE_ITEMS]]
    if isinstance(value, str):
        return _sanitize_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _sanitize_text(value)


def _model_dump(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    model_dump = getattr(value, "model_dump", None)
    if not callable(model_dump):
        return None
    dumped = model_dump(mode="json", exclude_none=True, by_alias=True)
    sanitized = sanitize_mcp_metadata(dumped)
    return sanitized if isinstance(sanitized, dict) and sanitized else None


def build_mcp_result_metadata(call_tool_result: Any) -> dict[str, Any] | None:
    """Build the artifact-only metadata envelope for one MCP tool result."""
    from mcp.types import EmbeddedResource, ResourceLink

    envelope: dict[str, Any] = {
        "contract_version": MCP_RESULT_METADATA_CONTRACT,
        "sanitization_policy": MCP_RESULT_METADATA_SANITIZATION,
    }

    result_meta = sanitize_mcp_metadata(getattr(call_tool_result, "meta", None))
    if isinstance(result_meta, dict) and result_meta:
        envelope["result_meta"] = result_meta

    content_metadata: list[dict[str, Any]] = []
    for index, item in enumerate(getattr(call_tool_result, "content", ())):
        entry: dict[str, Any] = {
            "index": index,
            "type": str(getattr(item, "type", type(item).__name__)),
        }
        annotations = _model_dump(getattr(item, "annotations", None))
        if annotations:
            entry["annotations"] = annotations
        item_meta = sanitize_mcp_metadata(getattr(item, "meta", None))
        if isinstance(item_meta, dict) and item_meta:
            entry["meta"] = item_meta

        if isinstance(item, ResourceLink):
            resource = {
                "name": _sanitize_text(item.name),
                "title": _sanitize_text(item.title) if item.title is not None else None,
                "description": _sanitize_text(item.description) if item.description is not None else None,
                "mime_type": _sanitize_text(item.mimeType) if item.mimeType is not None else None,
                "size": item.size,
            }
            entry["resource"] = {key: value for key, value in resource.items() if value is not None}
        elif isinstance(item, EmbeddedResource):
            resource_meta = sanitize_mcp_metadata(getattr(item.resource, "meta", None))
            if isinstance(resource_meta, dict) and resource_meta:
                entry["resource_meta"] = resource_meta

        if len(entry) > 2:
            content_metadata.append(entry)

    if content_metadata:
        envelope["content"] = content_metadata

    if len(envelope) == 2:
        return None
    return envelope
