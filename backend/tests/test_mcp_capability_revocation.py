"""Fail-closed MCP capability revocation regressions."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field

from deerflow.config.extensions_config import ExtensionsConfig, McpServerConfig
from deerflow.mcp import tools as mcp_tools
from deerflow.tools.tools import get_available_tools


class _Args(BaseModel):
    query: str = Field(..., description="query")


def _write_config(path: Path, *, enabled: bool) -> None:
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "srv": {
                        "enabled": enabled,
                        "type": "stdio",
                        "command": "fake-server",
                    }
                },
                "skills": {},
            }
        ),
        encoding="utf-8",
    )


def test_empty_current_config_still_enters_the_single_cache_authority() -> None:
    """Agent assembly may not bypass cache invalidation when zero servers remain."""
    config = MagicMock()
    config.tools = []
    config.models = []
    config.skill_evolution.enabled = False
    config.ui_tars.enabled = False
    config.acp_agents = {}

    with (
        patch("deerflow.config.extensions_config.ExtensionsConfig.from_file", return_value=ExtensionsConfig()),
        patch("deerflow.mcp.cache.get_cached_mcp_tools", return_value=[]) as get_cached,
    ):
        get_available_tools(include_mcp=True, app_config=config)

    get_cached.assert_called_once_with()


def test_required_mcp_failure_propagates_through_actual_tool_assembly() -> None:
    from deerflow.mcp.tools import RequiredMCPConfigurationError

    config = MagicMock()
    config.tools = []
    config.models = []
    config.skill_evolution.enabled = False
    config.ui_tars.enabled = False
    config.acp_agents = {}

    with (
        patch(
            "deerflow.mcp.cache.get_cached_mcp_tools",
            side_effect=RequiredMCPConfigurationError(
                "required evidence MCP unavailable"
            ),
        ),
        pytest.raises(
            RequiredMCPConfigurationError,
            match="required evidence MCP unavailable",
        ),
    ):
        get_available_tools(include_mcp=True, app_config=config)


@pytest.mark.asyncio
async def test_already_bound_stdio_tool_stops_after_server_is_disabled(tmp_path: Path, monkeypatch) -> None:
    """A tool captured by an in-flight Run cannot recreate a revoked session."""
    from deerflow.mcp.capability import server_capability_digest

    config_path = tmp_path / "extensions_config.json"
    _write_config(config_path, enabled=True)
    monkeypatch.setenv("DEER_FLOW_EXTENSIONS_CONFIG_PATH", str(config_path))
    server_config = McpServerConfig(enabled=True, type="stdio", command="fake-server")
    expected_digest = server_capability_digest(server_config)

    discovered_tool = StructuredTool(
        name="srv_inspect",
        description="inspect",
        args_schema=_Args,
        coroutine=AsyncMock(),
        response_format="content_and_artifact",
    )
    pool = MagicMock()
    pool.get_session = AsyncMock()
    pool.close_server = AsyncMock()

    with patch("deerflow.mcp.tools.get_session_pool", return_value=pool):
        bound_tool = mcp_tools._make_session_pool_tool(
            discovered_tool,
            "srv",
            {"transport": "stdio", "command": "fake-server"},
            expected_capability_digest=expected_digest,
        )

    _write_config(config_path, enabled=False)

    with pytest.raises(ToolException, match="capability was revoked or changed"):
        await bound_tool.coroutine(query="evidence")

    pool.close_server.assert_awaited_once_with("srv")
    pool.get_session.assert_not_awaited()
