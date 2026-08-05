"""Operator-owned generation check for already-bound MCP capabilities."""

from __future__ import annotations

import hashlib
import json

from deerflow.config.extensions_config import ExtensionsConfig, McpServerConfig


class McpCapabilityRevokedError(RuntimeError):
    """Raised when a bound MCP tool no longer matches current operator config."""


def server_capability_digest(config: McpServerConfig) -> str:
    """Return a deterministic, non-reversible generation for one server config."""
    payload = json.dumps(
        config.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def require_active_server_capability(server_name: str, expected_digest: str) -> None:
    """Fail closed unless the named server remains enabled and byte-equivalent."""
    try:
        extensions = ExtensionsConfig.from_file()
    except Exception as exc:
        raise McpCapabilityRevokedError("MCP capability configuration is unavailable") from exc

    server = extensions.mcp_servers.get(server_name)
    if not isinstance(server, McpServerConfig) or not server.enabled:
        raise McpCapabilityRevokedError("MCP capability is disabled or missing")
    if server_capability_digest(server) != expected_digest:
        raise McpCapabilityRevokedError("MCP capability generation changed")
