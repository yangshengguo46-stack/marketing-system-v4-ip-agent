"""Cross-transport MCP result-fidelity regressions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import StructuredTool
from mcp.types import AudioContent, CallToolResult, TextContent
from pydantic import BaseModel, Field

from deerflow.config.extensions_config import ExtensionsConfig, McpServerConfig
from deerflow.mcp import tools as mcp_tools
from deerflow.mcp.tools import _convert_call_tool_result, get_mcp_tools


class _Args(BaseModel):
    query: str = Field(..., description="query")


def test_generic_converter_drops_operator_private_result_metadata() -> None:
    private_key = "ip_agent_operator_private_sealed_source_handoff"
    result = CallToolResult(
        content=[TextContent(type="text", text="safe evidence")],
        _meta={
            private_key: {"relative_ref": "outputs/private/source.mp4"},
            "trace_id": "safe-trace",
        },
    )

    content, artifact = _convert_call_tool_result(result)

    assert content[0]["text"] == "safe evidence"
    assert artifact["mcp_metadata"]["result_meta"] == {
        "trace_id": "safe-trace"
    }


@pytest.mark.asyncio
async def test_http_mcp_uses_the_same_raw_result_conversion_as_stdio() -> None:
    """HTTP/SSE may not fall back to the third-party lossy result converter."""
    discovered_tool = StructuredTool(
        name="remote_inspect",
        description="inspect",
        args_schema=_Args,
        coroutine=AsyncMock(side_effect=AssertionError("third-party converted coroutine must not run")),
        response_format="content_and_artifact",
    )
    extensions = ExtensionsConfig(
        mcp_servers={
            "remote": McpServerConfig(
                enabled=True,
                type="http",
                url="http://127.0.0.1:9123/mcp",
            )
        }
    )
    server_connection = {
        "transport": "http",
        "url": "http://127.0.0.1:9123/mcp",
    }
    raw_result = CallToolResult(
        content=[
            AudioContent(
                type="audio",
                data="QUJD",
                mimeType="audio/mpeg",
                _meta={"speaker": "A"},
            )
        ],
        _meta={"trace_id": "trace-http"},
        isError=False,
    )
    session = AsyncMock()
    session.initialize = AsyncMock()
    session.call_tool = AsyncMock(return_value=raw_result)
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("deerflow.mcp.tools.ExtensionsConfig.from_file", return_value=extensions),
        patch("deerflow.mcp.tools.build_servers_config", return_value={"remote": server_connection}),
        patch("deerflow.mcp.tools.get_initial_oauth_headers", new=AsyncMock(return_value={})),
        patch("deerflow.mcp.tools.build_oauth_tool_interceptor", return_value=None),
        patch("langchain_mcp_adapters.client.MultiServerMCPClient") as client_type,
        patch("langchain_mcp_adapters.sessions.create_session", return_value=session_context),
    ):
        client_type.return_value.get_tools = AsyncMock(return_value=[discovered_tool])
        tools = await get_mcp_tools()
        content, artifact = await tools[0].coroutine(query="evidence")

    assert content[0]["type"] == "audio"
    assert content[0]["base64"] == "QUJD"
    assert artifact == {
        "mcp_metadata": {
            "contract_version": "mcp-result-metadata-v1",
            "sanitization_policy": "credential-redacted-bounded-v1",
            "result_meta": {"trace_id": "trace-http"},
            "content": [
                {
                    "index": 0,
                    "type": "audio",
                    "meta": {"speaker": "A"},
                }
            ],
        }
    }
    session.initialize.assert_awaited_once()
    session.call_tool.assert_awaited_once_with("inspect", {"query": "evidence"})


@pytest.mark.asyncio
async def test_http_wrapper_preserves_interceptor_headers_without_pooling() -> None:
    discovered_tool = StructuredTool(
        name="remote_inspect",
        description="inspect",
        args_schema=_Args,
        coroutine=AsyncMock(),
        response_format="content_and_artifact",
    )
    session = AsyncMock()
    session.initialize = AsyncMock()
    session.call_tool = AsyncMock(
        return_value=CallToolResult(
            content=[TextContent(type="text", text="ok")],
            isError=False,
        )
    )
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=False)

    async def inject_header(request, handler):
        return await handler(request.override(headers={"Authorization": "Bearer scoped"}))

    wrapped = mcp_tools._make_ephemeral_session_tool(
        discovered_tool,
        "remote",
        {
            "transport": "http",
            "url": "http://127.0.0.1:9123/mcp",
            "headers": {"X-Base": "present"},
        },
        [inject_header],
    )

    with patch("langchain_mcp_adapters.sessions.create_session", return_value=session_context) as create_session:
        content, artifact = await wrapped.coroutine(query="evidence")

    assert content[0]["text"] == "ok"
    assert artifact is None
    assert create_session.call_args.args[0]["headers"] == {
        "X-Base": "present",
        "Authorization": "Bearer scoped",
    }


@pytest.mark.asyncio
async def test_http_wrapper_reraises_call_error_even_if_session_context_suppresses_it() -> None:
    discovered_tool = StructuredTool(
        name="remote_inspect",
        description="inspect",
        args_schema=_Args,
        coroutine=AsyncMock(),
        response_format="content_and_artifact",
    )
    session = AsyncMock()
    session.initialize = AsyncMock()
    session.call_tool = AsyncMock(side_effect=RuntimeError("remote disconnected"))
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=True)
    wrapped = mcp_tools._make_ephemeral_session_tool(
        discovered_tool,
        "remote",
        {"transport": "http", "url": "http://127.0.0.1:9123/mcp"},
    )

    with (
        patch("langchain_mcp_adapters.sessions.create_session", return_value=session_context),
        pytest.raises(RuntimeError, match="remote disconnected"),
    ):
        await wrapped.coroutine(query="evidence")
