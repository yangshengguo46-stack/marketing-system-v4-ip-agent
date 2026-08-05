"""MCP (Model Context Protocol) integration using langchain-mcp-adapters."""

from .cache import (
    get_cached_mcp_tools,
    initialize_mcp_tools,
    reset_mcp_tools_cache,
)
from .client import build_server_params, build_servers_config

__all__ = [
    "build_server_params",
    "build_servers_config",
    "get_mcp_tools",
    "initialize_mcp_tools",
    "get_cached_mcp_tools",
    "reset_mcp_tools_cache",
]


def __getattr__(name: str):
    """Keep the heavy MCP tool graph lazy during metadata-only imports."""

    if name == "get_mcp_tools":
        from .tools import get_mcp_tools

        return get_mcp_tools
    raise AttributeError(name)
