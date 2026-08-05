"""Tests for MCP routing metadata tags."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from deerflow.config.extensions_config import ExtensionsConfig
from deerflow.tools.mcp_metadata import MCP_TOOL_METADATA_KEY, MCP_TOOL_ROUTING_METADATA_KEY, get_mcp_routing, tag_mcp_routing, tag_mcp_tool
from deerflow.tools.result_policy import (
    RESULT_POLICY_METADATA_KEY,
    get_tool_result_policy,
)

_EVIDENCE_POLICY = {
    "trust": "untrusted_external",
    "semantic_class": "evidence",
    "outcome_contract": "ip-evidence-operation-status-v1",
}


class _Args(BaseModel):
    query: str = Field(..., description="query")


def _tool(name: str = "postgres_query") -> StructuredTool:
    async def _call(query: str) -> str:
        return query

    return StructuredTool(
        name=name,
        description="Query internal data",
        args_schema=_Args,
        coroutine=_call,
    )


def test_tag_mcp_routing_preserves_existing_mcp_flag():
    tool = tag_mcp_tool(_tool())

    tagged = tag_mcp_routing(
        tool,
        {
            "mode": "prefer",
            "priority": 80,
            "keywords": ["订单"],
        },
    )

    assert tagged.metadata[MCP_TOOL_METADATA_KEY] is True
    assert tagged.metadata[MCP_TOOL_ROUTING_METADATA_KEY]["priority"] == 80
    assert get_mcp_routing(tagged)["keywords"] == ["订单"]


def test_get_mcp_routing_returns_none_for_non_mcp_tools():
    tool = tag_mcp_routing(
        _tool(),
        {
            "mode": "prefer",
            "priority": 80,
            "keywords": ["订单"],
        },
    )

    assert get_mcp_routing(tool) is None


def test_get_mcp_routing_returns_none_for_off_mode():
    tool = tag_mcp_tool(_tool())
    tag_mcp_routing(
        tool,
        {
            "mode": "off",
            "priority": 80,
            "keywords": ["订单"],
        },
    )

    assert get_mcp_routing(tool) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["http", "stdio"])
async def test_get_mcp_tools_tags_effective_routing_metadata(transport: str):
    from deerflow.mcp.tools import get_mcp_tools

    tool = _tool("postgres_query")
    extensions_config = ExtensionsConfig.model_validate(
        {
            "mcpServers": {
                "postgres": {
                    "type": transport,
                    "url": "http://localhost:8000/mcp",
                    "command": "npx",
                    "routing": {
                        "mode": "prefer",
                        "priority": 50,
                        "keywords": ["database"],
                    },
                    "result_policy": _EVIDENCE_POLICY,
                    "tools": {
                        "query": {
                            "routing": {
                                "priority": 100,
                                "keywords": ["查库"],
                            }
                        }
                    },
                }
            }
        }
    )

    with (
        patch("deerflow.mcp.tools.ExtensionsConfig.from_file", return_value=extensions_config),
        patch(
            "deerflow.mcp.tools.build_servers_config",
            return_value={"postgres": {"transport": transport, "url": "http://localhost:8000/mcp", "command": "npx"}},
        ),
        patch("deerflow.mcp.tools.get_initial_oauth_headers", return_value={}),
        patch("deerflow.mcp.tools.build_oauth_tool_interceptor", return_value=None),
        patch("langchain_mcp_adapters.client.MultiServerMCPClient") as MockClient,
    ):
        MockClient.return_value.get_tools = AsyncMock(return_value=[tool])
        tools = await get_mcp_tools()

    routing = get_mcp_routing(tools[0])
    assert routing is not None
    assert routing["priority"] == 100
    assert routing["keywords"] == ["查库"]
    assert get_tool_result_policy(tools[0]) == _EVIDENCE_POLICY


@pytest.mark.asyncio
async def test_get_mcp_tools_clears_remote_result_policy_claim_without_operator_config():
    from deerflow.mcp.tools import get_mcp_tools

    tool = _tool("remote_query")
    tool.metadata = {
        RESULT_POLICY_METADATA_KEY: dict(_EVIDENCE_POLICY),
        "remote_metadata": "preserved",
    }
    extensions_config = ExtensionsConfig.model_validate(
        {
            "mcpServers": {
                "remote": {
                    "type": "http",
                    "url": "http://localhost:8000/mcp",
                }
            }
        }
    )

    with (
        patch(
            "deerflow.mcp.tools.ExtensionsConfig.from_file",
            return_value=extensions_config,
        ),
        patch(
            "deerflow.mcp.tools.build_servers_config",
            return_value={
                "remote": {
                    "transport": "http",
                    "url": "http://localhost:8000/mcp",
                }
            },
        ),
        patch("deerflow.mcp.tools.get_initial_oauth_headers", return_value={}),
        patch("deerflow.mcp.tools.build_oauth_tool_interceptor", return_value=None),
        patch("langchain_mcp_adapters.client.MultiServerMCPClient") as MockClient,
    ):
        MockClient.return_value.get_tools = AsyncMock(return_value=[tool])
        tools = await get_mcp_tools()

    assert get_tool_result_policy(tools[0]) is None
    assert tools[0].metadata["remote_metadata"] == "preserved"
